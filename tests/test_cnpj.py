from __future__ import annotations

import pytest
from conftest import CNPJ_CLIENTE, CNPJ_EMPRESA, CNPJ_FORNECEDOR

from organizer_xml.core.cnpj import (
    digitos_validos,
    mascara,
    problema,
    somente_digitos,
)


@pytest.mark.parametrize(
    "entrada",
    [CNPJ_EMPRESA, "55.364.491/0001-41", "55364491000141", "  55364491000141 "],
)
def test_cnpj_valido_aceita_formatos(entrada: str) -> None:
    assert digitos_validos(entrada) is True
    assert problema(entrada) is None


def test_segundo_cnpj_valido() -> None:
    assert digitos_validos(CNPJ_FORNECEDOR) is True


def test_todos_digitos_iguais_invalido() -> None:
    assert digitos_validos("11111111111111") is False
    assert problema("11111111111111") is not None


def test_dv_incorreto_invalido() -> None:
    assert digitos_validos("55364491000142") is False
    assert "não confere" in (problema("55364491000142") or "")


def test_mascara() -> None:
    assert mascara(CNPJ_EMPRESA) == "55.364.491/0001-41"
    assert mascara(CNPJ_CLIENTE) == "99.888.777/0001-66"
    assert mascara("") == ""


def test_mascara_parcial_durante_digitacao() -> None:
    assert mascara("55") == "55"
    assert mascara("5536") == "55.36"
    assert mascara("55364491") == "55.364.491"
    assert mascara("553644910001") == "55.364.491/0001"


def test_campo_vazio_nao_e_erro() -> None:
    assert problema("") is None


def test_cnpj_incompleto_e_acima_do_limite() -> None:
    assert "incompleto" in (problema("5536449100014") or "").lower()
    assert "dígitos demais" in (problema("553644910001411") or "").lower()


def test_somente_digitos() -> None:
    assert somente_digitos("55.364.491/0001-41") == CNPJ_EMPRESA
    assert somente_digitos("") == ""
