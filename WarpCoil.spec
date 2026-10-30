# -*- mode: python ; coding: utf-8 -*-
# Build a single console executable on Windows and Linux with bundled UI assets.
a = Analysis(
    ['localdrop.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.'), ('app.js', '.'), ('style.css', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='WarpCoil',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
