from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import (
    CNPJ_CLIENTE,
    CNPJ_EMPRESA,
    CNPJ_FORNECEDOR,
    CNPJ_SAT,
    chave,
    cfe_xml,
    nfe_xml,
    nfse_xml,
)

from organizer_xml.core.models import TipoDocumento
from organizer_xml.core.parsers import analisar
from organizer_xml.core.parsers.common import data_da_chave, decodificar


def analisar_bytes(dados: bytes):
    return analisar(dados, "teste.xml")


# --- detecção e decodificação ------------------------------------------------


@pytest.mark.parametrize(
    ("dados", "esperado"),
    [
        (nfe_xml(), TipoDocumento.NFE),
        (cfe_xml(), TipoDocumento.CFE_LOTE),
        (nfse_xml(), TipoDocumento.NFSE),
        (b"<html><body>erro do servidor</body></html>", TipoDocumento.DESCONHECIDO),
        (b"<nfeProc><NFe>", TipoDocumento.INVALIDO),
    ],
)
def test_detecao_do_tipo(dados: bytes, esperado: TipoDocumento) -> None:
    assert analisar_bytes(dados).tipo is esperado


def test_decodificacao_utf16() -> None:
    dados = nfe_xml().decode("utf-8").encode("utf-16")
    assert analisar_bytes(dados).emit_cnpj == CNPJ_EMPRESA


# --- NF-e sintética ----------------------------------------------------------


def test_nfe_saida() -> None:
    item = analisar_bytes(nfe_xml())
    assert item.emit_cnpj == CNPJ_EMPRESA
    assert item.dest_cnpj == CNPJ_CLIENTE
    assert item.tp_nf == 1
    assert item.nat_op == "VENDA DE MERCADORIA"
    assert item.modelo == "55"
    assert item.data == date(2024, 6, 15)
    assert item.valor == pytest.approx(1234.56)
    assert item.chaves and len(item.chaves[0]) == 44
    assert item.erro is None


def test_nfe_devolucao_tem_tpnf_zero() -> None:
    item = analisar_bytes(nfe_xml(tp_nf=0, nat_op="DEVOLUCAO DE VENDA"))
    assert item.tp_nf == 0
    assert item.nat_op == "DEVOLUCAO DE VENDA"


def test_nfe_entrada() -> None:
    item = analisar_bytes(
        nfe_xml(emit=CNPJ_FORNECEDOR, dest=CNPJ_EMPRESA, nat_op="COMPRA DE MERCADORIA")
    )
    assert item.emit_cnpj == CNPJ_FORNECEDOR
    assert item.dest_cnpj == CNPJ_EMPRESA


def test_nfe_sem_dh_emi_usa_chave() -> None:
    item = analisar_bytes(nfe_xml(dh_emi="", chave_emitida=chave(CNPJ_EMPRESA, "2309")))
    assert item.data == date(2023, 9, 1)


def test_nfe_truncada_vira_invalida() -> None:
    dados = nfe_xml()
    item = analisar(dados[: len(dados) // 2], "truncado.xml")
    assert item.tipo is TipoDocumento.INVALIDO
    assert item.erro


def test_destinatario_cpf_nao_vira_cnpj() -> None:
    item = analisar_bytes(nfe_xml(dest=None, dest_cpf=True))
    assert item.dest_cnpj is None
    assert item.dest_cpf == "12345678909"


# --- SAT/CFE -----------------------------------------------------------------


def test_cfe_lote_usa_emitente_e_nao_o_provedor() -> None:
    item = analisar_bytes(cfe_xml())
    assert item.emit_cnpjs == (CNPJ_EMPRESA, CNPJ_CLIENTE)
    assert item.emit_cnpj is None  # dois emissores distintos no mesmo lote
    assert item.dest_cnpj is None
    assert item.data == date(2024, 7, 16)
    assert item.valor == pytest.approx(111.0)
    assert len(item.chaves) == 2
    assert item.erro is None


def test_cfe_lote_de_um_emitente_so() -> None:
    item = analisar_bytes(cfe_xml(emit_secundario=CNPJ_EMPRESA))
    assert item.emit_cnpjs == (CNPJ_EMPRESA,)
    assert item.emit_cnpj == CNPJ_EMPRESA


def test_cfe_sem_d_emi_usa_dh_envio() -> None:
    item = analisar_bytes(cfe_xml(d_emi=""))
    assert item.data == date(2024, 7, 16)


def test_cnpj_do_provedor_sat_nao_vira_emitente() -> None:
    """O CNPJ em CFe/ide é do provedor do SAT e jamais pode ser o da empresa."""
    item = analisar_bytes(cfe_xml())
    assert CNPJ_SAT not in item.emit_cnpjs


def test_cfe_sem_cupons_invalido() -> None:
    dados = b'<envCFe versao="1.00"><dhEnvio>20240716100000</dhEnvio></envCFe>'
    assert analisar_bytes(dados).erro


# --- NFS-e -------------------------------------------------------------------


def test_nfse_prestadora() -> None:
    item = analisar_bytes(nfse_xml())
    assert item.emit_cnpj == CNPJ_EMPRESA
    assert item.dest_cnpj == CNPJ_CLIENTE
    assert item.data == date(2024, 3, 11)
    assert item.erro is None


# --- utilitários -------------------------------------------------------------


def test_data_da_chave() -> None:
    assert data_da_chave(chave(CNPJ_EMPRESA, "2406")) == date(2024, 6, 1)
    assert data_da_chave("abc") is None
    assert data_da_chave(None) is None


def test_decodificar_latin1() -> None:
    assert "cafç" in decodificar(b"<a>caf\xe7</a>")
