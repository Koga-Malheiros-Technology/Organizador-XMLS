"""Amostragem de CNPJs presentes nos arquivos, para sugerir o CNPJ da empresa.

Roda sem o CNPJ informado: abre uma amostra espaçada da árvore, lê os emissores
e devolve os mais frequentes. É só uma sugestão — a decisão é do usuário.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

from .cnpj import mascara, somente_digitos
from .planner import analisar_arquivo

AMOSTRA_PADRAO = 200
MAXIMO_SUGESTOES = 30


def tamanho_amostra(total: int, limite: int = AMOSTRA_PADRAO) -> tuple[int, int]:
    """Devolve (quantos arquivos serão lidos, de quantos em quantos).

    O passo é arredondado para cima a partir da quantidade *desejada*: com
    `total // limite` um acervo de 201 arquivos leria os 200 primeiros, que é
    só o começo da base — exatamente o que a amostragem existe para evitar.
    """
    if total <= 0 or limite <= 0:
        return 0, 1
    lidos = min(total, limite)
    return lidos, max(1, -(-total // lidos))


def detectar_cnpjs(
    caminhos: Iterable[str],
    limite: int = AMOSTRA_PADRAO,
    progresso: Callable[[int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
) -> list[tuple[str, int]]:
    """Devolve [(cnpj mascarado, documentos em que aparece)], do mais ao menos frequente.

    A amostra é espaçada (um a cada `passo`) em vez de tomar os primeiros
    arquivos: os primeiros costumam ser o mesmo lote e não dizem nada sobre o
    restante da base.

    A contagem é por documento, não por ocorrência: um NF-e de saída para a
    própria empresa cita o CNPJ duas vezes (emitente e destinatário) e não
    pode pesar mais na sugestão que um documento que só cita uma vez.
    """
    lista = list(caminhos)
    if not lista:
        return []
    lidos, passo = tamanho_amostra(len(lista), limite)
    selecionados = lista[::passo][:lidos]

    contador: Counter[str] = Counter()
    for feitos, caminho in enumerate(selecionados, start=1):
        if cancelar and cancelar():
            break
        item = analisar_arquivo(caminho)
        cnpjs = list(item.emit_cnpjs) or ([item.emit_cnpj] if item.emit_cnpj else [])
        if item.dest_cnpj:
            cnpjs.append(item.dest_cnpj)
        vistos: set[str] = set()
        for cnpj in cnpjs:
            limpo = somente_digitos(cnpj or "")
            if len(limpo) == 14:
                vistos.add(limpo)
        for limpo in vistos:
            contador[limpo] += 1
        if progresso and feitos % 25 == 0:
            progresso(feitos)

    if progresso:
        progresso(lidos)
    sugestoes = contador.most_common(MAXIMO_SUGESTOES)
    return [(mascara(cnpj), quantidade) for cnpj, quantidade in sugestoes]
