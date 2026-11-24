"""Decodificação tolerante e extração de campos compartilhada pelos parsers."""

from __future__ import annotations

import re
from datetime import date

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_COMPACTA = re.compile(r"^(\d{4})(\d{2})(\d{2})")


def decodificar(dados: bytes) -> str:
    if dados.startswith(b"\xef\xbb\xbf"):
        return dados.decode("utf-8-sig", errors="replace")
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16", errors="replace")
    if b"\x00" in dados[:512]:
        return dados.decode("utf-16-le", errors="replace")
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("latin-1")


def elemento_raiz(texto: str) -> str | None:
    achado = re.search(r"<\s*([A-Za-z_][\w:.\-]*)", texto)
    return achado.group(1) if achado else None


def bloco(texto: str, tag: str) -> str | None:
    achado = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", texto, re.S)
    return achado.group(1) if achado else None


def tag_ci(texto: str, tag: str) -> str | None:
    achado = re.search(rf"<{tag}\b[^>]*>([^<]*)</{tag}>", texto, re.I | re.S)
    return achado.group(1).strip() if achado else None


def tag(texto: str | None, tag: str) -> str | None:
    if not texto:
        return None
    achado = re.search(rf"<{tag}\b[^>]*>([^<]*)</{tag}>", texto, re.S)
    return achado.group(1).strip() if achado else None


def tag_em(bloco_texto: str | None, tag: str) -> str | None:
    if not bloco_texto:
        return None
    achado = re.search(rf"<{tag}\b[^>]*>([^<]*)</{tag}>", bloco_texto, re.I | re.S)
    return achado.group(1).strip() if achado else None


def data_de_texto(valor: str | None) -> date | None:
    if not valor:
        return None
    achado = _ISO.search(valor)
    if achado:
        return _montar(*(int(g) for g in achado.groups()))
    achado = _COMPACTA.match(valor.strip())
    if achado:
        return _montar(*(int(g) for g in achado.groups()))
    return None


def data_da_chave(chave: str | None) -> date | None:
    """Fallback: ano e mês de emissão codificados na chave de acesso (posições 3-6)."""
    if not chave or len(chave) < 6 or not chave[2:6].isdigit():
        return None
    return _montar(2000 + int(chave[2:4]), int(chave[4:6]), 1)


def _montar(ano: int, mes: int, dia: int) -> date | None:
    if not 1 <= mes <= 12:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def numero(valor: str | None) -> float | None:
    if not valor:
        return None
    limpo = valor.strip().replace(".", "").replace(",", ".")
    if not limpo:
        return None
    try:
        return float(limpo)
    except ValueError:
        return None
