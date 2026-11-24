# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: executavel unico da interface grafica.

Roda dentro de um `.exe` que nao precisa de Python instalado na maquina do
cliente. `--onefile` (a forma deste spec) junta interpretador, biblioteca
padrao e o pacote `organizer_xml` num arquivo so, pronto para distribuicao.

O `icone.ico` entra duas vezes: como recurso do executavel (o icone que o
Explorer mostra) e como dado espalhado no `_MEIPASS` (o icone da janela).

Compilacao:

    uv sync --group build
    uv run pyinstaller --noconfirm --clean packaging/OrganizadorXML.spec
"""

from pathlib import Path

RAIZ = Path(SPECPATH).resolve()
PROJETO = RAIZ.parent
SRC = PROJETO / "src"

a = Analysis(
    [str(RAIZ / "entry_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(RAIZ / "icone.ico"), ".")],
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
    name="OrganizadorXML",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RAIZ / "icone.ico"),
    version=str(RAIZ / "version_info.txt"),
)
