"""
AI-Powered Smart Home Voice Hub Desktop Application.
Main Native Windows Entry Point.
"""

import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# Ensure current working directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gui.main_window import MainWindow

def main():
    # Enable High-DPI scaling for sharp crystal-clear fonts on modern Windows screens
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    app.setApplicationName("AI Smart Home Voice Hub")
    app.setOrganizationName("SmartHomeAI")

    window = MainWindow()
    window.show()

    print("[SUCCESS] AI Smart Home Voice Hub Desktop Application Started!")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

