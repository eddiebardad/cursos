# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None
project_root = os.path.abspath('.')

datas = [
    (os.path.join(project_root, 'schemas', 'course_schema.rdf'), 'schemas'),
]

a = Analysis(
    ['gui_app.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'providers.aprende',
        'providers.cognitiveclass',
        'providers.hubspot',
        'providers.netacad',
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
    a.binaries,
    a.datas,
    [],
    name='gui_app',
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
)
