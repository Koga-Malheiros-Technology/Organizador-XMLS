"""Fim a fim pela linha de comando.

O CLI não tinha nenhum teste: um atributo errado no argparse (`mover_` em vez
de `nao_mover_`) quebrava toda execução normal, e `--reverter` era inalcançável
porque `--origem/--destino/--cnpj` eram obrigatórios. Estes testes rodam o
`main()` de verdade, com código de saída.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import CNPJ_EMPRESA, CNPJ_FORNECEDOR, cfe_xml, nfe_xml

from organizer_xml.cli import main


@pytest.fixture
def base(tmp_path: Path) -> tuple[Path, Path]:
    origem = tmp_path / "origem"
    destino = tmp_path / "destino"
    (origem / "2021" / "notas").mkdir(parents=True)
    (origem / "2021" / "notas" / "a.xml").write_bytes(
        nfe_xml(emit=CNPJ_EMPRESA, dh_emi="2021-03-04T10:00:00-03:00")
    )
    (origem / "2021" / "notas" / "b.xml").write_bytes(
        nfe_xml(
            emit=CNPJ_FORNECEDOR,
            dest=CNPJ_EMPRESA,
            dh_emi="2021-03-05T10:00:00-03:00",
        )
    )
    (origem / "sped.txt").write_text("conteudo de SPED-EFD", encoding="utf-8")
    return origem, destino


def test_simulacao_nao_move_nada(base, capsys) -> None:
    origem, destino = base
    codigo = main(
        ["--origem", str(origem), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA, "--simular"]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "Simulação" in saida
    assert "Relatórios" in saida
    assert list(origem.rglob("*.xml")), "a simulação não pode mover arquivo"
    assert (destino / "_relatorios" / "movimentos.csv").is_file()
    assert (destino / "_relatorios" / "movimentos.json").is_file()


def test_execucao_move_e_reverte(base, capsys) -> None:
    origem, destino = base
    codigo = main(["--origem", str(origem), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA])
    assert codigo == 0

    movidos = sorted(p.name for p in destino.rglob("*.xml"))
    assert movidos == ["a.xml", "b.xml"]
    assert not list(origem.rglob("*.xml"))
    assert (origem / "sped.txt").is_file(), "SPED-EFD não pode ser tocado"
    assert not (destino / ".organizer_teste").exists()

    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    assert manifesto.is_file()

    # a linha de "Reversão" que o CLI imprime tem que ser executável de fato
    linha = next(
        linha
        for linha in capsys.readouterr().out.splitlines()
        if linha.startswith("Reversão:")
    )
    tokens = linha.split()
    assert tokens[:5] == ["Reversão:", "python", "-m", "organizer_xml", "--reverter"]
    codigo = main(tokens[4:])  # a partir de "--reverter"
    assert codigo == 0
    assert "Revertidos: 2" in capsys.readouterr().out
    assert sorted(p.name for p in origem.rglob("*.xml")) == ["a.xml", "b.xml"]
    assert not list(destino.rglob("*.xml"))


def test_cnpj_invalido_sai_com_erro(base, capsys) -> None:
    origem, destino = base
    codigo = main(["--origem", str(origem), "--destino", str(destino), "--cnpj", "11.111.111/1111-11"])
    assert codigo == 2
    assert "CNPJ inválido" in capsys.readouterr().err


def test_origem_inexistente(base, capsys) -> None:
    _, destino = base
    codigo = main(
        ["--origem", str(destino / "nao_existe"), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA]
    )
    assert codigo == 2
    assert "Origem não existe" in capsys.readouterr().err


def test_origem_igual_ao_destino(base, capsys) -> None:
    origem, _ = base
    codigo = main(["--origem", str(origem), "--destino", str(origem), "--cnpj", CNPJ_EMPRESA])
    assert codigo == 2
    assert "mesma pasta" in capsys.readouterr().err


def test_destino_dentro_da_origem(base, capsys) -> None:
    origem, _ = base
    codigo = main(
        ["--origem", str(origem), "--destino", str(origem / "2021" / "saida"), "--cnpj", CNPJ_EMPRESA]
    )
    assert codigo == 2
    assert "dentro da origem" in capsys.readouterr().err


def test_argumentos_obrigatorios_faltando(base) -> None:
    _, destino = base
    with pytest.raises(SystemExit) as erro:
        main(["--destino", str(destino)])
    assert erro.value.code == 2


def test_reverter_sem_manifesto(tmp_path, capsys) -> None:
    codigo = main(["--reverter", str(tmp_path / "nao_existe.jsonl")])
    assert codigo == 2
    assert "Manifesto não encontrado" in capsys.readouterr().err


def test_nao_mover_duplicados_e_nao_classificados(base, capsys) -> None:
    origem, destino = base
    (origem / "copia.xml").write_bytes(
        (origem / "2021" / "notas" / "a.xml").read_bytes()
    )
    (origem / "de_fora.xml").write_bytes(nfe_xml(emit=CNPJ_FORNECEDOR))
    codigo = main(
        [
            "--origem", str(origem),
            "--destino", str(destino),
            "--cnpj", CNPJ_EMPRESA,
            "--simular",
            "--nao-mover-duplicados",
            "--nao-mover-nao-classificados",
        ]
    )
    assert codigo == 0
    import json

    relatorio = json.loads(
        (destino / "_relatorios" / "movimentos.json").read_text(encoding="utf-8")
    )
    categorias = {m["categoria"] for m in relatorio["movimentos"]}
    assert "_Duplicados" not in categorias
    assert "_Nao_Classificados" not in categorias


def test_sat_no_cli(base, capsys) -> None:
    origem, destino = base
    (origem / "lote.xml").write_bytes(cfe_xml())
    codigo = main(["--origem", str(origem), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA])
    assert codigo == 0
    assert (destino / "2024" / "07" / "_CFE_SAT" / "lote.xml").is_file()


def test_copia_e_reverte(base, capsys) -> None:
    """`--copiar` organiza sem tocar na origem, e reverter apaga as cópias."""
    origem, destino = base
    codigo = main(
        ["--origem", str(origem), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA, "--copiar"]
    )
    assert codigo == 0

    saida = capsys.readouterr().out
    assert "Copiados: 2" in saida
    assert "Os originais continuam na pasta de origem." in saida
    assert sorted(p.name for p in destino.rglob("*.xml")) == ["a.xml", "b.xml"]
    assert sorted(p.name for p in origem.rglob("*.xml")) == ["a.xml", "b.xml"]

    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    import json

    assert json.loads(manifesto.read_text(encoding="utf-8").splitlines()[0])["modo"] == "copiar"

    linha = next(
        linha
        for linha in saida.splitlines()
        if linha.startswith("Reversão:")
    )
    codigo = main(linha.split()[4:])
    assert codigo == 0
    assert "Revertidos: 2" in capsys.readouterr().out
    assert not list(destino.rglob("*.xml"))
    # o original continua lá: reverter cópia apaga, não devolve
    assert sorted(p.name for p in origem.rglob("*.xml")) == ["a.xml", "b.xml"]


def test_copia_preserva_pastas_vazias_na_origem(base) -> None:
    """A limpeza de pastas vazias é do modo movimento; aqui não deve rodar."""
    origem, destino = base
    codigo = main(
        ["--origem", str(origem), "--destino", str(destino), "--cnpj", CNPJ_EMPRESA, "--copiar"]
    )
    assert codigo == 0
    assert (origem / "2021" / "notas").is_dir()
    assert list(origem.rglob("*.xml"))
