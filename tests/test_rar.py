"""Extração de RAR.

O 7-Zip não está instalado nesta máquina, então os testes que dependem dele
são pulados. O que dá para testar sem ele é a bookkeeping das pastas
temporárias — que é justamente o que vazava antes: as extrações ficavam em
%TEMP% para sempre, e uma base com muitos RAR enche o disco.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from organizer_xml.core import rar


def test_localizar_devolve_um_caminho_ou_none(monkeypatch) -> None:
    monkeypatch.setattr(rar.shutil, "which", lambda _nome: None)
    monkeypatch.setattr(rar.os.path, "isfile", lambda _c: False)
    assert rar.localizar() is None

    monkeypatch.setattr(rar.shutil, "which", lambda _nome: r"C:\7z.exe")
    assert rar.localizar() == r"C:\7z.exe"


def test_exigir_fala_com_o_usuario(monkeypatch) -> None:
    monkeypatch.setattr(rar, "localizar", lambda: None)
    with pytest.raises(rar.Sem7Zip) as erro:
        rar.exigir()
    assert "7-Zip" in str(erro.value)
    assert "winget" in str(erro.value)


def test_exigir_devolve_o_caminho(monkeypatch) -> None:
    monkeypatch.setattr(rar, "localizar", lambda: r"C:\7z.exe")
    assert rar.exigir() == r"C:\7z.exe"


def test_limpar_temporarios_apaga_o_que_foi_registrado(tmp_path, monkeypatch) -> None:
    pasta = tmp_path / "organizer_rar_1"
    (pasta / "sub").mkdir(parents=True)
    (pasta / "sub" / "nota.xml").write_text("<xml/>", encoding="utf-8")

    monkeypatch.setattr(rar, "_TEMPORARIOS", [str(pasta)])
    rar.limpar_temporarios()
    assert not pasta.exists()
    assert rar._TEMPORARIOS == []


def test_limpar_temporarios_ignora_pasta_ja_apagada(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(rar, "_TEMPORARIOS", [str(tmp_path / "nao_existe")])
    rar.limpar_temporarios()
    assert rar._TEMPORARIOS == []


def test_temporarios_limpos_limpa_mesmo_com_erro(monkeypatch) -> None:
    pasta = Path(os.environ.get("TEMP", ".")) / "organizer_rar_teste"
    pasta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rar, "_TEMPORARIOS", [str(pasta)])

    with pytest.raises(RuntimeError):
        with rar.temporarios_limpos():
            raise RuntimeError("falha no meio da operação")

    assert not pasta.exists()
    assert rar._TEMPORARIOS == []


def test_registro_somente_para_extrair_xmls(tmp_path, monkeypatch) -> None:
    """Só a extração cria pastas temporárias; localizar/listar não."""
    antes = list(rar._TEMPORARIOS)
    rar.localizar()
    assert rar._TEMPORARIOS == antes


@pytest.mark.skipif(rar.localizar() is None, reason="7-Zip não instalado")
def test_extrai_xmls_de_verdade(tmp_path: Path) -> None:
    """Exercita a extração de verdade: o 7-Zip abre, nós filtramos os XMLs.

    O arquivo é um .zip e não um .rar porque o 7-Zip gratuito não *cria* RAR
    (o codec de criação é proprietário): extrair RAR é justamente o que
    funciona, e é o que o 7-Zip faz aqui.
    """
    import zipfile

    compactado = tmp_path / "lote.zip"
    with zipfile.ZipFile(compactado, "w") as arquivo:
        arquivo.writestr("notas.xml", "<a/>")
        arquivo.writestr("sped.txt", "nao e xml")
        arquivo.writestr("sub/outro.xml", "<b/>")

    extraidos = rar.extrair_xmls(str(compactado))
    try:
        assert sorted(Path(p).name for p in extraidos) == ["notas.xml", "outro.xml"]
        assert all(p.lower().endswith(".xml") for p in extraidos)
        # o que não é XML foi apagado da extração
        assert not any(Path(p).name == "sped.txt" for p in extraidos)
    finally:
        rar.limpar_temporarios()

    assert rar._TEMPORARIOS == []


@pytest.mark.skipif(rar.localizar() is None, reason="7-Zip não instalado")
def test_arquivo_corrompido_nao_deixa_temporario_para_tras(tmp_path: Path) -> None:
    quebrado = tmp_path / "lote.zip"
    quebrado.write_bytes(b"isto nao e um zip")
    with pytest.raises(rar.Sem7Zip):
        rar.extrair_xmls(str(quebrado))
    assert rar._TEMPORARIOS == []


def test_listar_arquivo_inexistente() -> None:
    with pytest.raises(rar.Sem7Zip):
        rar.listar(r"C:\nao\existe\nao_existe.rar")
