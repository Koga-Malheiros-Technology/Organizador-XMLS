"""Localização do ícone da janela.

No executável congelado o `.ico` entra como dado do PyInstaller e fica
espalhado em `sys._MEIPASS`. Rodando do código-fonte, ele é procurado na
pasta `packaging/` do projeto.

Se o arquivo não estiver em nenhum dos dois lugares, devolve `None` e a
janela fica sem ícone — o que não impede o uso do programa.
"""

from __future__ import annotations

import sys
from pathlib import Path

NOME = "icone.ico"


def caminho() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        congelado = Path(base) / NOME
        if congelado.is_file():
            return congelado

    projeto = Path(__file__).resolve().parents[3]
    fonte = projeto / "packaging" / NOME
    if fonte.is_file():
        return fonte

    return None
