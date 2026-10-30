"""
Fish Speech GPU Setup & Model Downloader for NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM).
Clones fish-speech repo and downloads the 'fishaudio/openaudio-s1-mini' checkpoint (~3.5GB VRAM in fp16).
"""

import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.join(BASE_DIR, "fish_speech_repo")
CHECKPOINTS_DIR = os.path.join(REPO_DIR, "checkpoints", "openaudio-s1-mini")

def main():
    print("=" * 65)
    print("Fish Speech GPU Setup for Lenovo LOQ (RTX 4050 6GB VRAM)")
    print("=" * 65)

    # 1. Verify PyTorch & CUDA
    print("[1/4] Verifying PyTorch CUDA support...")
    try:
        import torch
        print(f"  PyTorch Version : {torch.__version__}")
        print(f"  CUDA Available  : {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU Device Name : {torch.cuda.get_device_name(0)}")
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  Total VRAM      : {vram_gb:.2f} GB")
        else:
            print("  [!] CUDA not yet active in torch. Run: pip install torch --index-url https://download.pytorch.org/whl/cu124")
    except ImportError:
        print("  [!] PyTorch not installed yet.")

    # 2. Clone fish-speech repo
    print("\n[2/4] Checking Fish Speech repository...")
    if not os.path.exists(REPO_DIR):
        print(f"  Cloning fish-speech into: {REPO_DIR}")
        try:
            subprocess.run(["git", "clone", "https://github.com/fishaudio/fish-speech.git", REPO_DIR], check=True)
            print("  [OK] Repository cloned successfully!")
        except Exception as e:
            print(f"  [!] Git clone error: {e}")
    else:
        print(f"  [OK] Fish Speech repository exists at: {REPO_DIR}")

    # 3. Download openaudio-s1-mini checkpoint
    print("\n[3/4] Checking openaudio-s1-mini checkpoint...")
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    
    # Try reading token from config or env
    hf_token = os.environ.get("HF_TOKEN")
    settings_file = os.path.join(BASE_DIR, "config", "app_settings.json")
    if not hf_token and os.path.exists(settings_file):
        try:
            import json
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                hf_token = settings.get("hf_token", "").strip() or None
        except Exception:
            pass

    try:
        from huggingface_hub import snapshot_download
        print("  Downloading 'fishaudio/openaudio-s1-mini' checkpoint from Hugging Face...")
        snapshot_download(
            repo_id="fishaudio/openaudio-s1-mini",
            local_dir=CHECKPOINTS_DIR,
            token=hf_token
        )
        print(f"  [OK] Checkpoint ready at: {CHECKPOINTS_DIR}")
    except Exception as e:
        print(f"  [Notice] Checkpoint download status: {e}")
        if "restricted" in str(e).lower() or "401" in str(e):
            print("\n  >> Hint: fishaudio/openaudio-s1-mini is a gated model.")
            print("  >> To download weights automatically:")
            print("     1. Visit: https://huggingface.co/fishaudio/openaudio-s1-mini and click 'Agree'")
            print("     2. Create token at https://huggingface.co/settings/tokens")
            print("     3. Enter your HF token in the Desktop App Settings tab or set $env:HF_TOKEN")
            print("     4. Meanwhile, the Desktop App is using High-Definition Egyptian Neural voice synthesis!")

    # 4. Generate Launch Script
    print("\n[4/4] Verifying startup scripts...")
    bat_path = os.path.join(BASE_DIR, "start_fish_server.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("TITLE Fish Speech CUDA API Server (RTX 4050 6GB)\n")
        f.write("COLOR 0A\n")
        f.write("echo Starting Fish Speech GPU API Server on http://127.0.0.1:8080...\n")
        f.write(f'cd /d "{REPO_DIR}"\n')
        f.write(r'..\.venv\Scripts\python.exe -m tools.api_server --listen 127.0.0.1:8080 --device cuda --half' + "\n")
        f.write("pause\n")

    print(f"  [OK] Server launcher created: {bat_path}")
    print("\n" + "=" * 65)
    print("Setup steps completed! You can launch the server via start_fish_server.bat")
    print("=" * 65)

if __name__ == "__main__":
    main()

