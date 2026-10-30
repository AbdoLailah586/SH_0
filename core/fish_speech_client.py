"""
Fish Speech GPU Voice Engine & Egyptian Arabic Neural Synthesis Hub.
Dedicated to NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM).

Features:
  - Background Fish Speech API Server Process Manager (CUDA + FP16 / BF16)
  - Mandatory Egyptian Arabic Reference Voice Timbre Cloning (Shakir / Salma / Custom)
  - High-Definition Egyptian Neural Fallback via edge-tts + ffmpeg (NO SAPI / NO pyttsx3!)
  - Live Dynamic Voice Synthesis for real-time battery numbers, stats, and LLM chat replies
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Dict, Any, List, Optional, Callable, Tuple
import requests
import edge_tts

from core.paths import resolve_path


class FishSpeechGPUServerManager:
    """Manages the local Fish Speech CUDA API server process on the RTX 4050 GPU."""
    def __init__(self, port: int = 8080):
        self.port = port
        self.api_url = f"http://127.0.0.1:{port}/v1/tts"
        self.process = None
        self._lock = threading.Lock()

    def is_online(self) -> bool:
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/", timeout=0.8)
            return resp.status_code in [200, 404, 405]
        except Exception:
            return False

    def start_server(self, repo_path: Optional[str] = None) -> bool:
        """Launches the Fish Speech API server in background on CUDA."""
        with self._lock:
            if self.is_online():
                return True

            if not repo_path:
                repo_path = resolve_path("fish_speech_repo")

            if not os.path.exists(repo_path):
                print(f"[FishSpeechManager] Repo path not found at: {repo_path}")
                return False

            cmd = [
                resolve_path(".venv/Scripts/python.exe"),
                "-m", "tools.api_server",
                "--listen", f"127.0.0.1:{self.port}",
                "--device", "cuda",
                "--half"
            ]

            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=repo_path,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                # Wait briefly for startup
                for _ in range(10):
                    time.sleep(1.0)
                    if self.is_online():
                        return True
            except Exception as e:
                print(f"[FishSpeechManager Start Error] {e}")

        return self.is_online()

    def stop_server(self):
        with self._lock:
            if self.process:
                try:
                    self.process.terminate()
                except Exception:
                    pass
                self.process = None

    def get_vram_usage(self) -> Dict[str, Any]:
        """Queries RTX 4050 VRAM stats via nvidia-smi."""
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,nounits,noheader"],
                encoding="utf-8"
            ).strip()
            parts = [p.strip() for p in out.split(",")]
            if len(parts) >= 3:
                return {
                    "used_mb": int(parts[0]),
                    "total_mb": int(parts[1]),
                    "util_pct": int(parts[2]),
                    "text": f"{parts[0]} MB / {parts[1]} MB ({parts[2]}% GPU)"
                }
        except Exception:
            pass
        return {"used_mb": 0, "total_mb": 6144, "util_pct": 0, "text": "RTX 4050 6GB"}


class FishSpeechClient:
    def __init__(self, api_url: str = "http://127.0.0.1:8080/v1/tts"):
        self.api_url = api_url
        self.server_manager = FishSpeechGPUServerManager(port=8080)
        self.timeout = 8.0

        # Reference voice paths
        self.ref_dir = resolve_path("config/reference_voices")
        self.default_ref_wav = os.path.join(self.ref_dir, "egyptian_male_ref.wav")
        self.default_ref_txt = os.path.join(self.ref_dir, "egyptian_male_ref.txt")

    def is_server_online(self) -> bool:
        return self.server_manager.is_online()

    def get_reference_audio_and_text(self, gender: str = "male") -> Tuple[str, str]:
        """Returns the appropriate Egyptian Arabic voice reference seed."""
        if gender == "female":
            wav_path = os.path.join(self.ref_dir, "egyptian_female_ref.wav")
            txt_path = os.path.join(self.ref_dir, "egyptian_female_ref.txt")
        else:
            # Check for custom user recorded voice first
            custom_wav = os.path.join(self.ref_dir, "custom_user_ref.wav")
            custom_txt = os.path.join(self.ref_dir, "custom_user_ref.txt")
            if os.path.exists(custom_wav) and os.path.getsize(custom_wav) > 10000:
                wav_path, txt_path = custom_wav, custom_txt
            else:
                wav_path, txt_path = self.default_ref_wav, self.default_ref_txt

        ref_text = ""
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    ref_text = f.read().strip()
            except Exception:
                pass

        return wav_path, ref_text

    def generate_with_fish_speech(
        self,
        text: str,
        output_path: str,
        emotion: str = "normal",
        gender: str = "male"
    ) -> bool:
        """
        Sends synthesis request to local Fish Speech CUDA API server
        with reference audio/text to clone Egyptian vocal timbre.
        """
        ref_wav, ref_txt = self.get_reference_audio_and_text(gender)

        payload = {
            "text": text,
            "format": "wav",
            "emotion": emotion,
            "reference_audio": ref_wav if os.path.exists(ref_wav) else None,
            "reference_text": ref_txt if ref_txt else None
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200 and len(resp.content) > 1000:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception as e:
            print(f"[FishSpeech Error] {e}")
        return False

    def generate_with_egyptian_neural(
        self,
        text: str,
        output_path: str,
        emotion: str = "normal",
        gender: str = "male"
    ) -> bool:
        """
        High-Definition Egyptian Neural Fallback (edge-tts + ffmpeg).
        Generates 100% natural colloquial Egyptian Arabic without robotic SAPI artifacts.
        """
        # Clean emotion tags like [friendly], [whisper] from spoken text
        clean_text = re.sub(r'\[.*?\]', '', text).strip()
        if not clean_text:
            clean_text = text

        voice = "ar-EG-ShakirNeural" if gender == "male" else "ar-EG-SalmaNeural"

        # Emotion pitch & rate modulation
        rate = "+0%"
        pitch = "+0Hz"
        if emotion == "whisper":
            rate = "-15%"
            pitch = "-4Hz"
        elif emotion == "excited":
            rate = "+10%"
            pitch = "+2Hz"
        elif emotion == "calm":
            rate = "-8%"
            pitch = "-2Hz"

        temp_mp3 = output_path + ".temp.mp3"
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        async def _synth():
            comm = edge_tts.Communicate(clean_text, voice=voice, rate=rate, pitch=pitch)
            await comm.save(temp_mp3)

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Run in separate thread if loop is already active
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(lambda: asyncio.run(_synth())).result()
                else:
                    loop.run_until_complete(_synth())
            except RuntimeError:
                asyncio.run(_synth())

            if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 500:
                # Convert to high-quality 44.1kHz 16-bit PCM .wav
                subprocess.run(
                    ["ffmpeg", "-y", "-i", temp_mp3, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", output_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                if os.path.exists(temp_mp3):
                    os.remove(temp_mp3)
                return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        except Exception as e:
            print(f"[Egyptian Neural Synth Error] {e}")
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)

        return False

    def generate_clip(
        self,
        text: str,
        output_path: str,
        emotion: str = "normal",
        gender: str = "male",
        prefer_fish_speech: bool = True
    ) -> Tuple[bool, str]:
        """
        Unified generator trying Fish Speech GPU first, then pure Egyptian Neural fallback.
        """
        if prefer_fish_speech and self.is_server_online():
            if self.generate_with_fish_speech(text, output_path, emotion, gender):
                return True, "Fish Speech (RTX 4050 GPU)"

        # High-Definition Egyptian Neural fallback
        if self.generate_with_egyptian_neural(text, output_path, emotion, gender):
            return True, "Egyptian Neural Voice (ar-EG)"

        return False, "Failed"

    def synthesize_live(self, text: str, emotion: str = "normal") -> Optional[str]:
        """
        Synthesizes dynamic text (live battery %, CPU stats, or live LLM reply)
        and returns the absolute path to the generated .wav file.
        """
        dynamic_dir = resolve_path("audio_cache/dynamic")
        os.makedirs(dynamic_dir, exist_ok=True)
        ts = int(time.time() * 1000)
        out_wav = os.path.join(dynamic_dir, f"live_{ts}.wav")

        success, _ = self.generate_clip(text, out_wav, emotion=emotion)
        if success:
            return out_wav
        return None

    def batch_generate_manifest(
        self,
        manifest_path: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        overwrite: bool = True
    ) -> Dict[str, Any]:
        """Generates all 70 variations in genuine Egyptian Arabic."""
        if not os.path.exists(manifest_path):
            return {"success": False, "generated": 0, "total": 0}

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        tasks = []
        for it in manifest.get("intents", []):
            for var in it.get("variations", []):
                rel_path = var.get("audio_file", "")
                text_ar = var.get("text_ar", "")
                emotion = var.get("emotion", "normal")
                full_path = resolve_path(rel_path)
                tasks.append({
                    "text": text_ar,
                    "path": full_path,
                    "rel_path": rel_path,
                    "emotion": emotion
                })

        total = len(tasks)
        generated = 0

        for i, t in enumerate(tasks):
            file_exists = os.path.exists(t["path"]) and os.path.getsize(t["path"]) > 1000
            if not file_exists or overwrite:
                success, method = self.generate_clip(t["text"], t["path"], t["emotion"])
                if success:
                    generated += 1
                time.sleep(0.3) # Rate smoothing
            else:
                method = "Cached"

            if on_progress:
                on_progress(i + 1, total, f"{t['rel_path']} ({method})")

        return {"success": True, "generated": generated, "total": total}
