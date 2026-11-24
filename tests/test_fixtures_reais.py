"""Validação contra os arquivos reais da base do cliente (COMAUTO).

São documentos fiscais verdadeiros: o que estes testes garantem é que nenhum
campo essencial é lido errado, não o contrário. Nenhum arquivo é gravado.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from organizer_xml.core.classifier import classificar
from organizer_xml.core.models import Categoria, TipoDocumento
from organizer_xml.core.parsers import analisar

CNPJ_COMAUTO = "55364491000141"
CNPJ_DESTINATARIO_DEVOLUCAO = "48292932000181"


def carregar(fixtures: Path, nome: str):
    caminho = fixtures / nome
    if not caminho.is_file():
        pytest.skip(f"fixture ausente: {nome}")
    return analisar(caminho.read_bytes(), str(caminho))


@pytest.mark.parametrize(
    "nome",
    [
        "nfe_saida_nfproc.XML",
        "nfe_saida_nfproc__copia.XML",
        "nfe_saida_serie4.XML",
        "nfe_devolucao.XML",
        "nfe_devolucao_cpf.XML",
        "cfe_lote_sat.xml",
    ],
)
def test_todo_fixture_real_e_lido(fixtures: Path, nome: str) -> None:
    item = carregar(fixtures, nome)
    assert item.erro is None
    assert item.tipo in (TipoDocumento.NFE, TipoDocumento.CFE_LOTE)
    assert item.data is not None
    assert item.valor and item.valor > 0
    assert item.chaves
    assert all(len(chave) == 44 for chave in item.chaves)


@pytest.mark.parametrize(
    ("nome", "data", "serie", "numero", "valor", "nat_op", "tp_nf"),
    [
        ("nfe_saida_nfproc.XML", date(2021, 8, 2), "2", "412756", 74090.0, "VENDA SUBST TRIBUTARIA A VISTA", 1),
        ("nfe_saida_serie4.XML", date(2022, 1, 4), "4", "600", 119129.0, "VENDA FORA DO ESTADO A NAO CONTRIBUITE A", 1),
        ("nfe_devolucao.XML", date(2021, 8, 2), "2", "412759", 49975.0, "DEVOLUCAO C/ SUBST TRIBUT", 0),
        ("nfe_devolucao_cpf.XML", date(2021, 8, 2), "2", "412765", 9750.0, "DEVOLUCAO C/ SUBST TRIBUT", 0),
    ],
)
def test_nfe_real_campos(
    fixtures: Path,
    nome: str,
    data: date,
    serie: str,
    numero: str,
    valor: float,
    nat_op: str,
    tp_nf: int,
) -> None:
    item = carregar(fixtures, nome)
    assert item.tipo is TipoDocumento.NFE
    assert item.emit_cnpj == CNPJ_COMAUTO
    assert item.emit_nome == "COMAUTO AUTO PECAS MARILIA LTDA"
    assert item.data == data
    assert item.serie == serie
    assert item.numero == numero
    assert item.valor == pytest.approx(valor)
    assert item.nat_op == nat_op
    assert item.tp_nf == tp_nf
    assert item.modelo == "55"


def test_nfe_real_de_saida_vai_para_saida(fixtures: Path) -> None:
    item = carregar(fixtures, "nfe_saida_nfproc.XML")
    decisao = classificar(item, CNPJ_COMAUTO)
    assert decisao.categoria is Categoria.SAIDA
    assert (decisao.ano, decisao.mes) == (2021, 8)


def test_devolucoes_reais_viram_devolucao(fixtures: Path) -> None:
    for nome in ("nfe_devolucao.XML", "nfe_devolucao_cpf.XML"):
        decisao = classificar(carregar(fixtures, nome), CNPJ_COMAUTO)
        assert decisao.categoria is Categoria.DEVOLUCAO, nome
        assert (decisao.ano, decisao.mes) == (2021, 8)


def test_devolucao_para_cnpj_nao_vira_entrada(fixtures: Path) -> None:
    item = carregar(fixtures, "nfe_devolucao.XML")
    assert item.dest_cnpj == CNPJ_DESTINATARIO_DEVOLUCAO
    assert classificar(item, CNPJ_COMAUTO).categoria is Categoria.DEVOLUCAO


def test_lote_sat_real(fixtures: Path) -> None:
    item = carregar(fixtures, "cfe_lote_sat.xml")
    assert item.tipo is TipoDocumento.CFE_LOTE
    assert item.modelo == "59"
    assert item.emit_cnpjs == (CNPJ_COMAUTO,)
    assert item.emit_cnpj == CNPJ_COMAUTO
    assert len(item.chaves) == 7
    assert item.data == date(2022, 1, 20)
    assert item.valor == pytest.approx(349120.0)
    assert item.dest_cpf == "01570381810"

    decisao = classificar(item, CNPJ_COMAUTO)
    assert decisao.categoria is Categoria.CFE_SAT
    assert (decisao.ano, decisao.mes) == (2022, 1)


def test_lote_sat_nao_e_da_empresa_quando_ela_e_o_provedor(fixtures: Path) -> None:
    """A empresa aparece como provedor no <ide> dos cupons, nunca como emitente."""
    item = carregar(fixtures, "cfe_lote_sat.xml")
    outro_cnpj = "11222333000181"
    assert classificar(item, outro_cnpj).categoria is Categoria.NAO_CLASSIFICADO


def test_copia_e_byte_a_byte_identica(fixtures: Path) -> None:
    original = (fixtures / "nfe_saida_nfproc.XML").read_bytes()
    copia = (fixtures / "nfe_saida_nfproc__copia.XML").read_bytes()
    assert original == copia


def test_documentos_reais_tem_anos_distintos(fixtures: Path) -> None:
    """Cobre 2021 e 2022, que é o intervalo que aparece na base real."""
    anos = {
        carregar(fixtures, nome).data.year
        for nome in ("nfe_saida_nfproc.XML", "nfe_saida_serie4.XML", "cfe_lote_sat.xml")
    }
    assert anos == {2021, 2022}
