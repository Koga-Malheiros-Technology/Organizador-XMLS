"""Identificação do tipo de documento fiscal pelo elemento raiz do XML."""

from __future__ import annotations

import re

from .models import TipoDocumento
from .parsers.common import elemento_raiz

_RAIZES: dict[str, TipoDocumento] = {
    "nfeProc": TipoDocumento.NFE,
    "NFe": TipoDocumento.NFE,
    "infNFe": TipoDocumento.NFE,
    "envCFe": TipoDocumento.CFE_LOTE,
    "CFe": TipoDocumento.CFE_LOTE,
    "CFE": TipoDocumento.CFE_LOTE,
    "cfedoc": TipoDocumento.CFE_LOTE,
    "LoteCFe": TipoDocumento.CFE_LOTE,
    "NFSe": TipoDocumento.NFSE,
    "nfse": TipoDocumento.NFSE,
    "Nfse": TipoDocumento.NFSE,
    "CompNfse": TipoDocumento.NFSE,
    "Rps": TipoDocumento.NFSE,
    "ConsultarNfseRpsResposta": TipoDocumento.NFSE,
    "ConsultarNfseServicoPrestadoResposta": TipoDocumento.NFSE,
}

_FIM = re.compile(r"</\s*([A-Za-z_][\w:.\-]*)\s*>")


def detectar(texto: str) -> TipoDocumento:
    raiz = elemento_raiz(texto)
    if raiz is None:
        return TipoDocumento.INVALIDO
    tipo = _RAIZES.get(raiz)
    if tipo is None:
        return TipoDocumento.DESCONHECIDO
    if not any(achado.group(1) == raiz for achado in _FIM.finditer(texto)):
        return TipoDocumento.INVALIDO
    return tipo
