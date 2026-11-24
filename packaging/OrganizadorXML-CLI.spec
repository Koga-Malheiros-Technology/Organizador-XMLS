# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: executavel unico de linha de comando.

Mesma build da interface, mas com console: e o que permite conferir a
classificacao por script e, principalmente, testar o executavel congelado de
ponta a ponta (o pool de processos em `spawn` precisa do `freeze_support()`).

    uv sync --group build
    uv run pyinstaller --noconfirm --clean packaging/OrganizadorXML-CLI.spec
"""

from pathlib import Path

RAIZ = Path(SPECPATH).resolve()
PROJETO = RAIZ.parent
SRC = PROJETO / "src"

a = Analysis(
    [str(RAIZ / "entry_cli.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "_pytest",
        "unittest",
        "doctest",
        "pydoc",
        "tkinter.test",
        "test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OrganizadorXML-CLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RAIZ / "icone.ico"),
    version=str(RAIZ / "version_info.txt"),
)
