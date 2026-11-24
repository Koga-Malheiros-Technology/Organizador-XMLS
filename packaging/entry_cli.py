"""Entrada do executável congelado de linha de comando.

Mesma razão do `entry_gui.py`: o pool de processos precisa do
`freeze_support()` antes de qualquer outra execução.
"""

from __future__ import annotations

import multiprocessing
import sys


def _rodar() -> int:
    multiprocessing.freeze_support()
    from organizer_xml.cli import main

    return main()


if __name__ == "__main__":
    sys.exit(_rodar())
