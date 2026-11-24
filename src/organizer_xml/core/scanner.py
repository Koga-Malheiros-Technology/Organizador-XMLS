"""Varredura recursiva da árvore de origem."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

EXTENSAO_XML = ".xml"
EXTENSAO_RAR = ".rar"
EXTENSAO_ZIP = ".zip"


@dataclass(slots=True)
class ResultadoVarredura:
    fiscais: list[str] = field(default_factory=list)
    nao_fiscais: int = 0
    rars: list[str] = field(default_factory=list)
    zips: list[str] = field(default_factory=list)
    pastas_ignoradas: int = 0

    @property
    def compactados(self) -> list[str]:
        return sorted(self.rars + self.zips)


def listar_arquivos(
    origem: Path,
    destino: Path | None = None,
    profundidade: int | None = None,
) -> ResultadoVarredura:
    """Lista os XMLs da árvore, ignorando a subárvore do destino.

    profundidade=1 examina só os arquivos direto da origem; None percorre tudo.
    """
    base = os.path.abspath(os.fspath(origem))
    limite = (
        os.path.normcase(os.path.abspath(os.fspath(destino))) if destino else None
    )

    resultado = ResultadoVarredura()
    for raiz, pastas, arquivos in os.walk(base):
        raiz_norm = os.path.normcase(os.path.abspath(raiz))
        if limite and _dentro(raiz_norm, limite):
            pastas.clear()
            resultado.pastas_ignoradas += 1
            continue

        mantidas: list[str] = []
        for pasta in pastas:
            caminho = os.path.normcase(os.path.abspath(os.path.join(raiz, pasta)))
            if limite and _dentro(caminho, limite):
                resultado.pastas_ignoradas += 1
                continue
            mantidas.append(pasta)
        pastas[:] = mantidas

        if profundidade is not None:
            nivel = _nivel(raiz, base)
            if nivel >= profundidade:
                pastas.clear()

        for nome in arquivos:
            extensao = os.path.splitext(nome)[1].lower()
            if extensao == EXTENSAO_XML:
                resultado.fiscais.append(os.path.join(raiz, nome))
            elif extensao == EXTENSAO_RAR:
                resultado.rars.append(os.path.join(raiz, nome))
            elif extensao == EXTENSAO_ZIP:
                resultado.zips.append(os.path.join(raiz, nome))
            else:
                resultado.nao_fiscais += 1

    resultado.fiscais.sort()
    resultado.rars.sort()
    resultado.zips.sort()
    return resultado


def _dentro(caminho: str, limite: str) -> bool:
    return caminho == limite or caminho.startswith(limite + os.sep)


def _nivel(raiz: str, base: str) -> int:
    relativo = os.path.relpath(raiz, base)
    if relativo == os.curdir:
        return 1
    return len(relativo.split(os.sep)) + 1
