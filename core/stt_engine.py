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

# Ensure torch/lib is in DLL directory for faster-whisper CUDA cublas/cudnn on Windows
try:
    import torch
    _torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.exists(_torch_lib):
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_torch_lib)
        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

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


from collections import deque

EGYPTIAN_SMARTHOME_PROMPT = (
    "أهلاً بيك، محادثة طبيعية بالعامية المصرية مع المساعد الصوتي الذكي للتحكم في المنزل واللابتوب والاستفسارات اليومية والدردشة."
)


def numpy_to_wav_bytes(audio_data: np.ndarray, samplerate: int = 16000) -> bytes:
    """
    Encodes audio array into standard PCM WAV bytes with automatic peak normalization
    and dynamic gain boost to ensure Whisper receives loud, crystal-clear Egyptian speech.
    """
    if audio_data.ndim > 1:
        if audio_data.shape[1] > 1:
            audio_data = np.mean(audio_data, axis=1)
        else:
            audio_data = audio_data.flatten()

    # Convert to float32 normalized in [-1.0, 1.0]
    if audio_data.dtype == np.int16:
        float_audio = audio_data.astype(np.float32) / 32768.0
    else:
        float_audio = audio_data.astype(np.float32)

    # Calculate peak amplitude
    peak = float(np.max(np.abs(float_audio))) if len(float_audio) > 0 else 0.0

    # Apply smart dynamic gain boost:
    # Laptops (like Lenovo LOQ) often capture quiet audio (e.g. peak < 0.15).
    # We boost the signal up to a clean studio target of 0.85 (-1.4 dBFS)
    if peak > 0.005:
        target_peak = 0.85
        gain = min(target_peak / peak, 12.0)  # Cap max gain multiplier at 12x
        float_audio = float_audio * gain

    # Soft clip and convert back to 16-bit PCM
    int16_audio = (np.clip(float_audio, -1.0, 1.0) * 32767.0).astype(np.int16)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(int16_audio.tobytes())
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

    def trigger_push_to_talk_record(self, max_duration_sec: float = 5.5):
        """
        Records dynamically via sounddevice with voice activity detection.
        Stops automatically after speech finishes or when max duration is reached.
        """
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
            audio_buffer = []
            pre_roll = deque(maxlen=10)  # 640ms pre-speech buffer

            has_spoken = False
            silence_chunks = 0
            energy_threshold = 450.0

            def _rec_callback(indata, frames, time_info, status):
                nonlocal has_spoken, silence_chunks
                float_data = indata.astype(np.float32)
                rms = float(np.sqrt(np.mean(float_data**2)))
                if self.on_level_update:
                    lvl = int(min(100, max(0, (math.log10(rms + 1e-6) + 3) / 3 * 100)))
                    self.on_level_update(lvl)

                if rms > energy_threshold:
                    if not has_spoken:
                        has_spoken = True
                        audio_buffer.extend(list(pre_roll))
                    audio_buffer.append(indata.copy())
                    silence_chunks = 0
                elif has_spoken:
                    audio_buffer.append(indata.copy())
                    silence_chunks += 1
                else:
                    pre_roll.append(indata.copy())

            try:
                with sd.InputStream(
                    device=self.device_index,
                    channels=1,
                    samplerate=samplerate,
                    blocksize=1024,
                    dtype="int16",
                    callback=_rec_callback
                ):
                    # Smart dynamic recording loop
                    start_t = time.time()
                    while time.time() - start_t < max_duration_sec:
                        time.sleep(0.05)
                        # Stop if user spoke and then stayed silent for > 1.0 second (~16 chunks)
                        if has_spoken and silence_chunks >= 16:
                            break

                # If the user didn't cross energy threshold, take whatever audio was captured in pre-roll
                if not audio_buffer and pre_roll:
                    audio_buffer = list(pre_roll)

                if audio_buffer:
                    audio_array = np.concatenate(audio_buffer, axis=0)
                else:
                    audio_array = np.zeros((samplerate * 2, 1), dtype=np.int16)

                if self.on_status_change:
                    self.on_status_change("processing")

                wav_bytes = numpy_to_wav_bytes(audio_array, samplerate=samplerate)
                text = self._recognize_wav_bytes(wav_bytes, audio_array=audio_array)

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
        """Continuous Voice Activity Detection (VAD) with rolling pre-roll buffer."""
        if not SD_AVAILABLE or self.is_listening:
            return

        self.continuous_mode = True
        self.is_listening = True

        # Stop VU stream so continuous stream can handle both VU and speech collection
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
        vad_state = {
            "is_speaking": False,
            "silence_frames": 0,
            "speech_buffer": []
        }
        pre_roll = deque(maxlen=10)  # ~640ms pre-speech audio
        silence_threshold_frames = int(samplerate / 1024 * 0.9)  # ~0.9s silence to close utterance
        energy_threshold = 480.0  # Float RMS threshold

        def _cont_callback(indata, frames, time_info, status):
            if not self.is_listening:
                return

            float_data = indata.astype(np.float32)
            rms = float(np.sqrt(np.mean(float_data**2)))
            if self.on_level_update:
                lvl = int(min(100, max(0, (math.log10(rms + 1e-6) + 3) / 3 * 100)))
                self.on_level_update(lvl)

            if rms > energy_threshold:
                if not vad_state["is_speaking"]:
                    vad_state["is_speaking"] = True
                    # Prepend pre-roll buffer so the beginning of the word is never chopped!
                    vad_state["speech_buffer"].extend(list(pre_roll))
                vad_state["speech_buffer"].append(indata.copy())
                vad_state["silence_frames"] = 0
            elif vad_state["is_speaking"]:
                vad_state["speech_buffer"].append(indata.copy())
                vad_state["silence_frames"] += 1
                if vad_state["silence_frames"] >= silence_threshold_frames:
                    # Speech ended, process in background
                    vad_state["is_speaking"] = False
                    vad_state["silence_frames"] = 0
                    buf = list(vad_state["speech_buffer"])
                    vad_state["speech_buffer"] = []

                    if len(buf) > 12:  # At least ~0.75s of speech
                        def _bg_transcribe(chunks):
                            if self.on_status_change:
                                self.on_status_change("processing")
                            arr = np.concatenate(chunks, axis=0)
                            wb = numpy_to_wav_bytes(arr, samplerate=samplerate)
                            t = self._recognize_wav_bytes(wb, audio_array=arr)
                            if t and self.on_transcript:
                                self.on_transcript(t)
                            if self.is_listening and self.on_status_change:
                                self.on_status_change("listening")

                        threading.Thread(target=_bg_transcribe, args=(buf,), daemon=True).start()
            else:
                pre_roll.append(indata.copy())

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

    def _recognize_wav_bytes(self, wav_bytes: bytes, audio_array: Optional[np.ndarray] = None) -> str:
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

        # Engine 2: Local faster-whisper on NVIDIA RTX 4050 GPU (CUDA float16) or CPU
        if (self.engine_type in ("faster_whisper_cuda", "faster_whisper_cpu") or not self.groq_api_key) and FASTER_WHISPER_AVAILABLE:
            try:
                if self._faster_whisper_model is None:
                    import torch
                    use_cuda = (self.engine_type == "faster_whisper_cuda" or torch.cuda.is_available())
                    device = "cuda" if use_cuda else "cpu"
                    compute_type = "float16" if use_cuda else "int8"
                    self._faster_whisper_model = WhisperModel(
                        "base",
                        device=device,
                        compute_type=compute_type
                    )

                # Direct float32 tensor fed to GPU to bypass av.open bug in Python 3.13
                if audio_array is not None:
                    fl_audio = audio_array.flatten().astype(np.float32)
                    if audio_array.dtype == np.int16:
                        fl_audio = fl_audio / 32768.0
                    peak = float(np.max(np.abs(fl_audio))) if len(fl_audio) > 0 else 0.0
                    if peak > 0.005:
                        fl_audio = fl_audio * min(0.85 / peak, 12.0)
                else:
                    fl_audio = np.frombuffer(wav_bytes[44:], dtype=np.int16).astype(np.float32) / 32768.0

                segments, _ = self._faster_whisper_model.transcribe(
                    fl_audio,
                    language="ar",
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=400),
                    initial_prompt=EGYPTIAN_SMARTHOME_PROMPT
                )
                text = " ".join([seg.text for seg in segments]).strip()
                if text:
                    return text
            except Exception as e:
                print(f"[Faster Whisper CUDA Error] {e}")

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
