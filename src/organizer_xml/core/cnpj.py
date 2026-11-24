"""Normalização, máscara e validação de CNPJ."""

from __future__ import annotations

import re

_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_NAO_DIGITO = re.compile(r"\D")


def somente_digitos(valor: str) -> str:
    return _NAO_DIGITO.sub("", valor or "")


def digitos_validos(cnpj: str) -> bool:
    numeros = somente_digitos(cnpj)
    if len(numeros) != 14 or len(set(numeros)) == 1:
        return False
    if _digito(numeros, 12, _PESOS_DV1) != int(numeros[12]):
        return False
    return _digito(numeros, 13, _PESOS_DV2) == int(numeros[13])


def _digito(numeros: str, tamanho: int, pesos: tuple[int, ...]) -> int:
    soma = sum(int(d) * peso for d, peso in zip(numeros[:tamanho], pesos))
    resto = 11 - soma % 11
    return 0 if resto >= 10 else resto


def mascara(cnpj: str) -> str:
    numeros = somente_digitos(cnpj)[:14]
    total = len(numeros)
    if total == 0:
        return ""
    if total > 12:
        return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
    if total > 8:
        return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:]}"
    if total > 5:
        return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:]}"
    if total > 2:
        return f"{numeros[:2]}.{numeros[2:]}"
    return numeros


def problema(cnpj: str) -> str | None:
    """Mensagem de erro para a interface, ou None quando o CNPJ está válido."""
    numeros = somente_digitos(cnpj)
    if not numeros:
        return None
    if len(numeros) > 14:
        return f"Dígitos demais: {len(numeros)} (o CNPJ tem 14)"
    if len(numeros) < 14:
        return f"CNPJ incompleto: faltam {14 - len(numeros)} dígito(s)"
    if len(set(numeros)) == 1:
        return "CNPJ inválido: todos os dígitos são iguais"
    if not digitos_validos(numeros):
        return "CNPJ inválido: dígito verificador não confere"
    return None
