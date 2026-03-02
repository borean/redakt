# -*- mode: python ; coding: utf-8 -*-

import platform
import os

# ── Bundle llama-server binary (platform-specific) ─────────────────────
_binaries = []
_bin_dir = os.path.join(os.path.dirname(os.path.abspath('.')), 'bin')

if platform.system() == "Darwin":
    _llama = os.path.join('bin', 'llama-server')
    if os.path.exists(_llama):
        _binaries.append((_llama, 'bin'))
elif platform.system() == "Windows":
    _llama = os.path.join('bin', 'llama-server.exe')
    if os.path.exists(_llama):
        _binaries.append((_llama, 'bin'))
elif platform.system() == "Linux":
    _llama = os.path.join('bin', 'llama-server')
    if os.path.exists(_llama):
        _binaries.append((_llama, 'bin'))


a = Analysis(
    ['redakt/__main__.py'],
    pathex=[],
    binaries=_binaries,
    datas=[('assets', 'assets')],
    hiddenimports=[
        'redakt', 'redakt.core', 'redakt.parsers', 'redakt.ui', 'redakt.api',
    ],
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
    [],
    exclude_binaries=True,
    name='Redakt',
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
    icon=['assets/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Redakt',
)
app = BUNDLE(
    coll,
    name='Redakt.app',
    icon='assets/icon.icns',
    bundle_identifier='com.redakt.app',
)
