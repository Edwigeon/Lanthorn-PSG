# -*- mode: python ; coding: utf-8 -*-
# Lanthorn PSG v0.3.2 — PyInstaller Spec File
# Builds a standalone executable for Windows or Linux

import sys
import os

block_cipher = None

# ---- Collect DLLs for sounddevice and soundfile on Windows ----
# These packages include native DLLs (portaudio, libsndfile) that PyInstaller
# needs to pick up explicitly on Windows.
from PyInstaller.utils.hooks import collect_dynamic_libs
sd_bins  = collect_dynamic_libs('sounddevice')
sf_bins  = collect_dynamic_libs('soundfile')

# ---- Bundle ffmpeg binaries if present (required by pydub for MP3 export) ----
# build.bat downloads these into tools\ffmpeg\ automatically.
ffmpeg_datas = []
ffmpeg_dir = os.path.join(os.path.dirname(SPEC), 'tools', 'ffmpeg')
for binary_name in ('ffmpeg.exe', 'ffprobe.exe', 'ffmpeg', 'ffprobe'):
    bin_path = os.path.join(ffmpeg_dir, binary_name)
    if os.path.isfile(bin_path):
        ffmpeg_datas.append((bin_path, 'ffmpeg'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=sd_bins + sf_bins,
    datas=[
        ('presets', 'presets'),
        ('ENGINE_SPEC.md', '.'),
        ('lanthorn_icon.png', '.'),
        ('lanthorn_icon.ico', '.'),
        ('LICENSE', '.'),
        ('Bazaar.csv', '.'),
        ('Lanthorn.csv', '.'),
        ('Iron_Waltz.csv', '.'),
    ] + ffmpeg_datas,
    hiddenimports=[
        'numpy',
        'sounddevice',
        'soundfile',
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'pyqtgraph',
        'pydub',
        'engine',
        'engine.oscillator',
        'engine.modifiers',
        'engine.playback',
        'engine.theory',
        'engine.preset_manager',
        'engine.csv_handler',
        'gui',
        'gui.main_window',
        'gui.tracker',
        'gui.workbench',
        'gui.visualizer',
        'gui.context_menu',
        'gui.export_dialog',
        'export',
        'export.wave_baker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['psg_runtime_hook.py'],
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
    name='LanthornPSG',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # No console window (GUI app)
    icon='lanthorn_icon.ico',
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
    upx=False,
    name='LanthornPSG',
)
