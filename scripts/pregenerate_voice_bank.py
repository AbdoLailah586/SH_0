"""
Batch Voice Bank Pre-Generator Script for Egyptian Arabic Smart Home Cache.
Generates genuine, high-definition Egyptian Arabic audio clips (.wav)
using Fish Speech (if online) or the Egyptian Neural Engine (ar-EG-ShakirNeural / ar-EG-SalmaNeural).
NO ROBOTIC SAPI / NO ENGLISH!
"""

import os
import shutil
import sys

# Ensure root directory is on sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.fish_speech_client import FishSpeechClient
from core.paths import resolve_path

def main():
    print("=" * 65)
    print("AI Smart Home Voice Hub - Egyptian Arabic Voice Bank Generator")
    print("=" * 65)

    manifest_path = resolve_path("config/voice_bank_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"[Error] Manifest file not found at: {manifest_path}")
        return

    client = FishSpeechClient()
    is_fish_online = client.is_server_online()
    print(f"Fish Speech RTX 4050 Server Status: {'ONLINE 🟢 (CUDA Active)' if is_fish_online else 'OFFLINE (Using Egyptian Neural ar-EG)'}")

    def progress(current, total, detail):
        pct = int(current / total * 100)
        sys.stdout.write(f"\r[{current:2d}/{total}] {pct:3d}% -> Generating Egyptian Arabic: {detail[:40]:<40}")
        sys.stdout.flush()

    print("\nStarting generation of 70 Egyptian Arabic audio clips...")
    result = client.batch_generate_manifest(manifest_path, on_progress=progress, overwrite=True)
    print(f"\n\n[SUCCESS] Completed!")
    print(f"Total phrases generated : {result['total']}")
    print(f"Cache location          : {resolve_path('audio_cache')}")

    # Synchronize to dist folder if it exists
    dist_cache = resolve_path("dist/SmartHomeVoiceHub/audio_cache")
    if os.path.exists(resolve_path("dist/SmartHomeVoiceHub")):
        os.makedirs(dist_cache, exist_ok=True)
        shutil.copytree(resolve_path("audio_cache"), dist_cache, dirs_exist_ok=True)
        print(f"Synchronized cache to   : {dist_cache}")

    print("=" * 65)

if __name__ == "__main__":
    main()
