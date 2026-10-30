"""
Multi-Engine Egyptian Arabic Speech-to-Text (STT) Hub.
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
from typing import List, Dict, Any, Optional, Callable
import numpy as np

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

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

from core.paths import resolve_path


EGYPTIAN_SMARTHOME_PROMPT = (
    "مساعد صوتي ذكي للسمارت هوم بالعامية المصرية: افتح النور، اطفي النور، وطي الصوت، علي الصوت، "
    "شغل التكييف على 22، افتح الشباك، بطارية اللابتوب كام، لمبة الاختبار، اقفل اللابتوب."
)


class STTEngine:
    def __init__(
        self,
        engine_type: str = "groq_whisper",
        device_index: Optional[int] = None,
        groq_api_key: Optional[str] = None
    ):
        self.engine_type = engine_type # 'groq_whisper', 'faster_whisper_cpu', 'google_ar'
        self.device_index = device_index
        self.language = "ar"
        self.groq_api_key = groq_api_key
        self._load_keys()

        self.is_listening = False
        self.is_recording = False
        self.continuous_mode = False

        self._stop_listening_fn = None
        self._level_stream = None
        self._faster_whisper_model = None
        self._lock = threading.Lock()

        # Callbacks
        self.on_transcript: Optional[Callable[[str], None]] = None
        self.on_level_update: Optional[Callable[[int], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

        self.recognizer = None
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8

        self._start_vu_meter_stream()

    def _load_keys(self):
        settings_file = resolve_path("config/app_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not self.groq_api_key:
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
                return devices
            except Exception:
                pass

        if not devices and SR_AVAILABLE:
            try:
                for idx, name in enumerate(sr.Microphone.list_microphone_names()):
                    devices.append({"index": idx, "name": name})
            except Exception:
                pass

        if not devices:
            devices.append({"index": None, "name": "Default System Microphone"})
        return devices

    def set_device_index(self, index: Optional[int]):
        with self._lock:
            self.device_index = index
            self._restart_vu_meter_stream()

    # --- LIVE VU METER ---

    def _start_vu_meter_stream(self):
        if not SD_AVAILABLE:
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
                self._level_stream.stop()
                self._level_stream.close()

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
        if not SR_AVAILABLE or self.is_recording:
            return

        def _record_worker():
            self.is_recording = True
            if self.on_status_change:
                self.on_status_change("listening")

            try:
                with sr.Microphone(device_index=self.device_index) as source:
                    audio = self.recognizer.record(source, duration=duration_sec)

                if self.on_status_change:
                    self.on_status_change("processing")

                text = self._recognize_audio(audio)
                if text and self.on_transcript:
                    self.on_transcript(text)
            except Exception as e:
                print(f"[PushToTalk Error] {e}")
            finally:
                self.is_recording = False
                if self.on_status_change:
                    self.on_status_change("idle")

        threading.Thread(target=_record_worker, daemon=True).start()

    def start_continuous_listening(self):
        if not SR_AVAILABLE or self.is_listening:
            return

        self.continuous_mode = True
        self.is_listening = True

        def _callback(recognizer, audio):
            if self.on_status_change:
                self.on_status_change("processing")

            try:
                text = self._recognize_audio(audio)
                if text and self.on_transcript:
                    self.on_transcript(text)
            except Exception as e:
                print(f"[VAD Recognize Error] {e}")
            finally:
                if self.is_listening and self.on_status_change:
                    self.on_status_change("listening")

        try:
            mic = sr.Microphone(device_index=self.device_index)
            with mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.4)

            self._stop_listening_fn = self.recognizer.listen_in_background(
                mic, _callback, phrase_time_limit=5.0
            )
            if self.on_status_change:
                self.on_status_change("listening")
        except Exception as e:
            print(f"[StartContinuous Error] {e}")
            self.is_listening = False

    def stop_continuous_listening(self):
        self.continuous_mode = False
        if self._stop_listening_fn:
            try:
                self._stop_listening_fn(wait_for_stop=False)
            except Exception:
                pass
            self._stop_listening_fn = None
        self.is_listening = False
        if self.on_status_change:
            self.on_status_change("idle")

    # --- MULTI-ENGINE TRANSCRIBER ---

    def _recognize_audio(self, audio: "sr.AudioData") -> str:
        if not audio:
            return ""

        wav_bytes = audio.get_wav_data()

        # Engine 1: Groq Whisper Large V3 Turbo (<200ms)
        if self.engine_type == "groq_whisper" and GROQ_AVAILABLE:
            if not self.groq_api_key:
                self._load_keys()

            if self.groq_api_key:
                try:
                    client = Groq(api_key=self.groq_api_key)
                    file_obj = io.BytesIO(wav_bytes)
                    file_obj.name = "audio.wav"

                    transcription = client.audio.transcriptions.create(
                        file=file_obj,
                        model="whisper-large-v3-turbo",
                        language="ar",
                        prompt=EGYPTIAN_SMARTHOME_PROMPT,
                        temperature=0.0
                    )
                    text = transcription.text.strip()
                    if text:
                        return text
                except Exception as e:
                    print(f"[Groq Whisper API Error] {e}. Falling back to next engine...")

        # Engine 2: Local faster-whisper on CPU (int8, 0% GPU VRAM)
        if self.engine_type == "faster_whisper_cpu" and FASTER_WHISPER_AVAILABLE:
            try:
                if self._faster_whisper_model is None:
                    # Run on Intel i5-12450HX CPU using int8 quantization
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
                text = self.recognizer.recognize_google(audio, language="ar-EG")
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
