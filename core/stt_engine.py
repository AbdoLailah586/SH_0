"""
Multi-Engine Egyptian Arabic Speech-to-Text (STT) Hub using Native sounddevice.
Eliminates all PyAudio dependencies and conflicts.
Engines:
  1. Primary: Groq Whisper API (whisper-large-v3-turbo) - Ultra-fast (<200ms, 0% GPU VRAM)
  2. Local CPU Fallback: faster-whisper (i5-12450HX int8, zero VRAM)
  3. Online Fallback: Google Speech Recognition ('ar-EG')
"""

import io
import json
import math
import os
import tempfile
import threading
import time
import wave
from typing import List, Dict, Any, Optional, Callable
import numpy as np

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

import requests
from core.paths import resolve_path


EGYPTIAN_SMARTHOME_PROMPT = (
    "مساعد صوتي ذكي للسمارت هوم بالعامية المصرية: افتح النور، اطفي النور، وطي الصوت، علي الصوت، "
    "شغل التكييف على 22، افتح الشباك، بطارية اللابتوب كام، لمبة الاختبار، اقفل اللابتوب، اسمك ايه."
)


def numpy_to_wav_bytes(audio_data: np.ndarray, samplerate: int = 16000) -> bytes:
    """Encodes int16 mono numpy audio array into standard PCM WAV bytes in memory."""
    if audio_data.ndim > 1:
        audio_data = audio_data.flatten()
    if audio_data.dtype != np.int16:
        audio_data = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_data.tobytes())
    return bio.getvalue()


class STTEngine:
    def __init__(
        self,
        engine_type: str = "groq_whisper",
        device_index: Optional[int] = None,
        groq_api_key: Optional[str] = None
    ):
        self.engine_type = engine_type  # 'groq_whisper', 'faster_whisper_cpu', 'google_ar'
        self.device_index = device_index
        self.language = "ar"
        self.groq_api_key = groq_api_key
        self._load_keys()

        self.is_listening = False
        self.is_recording = False
        self.continuous_mode = False

        self._level_stream = None
        self._continuous_stream = None
        self._faster_whisper_model = None
        self._lock = threading.Lock()

        # Callbacks
        self.on_transcript: Optional[Callable[[str], None]] = None
        self.on_level_update: Optional[Callable[[int], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

        self._start_vu_meter_stream()

    def _load_keys(self):
        settings_file = resolve_path("config/app_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not self.groq_api_key or len(self.groq_api_key) < 10:
                        self.groq_api_key = data.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
            except Exception:
                pass

    def list_microphones(self) -> List[Dict[str, Any]]:
        devices = []
        if SD_AVAILABLE:
            try:
                for idx, dev in enumerate(sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        devices.append({"index": idx, "name": dev.get("name", f"Microphone {idx}")})
                if devices:
                    return devices
            except Exception:
                pass

        return [{"index": None, "name": "Default System Microphone"}]

    def set_device_index(self, index: Optional[int]):
        with self._lock:
            self.device_index = index
            if not self.is_recording and not self.continuous_mode:
                self._restart_vu_meter_stream()

    # --- LIVE VU METER ---

    def _start_vu_meter_stream(self):
        if not SD_AVAILABLE or self.is_recording or self.continuous_mode:
            return

        def _audio_callback(indata, frames, time_info, status):
            if self.on_level_update:
                try:
                    rms = np.sqrt(np.mean(indata**2))
                    level = int(min(100, max(0, (math.log10(rms + 1e-6) + 3) / 3 * 100)))
                    self.on_level_update(level)
                except Exception:
                    pass

        try:
            if self._level_stream:
                try:
                    self._level_stream.stop()
                    self._level_stream.close()
                except Exception:
                    pass

            self._level_stream = sd.InputStream(
                device=self.device_index,
                channels=1,
                samplerate=16000,
                blocksize=1024,
                callback=_audio_callback
            )
            self._level_stream.start()
        except Exception:
            self._level_stream = None

    def _restart_vu_meter_stream(self):
        if self._level_stream:
            try:
                self._level_stream.stop()
                self._level_stream.close()
            except Exception:
                pass
            self._level_stream = None
        self._start_vu_meter_stream()

    # --- PUSH-TO-TALK & CONTINUOUS VAD ---

    def trigger_push_to_talk_record(self, duration_sec: float = 3.5):
        """Records directly via sounddevice and sends to STT (No PyAudio required)."""
        if not SD_AVAILABLE or self.is_recording:
            return

        def _record_worker():
            self.is_recording = True

            # Temporarily pause VU meter stream so recording has exclusive access
            if self._level_stream:
                try:
                    self._level_stream.stop()
                    self._level_stream.close()
                except Exception:
                    pass
                self._level_stream = None

            if self.on_status_change:
                self.on_status_change("listening")

            samplerate = 16000
            total_frames = int(duration_sec * samplerate)
            audio_buffer = []

            # Stream-based recording with live VU update during recording
            def _rec_callback(indata, frames, time_info, status):
                audio_buffer.append(indata.copy())
                if self.on_level_update:
                    try:
                        rms = np.sqrt(np.mean(indata**2))
                        lvl = int(min(100, max(0, (math.log10(rms + 1e-6) + 3) / 3 * 100)))
                        self.on_level_update(lvl)
                    except Exception:
                        pass

            try:
                with sd.InputStream(
                    device=self.device_index,
                    channels=1,
                    samplerate=samplerate,
                    blocksize=1024,
                    dtype="int16",
                    callback=_rec_callback
                ):
                    time.sleep(duration_sec)

                if audio_buffer:
                    audio_array = np.concatenate(audio_buffer, axis=0)
                else:
                    audio_array = np.zeros((total_frames, 1), dtype=np.int16)

                if self.on_status_change:
                    self.on_status_change("processing")

                wav_bytes = numpy_to_wav_bytes(audio_array, samplerate=samplerate)
                text = self._recognize_wav_bytes(wav_bytes)

                if text and self.on_transcript:
                    self.on_transcript(text)

            except Exception as e:
                print(f"[PushToTalk Error] {e}")
            finally:
                self.is_recording = False
                if self.on_status_change:
                    self.on_status_change("idle")
                # Resume normal VU meter
                if not self.continuous_mode:
                    self._restart_vu_meter_stream()

        threading.Thread(target=_record_worker, daemon=True).start()

    def start_continuous_listening(self):
        """Continuous Voice Activity Detection (VAD) via sounddevice."""
        if not SD_AVAILABLE or self.is_listening:
            return

        self.continuous_mode = True
        self.is_listening = True

        # Stop VU stream so continuous stream can handle both VU and speech collection
        if self._level_stream:
            try:
                self._level_stream.stop()
            except Exception:
                pass

        if self.on_status_change:
            self.on_status_change("listening")

        samplerate = 16000
        vad_state = {
            "is_speaking": False,
            "silence_frames": 0,
            "speech_buffer": []
        }
        silence_threshold_frames = int(samplerate / 1024 * 0.8)  # ~0.8s silence
        energy_threshold = 400  # Int16 RMS threshold

        def _cont_callback(indata, frames, time_info, status):
            if not self.is_listening:
                return

            rms = np.sqrt(np.mean(indata.astype(np.float32)**2))
            if self.on_level_update:
                lvl = int(min(100, max(0, (math.log10(rms + 1e-6) + 3) / 3 * 100)))
                self.on_level_update(lvl)

            if rms > energy_threshold:
                vad_state["is_speaking"] = True
                vad_state["silence_frames"] = 0
                vad_state["speech_buffer"].append(indata.copy())
            elif vad_state["is_speaking"]:
                vad_state["speech_buffer"].append(indata.copy())
                vad_state["silence_frames"] += 1
                if vad_state["silence_frames"] >= silence_threshold_frames:
                    # Speech ended, process in background
                    vad_state["is_speaking"] = False
                    vad_state["silence_frames"] = 0
                    buf = list(vad_state["speech_buffer"])
                    vad_state["speech_buffer"] = []

                    if len(buf) > 10:  # At least ~0.5s of audio
                        def _bg_transcribe(chunks):
                            if self.on_status_change:
                                self.on_status_change("processing")
                            arr = np.concatenate(chunks, axis=0)
                            wb = numpy_to_wav_bytes(arr, samplerate=samplerate)
                            t = self._recognize_wav_bytes(wb)
                            if t and self.on_transcript:
                                self.on_transcript(t)
                            if self.is_listening and self.on_status_change:
                                self.on_status_change("listening")

                        threading.Thread(target=_bg_transcribe, args=(buf,), daemon=True).start()

        try:
            self._continuous_stream = sd.InputStream(
                device=self.device_index,
                channels=1,
                samplerate=samplerate,
                blocksize=1024,
                dtype="int16",
                callback=_cont_callback
            )
            self._continuous_stream.start()
        except Exception as e:
            print(f"[StartContinuous Error] {e}")
            self.is_listening = False
            self.continuous_mode = False

    def stop_continuous_listening(self):
        self.continuous_mode = False
        self.is_listening = False
        if self._continuous_stream:
            try:
                self._continuous_stream.stop()
                self._continuous_stream.close()
            except Exception:
                pass
            self._continuous_stream = None

        if self.on_status_change:
            self.on_status_change("idle")
        self._restart_vu_meter_stream()

    # --- MULTI-ENGINE TRANSCRIBER ---

    def _recognize_wav_bytes(self, wav_bytes: bytes) -> str:
        if not wav_bytes or len(wav_bytes) < 1000:
            return ""

        # Engine 1: Groq Whisper Large V3 Turbo (<200ms)
        if self.engine_type == "groq_whisper":
            if not self.groq_api_key:
                self._load_keys()

            if self.groq_api_key:
                try:
                    headers = {"Authorization": f"Bearer {self.groq_api_key}"}
                    files = {"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")}
                    data = {
                        "model": "whisper-large-v3-turbo",
                        "language": "ar",
                        "prompt": EGYPTIAN_SMARTHOME_PROMPT,
                        "temperature": "0.0"
                    }
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=5.0
                    )
                    if resp.status_code == 200:
                        text = resp.json().get("text", "").strip()
                        if text:
                            return text
                    else:
                        print(f"[Groq Whisper API Status {resp.status_code}] {resp.text[:120]}")
                except Exception as e:
                    print(f"[Groq Whisper Request Error] {e}")

        # Engine 2: Local faster-whisper on CPU (int8, 0% GPU VRAM)
        if self.engine_type == "faster_whisper_cpu" and FASTER_WHISPER_AVAILABLE:
            try:
                if self._faster_whisper_model is None:
                    self._faster_whisper_model = WhisperModel(
                        "base",
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=4
                    )

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes)
                    temp_wav = f.name

                segments, _ = self._faster_whisper_model.transcribe(
                    temp_wav,
                    language="ar",
                    initial_prompt=EGYPTIAN_SMARTHOME_PROMPT
                )
                text = " ".join([seg.text for seg in segments]).strip()
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                if text:
                    return text
            except Exception as e:
                print(f"[Faster Whisper CPU Error] {e}")

        # Engine 3: Online Google Speech Recognition (ar-EG) fallback
        if SR_AVAILABLE:
            try:
                recognizer = sr.Recognizer()
                audio_data = sr.AudioData(wav_bytes, 16000, 2)
                text = recognizer.recognize_google(audio_data, language="ar-EG")
                return text.strip()
            except Exception:
                pass

        return ""

    def cleanup(self):
        self.stop_continuous_listening()
        if self._level_stream:
            try:
                self._level_stream.stop()
                self._level_stream.close()
            except Exception:
                pass
            self._level_stream = None
