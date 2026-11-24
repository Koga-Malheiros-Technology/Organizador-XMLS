from __future__ import annotations

from pathlib import Path

import pytest
from conftest import CNPJ_CLIENTE, CNPJ_EMPRESA, CNPJ_FORNECEDOR, nfe_xml

from organizer_xml.core.amostra import detectar_cnpjs, tamanho_amostra
from organizer_xml.core.cnpj import mascara


def test_tamanho_amostra_espaca_arquivos() -> None:
    assert tamanho_amostra(1000, limite=200) == (200, 5)
    assert tamanho_amostra(10, limite=200) == (10, 1)
    assert tamanho_amostra(0, limite=200) == (0, 1)


@pytest.mark.parametrize("total", [201, 250, 399, 401, 999, 1001, 5000])
def test_tamanho_amostra_cobre_a_base_inteira(total: int) -> None:
    """Logo acima do limite, `total // limite` lia só o começo da base."""
    lidos, passo = tamanho_amostra(total, limite=200)
    assert lidos == 200
    assert passo >= 2
    # o último índice lido tem de estar perto do fim da lista
    assert (lidos - 1) * passo >= total - passo


def test_detectar_cnpjs_sem_arquivos() -> None:
    assert detectar_cnpjs([]) == []


def test_detectar_cnpjs_acha_emitente_e_destinatario(tmp_path: Path) -> None:
    pasta = tmp_path / "x"
    pasta.mkdir()
    (pasta / "a.xml").write_bytes(nfe_xml())
    (pasta / "b.xml").write_bytes(
        nfe_xml(emit=CNPJ_FORNECEDOR, dest=CNPJ_EMPRESA)
    )
    (pasta / "c.xml").write_bytes(nfe_xml(emit=CNPJ_CLIENTE, dest=CNPJ_EMPRESA))

    # a empresa aparece como destinatária nos três; o cliente emite a e c;
    # o fornecedor emite só b
    encontrados = dict(detectar_cnpjs([str(p) for p in sorted(pasta.iterdir())]))
    assert encontrados[mascara(CNPJ_EMPRESA)] == 3
    assert encontrados[mascara(CNPJ_CLIENTE)] == 2
    assert encontrados[mascara(CNPJ_FORNECEDOR)] == 1


def test_detectar_cnpjs_ignora_ruido(tmp_path: Path) -> None:
    pasta = tmp_path / "x"
    pasta.mkdir()
    (pasta / "lixo.xml").write_bytes(b"<html>nao e fiscal</html>")
    assert detectar_cnpjs([str(pasta / "lixo.xml")]) == []


def test_detectar_cnpjs_conta_progresso(tmp_path: Path) -> None:
    pasta = tmp_path / "x"
    pasta.mkdir()
    for indice in range(4):
        (pasta / f"{indice}.xml").write_bytes(nfe_xml())
    vistos: list[int] = []
    detectar_cnpjs(
        [str(p) for p in sorted(pasta.iterdir())], progresso=vistos.append
    )
    assert vistos[-1] == 4


def test_detectar_cnpjs_conta_documento_e_nao_ocorrencia(tmp_path: Path) -> None:
    """Nota com o mesmo CNPJ nas duas pontas é um documento, não dois."""
    pasta = tmp_path / "x"
    pasta.mkdir()
    # operação entre a empresa e ela mesma: o CNPJ é citado duas vezes
    (pasta / "a.xml").write_bytes(
        nfe_xml(emit=CNPJ_EMPRESA, dest=CNPJ_EMPRESA)
    )
    # operação da empresa com um cliente: cada CNPJ citado uma vez
    (pasta / "b.xml").write_bytes(
        nfe_xml(emit=CNPJ_EMPRESA, dest=CNPJ_CLIENTE)
    )

    encontrados = dict(detectar_cnpjs([str(p) for p in sorted(pasta.iterdir())]))

    assert encontrados[mascara(CNPJ_EMPRESA)] == 2
    assert encontrados[mascara(CNPJ_CLIENTE)] == 1


def test_detectar_cnpjs_para_quando_cancela(tmp_path: Path) -> None:
    pasta = tmp_path / "x"
    pasta.mkdir()
    for indice in range(6):
        (pasta / f"{indice}.xml").write_bytes(nfe_xml())

    encontrados = detectar_cnpjs(
        [str(p) for p in sorted(pasta.iterdir())], cancelar=lambda: True
    )

    assert encontrados == []
