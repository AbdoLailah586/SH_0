"""
ESP32 Smart Home Hardware Controller.
Communicates with ESP32 board over:
  1. Local Wi-Fi (HTTP REST with mDNS 'esp32-smarthome.local' or configurable IP)
  2. Serial / Bluetooth COM port fallback
"""

import json
import threading
import time
from typing import Dict, Any, Optional, Tuple, Callable
import requests

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class ESP32Controller:
    def __init__(
        self,
        base_url: str = "http://esp32-smarthome.local",
        com_port: Optional[str] = None,
        baud_rate: int = 115200,
        mode: str = "wifi" # "wifi" or "serial"
    ):
        self.base_url = base_url.rstrip("/")
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.mode = mode
        self.timeout = 1.5  # Quick timeout for responsive GUI

        self.last_status: Dict[str, Any] = {
            "status": "offline",
            "device": "ESP32-SmartHome-Hub",
            "ip": "Unknown",
            "uptime_ms": 0,
            "led": False,
            "relays": [False, False, False, False],
            "ac": {"power": False, "temp": 22, "mode": "cool"},
            "window_curtain": {"position": 0}
        }
        self.last_ping_ms: int = -1
        self.is_connected: bool = False
        self._lock = threading.Lock()
        self._serial_conn = None

    def set_base_url(self, url: str):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"
        self.base_url = url.rstrip("/")

    # --- SERIAL FALLBACK ---

    def list_serial_ports(self):
        """Returns available COM ports."""
        if not SERIAL_AVAILABLE:
            return []
        try:
            return [port.device for port in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def connect_serial(self, port: str):
        if not SERIAL_AVAILABLE:
            return False
        try:
            if self._serial_conn and self._serial_conn.is_open:
                self._serial_conn.close()
            self._serial_conn = serial.Serial(port, self.baud_rate, timeout=1.0)
            self.com_port = port
            self.mode = "serial"
            return True
        except Exception as e:
            print(f"[ESP32 Serial Error] {e}")
            return False

    def _send_serial_cmd(self, cmd: str) -> Optional[Dict[str, Any]]:
        if not self._serial_conn or not self._serial_conn.is_open:
            return None
        try:
            with self._lock:
                self._serial_conn.write(f"{cmd.strip()}\n".encode("utf-8"))
                line = self._serial_conn.readline().decode("utf-8").strip()
                if line.startswith("{") and line.endswith("}"):
                    data = json.loads(line)
                    self.last_status.update(data)
                    self.is_connected = True
                    return data
        except Exception as e:
            print(f"[Serial Send Error] {e}")
        return None

    # --- HTTP REST API ---

    def _http_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[Dict[str, Any]], int]:
        """
        Executes HTTP GET to ESP32.
        Returns: (success, response_dict, latency_ms)
        """
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        url = f"{self.base_url}{endpoint}"

        t0 = time.perf_counter()
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    with self._lock:
                        self.last_status.update(data)
                        self.last_ping_ms = latency_ms
                        self.is_connected = True
                    return True, data, latency_ms
                except Exception:
                    return True, {"raw": resp.text}, latency_ms
            return False, None, latency_ms
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            with self._lock:
                self.is_connected = False
                self.last_ping_ms = -1
            return False, None, latency_ms

    # --- UNIFIED CONTROL METHODS ---

    def ping(self) -> Tuple[bool, int]:
        """Checks connection to ESP32 and measures ping time."""
        if self.mode == "serial":
            res = self._send_serial_cmd("STATUS")
            return (res is not None), 5
        else:
            success, data, latency = self._http_request("/status")
            return success, latency

    def get_status(self) -> Dict[str, Any]:
        """Fetches latest status from ESP32."""
        if self.mode == "serial":
            self._send_serial_cmd("STATUS")
        else:
            self._http_request("/status")
        return self.last_status

    def set_led(self, state: str) -> bool:
        """state: 'on', 'off', or 'toggle'"""
        if self.mode == "serial":
            cmd = f"LED:{state.upper()}"
            res = self._send_serial_cmd(cmd)
            return res is not None
        else:
            success, _, _ = self._http_request("/led", {"state": state})
            return success

    def set_relay(self, channel: int, state: str) -> bool:
        """channel: 1 to 4, state: 'on', 'off', or 'toggle'"""
        if self.mode == "serial":
            cmd = f"RELAY:{channel}:{state.upper()}"
            res = self._send_serial_cmd(cmd)
            return res is not None
        else:
            success, _, _ = self._http_request("/relay", {"ch": channel, "state": state})
            return success

    def set_all_lights(self, state: str) -> bool:
        """Turns on/off all 4 relays simultaneously."""
        results = []
        for ch in range(1, 5):
            results.append(self.set_relay(ch, state))
        return any(results)

    def set_ac(self, temp: int = 22, mode: str = "cool", power: Optional[str] = "on") -> bool:
        params = {"temp": temp, "mode": mode}
        if power:
            params["power"] = power
        success, _, _ = self._http_request("/ac", params)
        return success

    def set_window(self, pos: int) -> bool:
        """pos: 0 (closed) to 100 (fully open)"""
        pos = max(0, min(100, pos))
        success, _, _ = self._http_request("/window", {"pos": pos})
        return success

    # --- BACKGROUND ASYNC EXECUTION ---

    def execute_async(self, func: Callable, callback: Optional[Callable[[Any], None]] = None, *args, **kwargs):
        """Runs an ESP32 command in background thread so GUI never lags."""
        def _runner():
            res = func(*args, **kwargs)
            if callback:
                try:
                    callback(res)
                except Exception:
                    pass

        t = threading.Thread(target=_runner, daemon=True)
        t.start()

