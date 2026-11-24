"""A GUI é difícil de testar em CI, mas não pode quebrar na importação.

Estes testes sobem a janela de verdade (é a única forma de pegar erro de
atributo faltando) e verificam as regras que o usuário vê: sem CNPJ válido
nada anda, e Executar só liga depois de simular.

Cada teste cria a janela e destrói: duas raízes Tk simultâneas no mesmo
processo não são confiáveis, e a janela real do programa já é uma raiz.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from organizer_xml import config
from organizer_xml.core import rar
from organizer_xml.core.cnpj import mascara, problema, somente_digitos

tk = pytest.importorskip("tkinter")
from tkinter import messagebox  # noqa: E402

from organizer_xml.ui.app import (  # noqa: E402
    OrganizadorApp,
    caminho_chave,
    contar_movimentos,
)

CNPJ_VALIDO = "55.364.491/0001-41"
CNPJ_INVALIDO = "55.364.491/0001-42"
CNPJ_DIGITOS = "55364491000141"
FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.gui


def _criar_janela() -> "OrganizadorApp":
    """Abre a janela, com uma tentativa extra.

    Nesta máquina o Tcl do Python gerenciado pelo uv falha em ~1/3 das vezes
    ao ler o init.tcl quando o processo já fez bastante I/O (parece corrida de
    handle/antivírus no diretório tcl do Python): a janela é criada normalmente
    fora do pytest. Como a falha é transitória, uma segunda tentativa resolve;
    se as duas falharem, o teste é pulado com o motivo real.
    """
    ultimo: Exception | None = None
    for _ in range(2):
        try:
            return OrganizadorApp()
        except tk.TclError as erro:
            ultimo = erro
    pytest.skip(f"Tcl não pôde iniciar (transiente): {ultimo}")


@pytest.fixture
def app(tmp_path, monkeypatch):
    # a janela carrega e salva preferências em %APPDATA%; num teste isso não
    # pode encostar no arquivo real do usuário
    monkeypatch.setattr(config, "caminho_config", lambda: tmp_path / "config.json")
    # messagebox é modal e bloquearia o teste esperando clique de ninguém
    for nome in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, nome, lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    janela = _criar_janela()
    janela.withdraw()
    yield janela
    janela.destroy()


def _simular_de_verdade(app, tmp_path) -> None:
    """Roda uma simulação de verdade (thread + eventos) sobre uma pasta vazia."""
    (tmp_path / "origem").mkdir(exist_ok=True)
    app.origem_var.set(str(tmp_path / "origem"))
    app.destino_var.set(str(tmp_path / "destino"))
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()

    for _ in range(1000):
        app.update()
        if not app._ocupado():
            break
        time.sleep(0.01)
    assert not app._ocupado(), "a simulação não terminou a tempo"
    assert app.plano is not None, f"simulação não gerou plano: {app.status_var.get()}"


def mascarar_ao_digitar(valor: str) -> str:
    """Reproduz o que _ao_digitar_cnpj faz, sem depender de uma janela."""
    return mascara(somente_digitos(valor)[:14])


def test_mascara_e_aplicada_ao_digitar() -> None:
    assert mascarar_ao_digitar("55364491000141") == CNPJ_VALIDO
    assert mascarar_ao_digitar(CNPJ_VALIDO) == CNPJ_VALIDO
    assert mascarar_ao_digitar("abc") == ""
    assert mascarar_ao_digitar("5536449100014199999") == CNPJ_VALIDO


def test_cnpj_vazio_nao_e_aceito_por_problema() -> None:
    """`problema('')` devolve None: a validação tem de checar o tamanho."""
    assert problema("") is None
    assert somente_digitos("") == ""
    assert problema(CNPJ_VALIDO) is None
    assert problema(CNPJ_INVALIDO)


def test_contar_movimentos(tmp_path) -> None:
    manifesto = tmp_path / "m.jsonl"
    manifesto.write_text(
        '{"evento": "inicio"}\n'
        '{"evento": "movido", "origem": "a"}\n'
        '{"evento": "movido", "origem": "b"}\n'
        '{"evento": "fim"}\n',
        encoding="utf-8",
    )
    assert contar_movimentos(manifesto) == 2


def test_janela_monta_com_botoes_bloqueados(app) -> None:
    assert str(app.botao_simular["state"]) == "disabled"
    assert str(app.botao_executar["state"]) == "disabled"
    assert "obrigatório" in app.cnpj_status.get()


def test_cnpj_invalido_mantem_bloqueado(app) -> None:
    app.cnpj_var.set(CNPJ_INVALIDO)
    app._validar_cnpj()
    assert str(app.botao_simular["state"]) == "disabled"
    assert "inválido" in app.cnpj_status.get()


def test_executar_so_liga_apos_simulacao(app, tmp_path) -> None:
    app.cnpj_var.set(CNPJ_VALIDO)
    app._validar_cnpj()
    assert str(app.botao_simular["state"]) == "normal"
    assert str(app.botao_executar["state"]) == "disabled"

    _simular_de_verdade(app, tmp_path)
    assert str(app.botao_executar["state"]) == "normal"

    # trocar o CNPJ invalida o plano: não dá para executar o que foi simulado
    # com outro CNPJ, mesmo que o novo também seja válido
    app.cnpj_var.set("11.222.333/0001-81")
    app._validar_cnpj()
    assert app.plano is None
    assert str(app.botao_executar["state"]) == "disabled"

    app.cnpj_var.set(CNPJ_INVALIDO)
    app._validar_cnpj()
    assert str(app.botao_executar["state"]) == "disabled"


def test_mudar_opcao_invalida_o_plano(app, tmp_path) -> None:
    _simular_de_verdade(app, tmp_path)
    assert str(app.botao_executar["state"]) == "normal"

    # o plano já filtrou duplicatas e não classificados com a opção antiga
    app.duplicados_var.set(not bool(app.duplicados_var.get()))
    assert app.plano is None
    assert str(app.botao_executar["state"]) == "disabled"


def test_simulacao_descartada_se_o_contexto_mudar_durante(app, tmp_path) -> None:
    _simular_de_verdade(app, tmp_path)
    plano = app.plano

    # o usuário mexe na origem enquanto o worker ainda roda
    app.origem_var.set(str(tmp_path / "outra"))
    app._plano_pronto((plano, 5, "relatorios"))

    assert app.plano is None
    assert "descartada" in app.status_var.get()


@pytest.mark.parametrize("sufixo", ["\\", "/", "\\.", "/."])
def test_barra_final_no_campo_nao_descarta_a_simulacao(app, tmp_path, sufixo) -> None:
    """O Explorador entrega a pasta com barra final; isso não invalida o plano.

    O contexto congelado passa por `Path`, que normaliza a barra final, e o campo
    do usuário não. Sem normalizar os dois lados, toda simulação era descartada ao
    final — o usuário só via "Simulação descartada" e nenhum resultado.
    """
    (tmp_path / "origem").mkdir(exist_ok=True)
    app.origem_var.set(str(tmp_path / "origem") + sufixo)
    app.destino_var.set(str(tmp_path / "destino") + sufixo)
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()
    _esperar(app)

    assert app.plano is not None, f"simulação descartada: {app.status_var.get()}"
    assert str(app.botao_executar["state"]) == "normal"


def test_ponto_e_barra_final_ainda_invalida_o_plano(app, tmp_path) -> None:
    """A tolerância é só de forma: outra pasta de verdade continua invalidando."""
    origem = tmp_path / "origem"
    destino = tmp_path / "destino"
    origem.mkdir()
    app.cnpj_var.set(CNPJ_VALIDO)
    app.origem_var.set(str(origem))
    app.destino_var.set(str(destino))

    app._congelar_contexto(CNPJ_DIGITOS, str(origem), str(destino))
    assert app._contexto_preservado()

    # mesma pasta, escrita de outro jeito
    app.origem_var.set(str(origem) + "\\")
    assert app._contexto_preservado()

    # outra pasta, inclusive com a barra final
    app.origem_var.set(str(tmp_path / "outra") + "\\")
    assert not app._contexto_preservado()

    app.origem_var.set(str(origem))
    app.destino_var.set(str(tmp_path / "outro-destino") + "\\")
    assert not app._contexto_preservado()


def test_caminho_chave_normaliza_forma_mantem_pasta(tmp_path) -> None:
    pasta = tmp_path / "0Filial 01 LOJA 03 (no sistema da TECINCO e loja 01)"
    pasta.mkdir()
    bruto = str(pasta)
    assert caminho_chave(bruto + "\\") == caminho_chave(bruto)
    assert caminho_chave(bruto + "/") == caminho_chave(bruto)
    assert caminho_chave(bruto + "\\.") == caminho_chave(bruto)
    assert caminho_chave(bruto.upper()) == caminho_chave(bruto)
    assert caminho_chave(f"  {bruto}  ") == caminho_chave(bruto)
    # e pastas diferentes continuam diferentes
    assert caminho_chave(bruto) != caminho_chave(str(tmp_path / "outra"))
    assert caminho_chave("") == ""
    assert caminho_chave("   ") == ""


def test_digitar_aplica_mascara_na_janela(app) -> None:
    app.cnpj_var.set("55364491000141")
    app._ao_digitar_cnpj()
    assert app.cnpj_var.get() == CNPJ_VALIDO
    assert app.cnpj_status.get() == "CNPJ válido."


def test_esquecer_cnpj_limpa_o_campo(app) -> None:
    app.cnpj_var.set(CNPJ_VALIDO)
    app._validar_cnpj()
    app._esquecer_cnpj()
    assert app.cnpj_var.get() == ""
    assert str(app.botao_simular["state"]) == "disabled"
    assert str(app.botao_executar["state"]) == "disabled"


def _esperar(app) -> None:
    for _ in range(1000):
        app.update()
        if not app._ocupado():
            break
        time.sleep(0.01)
    assert not app._ocupado(), "o trabalho não terminou a tempo"


def _texto_log(app) -> str:
    return app.log.get("1.0", "end")


def _erros_dialogo(app, monkeypatch) -> list[str]:
    """Captura o que iria aparecer num `showerror` e devolve a lista."""
    vistos: list[str] = []
    monkeypatch.setattr(messagebox, "showerror", lambda titulo, texto, **k: vistos.append(texto))
    return vistos


def test_execucao_termina_sem_erro(app, tmp_path, monkeypatch) -> None:
    """Regressão: a execução terminava em `ERRO: name 'prog' is not defined`.

    `progresso` era definido no escopo de `_executar`, mas `prog` só existe como
    parâmetro de `tarefa`. Como `executar` só chama o callback no fim — depois de
    já ter copiado/movido tudo — os arquivos apareciam no destino e só então o
    erro subia. O usuário via "arquivos organizados" e um ERRO logo abaixo, e o
    plano continuava travado como se nada tivesse rodado.
    """
    erros = _erros_dialogo(app, monkeypatch)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(tmp_path / "destino"))
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()
    _esperar(app)
    assert app.plano is not None
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)

    app._executar()
    _esperar(app)

    assert erros == [], f"execução falhou: {_texto_log(app)}"
    assert "ERRO" not in _texto_log(app)
    # `_execucao_pronta` só roda no caminho de sucesso e é quem libera o plano
    assert app.plano is None
    assert "Concluído" in _texto_log(app)
    assert "1 movido(s)" in _texto_log(app)


def test_execucao_em_copia_termina_sem_erro(app, tmp_path, monkeypatch) -> None:
    """O mesmo caminho em modo cópia, que é o que o usuário estava usando."""
    erros = _erros_dialogo(app, monkeypatch)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(tmp_path / "destino"))
    app.cnpj_var.set(CNPJ_VALIDO)
    app.copiar_var.set(True)
    app._simular()
    _esperar(app)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)

    app._executar()
    _esperar(app)

    assert erros == [], f"execução falhou: {_texto_log(app)}"
    assert "ERRO" not in _texto_log(app)
    assert app.plano is None
    assert "1 copiado(s)" in _texto_log(app)


def test_reversao_termina_sem_erro(app, tmp_path, monkeypatch) -> None:
    """A reversão monta o callback de outro jeito; vale o mesmo rigor."""
    erros = _erros_dialogo(app, monkeypatch)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(tmp_path / "destino"))
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()
    _esperar(app)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    app._executar()
    _esperar(app)

    app._escolher_manifesto = lambda manifestos: manifestos[-1]
    app._reverter()
    _esperar(app)

    assert erros == [], f"reversão falhou: {_texto_log(app)}"
    assert "ERRO" not in _texto_log(app)
    assert "Revertido" in _texto_log(app)
    assert (origem / "2021" / "a.xml").is_file()


def test_ida_e_volta_pela_janela(app, tmp_path, monkeypatch) -> None:
    """Simular, executar e reverter pelas próprias funções da janela."""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    destino = tmp_path / "destino"
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")
    shutil.copy(FIXTURES / "nfe_devolucao.XML", origem / "2021" / "b.xml")
    sped = origem / "sped-efd.txt"
    sped.write_text("nao mover", encoding="utf-8")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(destino))
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()
    _esperar(app)

    assert app.plano is not None
    assert len(app.plano.movimentos) == 2
    # os relatórios são gravados pelo worker, antes de a janela reagir
    assert (destino / "_relatorios" / "movimentos.csv").is_file()
    assert (destino / "_relatorios" / "movimentos.json").is_file()
    assert sped.is_file()
    assert len(list(origem.rglob("*.xml"))) == 2

    app._executar()
    _esperar(app)

    assert not list(origem.rglob("*.xml"))
    assert sped.is_file()
    assert len(list(destino.rglob("*.xml"))) == 2
    manifesto = destino / "_relatorios" / "movimentos.jsonl"
    assert manifesto.is_file()

    app._escolher_manifesto = lambda manifestos: manifestos[-1]
    app._reverter()
    _esperar(app)

    assert sorted(p.name for p in origem.rglob("*.xml")) == ["a.xml", "b.xml"]
    assert not list(destino.rglob("*.xml"))


def test_mudar_para_copiar_nao_invalida_o_plano(app, tmp_path) -> None:
    """Copiar e mover organizam os mesmos arquivos nos mesmos lugares.

    Descartar a simulação aqui obrigaria o usuário a varrer a pasta de novo por
    causa de uma opção que não muda o plano.
    """
    _simular_de_verdade(app, tmp_path)
    assert str(app.botao_executar["state"]) == "normal"

    app.copiar_var.set(not bool(app.copiar_var.get()))

    assert app.plano is not None
    assert str(app.botao_executar["state"]) == "normal"


def test_confirmacao_de_execucao_avisa_que_a_origem_e_preservada(
    app, tmp_path, monkeypatch
) -> None:
    """O texto precisa dizer o que vai acontecer com o original antes de perguntar."""
    (tmp_path / "origem").mkdir()
    (tmp_path / "origem" / "a.xml").write_bytes(
        (FIXTURES / "nfe_saida_nfproc.XML").read_bytes()
    )
    app.origem_var.set(str(tmp_path / "origem"))
    app.destino_var.set(str(tmp_path / "destino"))
    app.cnpj_var.set(CNPJ_VALIDO)
    app._simular()
    _esperar(app)
    assert app.plano is not None

    perguntas: list[str] = []
    monkeypatch.setattr(
        messagebox, "askyesno", lambda titulo, texto, **k: perguntas.append(texto) or False
    )

    app.copiar_var.set(True)
    app._executar()

    assert len(perguntas) == 1
    assert "Copiar" in perguntas[0]
    assert "originais continuam na pasta de origem" in perguntas[0]

    perguntas.clear()
    app.copiar_var.set(False)
    app._executar()

    assert "Mover" in perguntas[0]
    assert "removidos da pasta de origem" in perguntas[0]


def test_ida_e_volta_em_copia_pela_janela(app, tmp_path, monkeypatch) -> None:
    """Copia pela janela, executa e reverte: o destino é limpo, a origem fica."""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    destino = tmp_path / "destino"
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")
    shutil.copy(FIXTURES / "nfe_devolucao.XML", origem / "2021" / "b.xml")
    antes = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}

    app.origem_var.set(str(origem))
    app.destino_var.set(str(destino))
    app.cnpj_var.set(CNPJ_VALIDO)
    app.copiar_var.set(True)
    app._simular()
    _esperar(app)
    assert app.plano is not None

    app._executar()
    _esperar(app)

    assert len(list(destino.rglob("*.xml"))) == 2
    # a origem continua com os mesmos arquivos, byte a byte
    depois = {caminho: caminho.read_bytes() for caminho in origem.rglob("*.xml")}
    assert depois == antes

    app._escolher_manifesto = lambda manifestos: manifestos[-1]
    app._reverter()
    _esperar(app)

    assert not list(destino.rglob("*.xml"))
    assert sorted(p.name for p in origem.rglob("*.xml")) == ["a.xml", "b.xml"]


def test_reversao_de_copia_avisa_que_apaga(app, tmp_path, monkeypatch) -> None:
    """Reverter uma cópia apaga arquivos; a janela precisa dizer isso."""
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    destino = tmp_path / "destino"
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(destino))
    app.cnpj_var.set(CNPJ_VALIDO)
    app.copiar_var.set(True)
    app._simular()
    _esperar(app)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    app._executar()
    _esperar(app)
    assert len(list(destino.rglob("*.xml"))) == 1

    perguntas: list[str] = []
    monkeypatch.setattr(
        messagebox, "askyesno", lambda titulo, texto, **k: perguntas.append(texto) or False
    )
    app._escolher_manifesto = lambda manifestos: manifestos[-1]
    app._reverter()

    assert len(perguntas) == 1
    assert "APAGAR" in perguntas[0]
    # recusou: a cópia continua no destino
    assert len(list(destino.rglob("*.xml"))) == 1


@pytest.mark.skipif(rar.localizar() is None, reason="7-Zip não instalado")
def test_ida_e_volta_com_rar(app, tmp_path, monkeypatch) -> None:
    """RAR dentro da janela: a extração vive até a execução e some depois."""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    origem = tmp_path / "origem"
    (origem / "2021").mkdir(parents=True)
    destino = tmp_path / "destino"
    shutil.copy(FIXTURES / "nfe_saida_nfproc.XML", origem / "2021" / "a.xml")

    # o 7-Zip gratuito não cria .rar, então monta-se um .zip e renomeia-se:
    # o que importa aqui é o nome, que é o que o scanner enxerga
    subprocess.run(
        [
            rar.localizar(),
            "a",
            "-y",
            str(tmp_path / "lote.zip"),
            str(origem / "2021" / "a.xml"),
        ],
        check=True,
        capture_output=True,
    )
    shutil.move(str(tmp_path / "lote.zip"), origem / "lote.rar")

    app.origem_var.set(str(origem))
    app.destino_var.set(str(destino))
    app.cnpj_var.set(CNPJ_VALIDO)
    app.rar_var.set(True)
    app._simular()
    _esperar(app)

    # uma cópia da origem + a cópia idêntica de dentro do .rar
    assert len(app.plano.movimentos) == 2
    assert rar.temporarios_criados(), "a extração precisa sobreviver até a execução"

    app._executar()
    _esperar(app)
    assert rar.temporarios_criados() == [], "a execução tem que limpar a extração"

    app._escolher_manifesto = lambda manifestos: manifestos[-1]
    app._reverter()
    _esperar(app)

    assert (origem / "2021" / "a.xml").is_file()
    assert (origem / "lote.rar").is_file()
    assert not list(destino.rglob("*.xml"))
    # o que veio do RAR não volta para a temporária: o .rar é a cópia original
    assert not list(Path(tempfile.gettempdir()).glob("organizer_rar_*"))


def test_trocar_pasta_invalida_o_plano(app, tmp_path) -> None:
    _simular_de_verdade(app, tmp_path)
    assert str(app.botao_executar["state"]) == "normal"

    # digitar outra origem descarta a simulação anterior
    app.origem_var.set(str(tmp_path / "outra-origem"))
    assert app.plano is None
    assert str(app.botao_executar["state"]) == "disabled"

    _simular_de_verdade(app, tmp_path)
    assert str(app.botao_executar["state"]) == "normal"
    app.destino_var.set(str(tmp_path / "outro-destino"))
    assert app.plano is None
    assert str(app.botao_executar["state"]) == "disabled"
