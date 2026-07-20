# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


def collect_files(root, patterns):
    entries = []
    base = Path(root)
    for pattern in patterns:
        for path in base.rglob(pattern):
            if path.is_file():
                entries.append((str(path), str(path.parent)))
    return entries

project_datas = [
    ('resources', 'resources'),
    ('version.json', '.')
]
project_datas += collect_files(
    'tools/pdf_converter/config',
    ['*.json', 'templates/*.json'],
)

hidden_imports = []
hidden_imports += collect_submodules('fitz')
hidden_imports += collect_submodules('PIL')
hidden_imports += collect_submodules('easyocr')
hidden_imports += collect_submodules('torch')
hidden_imports += collect_submodules('torchvision')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=project_datas,
    hiddenimports=hidden_imports,
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
    name='公考小工具',
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
    icon=['resources/toolsIco.ico'],
)
