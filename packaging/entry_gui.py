"""Entrada do executável congelado da interface gráfica.

O `multiprocessing.freeze_support()` precisa vir antes de qualquer outra
coisa: no Windows o pool de processos do planejador é criado com `spawn`, e o
processo filho reexecuta este mesmo `.exe`. Sem a chamada, cada worker
abriria uma janela nova do aplicativo.

O import do `tkinter` fica dentro de `_rodar` de propósito: no processo
filho a execução morre em `freeze_support()`, e assim ele nem carrega a
interface.
"""

from __future__ import annotations

import multiprocessing
import sys


def _rodar() -> int:
    multiprocessing.freeze_support()
    from organizer_xml.ui.app import main

    main()
    return 0


if __name__ == "__main__":
    sys.exit(_rodar())
