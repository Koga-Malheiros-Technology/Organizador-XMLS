"""Construção do plano de movimentos: lê, classifica e resolve conflitos de nome.

Nenhum arquivo é tocado aqui. O plano é uma lista de intenções, o que permite
mostrar o resultado antes de executar.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .classifier import PASTA_SEM_DATA, classificar
from .cnpj import mascara, somente_digitos
from .models import Categoria, Decisao, ItemDocumento, Movimento, Plano
from .parsers import analisar

TAMANHO_LOTE = 400
MOTIVO_DUPLICADO = "Conteúdo idêntico a outro arquivo da mesma execução"


def analisar_arquivo(caminho: str) -> ItemDocumento:
    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read()
    except OSError as erro:
        return ItemDocumento(
            origem=caminho, tamanho=0, digest="", erro=f"Leitura falhou: {erro}"
        )
    return analisar(dados, caminho)


def _processar_lote(lote: list[str]) -> list[ItemDocumento]:
    return [analisar_arquivo(caminho) for caminho in lote]


def ler_documentos(
    caminhos: Iterable[str],
    progresso: Callable[[int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    trabalhadores: int | None = None,
) -> Iterator[ItemDocumento]:
    """Lê os XMLs em paralelo e emite os itens conforme cada lote termina.

    Cai para leitura sequencial se o pool não puder ser criado, e também se
    ele morrer no meio do caminho — retomando do ponto em que parou, sem
    reler o que já foi emitido.
    """
    lista = list(caminhos)
    if not lista:
        return
    lotes = [
        lista[inicio : inicio + TAMANHO_LOTE]
        for inicio in range(0, len(lista), TAMANHO_LOTE)
    ]
    lidos = 0

    if trabalhadores != 1:
        pool: ProcessPoolExecutor | None = None
        try:
            pool = ProcessPoolExecutor(max_workers=trabalhadores)
        except (OSError, RuntimeError, ImportError, NotImplementedError, ValueError):
            pool = None

        if pool is not None:
            try:
                with pool:
                    for itens in pool.imap_unordered(_processar_lote, lotes):
                        for item in itens:
                            yield item
                        lidos += len(itens)
                        if progresso:
                            progresso(lidos)
                        if cancelar and cancelar():
                            pool.shutdown(wait=False, cancel_futures=True)
                            return
                return
            except Exception:  # noqa: BLE001 - o pool morreu; seguimos em série
                pass

    for caminho in lista[lidos:]:
        if cancelar and cancelar():
            return
        yield analisar_arquivo(caminho)
        lidos += 1
        if progresso:
            progresso(lidos)


def planejar(
    caminhos: Iterable[str],
    cnpj_empresa: str,
    progresso: Callable[[int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    mover_duplicados: bool = True,
    trabalhadores: int | None = None,
) -> Plano:
    empresa = somente_digitos(cnpj_empresa)
    plano = Plano()
    terceiros: Counter[str] = Counter()
    keepers: dict[str, int] = {}

    for item in ler_documentos(caminhos, progresso, cancelar, trabalhadores):
        _contar_terceiros(terceiros, empresa, item)
        if item.erro and not item.digest:
            plano.erros.append((item.origem, item.erro))
            continue

        movimento = _movimento(item, classificar(item, empresa))
        anterior = keepers.get(item.digest) if item.digest else None

        if anterior is None:
            if item.digest:
                keepers[item.digest] = len(plano.movimentos)
            plano.movimentos.append(movimento)
            continue

        if not mover_duplicados:
            plano.ignorados += 1
            continue

        if _melhor_arquivo(movimento.nome, plano.movimentos[anterior].nome):
            _vira_duplicado(plano.movimentos[anterior])
            keepers[item.digest] = len(plano.movimentos)
            plano.movimentos.append(movimento)
        else:
            plano.movimentos.append(_vira_duplicado(movimento))

    plano.cnpjs_terceiros = dict(terceiros.most_common(12))
    return plano


def destino_relativo(movimento: Movimento, sem_data: bool) -> str:
    if sem_data or movimento.ano is None or movimento.mes is None:
        partes = [PASTA_SEM_DATA, movimento.categoria.value]
    else:
        partes = [
            f"{movimento.ano:04d}",
            f"{movimento.mes:02d}",
            movimento.categoria.value,
        ]
    partes.append(movimento.nome)
    return os.path.join(*partes)


def _movimento(item: ItemDocumento, decisao: Decisao) -> Movimento:
    nome = os.path.basename(item.origem)
    movimento = Movimento(
        origem=item.origem,
        nome=nome,
        categoria=decisao.categoria,
        ano=decisao.ano,
        mes=decisao.mes,
        motivo=decisao.motivo,
        tamanho=item.tamanho,
        digest=item.digest,
        chaves=item.chaves,
        emit_cnpj=item.emit_cnpj,
        dest_cnpj=item.dest_cnpj,
        valor=item.valor,
    )
    movimento.destino_relativo = destino_relativo(movimento, decisao.sem_data)
    movimento.nome_final = nome
    return movimento


def _vira_duplicado(movimento: Movimento) -> Movimento:
    """Reclassifica no lugar, preservando ano/mês e o nome do arquivo."""
    movimento.categoria = Categoria.DUPLICADO
    movimento.motivo = MOTIVO_DUPLICADO
    movimento.destino_relativo = destino_relativo(movimento, movimento.ano is None)
    return movimento


def _melhor_arquivo(novo: str, atual: str) -> bool:
    """Em conteúdo idêntico, o nome mais curto é o arquivo 'oficial'.

    Sem isso, 'nota.xml - copia.xml' venceria 'nota.xml' só porque espaço
    ordena antes de ponto na comparação de texto.
    """
    if len(novo) != len(atual):
        return len(novo) < len(atual)
    return novo < atual


def _contar_terceiros(contador: Counter[str], empresa: str, item: ItemDocumento) -> None:
    candidatos = list(item.emit_cnpjs) or ([item.emit_cnpj] if item.emit_cnpj else [])
    if item.dest_cnpj:
        candidatos.append(item.dest_cnpj)
    for cnpj in candidatos:
        limpo = somente_digitos(cnpj or "")
        if limpo and limpo != empresa:
            contador[mascara(limpo)] += 1
