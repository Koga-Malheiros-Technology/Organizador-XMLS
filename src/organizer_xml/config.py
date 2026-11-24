"""Persistência das preferências do programa (CNPJ lembrado e últimas pastas)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .core.cnpj import mascara, somente_digitos

NOME_APP = "OrganizerXML"


def caminho_config() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / NOME_APP / "config.json"


@dataclass
class Preferencias:
    cnpj: str = ""
    lembrar_cnpj: bool = True
    origem: str = ""
    destino: str = ""
    extrair_rar: bool = False
    copiar: bool = False
    mover_duplicados: bool = True
    mover_nao_classificados: bool = True
    workers: int | None = None


def carregar() -> Preferencias:
    arquivo = caminho_config()
    if not arquivo.is_file():
        return Preferencias()
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Preferencias()
    conhecidos = {campo for campo in Preferencias.__dataclass_fields__}
    return Preferencias(**{k: v for k, v in dados.items() if k in conhecidos})


def salvar(preferencias: Preferencias) -> Path:
    arquivo = caminho_config()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = asdict(preferencias)
    dados["cnpj"] = somente_digitos(preferencias.cnpj) if preferencias.lembrar_cnpj else ""
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return arquivo


def esquecer_cnpj() -> None:
    arquivo = caminho_config()
    if not arquivo.is_file():
        return
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    dados["cnpj"] = ""
    dados["lembrar_cnpj"] = False
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cnpj_mascarado(valor: str) -> str:
    return mascara(somente_digitos(valor))
