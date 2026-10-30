"""
Zero-Latency Native Audio Playback Engine with Audio Ducking.
Plays pre-generated .wav clips through the laptop default speakers.
"""

import os
import random
import threading
import time
from typing import Callable, Optional
from core.audio_ducking import AudioDucker
from core.paths import resolve_path

# Using pygame.mixer for ultra-low latency native audio playback
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class AudioPlayer:
    def __init__(self, ducking_enabled: bool = True, duck_level: float = 0.25):
        self.ducking_enabled = ducking_enabled
        self.ducker = AudioDucker(duck_level=duck_level)
        self._is_playing = False
        self._lock = threading.Lock()
        self._playback_thread = None

        if PYGAME_AVAILABLE:
            try:
                # Initialize mixer with 44100Hz, 16-bit, 2 channels, 512 buffer for low latency
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            except Exception as e:
                try:
                    pygame.mixer.init()
                except Exception:
                    pass

    def is_playing(self) -> bool:
        return self._is_playing

    def play_wav(
        self,
        wav_path: str,
        on_start: Optional[Callable[[], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
        blocking: bool = False
    ):
        """
        Plays a .wav file with automatic volume ducking.
        """
        full_path = resolve_path(wav_path)

        if not os.path.exists(full_path):
            print(f"[AudioPlayer] File not found: {full_path}")
            if on_finish:
                on_finish()
            return False

        def _play_worker():
            with self._lock:
                self._is_playing = True

            try:
                if self.ducking_enabled:
                    self.ducker.start_ducking()

                if on_start:
                    try:
                        on_start()
                    except Exception:
                        pass

                if PYGAME_AVAILABLE and pygame.mixer.get_init():
                    sound = pygame.mixer.Sound(full_path)
                    sound_channel = sound.play()
                    while sound_channel and sound_channel.get_busy():
                        time.sleep(0.02)
                else:
                    # Windows winsound fallback
                    import winsound
                    winsound.PlaySound(full_path, winsound.SND_FILENAME)

            except Exception as e:
                print(f"[AudioPlayer Error] {e}")
            finally:
                if self.ducking_enabled:
                    # Brief rest before restoring volume to avoid click
                    time.sleep(0.08)
                    self.ducker.stop_ducking()

                with self._lock:
                    self._is_playing = False

                if on_finish:
                    try:
                        on_finish()
                    except Exception:
                        pass

        if blocking:
            _play_worker()
        else:
            self._playback_thread = threading.Thread(target=_play_worker, daemon=True)
            self._playback_thread.start()

        return True

    def stop(self):
        """Immediately stops any currently playing audio."""
        if PYGAME_AVAILABLE and pygame.mixer.get_init():
            pygame.mixer.stop()
        if self.ducking_enabled:
            self.ducker.stop_ducking()
        self._is_playing = False

