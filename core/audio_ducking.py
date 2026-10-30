"""
Audio Ducking System using Windows CoreAudio API (pycaw).
Temporarily lowers host laptop system master/media volume while AI speaks,
and restores it smoothly when playback finishes.
"""

import threading
import time

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False


class AudioDucker:
    def __init__(self, duck_level: float = 0.25):
        """
        :param duck_level: Volume multiplier/level when ducked (0.0 to 1.0).
        """
        self.duck_level = max(0.05, min(1.0, duck_level))
        self.is_ducked = False
        self.original_volume = None
        self._lock = threading.Lock()
        self._volume_endpoint = None
        self._init_endpoint()

    def _init_endpoint(self):
        if not PYCAW_AVAILABLE:
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._volume_endpoint = interface.QueryInterface(IAudioEndpointVolume)
        except Exception as e:
            self._volume_endpoint = None

    def start_ducking(self):
        """Ducks the system volume smoothly."""
        with self._lock:
            if self.is_ducked:
                return
            if not self._volume_endpoint:
                self._init_endpoint()
            if not self._volume_endpoint:
                return

            try:
                self.original_volume = self._volume_endpoint.GetMasterVolumeLevelScalar()
                # Only duck if current volume is higher than duck_level
                if self.original_volume > self.duck_level:
                    self._volume_endpoint.SetMasterVolumeLevelScalar(self.duck_level, None)
                    self.is_ducked = True
            except Exception:
                self.is_ducked = False

    def stop_ducking(self):
        """Restores the original system volume."""
        with self._lock:
            if not self.is_ducked or self.original_volume is None:
                self.is_ducked = False
                return
            if not self._volume_endpoint:
                self._init_endpoint()
            if not self._volume_endpoint:
                self.is_ducked = False
                return

            try:
                self._volume_endpoint.SetMasterVolumeLevelScalar(self.original_volume, None)
            except Exception:
                pass
            finally:
                self.is_ducked = False
                self.original_volume = None

