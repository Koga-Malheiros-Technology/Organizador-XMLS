from __future__ import annotations

import json
from pathlib import Path

from organizer_xml import config
from organizer_xml.config import Preferencias


def test_lembrar_cnpj_so_salva_se_marcado(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "caminho_config", lambda: destino)

    config.salvar(Preferencias(cnpj="55364491000141", lembrar_cnpj=True))
    assert json.loads(destino.read_text(encoding="utf-8"))["cnpj"] == "55364491000141"
    assert config.carregar().cnpj == "55364491000141"

    config.salvar(Preferencias(cnpj="55364491000141", lembrar_cnpj=False))
    assert config.carregar().cnpj == ""
    assert config.carregar().lembrar_cnpj is False


def test_esquecer_cnpj_apaga_o_lembrado(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "caminho_config", lambda: destino)
    config.salvar(Preferencias(cnpj="55364491000141", lembrar_cnpj=True))

    config.esquecer_cnpj()
    assert config.carregar().cnpj == ""
    assert config.carregar().lembrar_cnpj is False
    # as outras preferências continuam salvas
    assert config.carregar().destino == ""


def test_config_inexistente_devolve_padrao(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "caminho_config", lambda: tmp_path / "nao_existe.json")
    preferencias = config.carregar()
    assert preferencias.cnpj == ""
    assert preferencias.mover_duplicados is True
    # mover continua sendo o padrão: quem já usa o programa não troca de
    # comportamento sem pedir
    assert preferencias.copiar is False


def test_preferencia_copiar_passa_pelo_arquivo(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "caminho_config", lambda: destino)

    config.salvar(Preferencias(copiar=True))
    assert json.loads(destino.read_text(encoding="utf-8"))["copiar"] is True
    assert config.carregar().copiar is True


def test_config_antigo_sem_copiar_nao_quebra(tmp_path: Path, monkeypatch) -> None:
    """Arquivo de configuração anterior ao recurso continua carregando."""
    destino = tmp_path / "cfg.json"
    destino.write_text(
        json.dumps({"cnpj": "55364491000141", "extrair_rar": True}), encoding="utf-8"
    )
    monkeypatch.setattr(config, "caminho_config", lambda: destino)

    preferencias = config.carregar()
    assert preferencias.cnpj == "55364491000141"
    assert preferencias.extrair_rar is True
    assert preferencias.copiar is False


def test_config_corrompido_nao_quebra(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "cfg.json"
    destino.write_text("{ isso nao e json", encoding="utf-8")
    monkeypatch.setattr(config, "caminho_config", lambda: destino)
    assert config.carregar().cnpj == ""


def test_campos_desconhecidos_sao_ignorados(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "cfg.json"
    destino.write_text(
        json.dumps({"cnpj": "55364491000141", "campo_do_futuro": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "caminho_config", lambda: destino)
    assert config.carregar().cnpj == "55364491000141"


def test_cnpj_mascarado() -> None:
    assert config.cnpj_mascarado("55364491000141") == "55.364.491/0001-41"
    assert config.cnpj_mascarado("") == ""
