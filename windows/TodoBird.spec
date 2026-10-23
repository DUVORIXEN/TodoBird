# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

try:
    spec_dir = Path(SPECPATH).resolve()
except NameError:
    spec_dir = Path.cwd() / 'windows'

root_dir = spec_dir.parent if spec_dir.name.lower() == 'windows' else spec_dir

datas = [
    (str(root_dir / 'todo_bird_app' / 'assets'), 'todo_bird_app/assets'),
    (str(root_dir / 'todo_bird_app' / 'themes'), 'todo_bird_app/themes'),
    (str(root_dir / 'todo_bird_app' / 'i18n'), 'todo_bird_app/i18n'),
    (str(root_dir / 'todo_bird_app' / 'voice'), 'todo_bird_app/voice'),
    (str(root_dir / 'todo-bird-icon.ico'), '.'),
]

hiddenimports = [
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'pyttsx3',
    'pyttsx3.drivers',
    'pyttsx3.drivers.sapi5',
    'sqlite3',
    'ctypes',
    'winreg',
]

a = Analysis(
    [str(root_dir / 'todo_bird_app' / 'app.py')],
    pathex=[str(root_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pytest'],
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
    name='TodoBird',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root_dir / 'todo-bird-icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TodoBird',
)

try:
    if sys.platform == 'win32':
        import importlib.util
        msix_script = root_dir / 'windows' / 'build_msix.py'
        if msix_script.exists():
            print(f"Triggering MSIX packaging via {msix_script}...")
            spec = importlib.util.spec_from_file_location("build_msix", str(msix_script))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.build_msix()
except Exception as e:
    print(f"Notice: MSIX post-build step returned: {e}")

