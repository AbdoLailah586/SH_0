"""
Modern Cyberpunk / Glassmorphic Dark QSS Stylesheet for PyQt6.
Features deep obsidian backgrounds, sleek cyan/blue accents, rounded edges,
clean typography, and custom styled controls.
"""

DARK_THEME_QSS = """
/* --- GLOBAL APPLICATION STYLE --- */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', -apple-system, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

QMainWindow {
    background-color: #0b0e14;
}

/* --- TAB WIDGET & BAR --- */
QTabWidget::pane {
    border: 1px solid #30363d;
    background-color: #161b22;
    border-radius: 8px;
    margin-top: -1px;
}

QTabBar::tab {
    background: #0d1117;
    color: #8b949e;
    border: 1px solid #30363d;
    border-bottom: none;
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 13px;
}

QTabBar::tab:selected {
    background: #161b22;
    color: #58a6ff;
    border: 1px solid #30363d;
    border-bottom: 2px solid #58a6ff;
}

QTabBar::tab:hover:!selected {
    background: #1c2128;
    color: #c9d1d9;
}

/* --- GROUP BOX & CARDS --- */
QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    margin-top: 24px;
    padding: 16px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 6px;
    padding: 0 6px;
    color: #58a6ff;
    font-size: 13px;
}

/* --- PUSH BUTTONS --- */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #1f6feb;
    border-color: #388bfd;
    color: #ffffff;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}

/* --- PRIMARY ACCENT BUTTONS --- */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #238636);
    color: #ffffff;
    border: none;
    font-size: 14px;
    border-radius: 8px;
}

QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #388bfd, stop:1 #2ea043);
}

QPushButton#primaryBtn:pressed {
    background: #1f6feb;
}

/* --- GLOWING PUSH TO TALK BUTTON --- */
QPushButton#pttBtn {
    background: qradialgradient(cx:0.5, cy:0.5, radius: 0.8, fx:0.5, fy:0.5, stop:0 #1f6feb, stop:1 #0f3d7a);
    color: #ffffff;
    font-size: 16px;
    font-weight: bold;
    border: 2px solid #58a6ff;
    border-radius: 40px;
    min-width: 200px;
    min-height: 70px;
}

QPushButton#pttBtn:hover {
    background: qradialgradient(cx:0.5, cy:0.5, radius: 0.8, fx:0.5, fy:0.5, stop:0 #388bfd, stop:1 #1f6feb);
    border-color: #79c0ff;
}

QPushButton#pttBtn:pressed, QPushButton#pttBtn[active="true"] {
    background: qradialgradient(cx:0.5, cy:0.5, radius: 0.8, fx:0.5, fy:0.5, stop:0 #da3633, stop:1 #8e1519);
    border: 2px solid #f85149;
    color: #ffffff;
}

/* --- HARDWARE QUICK TOGGLE BUTTONS --- */
QPushButton.hardwareBtn {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px;
    font-size: 13px;
    text-align: left;
}

QPushButton.hardwareBtn[state="active"] {
    background-color: #13233a;
    border: 1px solid #1f6feb;
    color: #58a6ff;
}

/* --- INPUTS & COMBOBOX --- */
QLineEdit, QSpinBox, QComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    padding: 6px 10px;
    min-height: 22px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #58a6ff;
    background-color: #0d1117;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #30363d;
}

QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

/* --- PROGRESS & VU METER --- */
QProgressBar {
    border: 1px solid #30363d;
    border-radius: 6px;
    background-color: #0d1117;
    text-align: center;
    color: #c9d1d9;
    font-weight: bold;
    min-height: 18px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #238636, stop:0.7 #e3b341, stop:1 #da3633);
    border-radius: 5px;
}

/* --- TABLES & HEADERS --- */
QTableWidget {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    gridline-color: #21262d;
    color: #e6edf3;
}

QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    padding: 6px 10px;
    border: 1px solid #21262d;
    font-weight: 600;
}

QTableWidget::item:selected {
    background-color: #1f6feb;
    color: #ffffff;
}

/* --- SCROLLBARS --- */
QScrollBar:vertical {
    border: none;
    background: #0d1117;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #30363d;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #8b949e;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* --- STATUS BADGES --- */
QLabel#statusBadge {
    background-color: #238636;
    color: #ffffff;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
}

QLabel#statusBadgeIdle {
    background-color: #30363d;
    color: #8b949e;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
}

QLabel#statusBadgeActive {
    background-color: #da3633;
    color: #ffffff;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
}
"""

