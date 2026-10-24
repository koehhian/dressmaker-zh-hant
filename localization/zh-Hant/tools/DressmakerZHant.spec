# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parents[2]
datas = [(str(ROOT / 'localization/zh-Hant/translations.csv'), '.'), (str(ROOT / 'localization/zh-Hant/images'), 'images')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('UnityPy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# UnityPy imports these eagerly; their native library and CPU data must ship too.
datas += collect_data_files('archspec')
datas += collect_data_files('fmod_toolkit')


a = Analysis(
    [str(ROOT / 'localization/zh-Hant/tools/patcher.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='DressmakerZHant',
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
