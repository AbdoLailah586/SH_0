"""
Path Resolution Helper for Standalone Windows Executable & Source Code.
Handles PyInstaller frozen environments (sys._MEIPASS and sys.executable) seamlessly.
"""

import os
import sys

def get_app_dir() -> str:
    """Returns the root directory of the application."""
    if getattr(sys, 'frozen', False):
        # Running inside PyInstaller bundled .exe
        if hasattr(sys, '_MEIPASS') and os.path.exists(os.path.join(sys._MEIPASS, 'config')):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    # Running from Python source code
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_path(rel_path: str) -> str:
    """Resolves relative project paths to absolute paths."""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.normpath(os.path.join(get_app_dir(), rel_path))

