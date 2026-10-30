"""
Deterministic Egyptian Arabic Intent Parser.
Uses Arabic Normalization, Regex Patterns, and RapidFuzz Keyword Matching
to classify voice input in <20ms without GPU/LLM latency.
"""

import datetime
import json
import os
import random
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from core.paths import resolve_path

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


def normalize_arabic(text: str) -> str:
    """
    Normalizes Egyptian spoken Arabic text for robust pattern matching:
    - Removes Tashkeel (diacritics)
    - Normalizes Alef variations (أ, إ, آ, ٱ -> ا)
    - Normalizes Taa Marbuta (ة -> ه)
    - Normalizes Yaa (ى -> ي)
    - Cleans punctuation and excess whitespace
    """
    if not text:
        return ""

    text = text.strip()

    # Remove diacritics (Tashkeel)
    tashkeel = re.compile(r'[\u0617-\u061A\u064B-\u0652]')
    text = re.sub(tashkeel, '', text)

    # Normalize Alefs
    text = re.sub(r'[إأآٱ]', 'ا', text)

    # Normalize Taa Marbuta
    text = re.sub(r'ة', 'ه', text)

    # Normalize Alef Maqsura to Yaa
    text = re.sub(r'ى', 'ي', text)

    # Normalize Persian/Urdu Kaf and Yaa if any
    text = re.sub(r'ك', 'ك', text)
    text = re.sub(r'ي', 'ي', text)

    # Remove tatweel (kashida)
    text = re.sub(r'ـ', '', text)

    # Remove punctuation
    text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text)

    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text.lower()


class IntentParser:
    def __init__(self, manifest_path: Optional[str] = None, fuzzy_threshold: int = 75):
        self.fuzzy_threshold = fuzzy_threshold
        self.intents: List[Dict[str, Any]] = []
        self.manifest_path = manifest_path
        self._load_manifest(manifest_path)

    def _load_manifest(self, manifest_path: Optional[str]):
        if not manifest_path:
            manifest_path = resolve_path(os.path.join("config", "voice_bank_manifest.json"))

        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.intents = data.get("intents", [])
                    # Pre-normalize trigger patterns for speed
                    for it in self.intents:
                        it["_normalized_triggers"] = [
                            normalize_arabic(p) for p in it.get("trigger_patterns", [])
                        ]
            except Exception as e:
                print(f"[IntentParser Load Error] {e}")

    def is_night_time(self) -> bool:
        """Checks if current local time is after 12:00 AM (00:00 - 06:00)."""
        now = datetime.datetime.now()
        return 0 <= now.hour < 6

    def select_variation(self, intent: Dict[str, Any], is_night: bool = False) -> Dict[str, Any]:
        """
        Selects a variation from the intent.
        Prefers whisper variations if night mode is active.
        """
        variations = intent.get("variations", [])
        if not variations:
            return {"text_ar": "تمام يا فندم", "audio_file": "", "emotion": "normal"}

        if is_night:
            whisper_vars = [v for v in variations if v.get("emotion") == "whisper"]
            if whisper_vars:
                return random.choice(whisper_vars)

        # Standard randomized variation
        return random.choice(variations)

    def parse(
        self,
        spoken_text: str,
        night_mode_force: Optional[bool] = None
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], float, float]:
        """
        Parses spoken text and matches the optimal smart home intent.
        
        Returns:
            (matched_intent_dict, selected_variation_dict, latency_ms, confidence_score)
        """
        t0 = time.perf_counter()
        norm_text = normalize_arabic(spoken_text)

        if not norm_text:
            latency = (time.perf_counter() - t0) * 1000
            return None, {}, latency, 0.0

        is_night = self.is_night_time() if night_mode_force is None else night_mode_force

        best_intent = None
        best_score = 0.0

        # STAGE 1: Fast Exact Substring / Regex Match (<1ms)
        for intent in self.intents:
            for trig in intent.get("_normalized_triggers", []):
                if trig == norm_text:
                    latency = (time.perf_counter() - t0) * 1000
                    variation = self.select_variation(intent, is_night)
                    return intent, variation, latency, 100.0
                elif trig in norm_text:
                    # Partial exact match (e.g., "لو سمحت افتح النور يا فندم")
                    score = 92.0
                    if score > best_score:
                        best_score = score
                        best_intent = intent

        if best_intent and best_score >= 90.0:
            latency = (time.perf_counter() - t0) * 1000
            variation = self.select_variation(best_intent, is_night)
            return best_intent, variation, latency, best_score

        # STAGE 2: RapidFuzz Matching (<10ms)
        if RAPIDFUZZ_AVAILABLE:
            for intent in self.intents:
                for trig in intent.get("_normalized_triggers", []):
                    # Combine token sort ratio and partial ratio
                    ratio = fuzz.token_set_ratio(trig, norm_text)
                    if ratio > best_score:
                        best_score = ratio
                        best_intent = intent

        latency = (time.perf_counter() - t0) * 1000

        if best_intent and best_score >= self.fuzzy_threshold:
            variation = self.select_variation(best_intent, is_night)
            return best_intent, variation, latency, best_score

        return None, {}, latency, best_score

