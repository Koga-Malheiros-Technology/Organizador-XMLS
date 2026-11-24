"""Parser de NFS-e: padrão nacional (ABERT) e padrão municipal (ABRASF).

Não há amostra real deste documento na base do cliente: o layout é descrito
pelo padrão, sem validação contra arquivo emitido por prefeitura.
"""

from __future__ import annotations

import re

from ..models import ItemDocumento, TipoDocumento
from .common import data_de_texto, numero, tag_em

_RE_PRESTADOR = re.compile(
    r"<(prestador|Prestador)>(.*?)</\1>", re.S | re.I
)
_RE_TOMADOR = re.compile(r"<(tomador|Tomador)>(.*?)</\1>", re.S | re.I)
_RE_CNPJ = re.compile(r"<CNPJ>(\d{14})</CNPJ>", re.I)
_RE_CPF = re.compile(r"<CPF>(\d{11})</CPF>", re.I)
_RE_CHAVE = re.compile(r'<infNFSe\b[^>]*\bId="(?:NFSe)?(\d{40,50})"')


def parse(
    texto: str, origem: str, tamanho: int, digest: str
) -> ItemDocumento:
    item = ItemDocumento(
        origem=origem, tamanho=tamanho, digest=digest, tipo=TipoDocumento.NFSE
    )

    chave = _RE_CHAVE.search(texto)
    if chave:
        item.chaves = (chave.group(1),)

    prestador = _RE_PRESTADOR.search(texto)
    tomador = _RE_TOMADOR.search(texto)

    if prestador:
        cnpj = _RE_CNPJ.search(prestador.group(2))
        if cnpj:
            item.emit_cnpj = cnpj.group(1)
        item.emit_nome = (
            tag_em(prestador.group(2), "xNomePrestador")
            or tag_em(prestador.group(2), "RazaoSocial")
        )
    if tomador:
        cnpj = _RE_CNPJ.search(tomador.group(2))
        cpf = _RE_CPF.search(tomador.group(2))
        if cnpj:
            item.dest_cnpj = cnpj.group(1)
        if cpf:
            item.dest_cpf = cpf.group(1)
        item.dest_nome = (
            tag_em(tomador.group(2), "xNomeTomador")
            or tag_em(tomador.group(2), "RazaoSocial")
        )

    item.numero = tag_em(texto, "numeroNFSe")
    item.serie = tag_em(texto, "serie")
    item.data = data_de_texto(
        tag_em(texto, "DataEmissao") or tag_em(texto, "DataEmissaoNfse")
    )
    item.valor = numero(
        tag_em(texto, "valorLiquidoNfse") or tag_em(texto, "valorTotalServicos")
    )

    tipo_nfse = tag_em(texto, "tipoNFSe")
    if tipo_nfse == "1":
        item.tp_nf = 1
    elif tipo_nfse == "2":
        item.tp_nf = 0

    if not prestador or not tomador:
        item.erro = "NFS-e sem prestador/tomador identificáveis"
    return item
