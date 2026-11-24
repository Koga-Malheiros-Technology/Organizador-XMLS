from __future__ import annotations

from conftest import (
    CNPJ_CLIENTE,
    CNPJ_EMPRESA,
    CNPJ_FORNECEDOR,
    chave,
    cfe_xml,
    nfe_xml,
)

from organizer_xml.core.classifier import classificar
from organizer_xml.core.cnpj import mascara
from organizer_xml.core.models import Categoria
from organizer_xml.core.parsers import analisar


def decisao(dados: bytes, cnpj: str = CNPJ_EMPRESA):
    return classificar(analisar(dados, "teste.xml"), cnpj)


# --- regras de negócio --------------------------------------------------------


def test_saida() -> None:
    resultado = decisao(nfe_xml())
    assert resultado.categoria is Categoria.SAIDA
    assert (resultado.ano, resultado.mes) == (2024, 6)


def test_entrada() -> None:
    resultado = decisao(nfe_xml(emit=CNPJ_FORNECEDOR, dest=CNPJ_EMPRESA))
    assert resultado.categoria is Categoria.ENTRADA
    assert (resultado.ano, resultado.mes) == (2024, 6)


def test_devolucao_tem_precedencia_sobre_entrada() -> None:
    """Devolução devolvida ao fornecedor tem tpNF=0 e destino fora da empresa."""
    resultado = decisao(
        nfe_xml(emit=CNPJ_EMPRESA, dest=CNPJ_FORNECEDOR, tp_nf=0, nat_op="DEVOLUCAO")
    )
    assert resultado.categoria is Categoria.DEVOLUCAO


def test_cnpj_formatado_e_aceito() -> None:
    resultado = decisao(nfe_xml(), "55.364.491/0001-41")
    assert resultado.categoria is Categoria.SAIDA


def test_empresa_nas_duas_pontas_e_ambiguo() -> None:
    resultado = decisao(nfe_xml(emit=CNPJ_EMPRESA, dest=CNPJ_EMPRESA))
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO
    assert "emitente e destinatária" in resultado.motivo


def test_terceiro_nao_e_da_empresa() -> None:
    resultado = decisao(nfe_xml(emit=CNPJ_FORNECEDOR, dest=CNPJ_CLIENTE))
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO
    assert mascara(CNPJ_FORNECEDOR) in resultado.motivo


def test_cpf_como_destinatario() -> None:
    """CPF nunca é a empresa; o documento vai para não classificados."""
    acesso = chave(CNPJ_FORNECEDOR)
    dados = (
        f'<nfeProc><NFe><infNFe versao="4.00" Id="NFe{acesso}">'
        "<ide><mod>55</mod><natOp>VENDA</natOp><tpNF>1</tpNF>"
        "<dhEmi>2024-06-15T10:00:00-03:00</dhEmi></ide>"
        "<emit><xNome>FORNECEDOR SEM CNPJ</xNome></emit>"
        "<dest><CPF>12345678909</CPF><xNome>CONSUMIDOR</xNome></dest>"
        "</infNFe></NFe>"
        f"<protNFe><infProt><chNFe>{acesso}</chNFe></infProt></protNFe>"
        "</nfeProc>"
    ).encode("utf-8")
    resultado = decisao(dados)
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO
    assert "CPF" in resultado.motivo


def test_lote_sat_da_empresa() -> None:
    resultado = decisao(cfe_xml())
    assert resultado.categoria is Categoria.CFE_SAT
    assert resultado.ano == 2024
    assert resultado.mes == 7


def test_lote_sat_de_terceiros() -> None:
    resultado = decisao(cfe_xml(emit=CNPJ_CLIENTE, emit_secundario=CNPJ_FORNECEDOR))
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO


def test_sat_nao_confunde_provedor_com_empresa() -> None:
    """Se a empresa for só o provedor do SAT e ninguém emitir os cupons, não é dela."""
    resultado = decisao(
        cfe_xml(emit=CNPJ_CLIENTE, emit_secundario=CNPJ_FORNECEDOR, cnpj_sat=CNPJ_EMPRESA)
    )
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO


# --- datas --------------------------------------------------------------------


def test_sem_data_usa_prefixo_dedicado() -> None:
    """Sem dhEmi e com chave ilegível, o documento continua classificado por data nula."""
    resultado = decisao(nfe_xml(dh_emi="", chave_emitida="3" * 44))
    assert resultado.categoria is Categoria.SAIDA
    assert resultado.sem_data is True
    assert resultado.ano is None
    assert resultado.mes is None


def test_data_da_chave_como_fallback() -> None:
    resultado = decisao(nfe_xml(dh_emi="", chave_emitida=chave(CNPJ_EMPRESA, "2311")))
    assert resultado.ano == 2023
    assert resultado.mes == 11
    assert resultado.sem_data is False


# --- degenerados ---------------------------------------------------------------


def test_xml_invalido() -> None:
    resultado = classificar(analisar(b"<nfeProc><NFe>", "x.xml"), CNPJ_EMPRESA)
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO
    assert resultado.ano is None


def test_documento_desconhecido() -> None:
    resultado = classificar(analisar(b"<xpto><a>1</a></xpto>", "x.xml"), CNPJ_EMPRESA)
    assert resultado.categoria is Categoria.NAO_CLASSIFICADO
