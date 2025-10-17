# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['versions\\standalone_v1.2.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Program Files/VideoLAN/VLC/libvlc.dll', '.'), ('C:/Program Files/VideoLAN/VLC/libvlccore.dll', '.'), ('C:/Program Files/VideoLAN/VLC/plugins', 'plugins')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CustomPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
