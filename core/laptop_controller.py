"""
Host Windows Laptop OS Controller.
Provides direct programmatic access to:
  - Master Volume control (Up, Down, Mute, Set X%) via CoreAudio
  - Media Keys (Play/Pause, Next Track, Previous Track)
  - Session & Power (Lock Screen, Turn off display, Close active window)
  - Application Launching (Chrome, Spotify, Notepad, VS Code)
  - System Monitoring (Battery percentage, CPU, RAM)
"""

import ctypes
import os
import subprocess
import time
from typing import Dict, Any, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False

# Windows Virtual Key Codes
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

# Windows Constants
HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
WM_CLOSE = 0x0010


class LaptopController:
    def __init__(self):
        self._vol_endpoint = None
        self._init_audio()

    def _init_audio(self):
        if not PYCAW_AVAILABLE:
            return
        try:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._vol_endpoint = interface.QueryInterface(IAudioEndpointVolume)
        except Exception:
            self._vol_endpoint = None

    # --- VOLUME CONTROLS ---

    def get_volume(self) -> int:
        """Returns master volume percent (0-100)."""
        if not self._vol_endpoint:
            self._init_audio()
        if self._vol_endpoint:
            try:
                scalar = self._vol_endpoint.GetMasterVolumeLevelScalar()
                return int(round(scalar * 100))
            except Exception:
                pass
        return 50

    def set_volume(self, percent: int) -> bool:
        """Sets master volume to a specific percentage (0-100)."""
        percent = max(0, min(100, percent))
        if not self._vol_endpoint:
            self._init_audio()
        if self._vol_endpoint:
            try:
                self._vol_endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
                return True
            except Exception:
                pass
        return False

    def volume_up(self, step: int = 15) -> int:
        """Increases volume by step %."""
        cur = self.get_volume()
        new_vol = min(100, cur + step)
        self.set_volume(new_vol)
        return new_vol

    def volume_down(self, step: int = 15) -> int:
        """Decreases volume by step %."""
        cur = self.get_volume()
        new_vol = max(0, cur - step)
        self.set_volume(new_vol)
        return new_vol

    def toggle_mute(self) -> bool:
        """Toggles audio mute."""
        if not self._vol_endpoint:
            self._init_audio()
        if self._vol_endpoint:
            try:
                cur_mute = self._vol_endpoint.GetMute()
                self._vol_endpoint.SetMute(not cur_mute, None)
                return not cur_mute
            except Exception:
                pass
        # Fallback via keybd_event
        self._send_key(VK_VOLUME_MUTE)
        return True

    # --- MEDIA CONTROLS ---

    def _send_key(self, vk_code: int):
        """Simulates a key press and release using Windows user32."""
        try:
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP
        except Exception as e:
            print(f"[Keybd Error] {e}")

    def media_play_pause(self):
        """Toggles media play/pause across Windows media players."""
        self._send_key(VK_MEDIA_PLAY_PAUSE)

    def media_next(self):
        """Skips to next track."""
        self._send_key(VK_MEDIA_NEXT_TRACK)

    def media_prev(self):
        """Goes to previous track."""
        self._send_key(VK_MEDIA_PREV_TRACK)

    # --- SESSION & POWER ACTIONS ---

    def lock_workstation(self):
        """Instantly locks the Windows user session."""
        try:
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception as e:
            print(f"[LockWorkStation Error] {e}")
            return False

    def turn_off_monitor(self):
        """Turns off the laptop / monitor display (wakes on mouse/key move)."""
        try:
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
            return True
        except Exception as e:
            print(f"[TurnOffMonitor Error] {e}")
            return False

    def close_active_window(self):
        """Closes the current foreground active window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return True
        except Exception as e:
            print(f"[CloseActiveWindow Error] {e}")
        return False

    # --- APPLICATION LAUNCHER ---

    def launch_app(self, app_name: str) -> bool:
        """Launches common applications without blocking."""
        app_name = app_name.lower().strip()
        try:
            if "chrome" in app_name:
                subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=True)
            elif "spotify" in app_name:
                subprocess.Popen(["cmd", "/c", "start", "spotify:"], shell=True)
            elif "notepad" in app_name:
                subprocess.Popen(["notepad.exe"])
            elif "calc" in app_name:
                subprocess.Popen(["calc.exe"])
            elif "code" in app_name or "vscode" in app_name:
                subprocess.Popen(["cmd", "/c", "code"], shell=True)
            elif "explorer" in app_name:
                subprocess.Popen(["explorer.exe"])
            else:
                subprocess.Popen(["cmd", "/c", "start", app_name], shell=True)
            return True
        except Exception as e:
            print(f"[LaunchApp Error] {e}")
            return False

    # --- SYSTEM STATUS ---

    def get_battery_info(self) -> Dict[str, Any]:
        """Returns battery status: percent, plugged in, and formatted string."""
        if not PSUTIL_AVAILABLE:
            return {"percent": 100, "plugged": True, "text_ar": "معلومات البطارية غير متاحة"}

        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {"percent": 100, "plugged": True, "text_ar": "الجهاز متصل بالكهرباء مباشرة"}

            pct = int(battery.percent)
            plugged = battery.power_plugged
            status_text = "متصل بالشاحن" if plugged else "شغال على البطارية"
            text_ar = f"نسبة البطارية {pct} بالمية، و{status_text}"
            return {"percent": pct, "plugged": plugged, "text_ar": text_ar}
        except Exception:
            return {"percent": 100, "plugged": True, "text_ar": "البطارية تمام"}

    def get_system_stats(self) -> Dict[str, Any]:
        """Returns CPU usage and RAM usage percentage."""
        cpu = 0
        ram = 0
        if PSUTIL_AVAILABLE:
            try:
                cpu = int(psutil.cpu_percent(interval=None))
                ram = int(psutil.virtual_memory().percent)
            except Exception:
                pass
        return {"cpu_percent": cpu, "ram_percent": ram}

