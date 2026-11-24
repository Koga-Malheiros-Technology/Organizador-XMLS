from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import CNPJ_EMPRESA, CNPJ_FORNECEDOR, cfe_xml, nfe_xml

from organizer_xml.core.executor import (
    MODO_COPIAR,
    MODO_MOVER,
    executar,
    modo_manifesto,
    reverter,
)
from organizer_xml.core.planner import planejar
from organizer_xml.core.report import escrever_csv, escrever_json, resumo_textual
from organizer_xml.core.scanner import listar_arquivos

SERIE = 1


@pytest.fixture
def origem(tmp_path: Path) -> Path:
    pasta = tmp_path / "origem"
    (pasta / "2021" / "sub").mkdir(parents=True)
    (pasta / "2021" / "notas").mkdir(parents=True)

    (pasta / "2021" / "notas" / "saida.xml").write_bytes(nfe_xml())
    (pasta / "2021" / "notas" / "saida - copia.xml").write_bytes(nfe_xml())
    (pasta / "2021" / "notas" / "entrada.xml").write_bytes(
        nfe_xml(emit=CNPJ_FORNECEDOR, dest=CNPJ_EMPRESA, dh_emi="2021-03-02T08:00:00-03:00")
    )
    (pasta / "2021" / "notas" / "devolucao.xml").write_bytes(
        nfe_xml(tp_nf=0, nat_op="DEVOLUCAO", dh_emi="2021-03-05T08:00:00-03:00")
    )
    (pasta / "2021" / "sub" / "lote.xml").write_bytes(cfe_xml())
    (pasta / "2021" / "notas" / "efd.txt").write_text("nao mexer", encoding="utf-8")
    (pasta / "2021" / "backup.zip").write_bytes(b"PK\x03\x04")
    return pasta


@pytest.fixture
def destino(tmp_path: Path) -> Path:
    return tmp_path / "destino"


# --- scanner ------------------------------------------------------------------


def test_varredura_encontra_xml_e_conta_o_resto(origem: Path, destino: Path) -> None:
    resultado = listar_arquivos(origem, destino)
    assert len(resultado.fiscais) == 5
    assert resultado.nao_fiscais == 1
    assert resultado.rars == []
    assert len(resultado.zips) == 1
    assert len(resultado.compactados) == 1


def test_varredura_ignora_subarvore_do_destino(origem: Path) -> None:
    """Destino dentro da origem é o caso perigoso: não pode ser reprocessado."""
    dentro = origem / "JaOrganizados"
    (dentro / "2024").mkdir(parents=True)
    (dentro / "2024" / "antigo.xml").write_bytes(nfe_xml())
    (dentro / "2024" / "notas.txt").write_text("nao contar", encoding="utf-8")

    resultado = listar_arquivos(origem, dentro)
    assert len(resultado.fiscais) == 5
    assert resultado.pastas_ignoradas >= 1
    assert not any("antigo.xml" in caminho for caminho in resultado.fiscais)


def test_varredura_com_profundidade(origem: Path, destino: Path) -> None:
    resultado = listar_arquivos(origem, destino, profundidade=1)
    assert resultado.fiscais == []


# --- planner ------------------------------------------------------------------


def montar_plano(origem: Path, **kwargs) -> object:
    varredura = listar_arquivos(origem, kwargs.get("destino"))
    return planejar(
        varredura.fiscais,
        CNPJ_EMPRESA,
        mover_duplicados=kwargs.get("mover_duplicados", True),
        trabalhadores=1,
    )


def test_planejamento_por_categoria(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    contagem = plano.por_categoria()
    assert contagem["Saida"] == 1
    assert contagem["Entrada"] == 1
    assert contagem["_Devolucoes"] == 1
    assert contagem["_CFE_SAT"] == 1
    assert contagem["_Duplicados"] == 1
    assert len(plano.movimentos) == 5


def test_estrutura_por_ano_mes_e_categoria(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    destinos = {m.destino_relativo for m in plano.movimentos}
    assert "2024\\06\\Saida\\saida.xml" in destinos
    assert "2021\\03\\Entrada\\entrada.xml" in destinos
    assert "2021\\03\\_Devolucoes\\devolucao.xml" in destinos
    assert "2024\\07\\_CFE_SAT\\lote.xml" in destinos
    assert "2024\\06\\_Duplicados\\saida - copia.xml" in destinos


def test_duplicado_pode_ficar_para_tras(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino, mover_duplicados=False)
    assert "_Duplicados" not in plano.por_categoria()
    assert plano.ignorados == 1
    assert len(plano.movimentos) == 4


def test_terceiros_aparecem_no_relatorio(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    assert plano.cnpjs_terceiros


def test_resumo_textual_nao_quebra(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    resumo = resumo_textual(plano, CNPJ_EMPRESA)
    assert "55.364.491/0001-41" in resumo
    assert "Saida" in resumo


def test_relatorios_sao_gravados(origem: Path, destino: Path, tmp_path: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    csv = escrever_csv(plano, tmp_path / "rel" / "movimentos.csv")
    json_saida = escrever_json(plano, tmp_path / "rel" / "movimentos.json")

    assert csv.read_text(encoding="utf-8-sig").count("\n") == 6
    dados = json.loads(json_saida.read_text(encoding="utf-8"))
    assert dados["resumo"]["total"] == 5
    assert len(dados["movimentos"]) == 5


# --- execução e reversão ------------------------------------------------------


def test_execucao_move_os_arquivos(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    resultado = executar(plano, destino, manifesto, limpar_vazias=False)

    assert resultado.movidos == 5
    assert resultado.falhas == []
    assert (destino / "2024" / "06" / "Saida" / "saida.xml").is_file()
    assert (destino / "2021" / "03" / "Entrada" / "entrada.xml").is_file()
    assert (destino / "2021" / "03" / "_Devolucoes" / "devolucao.xml").is_file()
    assert (destino / "2024" / "07" / "_CFE_SAT" / "lote.xml").is_file()
    assert (destino / "2024" / "06" / "_Duplicados" / "saida - copia.xml").is_file()
    assert not list(origem.rglob("*.xml"))
    # arquivos não fiscais continuam na origem
    assert (origem / "2021" / "notas" / "efd.txt").is_file()
    assert (origem / "2021" / "backup.zip").is_file()


def test_manifesto_registra_cada_movimento(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, limpar_vazias=False)

    linhas = [
        json.loads(linha)
        for linha in manifesto.read_text(encoding="utf-8").splitlines()
        if linha
    ]
    eventos = [linha["evento"] for linha in linhas]
    assert eventos[0] == "inicio"
    assert eventos[-1] == "fim"
    assert eventos.count("movido") == 5


def test_reversao_devolve_os_arquivos(origem: Path, destino: Path) -> None:
    antes = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, limpar_vazias=False)

    resultado = reverter(manifesto)
    assert resultado.movidos == 5
    assert resultado.falhas == []
    depois = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    assert depois == antes
    assert not list(destino.rglob("*.xml"))


def test_reversao_recusa_arquivo_alterado(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, limpar_vazias=False)

    alterado = destino / "2024" / "06" / "Saida" / "saida.xml"
    alterado.write_bytes(b"<alterado/>")

    resultado = reverter(manifesto)
    assert resultado.movidos == 4
    assert len(resultado.falhas) == 1
    assert "alterado" in resultado.falhas[0][1]


def test_colisao_de_nome_ganha_sufixo(origem: Path, destino: Path) -> None:
    (destino / "2024" / "06" / "Saida").mkdir(parents=True)
    (destino / "2024" / "06" / "Saida" / "saida.xml").write_bytes(b"antigo")

    plano = montar_plano(origem, destino=destino)
    executar(plano, destino, destino / "m.jsonl", limpar_vazias=False)

    assert (destino / "2024" / "06" / "Saida" / "saida.xml").read_bytes() == b"antigo"
    assert (destino / "2024" / "06" / "Saida" / "saida (2).xml").is_file()


def test_execucao_cancela_antes_de_mover_tudo(origem: Path, destino: Path) -> None:
    plano = montar_plano(origem, destino=destino)
    resultado = executar(
        plano,
        destino,
        destino / "m.jsonl",
        cancelar=lambda: True,
        limpar_vazias=False,
    )
    assert resultado.cancelado is True
    assert resultado.movidos == 0
    assert len(list(origem.rglob("*.xml"))) == 5


def test_reversao_de_rar_descarta_a_copia_em_vez_de_recriar_temporaria(
    tmp_path: Path,
) -> None:
    """Arquivo que veio de dentro de um .rar não tem onde voltar.

    A pasta temporária de extração já foi apagada e o .rar segue guardando a
    cópia original, então devolver o arquivo para lá só criaria um diretório
    órfão em %TEMP% com um arquivo que ninguém vai encontrar.
    """
    extraido = tmp_path / "organizer_rar_abc123" / "2024" / "06"
    extraido.mkdir(parents=True)
    (extraido / "nota.xml").write_bytes(b"<nfe/>")

    destino = tmp_path / "destino"
    plano = montar_plano(extraido, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(
        plano,
        destino,
        manifesto,
        contexto={"extracoes": [str(tmp_path / "organizer_rar_abc123")]},
        limpar_vazias=False,
    )
    assert list(destino.rglob("*.xml"))

    # simula o fim da execução, que limpa as temporárias
    shutil.rmtree(tmp_path / "organizer_rar_abc123")

    resultado = reverter(manifesto)

    assert resultado.falhas == []
    assert resultado.movidos == len(plano.movimentos)
    assert not list(destino.rglob("*.xml"))
    assert not (tmp_path / "organizer_rar_abc123").exists()
    assert any("RAR" in aviso for aviso in resultado.avisos)


def test_reversao_comum_nao_e_tratada_como_extracao(tmp_path: Path) -> None:
    """Sem 'extracoes' no contexto, o comportamento antigo é mantido."""
    origem = tmp_path / "notas"
    origem.mkdir()
    (origem / "nota.xml").write_bytes(b"<nfe/>")
    destino = tmp_path / "destino"

    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, limpar_vazias=False)

    resultado = reverter(manifesto)

    assert resultado.avisos == []
    assert (origem / "nota.xml").is_file()


# --- copia --------------------------------------------------------------------


def test_copia_mantem_os_originais_e_marca_o_modo(origem: Path, destino: Path) -> None:
    antes = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"

    resultado = executar(plano, destino, manifesto, copiar=True, limpar_vazias=False)

    assert resultado.movidos == 5
    assert resultado.falhas == []
    # os originais continuam intactos...
    depois = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    assert depois == antes
    # ...e as cópias existem no destino
    assert len(list(destino.rglob("*.xml"))) == 5
    cabecalho = json.loads(manifesto.read_text(encoding="utf-8").splitlines()[0])
    assert cabecalho["modo"] == "copiar"
    assert modo_manifesto(manifesto) == MODO_COPIAR


def test_modo_padrao_continua_sendo_mover(origem: Path, destino: Path) -> None:
    """O manifesto não pode ficar sem modo: a reversão depende dele."""
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"

    executar(plano, destino, manifesto, limpar_vazias=False)

    cabecalho = json.loads(manifesto.read_text(encoding="utf-8").splitlines()[0])
    assert cabecalho["modo"] == "mover"
    assert modo_manifesto(manifesto) == MODO_MOVER


def test_copia_nao_apaga_pasta_vazia_na_origem(origem: Path, destino: Path) -> None:
    """Com `limpar_vazias` ligado, a cópia não pode encostar na origem.

    Os arquivos continuam lá justamente porque o usuário pediu para preservá-los;
    uma limpeza aqui seria perda de dados silenciosa.
    """
    plano = montar_plano(origem, destino=destino)

    executar(plano, destino, destino / "m.jsonl", copiar=True, limpar_vazias=True)

    assert list(origem.rglob("*.xml"))
    assert (origem / "2021" / "notas").is_dir()


def test_reversao_de_copia_apaga_a_copia_e_preserva_o_original(
    origem: Path, destino: Path
) -> None:
    antes = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, copiar=True, limpar_vazias=False)

    resultado = reverter(manifesto)

    assert resultado.falhas == []
    assert resultado.movidos == 5
    # o destino foi limpo...
    assert not list(destino.rglob("*.xml"))
    # ...e a origem segue idêntica, sem duplicata criada pelo caminho "velho"
    depois = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    assert depois == antes
    assert any("originais continuam" in aviso for aviso in resultado.avisos)


def test_reversao_de_copia_nao_recria_arquivo_alterado(origem: Path, destino: Path) -> None:
    """A verificação de tamanho protege a edição feita na cópia.

    Sem isso, reverter apagaria um arquivo que o usuário pode ter ajustado à mão
    para uso no destino.
    """
    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(plano, destino, manifesto, copiar=True, limpar_vazias=False)

    editado = destino / "2024" / "06" / "Saida" / "saida.xml"
    editado.write_bytes(b"<corrigido a mao/>")

    resultado = reverter(manifesto)

    assert resultado.movidos == 4
    assert len(resultado.falhas) == 1
    assert "alterado" in resultado.falhas[0][1]
    assert editado.is_file()
    assert len(list(origem.rglob("*.xml"))) == 5


def test_copia_com_nome_ocupado_ganha_sufixo(origem: Path, destino: Path) -> None:
    """Colisão resolve igual no modo cópia, sem sobrescrever nada."""
    (destino / "2024" / "06" / "Saida").mkdir(parents=True)
    (destino / "2024" / "06" / "Saida" / "saida.xml").write_bytes(b"antigo")

    plano = montar_plano(origem, destino=destino)
    executar(plano, destino, destino / "m.jsonl", copiar=True, limpar_vazias=False)

    assert (destino / "2024" / "06" / "Saida" / "saida.xml").read_bytes() == b"antigo"
    assert (destino / "2024" / "06" / "Saida" / "saida (2).xml").is_file()
    assert (origem / "2021" / "notas" / "saida.xml").is_file()


def test_copia_interrompida_no_meio_nao_deixa_arquivo_no_destino(
    tmp_path: Path, monkeypatch, destino: Path
) -> None:
    """Cópia que falha depois de criar o alvo não pode deixar órfão.

    A reversão só apaga o que está no manifesto; um alvo truncado ficaria para
    sempre sem registro e sem volta.
    """
    origem = tmp_path / "notas"
    origem.mkdir()
    (origem / "nota.xml").write_bytes(nfe_xml())

    def copia_que_quebra(entrada, saida, *args, **kwargs):
        Path(saida).write_bytes(b"truncado")
        raise OSError("disco cheio")

    monkeypatch.setattr(shutil, "copy2", copia_que_quebra)
    plano = montar_plano(origem, destino=destino)
    resultado = executar(plano, destino, destino / "m.jsonl", copiar=True)

    assert resultado.movidos == 0
    assert len(resultado.falhas) == 1
    assert not list(destino.rglob("*.xml"))
    assert (origem / "nota.xml").is_file()


def test_copia_e_movimento_mesmos_destinos(origem: Path, destino: Path) -> None:
    """Trocar entre copiar e mover não pode mexer no plano.

    Por isso a opção fica fora do contexto da simulação: é a mesma organização
    de arquivos, só muda o que acontece com o original.
    """
    primeiro = montar_plano(origem, destino=destino)
    segundo = montar_plano(origem, destino=destino)
    assert [m.destino_relativo for m in primeiro.movimentos] == [
        m.destino_relativo for m in segundo.movimentos
    ]


def test_manifesto_antigo_sem_modo_reverte_como_movimento(tmp_path: Path) -> None:
    """Manifesto gerado antes da opção copiar precisa continuar legível.

    Quem tem execuções antigas na pasta `_relatorios` não pode perder a forma de
    desfazê-las, então ausência do campo significa o comportamento de sempre.
    """
    origem = tmp_path / "notas"
    origem.mkdir()
    (origem / "nota.xml").write_bytes(nfe_xml())
    destino = tmp_path / "destino"

    plano = montar_plano(origem, destino=destino)
    manifesto = destino / "m.jsonl"
    executar(plano, destino, manifesto, limpar_vazias=False)

    # simula o cabeçalho que o executor antigo escrevia, sem o campo "modo"
    linhas = manifesto.read_text(encoding="utf-8").splitlines()
    cabecalho = json.loads(linhas[0])
    cabecalho.pop("modo")
    assert "modo" not in cabecalho
    manifesto.write_text(
        "\n".join([json.dumps(cabecalho, ensure_ascii=False), *linhas[1:]]) + "\n",
        encoding="utf-8",
    )
    assert modo_manifesto(manifesto) == MODO_MOVER

    resultado = reverter(manifesto)

    assert resultado.falhas == []
    assert resultado.movidos == 1
    assert list(origem.rglob("*.xml")) == [origem / "nota.xml"]
    assert not list(destino.rglob("*.xml"))


def test_modo_manifesto_desconhecido_e_tratado_como_mover(tmp_path: Path) -> None:
    assert modo_manifesto(tmp_path / "nao-existe.jsonl") == MODO_MOVER
    assert modo_manifesto(tmp_path) == MODO_MOVER

    manifesto = tmp_path / "m.jsonl"
    manifesto.write_text("nao e json\n", encoding="utf-8")
    assert modo_manifesto(manifesto) == MODO_MOVER

    manifesto.write_text(
        json.dumps({"evento": "inicio", "modo": "inventado"}) + "\n", encoding="utf-8"
    )
    assert modo_manifesto(manifesto) == "inventado"

    manifesto.write_text(
        json.dumps({"evento": "inicio", "total": 3}) + "\n", encoding="utf-8"
    )
    assert modo_manifesto(manifesto) == MODO_MOVER


def test_copia_de_rar_e_descartada_na_reversao(tmp_path: Path) -> None:
    """RAR + cópia: a extração morre com a execução e a reversão só apaga a cópia.

    A checagem de extração tem de vir antes da de cópia: senão o arquivo seria
    contado como "cópia apagada" e o usuário receberia um aviso dizendo que o
    original continua na origem — o que é falso, ele está dentro do .rar.
    """
    extraido = tmp_path / "organizer_rar_abc123"
    extraido.mkdir(parents=True)
    (extraido / "nota.xml").write_bytes(nfe_xml())
    destino = tmp_path / "destino"

    plano = montar_plano(extraido, destino=destino)
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    executar(
        plano,
        destino,
        manifesto,
        contexto={"extracoes": [str(extraido)]},
        copiar=True,
        limpar_vazias=False,
    )
    assert list(destino.rglob("*.xml"))

    shutil.rmtree(extraido)

    resultado = reverter(manifesto)

    assert resultado.falhas == []
    assert resultado.movidos == len(plano.movimentos)
    assert not list(destino.rglob("*.xml"))
    assert not extraido.exists()
    assert any("RAR" in aviso for aviso in resultado.avisos)
    # não pode dizer que o original está na origem: quem guarda o arquivo é o .rar
    assert not any("originais continuam" in aviso for aviso in resultado.avisos)
