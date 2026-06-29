# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# paho-mqtt 1.x ships `paho` as a pkgutil namespace package, which PyInstaller's
# import analysis misses — collect it explicitly so the frozen build has it.
paho_datas, paho_binaries, paho_hidden = collect_all('paho')

a = Analysis(
    ['TRC_Tally_Cloud_Client.py'],
    pathex=[],
    binaries=paho_binaries,
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('tally.svg', '.'),
        ('ColorSchemes.json', '.'),
    ] + paho_datas,
    hiddenimports=paho_hidden + collect_submodules('serial') + [
        'paho.mqtt.client', 'serial.tools.list_ports',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TRC_Tally_Cloud_Client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
