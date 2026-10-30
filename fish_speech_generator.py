"""
Fish Speech Voice Generator & Cache Upgrader Module.
Used for generating, fine-tuning, and upgrading voice cache clips with Fish Speech on RTX 4050 GPU.
Supports emotion tags like [friendly], [whisper], [excited], [calm] with Egyptian vocal timbre.
"""

import argparse
import os
import sys

from core.fish_speech_client import FishSpeechClient
from core.paths import resolve_path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Fish Speech Audio Cache Batch Generator")
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1/tts", help="Fish Speech API URL")
    parser.add_argument("--overwrite", action="store_true", help="Force overwrite all cached clips")
    parser.add_argument("--text", default=None, help="Generate single phrase in Egyptian Arabic")
    parser.add_argument("--out", default=None, help="Output wav file for single phrase")
    parser.add_argument("--emotion", default="normal", help="Emotion tag: friendly, whisper, excited, calm")
    parser.add_argument("--gender", default="male", help="Voice gender: male, female")
    args = parser.parse_args()

    client = FishSpeechClient(api_url=args.url)

    print("=" * 65)
    print("Fish Speech Egyptian Smart Home Voice Bank Engine")
    print(f"Target Server : {args.url}")
    is_online = client.is_server_online()
    print(f"Server Status : {'ONLINE 🟢 (RTX 4050 GPU Active)' if is_online else 'OFFLINE (Using Egyptian Neural ar-EG)'}")
    print("=" * 65)

    if args.text and args.out:
        print(f"Generating single phrase: '{args.text}' [{args.emotion}] -> {args.out}")
        success, method = client.generate_clip(args.text, args.out, emotion=args.emotion, gender=args.gender)
        print(f"Result: {'SUCCESS' if success else 'FAILED'} (Engine: {method})")
        return

    manifest_path = resolve_path("config/voice_bank_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"[Error] Manifest file missing at: {manifest_path}")
        return

    def on_prog(curr, total, file_info):
        pct = int(curr / total * 100)
        sys.stdout.write(f"\r[{curr:2d}/{total}] {pct:3d}% Processing Egyptian Arabic: {file_info[:38]:<38}")
        sys.stdout.flush()

    print(f"Starting batch generation (Overwrite: {args.overwrite})...")
    res = client.batch_generate_manifest(manifest_path, on_progress=on_prog, overwrite=args.overwrite)
    print("\n\n" + "=" * 65)
    print(f"[COMPLETED] Total: {res['total']} | Newly Generated: {res['generated']}")
    print(f"Audio cache is ready at: {resolve_path('audio_cache')}")
    print("=" * 65)


if __name__ == "__main__":
    main()
