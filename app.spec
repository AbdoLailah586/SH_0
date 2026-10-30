# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('audio_cache', 'audio_cache'),
        ('config', 'config'),
        ('esp32_firmware', 'esp32_firmware'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'pycaw',
        'comtypes',
        'pygame',
        'sounddevice',
        'rapidfuzz',
        'websockets',
        'pynput',
        'pynput.keyboard',
        'requests',
        'psutil',
        'serial',
        'speech_recognition',
        'edge_tts',
        'cryptography',
        'groq',
        'openai',
        'faster_whisper',
        'core.paths',
        'core.llm_brain',
        'core.fish_speech_client',
        'core.lan_receiver',
        'core.intent_parser',
        'core.laptop_controller',
        'core.esp32_controller',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SmartHomeVoiceHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartHomeVoiceHub',
)
