"""
Tab 1: Live Voice & Control Dashboard.
Provides:
  - Real-time audio VU level meter
  - Microphone device dropdown (Laptop mic, AirPods, LAN stream)
  - Push-To-Talk button + Continuous Listening (VAD) toggle
  - Live execution log showing Arabic input -> Intent -> Action -> Audio Cache -> Latency
  - Quick-test hardware toggles for ESP32 and Laptop OS controls
"""

import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView, QLineEdit, QCheckBox
)


class DashboardTab(QWidget):
    # Signals for thread-safe cross-component communication
    request_ptt = pyqtSignal()
    request_toggle_continuous = pyqtSignal(bool)
    request_manual_command = pyqtSignal(str)
    request_esp32_led = pyqtSignal()
    request_esp32_relay = pyqtSignal(int) # channel 1-4
    request_laptop_volume_up = pyqtSignal()
    request_laptop_volume_down = pyqtSignal()
    request_laptop_mute = pyqtSignal()
    request_laptop_lock = pyqtSignal()
    request_laptop_battery = pyqtSignal()
    mic_device_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- 1. AUDIO INPUT & STATUS BAR ---
        top_group = QGroupBox("مستوى الصوت والميكروفون (Audio Input & Level)")
        top_layout = QHBoxLayout(top_group)

        # Mic Selector
        mic_label = QLabel("الميكروفون:")
        mic_label.setStyleSheet("font-weight: bold; color: #58a6ff;")
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(220)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_combo_changed)

        # Status Badge
        self.status_badge = QLabel("جاهز (IDLE)")
        self.status_badge.setObjectName("statusBadgeIdle")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setFixedWidth(130)

        # Audio VU Level Meter
        vu_label = QLabel("مستوى الصوت:")
        vu_label.setStyleSheet("color: #8b949e;")
        self.vu_meter = QProgressBar()
        self.vu_meter.setRange(0, 100)
        self.vu_meter.setValue(0)
        self.vu_meter.setTextVisible(False)
        self.vu_meter.setFixedHeight(16)

        top_layout.addWidget(mic_label)
        top_layout.addWidget(self.mic_combo)
        top_layout.addSpacing(15)
        top_layout.addWidget(vu_label)
        top_layout.addWidget(self.vu_meter)
        top_layout.addSpacing(15)
        top_layout.addWidget(self.status_badge)

        main_layout.addWidget(top_group)

        # --- 2. VOICE CONTROLS & MANUAL COMMAND ---
        voice_group = QGroupBox("التحكم الصوتي المباشر (Voice Trigger Hub)")
        voice_layout = QVBoxLayout(voice_group)

        btn_row = QHBoxLayout()

        # Big Glowing PTT Button
        self.btn_ptt = QPushButton("🎙️ اضغط للتحدث (Push-to-Talk)\n[اختصار لوحة المفاتيح: Ctrl+Space]")
        self.btn_ptt.setObjectName("pttBtn")
        self.btn_ptt.clicked.connect(lambda: self.request_ptt.emit())
        btn_row.addWidget(self.btn_ptt, stretch=2)

        # Continuous VAD Toggle
        ctrl_col = QVBoxLayout()
        self.chk_continuous = QCheckBox("استماع مستمر تلقائي (Continuous VAD)")
        self.chk_continuous.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6edf3;")
        self.chk_continuous.toggled.connect(lambda checked: self.request_toggle_continuous.emit(checked))

        self.lbl_vad_info = QLabel("يكتشف الكلام المصري تلقائياً عند التحدث\nدون الحاجة للضغط على أي زر.")
        self.lbl_vad_info.setStyleSheet("color: #8b949e; font-size: 11px;")

        ctrl_col.addWidget(self.chk_continuous)
        ctrl_col.addWidget(self.lbl_vad_info)
        btn_row.addLayout(ctrl_col, stretch=1)

        voice_layout.addLayout(btn_row)

        # Manual Arabic Command Input (for quick testing without microphone)
        manual_row = QHBoxLayout()
        self.input_manual = QLineEdit()
        self.input_manual.setPlaceholderText("أو اكتب أمراً مصرياً للتجربة السريعة (مثال: 'افتح النور'، 'وطي الصوت'، 'بطارية اللابتوب كام')...")
        self.input_manual.returnPressed.connect(self._on_manual_submit)

        self.btn_send_manual = QPushButton("إرسال الأمر ⚡")
        self.btn_send_manual.setObjectName("primaryBtn")
        self.btn_send_manual.setFixedWidth(130)
        self.btn_send_manual.clicked.connect(self._on_manual_submit)

        manual_row.addWidget(self.input_manual)
        manual_row.addWidget(self.btn_send_manual)
        voice_layout.addLayout(manual_row)

        main_layout.addWidget(voice_group)

        # --- 3. LIVE TRANSCRIPT & EXECUTION LOG TABLE ---
        table_group = QGroupBox("سجل الأوامر والاستجابة بالمللي ثانية (Live Transcript & Execution Log)")
        table_layout = QVBoxLayout(table_group)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels([
            "الوقت", "الجملة المنطوقة (User Arabic)", "النية المكتشفة (Intent)",
            "الإجراء المنفذ (Action)", "الملف الصوتي المشغل (.wav)", "السرعة (Latency)"
        ])
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.log_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        table_layout.addWidget(self.log_table)
        main_layout.addWidget(table_group, stretch=2)

        # --- 4. QUICK HARDWARE & LAPTOP MANUAL OVERRIDES ---
        hw_group = QGroupBox("التحكم اليدوي السريع للهاردوير واللابتوب (Quick Overrides)")
        hw_layout = QHBoxLayout(hw_group)

        self.btn_led = QPushButton("🔵 ليد البوردة (GPIO 2)")
        self.btn_led.clicked.connect(lambda: self.request_esp32_led.emit())

        self.btn_relay1 = QPushButton("💡 ريلاي 1: نور الريسبشن")
        self.btn_relay1.clicked.connect(lambda: self.request_esp32_relay.emit(1))

        self.btn_relay2 = QPushButton("🛏️ ريلاي 2: نور الأوضة")
        self.btn_relay2.clicked.connect(lambda: self.request_esp32_relay.emit(2))

        self.btn_relay3 = QPushButton("🌀 ريلاي 3: المروحة")
        self.btn_relay3.clicked.connect(lambda: self.request_esp32_relay.emit(3))

        self.btn_vol_down = QPushButton("🔉 وطي الصوت")
        self.btn_vol_down.clicked.connect(lambda: self.request_laptop_volume_down.emit())

        self.btn_vol_up = QPushButton("🔊 علي الصوت")
        self.btn_vol_up.clicked.connect(lambda: self.request_laptop_volume_up.emit())

        self.btn_lock = QPushButton("🔒 قفل اللابتوب")
        self.btn_lock.clicked.connect(lambda: self.request_laptop_lock.emit())

        hw_layout.addWidget(self.btn_led)
        hw_layout.addWidget(self.btn_relay1)
        hw_layout.addWidget(self.btn_relay2)
        hw_layout.addWidget(self.btn_relay3)
        hw_layout.addWidget(self.btn_vol_down)
        hw_layout.addWidget(self.btn_vol_up)
        hw_layout.addWidget(self.btn_lock)

        main_layout.addWidget(hw_group)

    # --- SLOTS & HELPER METHODS ---

    def populate_mic_devices(self, devices):
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        for dev in devices:
            self.mic_combo.addItem(f"{dev['name']}", dev['index'])
        self.mic_combo.blockSignals(False)

    def _on_mic_combo_changed(self, index):
        dev_idx = self.mic_combo.currentData()
        self.mic_device_changed.emit(dev_idx if dev_idx is not None else 0)

    def _on_manual_submit(self):
        text = self.input_manual.text().strip()
        if text:
            self.request_manual_command.emit(text)
            self.input_manual.clear()

    def update_vu_level(self, level: int):
        self.vu_meter.setValue(level)

    def update_status(self, status: str):
        """status: 'idle', 'listening', 'processing', 'speaking'"""
        if status == "listening":
            self.status_badge.setText("سامعك.. اتكلم 🎙️")
            self.status_badge.setObjectName("statusBadgeActive")
            self.btn_ptt.setProperty("active", True)
        elif status == "processing":
            self.status_badge.setText("جاري الفهم ⚡")
            self.status_badge.setObjectName("statusBadgeActive")
            self.btn_ptt.setProperty("active", True)
        elif status == "speaking":
            self.status_badge.setText("بيتكلم 🔊")
            self.status_badge.setObjectName("statusBadge")
            self.btn_ptt.setProperty("active", False)
        else:
            self.status_badge.setText("جاهز (IDLE)")
            self.status_badge.setObjectName("statusBadgeIdle")
            self.btn_ptt.setProperty("active", False)

        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.btn_ptt.style().unpolish(self.btn_ptt)
        self.btn_ptt.style().polish(self.btn_ptt)

    def append_log_entry(
        self,
        user_spoken: str,
        intent_id: str,
        action: str,
        audio_file: str,
        latency_ms: float
    ):
        """Appends a row to the execution log."""
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        self.log_table.setItem(row, 0, QTableWidgetItem(now_str))
        self.log_table.setItem(row, 1, QTableWidgetItem(user_spoken))
        self.log_table.setItem(row, 2, QTableWidgetItem(intent_id))
        self.log_table.setItem(row, 3, QTableWidgetItem(action))
        self.log_table.setItem(row, 4, QTableWidgetItem(audio_file))
        self.log_table.setItem(row, 5, QTableWidgetItem(f"{int(latency_ms)} ms"))

        # Scroll to bottom
        self.log_table.scrollToBottom()

