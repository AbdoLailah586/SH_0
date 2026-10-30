"""
Tab 4: Settings & STT/LLM Engine.
Provides configuration for:
  - Groq LPU & OpenRouter AI Brain API Keys with live "Test Key" buttons
  - Speech-to-Text Engine Selection (Groq Whisper Large V3 Turbo, faster-whisper CPU int8, Google ar-EG)
  - Intent parser fuzzy threshold & Night Whisper Mode rules
  - Audio Ducking percentage level
  - Fish Speech API endpoint & Windows System Tray settings
"""

import json
import os
import requests
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QCheckBox, QGroupBox, QLineEdit,
    QGridLayout, QMessageBox
)

from core.paths import resolve_path


class SettingsTab(QWidget):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_file = resolve_path("config/app_settings.json")
        self.settings_data = self.load_settings()
        self.init_ui()

    def load_settings(self) -> dict:
        defaults = {
            "stt_engine": "groq_whisper",
            "whisper_model": "base",
            "groq_api_key": "",
            "openrouter_api_key": "",
            "hf_token": "",
            "fuzzy_threshold": 75,
            "night_mode": False,
            "auto_night_schedule": True,
            "ducking_enabled": True,
            "ducking_level": 0.25,
            "fish_speech_url": "http://127.0.0.1:8080/v1/tts",
            "minimize_to_tray_on_close": True
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- 1. AI LLM BRAIN & API KEYS ---
        llm_group = QGroupBox("عقل الذكاء الاصطناعي ومفاتيح الـ API (Groq LPU + OpenRouter)")
        llm_layout = QGridLayout(llm_group)
        llm_layout.setSpacing(10)

        # Groq API Key
        llm_layout.addWidget(QLabel("Groq API Key (LPU سريع <250ms):"), 0, 0)
        self.input_groq_key = QLineEdit(self.settings_data.get("groq_api_key", ""))
        self.input_groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_groq_key.setPlaceholderText("gsk_...")
        llm_layout.addWidget(self.input_groq_key, 0, 1)

        self.btn_test_groq = QPushButton("فحص مفتاح Groq ⚡")
        self.btn_test_groq.clicked.connect(self._test_groq_key)
        llm_layout.addWidget(self.btn_test_groq, 0, 2)

        # OpenRouter API Key
        llm_layout.addWidget(QLabel("OpenRouter Key (بديل مجاني للطوارئ):"), 1, 0)
        self.input_openrouter_key = QLineEdit(self.settings_data.get("openrouter_api_key", ""))
        self.input_openrouter_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_openrouter_key.setPlaceholderText("sk-or-v1-...")
        llm_layout.addWidget(self.input_openrouter_key, 1, 1)

        self.btn_test_or = QPushButton("فحص OpenRouter ⚡")
        self.btn_test_or.clicked.connect(self._test_openrouter_key)
        llm_layout.addWidget(self.btn_test_or, 1, 2)

        # Hugging Face Token (for Fish Speech gated models)
        llm_layout.addWidget(QLabel("Hugging Face Token (لتحميل موديل Fish Speech):"), 2, 0)
        self.input_hf_token = QLineEdit(self.settings_data.get("hf_token", ""))
        self.input_hf_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_hf_token.setPlaceholderText("hf_...")
        llm_layout.addWidget(self.input_hf_token, 2, 1)

        self.btn_test_hf = QPushButton("فحص HF Token ⚡")
        self.btn_test_hf.clicked.connect(self._test_hf_token)
        llm_layout.addWidget(self.btn_test_hf, 2, 2)

        main_layout.addWidget(llm_group)

        # --- 2. STT ENGINE SELECTION ---
        stt_group = QGroupBox("محرك تحويل الصوت لنص مصري (Speech-to-Text Engine)")
        stt_layout = QGridLayout(stt_group)
        stt_layout.setSpacing(10)

        stt_layout.addWidget(QLabel("محرك الـ STT الأساسي:"), 0, 0)
        self.combo_stt = QComboBox()
        self.combo_stt.addItem("Groq Whisper Large V3 Turbo (<200ms، 0% VRAM) ⚡ [موصى به]", "groq_whisper")
        self.combo_stt.addItem("Local Faster-Whisper على معالج i5-12450HX (أوفلاين بدون كارت شاشة)", "faster_whisper_cpu")
        self.combo_stt.addItem("Google Speech Recognition (ar-EG) - سريع وخفيف", "google_ar")
        
        idx = self.combo_stt.findData(self.settings_data.get("stt_engine", "groq_whisper"))
        if idx >= 0:
            self.combo_stt.setCurrentIndex(idx)
        stt_layout.addWidget(self.combo_stt, 0, 1, 1, 2)

        main_layout.addWidget(stt_group)

        # --- 3. INTENT PARSER & NIGHT WHISPER MODE ---
        intent_group = QGroupBox("محرك فهم الأوامر المباشرة والوضع الليلي (Intent Engine)")
        intent_layout = QGridLayout(intent_group)
        intent_layout.setSpacing(10)

        intent_layout.addWidget(QLabel("حساسية مطابقة الكلام (Fuzzy Threshold):"), 0, 0)
        slider_layout = QHBoxLayout()
        self.slider_fuzzy = QSlider(Qt.Orientation.Horizontal)
        self.slider_fuzzy.setRange(50, 95)
        self.slider_fuzzy.setValue(int(self.settings_data.get("fuzzy_threshold", 75)))

        self.lbl_fuzzy_val = QLabel(f"{self.slider_fuzzy.value()}%")
        self.lbl_fuzzy_val.setStyleSheet("font-weight: bold; color: #58a6ff; min-width: 40px;")
        self.slider_fuzzy.valueChanged.connect(lambda v: self.lbl_fuzzy_val.setText(f"{v}%"))

        slider_layout.addWidget(self.slider_fuzzy)
        slider_layout.addWidget(self.lbl_fuzzy_val)
        intent_layout.addLayout(slider_layout, 0, 1, 1, 2)

        self.chk_auto_night = QCheckBox("تفعيل وضع الهمس الليلي تلقائياً بعد 12:00 منتصف الليل (Auto Night Whisper)")
        self.chk_auto_night.setChecked(self.settings_data.get("auto_night_schedule", True))
        intent_layout.addWidget(self.chk_auto_night, 1, 0, 1, 3)

        self.chk_force_night = QCheckBox("تثبيت وضع الهمس الليلي الآن يدوياً (Force Night Mode)")
        self.chk_force_night.setChecked(self.settings_data.get("night_mode", False))
        intent_layout.addWidget(self.chk_force_night, 2, 0, 1, 3)

        main_layout.addWidget(intent_group)

        # --- 4. AUDIO DUCKING & SPEAKERS ---
        audio_group = QGroupBox("توطئة صوت اللابتوب التلقائية أثناء الكلام (Audio Ducking)")
        audio_layout = QGridLayout(audio_group)
        audio_layout.setSpacing(10)

        self.chk_ducking = QCheckBox("تفعيل الـ Audio Ducking (خفض صوت الميديا أثناء تحدث المساعد)")
        self.chk_ducking.setChecked(self.settings_data.get("ducking_enabled", True))
        audio_layout.addWidget(self.chk_ducking, 0, 0, 1, 3)

        audio_layout.addWidget(QLabel("نسبة الصوت أثناء الخفض:"), 1, 0)
        duck_slider_layout = QHBoxLayout()
        self.slider_duck = QSlider(Qt.Orientation.Horizontal)
        self.slider_duck.setRange(5, 50)
        duck_val = int(self.settings_data.get("ducking_level", 0.25) * 100)
        self.slider_duck.setValue(duck_val)

        self.lbl_duck_val = QLabel(f"{duck_val}%")
        self.lbl_duck_val.setStyleSheet("font-weight: bold; color: #58a6ff; min-width: 40px;")
        self.slider_duck.valueChanged.connect(lambda v: self.lbl_duck_val.setText(f"{v}%"))

        duck_slider_layout.addWidget(self.slider_duck)
        duck_slider_layout.addWidget(self.lbl_duck_val)
        audio_layout.addLayout(duck_slider_layout, 1, 1, 1, 2)

        main_layout.addWidget(audio_group)

        # --- 5. SYSTEM & TRAY ---
        sys_group = QGroupBox("التشغيل بالخلفية وإغلاق النافذة")
        sys_layout = QHBoxLayout(sys_group)
        self.chk_tray = QCheckBox("التصغير إلى جوار الساعة في شريط المهام (System Tray) عند إغلاق النافذة")
        self.chk_tray.setChecked(self.settings_data.get("minimize_to_tray_on_close", True))
        sys_layout.addWidget(self.chk_tray)
        main_layout.addWidget(sys_group)

        # --- 6. SAVE BUTTON ---
        self.btn_save = QPushButton("💾 حفظ الإعدادات وتطبيقها فوراً (Save Settings)")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setFixedHeight(40)
        self.btn_save.clicked.connect(self.save_settings)
        main_layout.addWidget(self.btn_save)

        main_layout.addStretch()

    def _test_groq_key(self):
        key = self.input_groq_key.text().strip()
        if not key:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة مفتاح Groq API أولاً.")
            return

        url = "https://api.groq.com/openai/v1/models"
        headers = {"Authorization": f"Bearer {key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=3.5)
            if resp.status_code == 200:
                QMessageBox.information(self, "نجاح ⚡", "تم التحقق من مفتاح Groq API بنجاح! جاهز للاستخدام الفوري.")
            else:
                QMessageBox.critical(self, "خطأ", f"فشل التحقق من مفتاح Groq (كود: {resp.status_code})")
        except Exception as e:
            QMessageBox.critical(self, "خطأ اتصال", f"تعذر الاتصال بـ Groq: {e}")

    def _test_openrouter_key(self):
        key = self.input_openrouter_key.text().strip()
        url = "https://openrouter.ai/api/v1/models"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            resp = requests.get(url, headers=headers, timeout=4.0)
            if resp.status_code == 200:
                QMessageBox.information(self, "نجاح ⚡", "سيرفر OpenRouter يعمل وجاهز كبديل مجاني للطوارئ!")
            else:
                QMessageBox.warning(self, "تنبيه", f"استجابة OpenRouter: {resp.status_code}")
        except Exception as e:
            QMessageBox.critical(self, "خطأ اتصال", f"تعذر الاتصال بـ OpenRouter: {e}")

    def _test_hf_token(self):
        token = self.input_hf_token.text().strip()
        if not token:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال رمز Hugging Face Token (يبدأ بـ hf_).")
            return
        url = "https://huggingface.co/api/whoami-v2"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=4.0)
            if resp.status_code == 200:
                user = resp.json().get("name", "User")
                QMessageBox.information(self, "نجاح ⚡", f"تم التحقق من حساب Hugging Face بنجاح! مرحباً {user}.")
            else:
                QMessageBox.critical(self, "خطأ", f"رمز HF غير صالح (كود {resp.status_code}).")
        except Exception as e:
            QMessageBox.critical(self, "خطأ اتصال", f"تعذر الاتصال بـ Hugging Face: {e}")

    def save_settings(self):
        updated = {
            "stt_engine": self.combo_stt.currentData(),
            "groq_api_key": self.input_groq_key.text().strip(),
            "openrouter_api_key": self.input_openrouter_key.text().strip(),
            "hf_token": self.input_hf_token.text().strip(),
            "fuzzy_threshold": self.slider_fuzzy.value(),
            "night_mode": self.chk_force_night.isChecked(),
            "auto_night_schedule": self.chk_auto_night.isChecked(),
            "ducking_enabled": self.chk_ducking.isChecked(),
            "ducking_level": self.slider_duck.value() / 100.0,
            "minimize_to_tray_on_close": self.chk_tray.isChecked()
        }
        self.settings_data.update(updated)

        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings_data, f, ensure_ascii=False, indent=2)
            self.settings_saved.emit(self.settings_data)
            QMessageBox.information(self, "نجاح", "تم حفظ وتفعيل الإعدادات بنجاح!")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ الإعدادات: {e}")
