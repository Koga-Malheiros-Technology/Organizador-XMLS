"""Despacho para o parser adequado a cada tipo de documento."""

from __future__ import annotations

import hashlib

from ..detect import detectar
from ..models import ItemDocumento, TipoDocumento
from . import cfe, nfe, nfse
from .common import decodificar

_POR_TIPO = {
    TipoDocumento.NFE: nfe.parse,
    TipoDocumento.CFE_LOTE: cfe.parse,
    TipoDocumento.NFSE: nfse.parse,
}


def analisar(
    dados: bytes, origem: str, tamanho: int | None = None
) -> ItemDocumento:
    texto = decodificar(dados)
    digest = hashlib.sha1(dados).hexdigest()
    tamanho = len(dados) if tamanho is None else tamanho

    tipo = detectar(texto)
    parser = _POR_TIPO.get(tipo)
    if parser is None:
        motivo = (
            "XML sem elemento raiz reconhecível"
            if tipo is TipoDocumento.INVALIDO
            else f"Documento fiscal não suportado (raiz <{_raiz(texto)}>)"
        )
        return ItemDocumento(
            origem=origem,
            tamanho=tamanho,
            digest=digest,
            tipo=tipo,
            erro=motivo,
        )

    item = parser(texto, origem, tamanho, digest)
    if tipo is TipoDocumento.NFE and item.erro:
        item.tipo = TipoDocumento.INVALIDO
    return item


def _raiz(texto: str) -> str:
    from .common import elemento_raiz

    return elemento_raiz(texto) or "?"
