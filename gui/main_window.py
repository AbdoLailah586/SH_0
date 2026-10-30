"""
Main Native Windows Desktop Application Window for AI Smart Home Voice Hub.
Integrates:
  - 4 Modular Tabs (Dashboard, Audio Cache & Fish Speech, ESP32 Manager, Settings)
  - LLM Brain (Groq LPU Primary + OpenRouter Fallback + Tool Calling)
  - Zero-Latency Static Audio Cache + Live Dynamic Synthesis for Battery & Chat
  - Windows System Tray Icon & Global Hotkey (Ctrl+Space)
  - Secure HTTPS/WSS Mobile Mic LAN Bridge
"""

import os
import sys
import threading
import time
from typing import Optional, List, Dict, Any, Tuple, Callable
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap, QPainter, QBrush
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QSystemTrayIcon, QMenu, QMessageBox, QApplication
)

from core.audio_player import AudioPlayer
from core.laptop_controller import LaptopController
from core.esp32_controller import ESP32Controller
from core.intent_parser import IntentParser
from core.stt_engine import STTEngine
from core.lan_receiver import MobileMicLANBridge
from core.fish_speech_client import FishSpeechClient
from core.llm_brain import LLMBrain
from core.paths import resolve_path

from gui.styles import DARK_THEME_QSS
from gui.tab_dashboard import DashboardTab
from gui.tab_audio_cache import AudioCacheTab
from gui.tab_esp32_devices import ESP32DevicesTab
from gui.tab_settings import SettingsTab

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


def create_app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Outer circle
    brush = QBrush(QColor("#1f6feb"))
    painter.setBrush(brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)

    # Inner core
    brush_inner = QBrush(QColor("#58a6ff"))
    painter.setBrush(brush_inner)
    painter.drawEllipse(18, 18, 28, 28)

    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    signal_transcript_ready = pyqtSignal(str)
    signal_vu_level = pyqtSignal(int)
    signal_status_change = pyqtSignal(str)
    signal_lan_command = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Smart Home Voice Hub - Lenovo LOQ RTX 4050 Edition (.exe)")
        self.resize(1140, 800)
        self.setMinimumSize(940, 660)

        self.setStyleSheet(DARK_THEME_QSS)
        self.app_icon = create_app_icon()
        self.setWindowIcon(self.app_icon)

        # Core Engines
        self.laptop = LaptopController()
        self.esp32 = ESP32Controller()
        self.intent_parser = IntentParser()
        self.audio_player = AudioPlayer(ducking_enabled=True, duck_level=0.25)
        self.fish_client = FishSpeechClient()
        self.stt_engine = STTEngine(engine_type="groq_whisper")
        self.llm = LLMBrain()
        self.lan_bridge = MobileMicLANBridge(port=8765)

        # Connect LLM Tool Handlers
        self.llm.esp32_handler = self._llm_handle_esp32
        self.llm.laptop_handler = self._llm_handle_laptop

        # Signals
        self.signal_transcript_ready.connect(self.process_spoken_arabic_command)
        self.signal_vu_level.connect(self._on_vu_level)
        self.signal_status_change.connect(self._on_stt_status)
        self.signal_lan_command.connect(self.process_spoken_arabic_command)

        self.init_tabs()
        self.init_system_tray()
        self._wire_engine_callbacks()
        self._init_global_hotkey()
        self.lan_bridge.start()

    def init_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Tab 1: Live Voice & Control Dashboard
        self.tab_dashboard = DashboardTab(self)
        self.tab_dashboard.request_ptt.connect(self._trigger_ptt)
        self.tab_dashboard.request_toggle_continuous.connect(self._toggle_continuous_listening)
        self.tab_dashboard.request_manual_command.connect(self.process_spoken_arabic_command)
        self.tab_dashboard.request_esp32_led.connect(lambda: self.esp32.set_led("toggle"))
        self.tab_dashboard.request_esp32_relay.connect(lambda ch: self.esp32.set_relay(ch, "toggle"))
        self.tab_dashboard.request_laptop_volume_up.connect(lambda: self.laptop.volume_up(15))
        self.tab_dashboard.request_laptop_volume_down.connect(lambda: self.laptop.volume_down(15))
        self.tab_dashboard.request_laptop_mute.connect(lambda: self.laptop.toggle_mute())
        self.tab_dashboard.request_laptop_lock.connect(lambda: self.laptop.lock_workstation())
        self.tab_dashboard.request_laptop_battery.connect(self._handle_battery_request)
        self.tab_dashboard.mic_device_changed.connect(lambda idx: self.stt_engine.set_device_index(idx))

        mics = self.stt_engine.list_microphones()
        self.tab_dashboard.populate_mic_devices(mics)

        # Tab 2: Pre-Generated Audio Cache & Fish Speech Studio
        self.tab_audio_cache = AudioCacheTab(self)
        self.tab_audio_cache.request_preview_audio.connect(self._preview_cached_audio)

        # Tab 3: ESP32 & Network Devices Manager
        self.tab_esp32 = ESP32DevicesTab(self.esp32, self)
        self.tab_esp32.request_toggle_led.connect(lambda: self.esp32.set_led("toggle"))
        self.tab_esp32.request_toggle_relay.connect(lambda ch: self.esp32.set_relay(ch, "toggle"))

        # Tab 4: Settings & STT/LLM Engine
        self.tab_settings = SettingsTab(self)
        self.tab_settings.settings_saved.connect(self._on_settings_saved)

        self.tabs.addTab(self.tab_dashboard, "🎙️ لوحة التحكم والصوت المباشر (Dashboard)")
        self.tabs.addTab(self.tab_audio_cache, "🎵 كاش الأصوات و Fish Speech RTX 4050")
        self.tabs.addTab(self.tab_esp32, "⚡ هاردوير ESP32 ومايك الموبايل المشفر")
        self.tabs.addTab(self.tab_settings, "⚙️ إعدادات الذكاء الاصطناعي و Groq LLM")

        self.setCentralWidget(self.tabs)

    def init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("AI Smart Home Voice Hub (Lenovo LOQ RTX 4050)")

        tray_menu = QMenu()
        action_show = QAction("إظهار / إخفاء النافذة", self)
        action_show.triggered.connect(self._toggle_window_visibility)

        action_ptt = QAction("🎙️ التحدث بالأمر الصوتي (PTT)", self)
        action_ptt.triggered.connect(self._trigger_ptt)

        action_toggle_light = QAction("💡 تبديل نور الريسبشن (Relay 1)", self)
        action_toggle_light.triggered.connect(lambda: self.esp32.set_relay(1, "toggle"))

        action_lock = QAction("🔒 قفل اللابتوب فوراً", self)
        action_lock.triggered.connect(lambda: self.laptop.lock_workstation())

        action_exit = QAction("❌ خروج نهائي من البرنامج", self)
        action_exit.triggered.connect(self._quit_application)

        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        tray_menu.addAction(action_ptt)
        tray_menu.addAction(action_toggle_light)
        tray_menu.addAction(action_lock)
        tray_menu.addSeparator()
        tray_menu.addAction(action_exit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window_visibility()

    def closeEvent(self, event):
        minimize_to_tray = self.tab_settings.settings_data.get("minimize_to_tray_on_close", True)
        if minimize_to_tray and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "AI Smart Home Hub",
                "البرنامج شغال في الخلفية. استخدم Ctrl+Space للتحدث في أي وقت.",
                QSystemTrayIcon.MessageIcon.Information,
                2500
            )
        else:
            self._quit_application()

    def _quit_application(self):
        self.stt_engine.cleanup()
        self.lan_bridge.stop()
        self.tray_icon.hide()
        QApplication.quit()

    def _init_global_hotkey(self):
        if not PYNPUT_AVAILABLE:
            return

        def _on_hotkey():
            self.signal_status_change.emit("listening")
            self._trigger_ptt()

        try:
            hotkey_listener = keyboard.GlobalHotKeys({
                '<ctrl>+<space>': _on_hotkey
            })
            hotkey_listener.daemon = True
            hotkey_listener.start()
        except Exception as e:
            print(f"[Global Hotkey Warning] {e}")

    def _wire_engine_callbacks(self):
        self.stt_engine.on_transcript = lambda text: self.signal_transcript_ready.emit(text)
        self.stt_engine.on_level_update = lambda lvl: self.signal_vu_level.emit(lvl)
        self.stt_engine.on_status_change = lambda st: self.signal_status_change.emit(st)

        self.lan_bridge.on_command_received = lambda text: self.signal_lan_command.emit(text)
        self.lan_bridge.on_client_count_change = lambda cnt: self.tab_esp32.update_client_count(cnt)

    def _on_vu_level(self, level: int):
        self.tab_dashboard.update_vu_level(level)

    def _on_stt_status(self, status: str):
        self.tab_dashboard.update_status(status)

    def _trigger_ptt(self):
        self.stt_engine.trigger_push_to_talk_record(duration_sec=3.5)

    def _toggle_continuous_listening(self, active: bool):
        if active:
            self.stt_engine.start_continuous_listening()
        else:
            self.stt_engine.stop_continuous_listening()

    def _preview_cached_audio(self, wav_rel_path: str):
        self.audio_player.play_wav(
            wav_rel_path,
            on_start=lambda: self.tab_dashboard.update_status("speaking"),
            on_finish=lambda: self.tab_dashboard.update_status("idle")
        )

    def _on_settings_saved(self, settings: dict):
        self.intent_parser.fuzzy_threshold = settings.get("fuzzy_threshold", 75)
        self.audio_player.ducking_enabled = settings.get("ducking_enabled", True)
        self.audio_player.ducker.duck_level = settings.get("ducking_level", 0.25)
        self.stt_engine.engine_type = settings.get("stt_engine", "groq_whisper")
        self.llm._load_keys_from_settings()

    # --- LLM TOOL CALLING HANDLERS ---

    def _llm_handle_esp32(self, action: str, channel: Optional[int], state: Optional[str], value: Optional[int]):
        state = state or "toggle"
        if action == "relay" and channel:
            return self.esp32.set_relay(channel, state)
        elif action == "led":
            return self.esp32.set_led(state)
        elif action == "all_lights":
            return self.esp32.set_all_lights(state)
        elif action == "ac":
            return self.esp32.set_ac(temp=value or 22, mode="cool", power=state)
        elif action == "window":
            return self.esp32.set_window(value or 100)
        return "Unknown ESP32 action"

    def _llm_handle_laptop(self, command: str, app_name: Optional[str], step: Optional[int]):
        step = step or 15
        if command == "volume_up":
            return self.laptop.volume_up(step)
        elif command == "volume_down":
            return self.laptop.volume_down(step)
        elif command == "mute":
            return self.laptop.toggle_mute()
        elif command == "lock_screen":
            return self.laptop.lock_workstation()
        elif command == "play_pause":
            return self.laptop.media_play_pause()
        elif command == "launch_app" and app_name:
            return self.laptop.launch_app(app_name)
        elif command == "get_battery":
            return self.laptop.get_battery_info()
        elif command == "get_stats":
            return self.laptop.get_system_stats()
        return "Unknown Laptop command"

    def _handle_battery_request(self):
        batt = self.laptop.get_battery_info()
        text = f"نسبة شحن بطارية اللابتوب دلوقتي {batt['percent']} في المية، و{batt['text_ar']}."
        self._synthesize_and_play_live(text, action_desc=f"Battery: {batt['percent']}%")

    def _synthesize_and_play_live(self, text: str, action_desc: str = "Live Dynamic Response"):
        t0 = time.perf_counter()
        def _worker():
            live_wav = self.fish_client.synthesize_live(text)
            latency = (time.perf_counter() - t0) * 1000
            if live_wav and os.path.exists(live_wav):
                self.audio_player.play_wav(
                    live_wav,
                    on_start=lambda: self.tab_dashboard.update_status("speaking"),
                    on_finish=lambda: self.tab_dashboard.update_status("idle")
                )
                self.tab_dashboard.append_log_entry(
                    user_spoken=text,
                    intent_id="LIVE_DYNAMIC_SYNTHESIS",
                    action=action_desc,
                    audio_file=os.path.basename(live_wav),
                    latency_ms=latency
                )
        threading.Thread(target=_worker, daemon=True).start()

    # --- MAIN COMMAND ROUTER ---

    def process_spoken_arabic_command(self, spoken_text: str):
        if not spoken_text:
            return

        night_force = self.tab_settings.settings_data.get("night_mode", False)
        intent, variation, parse_latency, confidence = self.intent_parser.parse(
            spoken_text, night_mode_force=night_force
        )

        # 1. Check for Dynamic Value Intents (Battery / System Resources)
        if intent and intent.get("intent_id") == "BATTERY_STATUS":
            self._handle_battery_request()
            return
        elif intent and intent.get("intent_id") == "SYSTEM_RESOURCES":
            stats = self.laptop.get_system_stats()
            text = f"استهلاك المعالج دلوقتي {stats['cpu_percent']} في المية، واستهلاك الرامات {stats['ram_percent']} في المية يا فندم."
            self._synthesize_and_play_live(text, action_desc=f"CPU: {stats['cpu_percent']}%, RAM: {stats['ram_percent']}%")
            return

        # 2. Check for Static Fast Match (<1ms)
        if intent and confidence >= 85.0:
            action_type = intent.get("action_type")
            payload = intent.get("action_payload", {})
            intent_id = intent.get("intent_id", "")
            audio_file = variation.get("audio_file", "")
            action_desc = f"{action_type}: {payload}"

            if action_type == "esp32":
                ep = payload.get("endpoint", "")
                params = payload.get("params", {})
                if ep == "/led":
                    self.esp32.set_led(params.get("state", "toggle"))
                elif ep == "/relay":
                    self.esp32.set_relay(params.get("ch", 1), params.get("state", "toggle"))
                elif ep == "/all_lights":
                    self.esp32.set_all_lights(params.get("state", "off"))
                elif ep == "/ac":
                    self.esp32.set_ac(temp=params.get("temp", 22), mode=params.get("mode", "cool"), power=params.get("power", "on"))
                elif ep == "/window":
                    self.esp32.set_window(params.get("pos", 0))

            elif action_type == "laptop":
                act = payload.get("action", "")
                if act == "volume_up":
                    self.laptop.volume_up(payload.get("step", 15))
                elif act == "volume_down":
                    self.laptop.volume_down(payload.get("step", 15))
                elif act == "mute":
                    self.laptop.toggle_mute()
                elif act == "lock_screen":
                    self.laptop.lock_workstation()
                elif act == "play_pause":
                    self.laptop.media_play_pause()
                elif act == "launch_app":
                    self.laptop.launch_app(payload.get("app", ""))

            if audio_file:
                self.audio_player.play_wav(
                    audio_file,
                    on_start=lambda: self.tab_dashboard.update_status("speaking"),
                    on_finish=lambda: self.tab_dashboard.update_status("idle")
                )

            self.tab_dashboard.append_log_entry(
                user_spoken=spoken_text,
                intent_id=f"{intent_id} ({int(confidence)}%)",
                action=action_desc,
                audio_file=audio_file,
                latency_ms=parse_latency
            )
            return

        # 3. Route to Groq / OpenRouter LLM Brain for General Questions or Complex Multi-Step Commands
        def _llm_worker():
            self.tab_dashboard.update_status("processing")
            reply_text, executed_actions, provider, llm_latency = self.llm.process_user_query(spoken_text)

            live_wav = self.fish_client.synthesize_live(reply_text)
            if live_wav and os.path.exists(live_wav):
                self.audio_player.play_wav(
                    live_wav,
                    on_start=lambda: self.tab_dashboard.update_status("speaking"),
                    on_finish=lambda: self.tab_dashboard.update_status("idle")
                )

            act_str = ", ".join(executed_actions) if executed_actions else "Conversation Reply"
            self.tab_dashboard.append_log_entry(
                user_spoken=spoken_text,
                intent_id=f"LLM: {provider}",
                action=act_str,
                audio_file=os.path.basename(live_wav) if live_wav else "Live Synthesis",
                latency_ms=llm_latency
            )

        threading.Thread(target=_llm_worker, daemon=True).start()
