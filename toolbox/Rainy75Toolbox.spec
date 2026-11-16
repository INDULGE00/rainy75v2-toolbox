# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Rainy75 toolbox single-file build.

The whole application (web UI, studio server, firmware snapshot, toolchain) is
shipped as one ``payload.zip`` data file which app_main.py expands into
%LOCALAPPDATA% on first launch. Only the modules that are imported dynamically
(``import studio`` from the extracted payload) need to be listed here, so that
PIL and the stdlib pieces the server needs are collected into the archive.

Build with:  python toolbox/make_exe.py
"""

a = Analysis(
    ['app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('payload.zip', '.')],
    hiddenimports=[
        'PIL.Image', 'PIL.ImageChops', 'PIL.ImageDraw', 'PIL.ImageFilter',
        'PIL.ImageFont', 'PIL.GifImagePlugin', 'PIL.JpegImagePlugin',
        'PIL.PngImagePlugin',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Rainy75Toolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
