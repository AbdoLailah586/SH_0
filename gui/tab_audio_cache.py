"""
Tab 2: Pre-Generated Audio Cache & Fish Speech Studio (RTX 4050 GPU).
Provides:
  - Live RTX 4050 6GB VRAM & Fish Speech Server status monitor
  - Start/Restart Fish Speech GPU Server button
  - Record 15-second custom Egyptian Arabic voice reference seed
  - Regenerate All 70 Clips in pure Egyptian Arabic
  - Full table of intents, audio preview with ducking, and single-phrase generation
"""

import json
import os
import threading
import time
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QHeaderView,
    QLineEdit, QComboBox, QProgressBar, QMessageBox, QInputDialog
)

from core.fish_speech_client import FishSpeechClient
from core.paths import resolve_path

try:
    import sounddevice as sd
    import numpy as np
    import soundfile as sf
    SD_REC_AVAILABLE = True
except ImportError:
    SD_REC_AVAILABLE = False


class AudioCacheTab(QWidget):
    request_preview_audio = pyqtSignal(str)
    signal_gpu_status = pyqtSignal(dict, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manifest_path = resolve_path("config/voice_bank_manifest.json")
        self.fish_client = FishSpeechClient()
        self.manifest_data = {}
        self.table_items = []

        self.signal_gpu_status.connect(self._apply_gpu_status)
        self.init_ui()
        self.load_manifest()

        # Timer to periodically check GPU & Server status
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self._check_gpu_and_server_status)
        self.check_timer.start(4000)
        self._check_gpu_and_server_status()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- 1. GPU & FISH SPEECH CUDA STATUS BAR ---
        gpu_group = QGroupBox("حالة كارت الشاشة RTX 4050 6GB وسيرفر Fish Speech")
        gpu_layout = QHBoxLayout(gpu_group)

        self.lbl_vram = QLabel("ذاكرة الـ VRAM: فحص...")
        self.lbl_vram.setStyleSheet("font-size: 13px; font-weight: bold; color: #58a6ff;")

        self.lbl_fish_status = QLabel("سيرفر Fish Speech: فحص...")
        self.lbl_fish_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #e3b341;")

        self.btn_start_server = QPushButton("⚡ تشغيل سيرفر GPU")
        self.btn_start_server.clicked.connect(self._on_start_server_clicked)

        self.btn_record_ref = QPushButton("🎙️ تسجيل صوتك المرجعي (15s)")
        self.btn_record_ref.clicked.connect(self._on_record_ref_clicked)

        self.btn_batch_generate = QPushButton("🔄 إعادة توليد كل الـ 70 ملف بالمصري")
        self.btn_batch_generate.setObjectName("primaryBtn")
        self.btn_batch_generate.clicked.connect(self._on_batch_generate_clicked)

        gpu_layout.addWidget(self.lbl_vram)
        gpu_layout.addWidget(self.lbl_fish_status)
        gpu_layout.addWidget(self.btn_start_server)
        gpu_layout.addWidget(self.btn_record_ref)
        gpu_layout.addWidget(self.btn_batch_generate)

        main_layout.addWidget(gpu_group)

        # Progress Bar for batch operations
        self.batch_progress = QProgressBar()
        self.batch_progress.setVisible(False)
        self.batch_progress.setFixedHeight(18)
        main_layout.addWidget(self.batch_progress)

        # --- 2. FILTER & SEARCH BAR ---
        filter_row = QHBoxLayout()

        lbl_cat = QLabel("التصنيف:")
        self.combo_category = QComboBox()
        self.combo_category.addItem("الكل (All Categories)", "all")
        self.combo_category.addItem("الإضاءة (Lighting)", "lighting")
        self.combo_category.addItem("هاردوير ESP32", "esp32_hardware")
        self.combo_category.addItem("التكييف والستائر (AC & Climate)", "ac_climate")
        self.combo_category.addItem("التحكم في اللابتوب (Laptop OS)", "laptop_control")
        self.combo_category.addItem("التحيات (Greetings)", "greetings")
        self.combo_category.addItem("وضع الهمس الليلي (Night Whispers)", "whispers")
        self.combo_category.currentIndexChanged.connect(self.filter_table)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("بحث في الجمل المصرية أو الـ Intent ID...")
        self.input_search.textChanged.connect(self.filter_table)

        filter_row.addWidget(lbl_cat)
        filter_row.addWidget(self.combo_category)
        filter_row.addWidget(self.input_search)

        main_layout.addLayout(filter_row)

        # --- 3. CACHE TABLE ---
        self.cache_table = QTableWidget()
        self.cache_table.setColumnCount(7)
        self.cache_table.setHorizontalHeaderLabels([
            "التصنيف", "النية (Intent ID)", "المشاعر (Emotion)",
            "الرد الصوتي بالعامية المصرية", "مسار الملف (.wav)", "حالة الكاش", "معاينة الصوت"
        ])
        self.cache_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.cache_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.verticalHeader().setVisible(False)
        self.cache_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        main_layout.addWidget(self.cache_table, stretch=2)

        # --- 4. FISH SPEECH STUDIO: ADD & GENERATE NEW PHRASE ---
        studio_group = QGroupBox("استوديو Fish Speech: توليد وحفظ جملة جديدة بالعامية المصرية")
        studio_layout = QHBoxLayout(studio_group)

        self.input_new_intent = QLineEdit()
        self.input_new_intent.setPlaceholderText("Intent ID (e.g. LIGHT_ON)")
        self.input_new_intent.setFixedWidth(180)

        self.input_new_phrase = QLineEdit()
        self.input_new_phrase.setPlaceholderText("الجملة بالعامية المصرية (مثال: 'تمام نورتلك المكان يا باشا')...")

        self.combo_new_emotion = QComboBox()
        self.combo_new_emotion.addItems(["normal", "friendly", "whisper", "excited", "calm"])
        self.combo_new_emotion.setFixedWidth(100)

        self.combo_gender = QComboBox()
        self.combo_gender.addItem("رجل (Shakir)", "male")
        self.combo_gender.addItem("سيدة (Salma)", "female")
        self.combo_gender.setFixedWidth(110)

        self.btn_generate_single = QPushButton("توليد وإضافة للكاش 🎙️")
        self.btn_generate_single.clicked.connect(self._on_generate_single_clicked)

        studio_layout.addWidget(QLabel("Intent:"))
        studio_layout.addWidget(self.input_new_intent)
        studio_layout.addWidget(QLabel("النص:"))
        studio_layout.addWidget(self.input_new_phrase)
        studio_layout.addWidget(QLabel("المشاعر:"))
        studio_layout.addWidget(self.combo_new_emotion)
        studio_layout.addWidget(QLabel("الصوت:"))
        studio_layout.addWidget(self.combo_gender)
        studio_layout.addWidget(self.btn_generate_single)

        main_layout.addWidget(studio_group)

    def load_manifest(self):
        if not os.path.exists(self.manifest_path):
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self.manifest_data = json.load(f)
        except Exception:
            return

        self.table_items = []
        cached_count = 0
        total_count = 0

        for it in self.manifest_data.get("intents", []):
            cat = it.get("category", "")
            intent_id = it.get("intent_id", "")
            for var in it.get("variations", []):
                total_count += 1
                rel_path = var.get("audio_file", "")
                text_ar = var.get("text_ar", "")
                emotion = var.get("emotion", "normal")
                full_path = resolve_path(rel_path)
                exists = os.path.exists(full_path) and os.path.getsize(full_path) > 1000
                if exists:
                    cached_count += 1

                self.table_items.append({
                    "category": cat,
                    "intent_id": intent_id,
                    "emotion": emotion,
                    "text_ar": text_ar,
                    "rel_path": rel_path,
                    "exists": exists
                })

        self.filter_table()

    def filter_table(self):
        cat_filter = self.combo_category.currentData()
        search_query = self.input_search.text().strip().lower()

        filtered = []
        for item in self.table_items:
            if cat_filter != "all" and item["category"] != cat_filter:
                continue
            if search_query:
                in_intent = search_query in item["intent_id"].lower()
                in_text = search_query in item["text_ar"].lower()
                if not in_intent and not in_text:
                    continue
            filtered.append(item)

        self.cache_table.setRowCount(len(filtered))
        for row, item in enumerate(filtered):
            self.cache_table.setItem(row, 0, QTableWidgetItem(item["category"]))
            self.cache_table.setItem(row, 1, QTableWidgetItem(item["intent_id"]))
            self.cache_table.setItem(row, 2, QTableWidgetItem(f"[{item['emotion']}]"))
            self.cache_table.setItem(row, 3, QTableWidgetItem(item["text_ar"]))
            self.cache_table.setItem(row, 4, QTableWidgetItem(item["rel_path"]))

            status_item = QTableWidgetItem("مصري جاهز ✅" if item["exists"] else "غير موجود ❌")
            status_item.setForeground(Qt.GlobalColor.green if item["exists"] else Qt.GlobalColor.red)
            self.cache_table.setItem(row, 5, status_item)

            btn_play = QPushButton("▶ تشغيل")
            btn_play.setFixedWidth(75)
            rel_p = item["rel_path"]
            btn_play.clicked.connect(lambda checked, p=rel_p: self.request_preview_audio.emit(p))
            self.cache_table.setCellWidget(row, 6, btn_play)

    def _check_gpu_and_server_status(self):
        def _worker():
            vram = self.fish_client.server_manager.get_vram_usage()
            online = self.fish_client.is_server_online()
            self.signal_gpu_status.emit(vram, online)

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_gpu_status(self, vram: dict, online: bool):
        self.lbl_vram.setText(f"VRAM (RTX 4050): {vram.get('text', 'RTX 4050')}")
        if online:
            self.lbl_fish_status.setText("سيرفر Fish Speech: متصل بـ CUDA 🟢")
            self.lbl_fish_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #238636;")
        else:
            self.lbl_fish_status.setText("سيرفر Fish Speech: غير متصل (بديل Neural مصري جاهز) 🟡")
            self.lbl_fish_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #e3b341;")

    def _on_start_server_clicked(self):
        self.btn_start_server.setEnabled(False)
        self.btn_start_server.setText("جاري التشغيل...")

        def _worker():
            success = self.fish_client.server_manager.start_server()
            self.btn_start_server.setEnabled(True)
            self.btn_start_server.setText("⚡ تشغيل سيرفر GPU")
            if success:
                QMessageBox.information(self, "نجاح", "تم تشغيل سيرفر Fish Speech بنجاح على كارت RTX 4050!")
            else:
                QMessageBox.warning(self, "تنبيه", "تعذر تشغيل السيرفر تلقائياً. تأكد من تحميل الأوزان وتشغيل start_fish_server.bat")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_record_ref_clicked(self):
        """Records 15 seconds from the microphone to create custom Egyptian reference voice seed."""
        text, ok = QInputDialog.getText(self, "تسجيل صوتك المرجعي", "اكتب الجملة التي ستقرأها بصوتك (مثال: أهلاً بيك يا فندم أنا المساعد الذكي):")
        if not ok or not text.strip():
            return

        ref_dir = resolve_path("config/reference_voices")
        os.makedirs(ref_dir, exist_ok=True)
        custom_wav = os.path.join(ref_dir, "custom_user_ref.wav")
        custom_txt = os.path.join(ref_dir, "custom_user_ref.txt")

        QMessageBox.information(self, "بدء التسجيل", "اضغط OK ثم تحدث بصوت واضح لمدة 12 ثانية...")

        def _record():
            try:
                sample_rate = 44100
                duration = 12
                recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
                sd.wait()

                # Save as 16-bit WAV
                import wave
                with wave.open(custom_wav, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(recording.tobytes())

                with open(custom_txt, "w", encoding="utf-8") as f:
                    f.write(text.strip())

                QMessageBox.information(self, "تم الحفظ", f"تم تسجيل وحفظ صوتك المرجعي بنجاح!\nالمسار: {custom_wav}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التسجيل: {e}")

        threading.Thread(target=_record, daemon=True).start()

    def _on_generate_single_clicked(self):
        intent = self.input_new_intent.text().strip().upper()
        phrase = self.input_new_phrase.text().strip()
        emotion = self.combo_new_emotion.currentText()
        gender = self.combo_gender.currentData()

        if not intent or not phrase:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال اسم الـ Intent والجملة بالعامية المصرية.")
            return

        rel_path = f"audio_cache/custom/{intent.lower()}_1.wav"
        full_path = resolve_path(rel_path)

        success, method = self.fish_client.generate_clip(phrase, full_path, emotion=emotion, gender=gender)
        if success:
            QMessageBox.information(self, "نجاح", f"تم توليد المقطع الصوتي المصري وحفظه بنجاح!\nالمحرك: {method}\nالمسار: {rel_path}")
            self.input_new_intent.clear()
            self.input_new_phrase.clear()
            self.load_manifest()
        else:
            QMessageBox.critical(self, "خطأ", "تعذر توليد المقطع الصوتي.")

    def _on_batch_generate_clicked(self):
        self.btn_batch_generate.setEnabled(False)
        self.batch_progress.setVisible(True)
        self.batch_progress.setValue(0)

        def _worker():
            def progress(current, total, detail):
                pct = int(current / total * 100)
                self.batch_progress.setValue(pct)

            self.fish_client.batch_generate_manifest(self.manifest_path, on_progress=progress, overwrite=True)
            self.load_manifest()
            self.btn_batch_generate.setEnabled(True)
            self.batch_progress.setVisible(False)
            QMessageBox.information(self, "تم", "تم توليد جميع ملفات الكاش بالعامية المصرية بنجاح!")

        threading.Thread(target=_worker, daemon=True).start()
