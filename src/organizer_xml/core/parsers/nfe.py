"""Parser de NF-e (modelo 55) nos layouts 3.10 e 4.00."""

from __future__ import annotations

import re

from ..models import ItemDocumento, TipoDocumento
from .common import bloco, data_da_chave, data_de_texto, numero, tag

_RE_CHAVE_ID = re.compile(r'<infNFe\b[^>]*\bId="(?:NFe)?(\d{44})"')
_RE_CHAVE_PROT = re.compile(r"<chNFe>(\d{44})</chNFe>")
_RE_NATOP = re.compile(r"<natOp>([^<]*)</natOp>")
_RE_TPNF = re.compile(r"<tpNF>(\d)</tpNF>")
_RE_VNF = re.compile(r"<ICMSTot>.*?<vNF>([\d.,]+)</vNF>", re.S)
_RE_CNPJ = re.compile(r"<CNPJ>(\d{14})</CNPJ>")
_RE_CPF = re.compile(r"<CPF>(\d{11})</CPF>")


def parse(
    texto: str, origem: str, tamanho: int, digest: str
) -> ItemDocumento:
    item = ItemDocumento(
        origem=origem, tamanho=tamanho, digest=digest, tipo=TipoDocumento.NFE
    )

    achado = _RE_CHAVE_ID.search(texto) or _RE_CHAVE_PROT.search(texto)
    chave = achado.group(1) if achado else None
    if chave:
        item.chaves = (chave,)

    ide = bloco(texto, "ide")
    item.modelo = tag(ide, "mod")
    item.serie = tag(ide, "serie")
    item.numero = tag(ide, "nNF")
    natop = _valor(ide, texto, "natOp", _RE_NATOP)
    item.nat_op = natop or None
    tpnf = _valor(ide, texto, "tpNF", _RE_TPNF)
    item.tp_nf = int(tpnf) if tpnf and tpnf.isdigit() else None

    emit = bloco(texto, "emit")
    if emit:
        cnpj = _RE_CNPJ.search(emit)
        if cnpj:
            item.emit_cnpj = cnpj.group(1)
        item.emit_nome = tag(emit, "xNome")

    dest = bloco(texto, "dest")
    if dest:
        cnpj = _RE_CNPJ.search(dest)
        if cnpj:
            item.dest_cnpj = cnpj.group(1)
        cpf = _RE_CPF.search(dest)
        if cpf:
            item.dest_cpf = cpf.group(1)
        item.dest_nome = tag(dest, "xNome")

    item.data = (
        data_de_texto(tag(ide, "dhEmi"))
        or data_de_texto(tag(texto, "dhRecbto"))
        or data_da_chave(chave)
    )
    vnf = _RE_VNF.search(texto)
    item.valor = numero(vnf.group(1)) if vnf else None

    if not item.chaves and not item.emit_cnpj:
        item.erro = "NF-e sem chave de acesso e sem CNPJ do emitente"
    return item


def _valor(
    ide: str, texto: str, nome: str, expressao: re.Pattern[str]
) -> str | None:
    """Lê a tag no bloco <ide> e, se faltar, procura a primeira ocorrência no documento."""
    achado = tag(ide, nome)
    if achado:
        return achado.strip()
    encontrado = expressao.search(texto)
    return encontrado.group(1).strip() if encontrado else None

