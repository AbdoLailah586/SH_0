"""
Generate High-Quality Egyptian Reference Voice Seeds for Fish Speech Voice Cloning.
Uses edge-tts (ar-EG-ShakirNeural & ar-EG-SalmaNeural) + ffmpeg to output 16-bit 44.1kHz PCM .wav.
"""

import asyncio
import os
import subprocess
import sys
import edge_tts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(BASE_DIR, "config", "reference_voices")
os.makedirs(REF_DIR, exist_ok=True)

MALE_TEXT = "أهلاً بيك يا فندم، أنا المساعد الصوتي الذكي في بيتك، جاهز في أي وقت عشان أنفذ كل طلباتك وأتحكم في البيت واللابتوب بكل سهولة."
FEMALE_TEXT = "صباح الخير يا فندم، نورت بيتك الذكي، كل الأجهزة والأنوار جاهزة ومستعدة لكل أوامرك طول اليوم، تحت أمرك دايماً."

async def save_with_retry(text, voice, mp3_path, retries=3):
    for attempt in range(retries):
        try:
            comm = edge_tts.Communicate(text, voice=voice)
            await comm.save(mp3_path)
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000:
                return True
        except Exception as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2.0)
    return False

async def generate():
    print("[*] Generating Egyptian Reference Seeds for Fish Speech...")

    # 1. Male reference
    male_mp3 = os.path.join(REF_DIR, "male_temp.mp3")
    male_wav = os.path.join(REF_DIR, "egyptian_male_ref.wav")
    male_txt = os.path.join(REF_DIR, "egyptian_male_ref.txt")
    
    if not os.path.exists(male_wav) or os.path.getsize(male_wav) < 10000:
        await save_with_retry(MALE_TEXT, "ar-EG-ShakirNeural", male_mp3)
        subprocess.run(["ffmpeg", "-y", "-i", male_mp3, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", male_wav],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(male_mp3):
            os.remove(male_mp3)

    with open(male_txt, "w", encoding="utf-8") as f:
        f.write(MALE_TEXT)

    print(f"  [OK] Egyptian Male Reference: {male_wav} ({os.path.getsize(male_wav)} bytes)")

    await asyncio.sleep(1.5)

    # 2. Female reference
    female_mp3 = os.path.join(REF_DIR, "female_temp.mp3")
    female_wav = os.path.join(REF_DIR, "egyptian_female_ref.wav")
    female_txt = os.path.join(REF_DIR, "egyptian_female_ref.txt")

    await save_with_retry(FEMALE_TEXT, "ar-EG-SalmaNeural", female_mp3)
    subprocess.run(["ffmpeg", "-y", "-i", female_mp3, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", female_wav],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(female_mp3):
        os.remove(female_mp3)

    with open(female_txt, "w", encoding="utf-8") as f:
        f.write(FEMALE_TEXT)

    print(f"  [OK] Egyptian Female Reference: {female_wav} ({os.path.getsize(female_wav)} bytes)")
    print("[SUCCESS] Reference seeds ready in config/reference_voices/!")

if __name__ == "__main__":
    asyncio.run(generate())
