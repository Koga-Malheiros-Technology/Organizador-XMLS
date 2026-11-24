"""Leitura de arquivos compactados (.rar e .zip) via 7-Zip.

O formato RAR não é suportado pela biblioteca padrão do Python e o módulo
rarfile exigiria o unrar.exe do WinRAR. Como o 7-Zip resolve RAR e ZIP, a
extração de ambos é delegada a ele via linha de comando.

As extrações são área de rascunho: vivem em pastas temporárias que
`limpar_temporarios()` remove no fim. O arquivo de origem nunca é alterado,
então descartar a cópia extraída é seguro mesmo cancelando a operação.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from collections.abc import Iterator

CANDIDATOS = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
)

_JA_CRIADO = "7z.exe"

_TEMPORARIOS: list[str] = []


class Sem7Zip(Exception):
    pass


def localizar() -> str | None:
    achado = shutil.which(_JA_CRIADO)
    if achado:
        return achado
    for caminho in CANDIDATOS:
        if os.path.isfile(caminho):
            return caminho
    return None


def exigir() -> str:
    caminho = localizar()
    if not caminho:
        raise Sem7Zip(
            "7-Zip não encontrado. Instale com: winget install 7zip.7zip"
        )
    return caminho


def listar(arquivo: str) -> list[str]:
    caminho = exigir()
    processo = subprocess.run(
        [caminho, "l", "-ba", "-slt", os.fspath(arquivo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if processo.returncode != 0:
        raise Sem7Zip(f"Falha ao listar {arquivo}: {processo.stderr.strip()}")
    nomes: list[str] = []
    for linha in processo.stdout.splitlines():
        if linha.startswith("Path = "):
            nomes.append(linha[len("Path = ") :].strip())
    return nomes


def extrair_xmls(arquivo: str) -> list[str]:
    """Extrai para uma pasta temporária e devolve apenas os XMLs, deletando o resto.

    A pasta fica registrada para `limpar_temporarios()`; o chamador deve
    limpá-la depois de terminar de usar os arquivos devolvidos.
    """
    caminho = exigir()
    destino = tempfile.mkdtemp(prefix="organizer_rar_")
    _TEMPORARIOS.append(destino)
    processo = subprocess.run(
        [
            caminho,
            "x",
            "-y",
            "-bd",
            f"-o{destino}",
            os.fspath(arquivo),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if processo.returncode != 0:
        shutil.rmtree(destino, ignore_errors=True)
        _TEMPORARIOS.remove(destino)
        raise Sem7Zip(f"Falha ao extrair {arquivo}: {processo.stderr.strip()}")

    xmls: list[str] = []
    for raiz, _, arquivos in os.walk(destino):
        for nome in arquivos:
            caminho_xml = os.path.join(raiz, nome)
            if os.path.splitext(nome)[1].lower() == ".xml":
                xmls.append(caminho_xml)
            else:
                os.remove(caminho_xml)
    return xmls


def limpar_temporarios() -> None:
    """Apaga as pastas de extração que ainda existirem."""
    while _TEMPORARIOS:
        destino = _TEMPORARIOS.pop()
        shutil.rmtree(destino, ignore_errors=True)


def temporarios_criados() -> list[str]:
    """Pastas de extração ativas.

    O executor grava isto no manifesto para que a reversão saiba que esses
    arquivos vieram de dentro de um .rar: eles não podem voltar para a pasta
    temporária (ela é apagada), e não precisam voltar — o .rar continua
    guardando a cópia original.
    """
    return list(_TEMPORARIOS)


@contextmanager
def temporarios_limpos() -> Iterator[None]:
    """Garante a limpeza das extrações mesmo se algo der errado no meio."""
    try:
        yield
    finally:
        limpar_temporarios()
