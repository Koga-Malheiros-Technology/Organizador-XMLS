"""Parser de arquivo de lote SAT/CFE (envCFe, modelo 59).

Cada cupom do lote é lido individualmente: o CNPJ do emitente fica em
CFe/emit/CNJ, enquanto o CNPJ em CFe/ide/CNPJ é o provedor do SAT.
"""

from __future__ import annotations

import re

from ..models import ItemDocumento, TipoDocumento
from .common import bloco, data_de_texto, numero, tag

_RE_CFE = re.compile(r"<CFe>(.*?)</CFe>", re.S)
_RE_CHAVE = re.compile(r'<infCFe\b[^>]*\bId="CFe(\d{44})"')
_RE_CNPJ = re.compile(r"<CNPJ>(\d{14})</CNPJ>")
_RE_CPF = re.compile(r"<CPF>(\d{11})</CPF>")
_RE_DH_ENVIO = re.compile(r"<dhEnvio>(\d{14})</dhEnvio>")
_RE_VALOR = re.compile(r"<vCFe>([\d.,]+)</vCFe>|<vNF>([\d.,]+)</vNF>")


def parse(
    texto: str, origem: str, tamanho: int, digest: str
) -> ItemDocumento:
    item = ItemDocumento(
        origem=origem, tamanho=tamanho, digest=digest, tipo=TipoDocumento.CFE_LOTE
    )

    chaves: list[str] = []
    emitentes: list[str] = []
    emit_nome: str | None = None
    destinatario_cnpj: str | None = None
    destinatario_cpf: str | None = None
    destinatario_nome: str | None = None
    primeira_data = None
    total = 0.0
    serie: str | None = None
    numero_cupom: str | None = None

    for achado in _RE_CFE.finditer(texto):
        cupom = achado.group(1)
        chave = _RE_CHAVE.search(cupom)
        if chave:
            chaves.append(chave.group(1))

        ide = bloco(cupom, "ide")
        if primeira_data is None:
            d_emissao = tag(ide, "dEmi")
            if d_emissao:
                primeira_data = data_de_texto(d_emissao)
            if serie is None:
                serie = tag(ide, "nserieSAT")
            if numero_cupom is None:
                numero_cupom = tag(ide, "nCFe")

        emit = bloco(cupom, "emit")
        if emit:
            cnpj = _RE_CNPJ.search(emit)
            if cnpj:
                emitentes.append(cnpj.group(1))
            nome = tag(emit, "xNome")
            if emit_nome is None and nome:
                emit_nome = nome

        dest = bloco(cupom, "dest")
        if dest:
            cnpj = _RE_CNPJ.search(dest)
            cpf = _RE_CPF.search(dest)
            if cnpj:
                destinatario_cnpj = cnpj.group(1)
            if cpf:
                destinatario_cpf = cpf.group(1)
            if destinatario_nome is None:
                destinatario_nome = tag(dest, "xNome")

        valor = _RE_VALOR.search(cupom)
        if valor:
            total += numero(valor.group(1) or valor.group(2)) or 0.0

    item.chaves = tuple(chaves)
    unicos = list(dict.fromkeys(emitentes))
    item.emit_cnpjs = tuple(unicos)
    item.emit_cnpj = unicos[0] if len(unicos) == 1 else None
    item.emit_nome = emit_nome
    item.dest_cnpj = destinatario_cnpj
    item.dest_cpf = destinatario_cpf
    item.dest_nome = destinatario_nome
    item.modelo = "59"
    item.serie = serie
    item.numero = numero_cupom
    item.valor = total or None

    envio = _RE_DH_ENVIO.search(texto)
    item.data = primeira_data or (data_de_texto(envio.group(1)) if envio else None)

    if not chaves:
        item.erro = "Lote SAT sem cupons (CFe) reconhecíveis"
    return item
