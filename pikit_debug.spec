# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PiKit DEBUG build.

- console=True     → opens a terminal window so all output/tracebacks are visible
- uac_admin=False  → no UAC prompt so it can be launched directly from cmd
- name='PiKit_Debug'

Build with:  pyinstaller pikit_debug.spec
Run with:    dist\PiKit_Debug\PiKit_Debug.exe --debug
"""

import os

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/pishrink.sh', 'assets'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'win32api',
        'win32file',
        'win32con',
        'winerror',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy'],
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
    name='PiKit_Debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # ← console window — all output visible
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,       # ← no UAC prompt for easy debugging
    icon='assets/pikit.ico' if os.path.exists('assets/pikit.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PiKit_Debug',
)
