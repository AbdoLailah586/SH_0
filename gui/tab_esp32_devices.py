"""
Tab 3: ESP32 Smart Home Hardware & Network Devices Manager.
Provides:
  - ESP32 Wi-Fi (HTTP REST / mDNS) and Serial/Bluetooth connection management
  - Ping health check & latency meter in ms
  - Real-time relay channel status indicators and manual toggle buttons
  - Mobile Mic LAN Bridge server status, local Wi-Fi IP, and connection info
"""

import threading
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QGroupBox, QGridLayout, QMessageBox,
    QApplication
)

from core.esp32_controller import ESP32Controller
from core.lan_receiver import get_local_lan_ip


class ESP32DevicesTab(QWidget):
    request_toggle_led = pyqtSignal()
    request_toggle_relay = pyqtSignal(int) # ch 1-4
    connection_status_updated = pyqtSignal(bool, int)

    def __init__(self, esp32_controller: ESP32Controller, parent=None):
        super().__init__(parent)
        self.esp = esp32_controller
        self.init_ui()

        # Ping timer
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self._auto_ping)
        self.ping_timer.start(4000)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- 1. ESP32 CONNECTION SETTINGS ---
        conn_group = QGroupBox("إعدادات الاتصال ببوردة ESP32 (Connection Settings)")
        conn_layout = QGridLayout(conn_group)
        conn_layout.setSpacing(12)

        # Mode selector
        conn_layout.addWidget(QLabel("نوع الاتصال:"), 0, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("شبكة الواي فاي المنزلية (Wi-Fi REST / mDNS)", "wifi")
        self.combo_mode.addItem("منفذ السيريال / بلوتوث (Serial / Bluetooth COM)", "serial")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        conn_layout.addWidget(self.combo_mode, 0, 1, 1, 2)

        # Wi-Fi IP / mDNS
        conn_layout.addWidget(QLabel("عنوان IP أو mDNS:"), 1, 0)
        self.input_ip = QLineEdit(self.esp.base_url)
        self.input_ip.setPlaceholderText("http://esp32-smarthome.local أو http://192.168.1.50")
        conn_layout.addWidget(self.input_ip, 1, 1)

        self.btn_save_ip = QPushButton("حفظ والاتصال")
        self.btn_save_ip.clicked.connect(self._on_save_ip)
        conn_layout.addWidget(self.btn_save_ip, 1, 2)

        # Serial COM Port
        conn_layout.addWidget(QLabel("منفذ السيريال (COM Port):"), 2, 0)
        self.combo_com = QComboBox()
        self.combo_com.setEnabled(False)
        self._refresh_serial_ports()
        conn_layout.addWidget(self.combo_com, 2, 1)

        btn_row_com = QHBoxLayout()
        self.btn_refresh_com = QPushButton("تحديث المنافذ")
        self.btn_refresh_com.clicked.connect(self._refresh_serial_ports)
        self.btn_connect_com = QPushButton("اتصال سيريال")
        self.btn_connect_com.clicked.connect(self._on_connect_serial)
        btn_row_com.addWidget(self.btn_refresh_com)
        btn_row_com.addWidget(self.btn_connect_com)
        conn_layout.addLayout(btn_row_com, 2, 2)

        # Ping & Health Indicator
        conn_layout.addWidget(QLabel("حالة الاتصال والسرعة:"), 3, 0)
        self.lbl_ping = QLabel("جاري الفحص... ⚪")
        self.lbl_ping.setStyleSheet("font-weight: bold; font-size: 14px; color: #8b949e;")
        conn_layout.addWidget(self.lbl_ping, 3, 1)

        self.btn_manual_ping = QPushButton("فحص الاتصال الآن (Ping ⚡)")
        self.btn_manual_ping.clicked.connect(self._auto_ping)
        conn_layout.addWidget(self.btn_manual_ping, 3, 2)

        main_layout.addWidget(conn_group)

        # --- 2. HARDWARE CHANNELS & ONBOARD LED ---
        hw_group = QGroupBox("حالة أطراف ومخارج البوردة (ESP32 GPIO Channels)")
        hw_layout = QGridLayout(hw_group)
        hw_layout.setSpacing(14)

        # GPIO 2 Onboard LED (Zero Hardware Required)
        hw_layout.addWidget(QLabel("لمبة الاختبار على البوردة (GPIO 2 - Built-in LED):"), 0, 0)
        self.lbl_led_state = QLabel("مطفية (OFF) ⚪")
        self.lbl_led_state.setStyleSheet("font-weight: bold; color: #8b949e;")
        self.btn_toggle_led = QPushButton("تبديل حالة الليد (Toggle)")
        self.btn_toggle_led.clicked.connect(lambda: self.request_toggle_led.emit())
        hw_layout.addWidget(self.lbl_led_state, 0, 1)
        hw_layout.addWidget(self.btn_toggle_led, 0, 2)

        # Relay 1 (GPIO 26 - Reception Light)
        hw_layout.addWidget(QLabel("ريلاي 1 - نور الريسبشن (GPIO 26):"), 1, 0)
        self.lbl_relay1_state = QLabel("مغلق (OFF) ⚪")
        self.lbl_relay1_state.setStyleSheet("font-weight: bold; color: #8b949e;")
        self.btn_toggle_r1 = QPushButton("تبديل ريلاي 1")
        self.btn_toggle_r1.clicked.connect(lambda: self.request_toggle_relay.emit(1))
        hw_layout.addWidget(self.lbl_relay1_state, 1, 1)
        hw_layout.addWidget(self.btn_toggle_r1, 1, 2)

        # Relay 2 (GPIO 27 - Bedroom Light)
        hw_layout.addWidget(QLabel("ريلاي 2 - نور غرفة النوم (GPIO 27):"), 2, 0)
        self.lbl_relay2_state = QLabel("مغلق (OFF) ⚪")
        self.lbl_relay2_state.setStyleSheet("font-weight: bold; color: #8b949e;")
        self.btn_toggle_r2 = QPushButton("تبديل ريلاي 2")
        self.btn_toggle_r2.clicked.connect(lambda: self.request_toggle_relay.emit(2))
        hw_layout.addWidget(self.lbl_relay2_state, 2, 1)
        hw_layout.addWidget(self.btn_toggle_r2, 2, 2)

        # Relay 3 (GPIO 14 - Fan / Appliance)
        hw_layout.addWidget(QLabel("ريلاي 3 - المروحة / الأجهزة (GPIO 14):"), 3, 0)
        self.lbl_relay3_state = QLabel("مغلق (OFF) ⚪")
        self.lbl_relay3_state.setStyleSheet("font-weight: bold; color: #8b949e;")
        self.btn_toggle_r3 = QPushButton("تبديل ريلاي 3")
        self.btn_toggle_r3.clicked.connect(lambda: self.request_toggle_relay.emit(3))
        hw_layout.addWidget(self.lbl_relay3_state, 3, 1)
        hw_layout.addWidget(self.btn_toggle_r3, 3, 2)

        # Relay 4 (GPIO 12 - Aux)
        hw_layout.addWidget(QLabel("ريلاي 4 - المخرج الاحتياطي (GPIO 12):"), 4, 0)
        self.lbl_relay4_state = QLabel("مغلق (OFF) ⚪")
        self.lbl_relay4_state.setStyleSheet("font-weight: bold; color: #8b949e;")
        self.btn_toggle_r4 = QPushButton("تبديل ريلاي 4")
        self.btn_toggle_r4.clicked.connect(lambda: self.request_toggle_relay.emit(4))
        hw_layout.addWidget(self.lbl_relay4_state, 4, 1)
        hw_layout.addWidget(self.btn_toggle_r4, 4, 2)

        main_layout.addWidget(hw_group)

        # --- 3. MOBILE MIC LAN SERVER PORTAL ---
        lan_group = QGroupBox("جسر مايك الموبايل اللاسلكي (Wi-Fi Mobile Mic LAN Bridge)")
        lan_layout = QVBoxLayout(lan_group)

        lan_ip = get_local_lan_ip()
        self.mobile_url = f"https://{lan_ip}:8766"

        info_lbl = QLabel(
            f"افتح الرابط الآمن التالي من متصفح أي موبايل (أو AirPods متصلة بالموبايل) على نفس شبكة الواي فاي:\n"
            f"🔒 الرابط المشفر (HTTPS): {self.mobile_url}"
        )
        info_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff; line-height: 1.5;")

        sub_info = QLabel("تم تفعيل تشفير HTTPS تلقائياً لفتح صلاحية مايك الموبايل وسماعات البلوتوث (AirPods) بدون حظر المتصفح.\n(عند الفتح لأول مرة، وافق على شهادة الأمان المحلية واضغط Proceed/Advanced).")
        sub_info.setStyleSheet("color: #8b949e; font-size: 12px;")

        btn_row_lan = QHBoxLayout()
        self.btn_copy_url = QPushButton("📋 نسخ الرابط للموبايل")
        self.btn_copy_url.clicked.connect(self._copy_url)

        self.lbl_clients_count = QLabel("الأجهزة المتصلة حالياً: 0 📱")
        self.lbl_clients_count.setStyleSheet("font-weight: bold; color: #238636;")

        btn_row_lan.addWidget(self.btn_copy_url)
        btn_row_lan.addSpacing(20)
        btn_row_lan.addWidget(self.lbl_clients_count)
        btn_row_lan.addStretch()

        lan_layout.addWidget(info_lbl)
        lan_layout.addWidget(sub_info)
        lan_layout.addLayout(btn_row_lan)

        main_layout.addWidget(lan_group)
        main_layout.addStretch()

    # --- SLOTS & UPDATES ---

    def _copy_url(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.mobile_url)
        QMessageBox.information(self, "تم النسخ", f"تم نسخ الرابط إلى الحافظة:\n{self.mobile_url}")

    def update_client_count(self, count: int):
        self.lbl_clients_count.setText(f"الأجهزة المتصلة حالياً: {count} 📱")

    def _on_mode_changed(self):
        mode = self.combo_mode.currentData()
        self.esp.mode = mode
        self.combo_com.setEnabled(mode == "serial")
        self.input_ip.setEnabled(mode == "wifi")

    def _refresh_serial_ports(self):
        self.combo_com.clear()
        ports = self.esp.list_serial_ports()
        if ports:
            self.combo_com.addItems(ports)
        else:
            self.combo_com.addItem("لا يوجد منافذ COM")

    def _on_connect_serial(self):
        port = self.combo_com.currentText()
        if port and "لا يوجد" not in port:
            success = self.esp.connect_serial(port)
            if success:
                QMessageBox.information(self, "نجاح", f"تم الاتصال بمنفذ السيريال: {port}")
            else:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالمنفذ: {port}")
        self._auto_ping()

    def _on_save_ip(self):
        url = self.input_manual_ip = self.input_ip.text().strip()
        self.esp.set_base_url(url)
        self._auto_ping()

    def _auto_ping(self):
        def _worker():
            success, latency = self.esp.ping()
            st = self.esp.get_status()
            return success, latency, st

        def _update(result):
            success, latency, st = result
            if success:
                self.lbl_ping.setText(f"متصل (Online) 🟢 - سرعة الاستجابة: {latency} ms")
                self.lbl_ping.setStyleSheet("font-weight: bold; font-size: 13px; color: #238636;")
            else:
                self.lbl_ping.setText("غير متصل (Disconnected) 🔴")
                self.lbl_ping.setStyleSheet("font-weight: bold; font-size: 13px; color: #da3633;")

            # Update LED & Relay states
            led = st.get("led", False)
            self.lbl_led_state.setText("مضيئة (ON) 🔵" if led else "مطفية (OFF) ⚪")
            self.lbl_led_state.setStyleSheet("font-weight: bold; color: #58a6ff;" if led else "font-weight: bold; color: #8b949e;")

            relays = st.get("relays", [False, False, False, False])
            self._update_relay_label(self.lbl_relay1_state, relays[0] if len(relays) > 0 else False)
            self._update_relay_label(self.lbl_relay2_state, relays[1] if len(relays) > 1 else False)
            self._update_relay_label(self.lbl_relay3_state, relays[2] if len(relays) > 2 else False)
            self._update_relay_label(self.lbl_relay4_state, relays[3] if len(relays) > 3 else False)

        threading.Thread(target=lambda: _update(_worker()), daemon=True).start()

    def _update_relay_label(self, label: QLabel, state: bool):
        label.setText("شغال (ON) 💡" if state else "مغلق (OFF) ⚪")
        label.setStyleSheet("font-weight: bold; color: #238636;" if state else "font-weight: bold; color: #8b949e;")

