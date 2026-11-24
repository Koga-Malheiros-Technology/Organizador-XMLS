"""Estruturas de dados compartilhadas entre varredura, classificação e execução."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Categoria(str, Enum):
    ENTRADA = "Entrada"
    SAIDA = "Saida"
    DEVOLUCAO = "_Devolucoes"
    CFE_SAT = "_CFE_SAT"
    DUPLICADO = "_Duplicados"
    NAO_CLASSIFICADO = "_Nao_Classificados"


class TipoDocumento(str, Enum):
    NFE = "nfe"
    CFE_LOTE = "cfe_lote"
    NFSE = "nfse"
    DESCONHECIDO = "desconhecido"
    INVALIDO = "invalido"


@dataclass(slots=True)
class ItemDocumento:
    origem: str
    tamanho: int
    digest: str
    tipo: TipoDocumento = TipoDocumento.DESCONHECIDO
    modelo: str | None = None
    emit_cnpj: str | None = None
    emit_cnpjs: tuple[str, ...] = ()
    emit_nome: str | None = None
    dest_cnpj: str | None = None
    dest_cpf: str | None = None
    dest_nome: str | None = None
    serie: str | None = None
    numero: str | None = None
    tp_nf: int | None = None
    nat_op: str | None = None
    chaves: tuple[str, ...] = ()
    data: date | None = None
    valor: float | None = None
    erro: str | None = None


@dataclass(slots=True)
class Decisao:
    categoria: Categoria
    ano: int | None
    mes: int | None
    motivo: str
    sem_data: bool = False


@dataclass(slots=True)
class Movimento:
    origem: str
    nome: str
    categoria: Categoria
    ano: int | None
    mes: int | None
    motivo: str
    tamanho: int
    digest: str
    chaves: tuple[str, ...] = ()
    emit_cnpj: str | None = None
    dest_cnpj: str | None = None
    valor: float | None = None
    destino_relativo: str = ""
    nome_final: str = ""


@dataclass(slots=True)
class Plano:
    movimentos: list[Movimento] = field(default_factory=list)
    erros: list[tuple[str, str]] = field(default_factory=list)
    ja_organizados: int = 0
    ignorados: int = 0
    cnpjs_terceiros: dict[str, int] = field(default_factory=dict)

    def por_categoria(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for movimento in self.movimentos:
            contagem[movimento.categoria.value] = (
                contagem.get(movimento.categoria.value, 0) + 1
            )
        return contagem

    def por_ano_mes(self) -> dict[tuple[str, str], dict[str, int]]:
        agrupado: dict[tuple[str, str], dict[str, int]] = {}
        for movimento in self.movimentos:
            chave = (
                str(movimento.ano or "----"),
                f"{movimento.mes:02d}" if movimento.mes else "--",
            )
            linha = agrupado.setdefault(chave, {})
            linha[movimento.categoria.value] = (
                linha.get(movimento.categoria.value, 0) + 1
            )
        return dict(sorted(agrupado.items()))

    def por_ano_mes_valor(self) -> dict[tuple[str, str], dict[str, float]]:
        agrupado: dict[tuple[str, str], dict[str, float]] = {}
        for movimento in self.movimentos:
            chave = (
                str(movimento.ano or "----"),
                f"{movimento.mes:02d}" if movimento.mes else "--",
            )
            linha = agrupado.setdefault(chave, {})
            categoria = movimento.categoria.value
            linha[categoria] = linha.get(categoria, 0.0) + (movimento.valor or 0.0)
        return dict(sorted(agrupado.items()))


@dataclass(slots=True)
class ResultadoExecucao:
    movidos: int = 0
    ignorados: int = 0
    falhas: list[tuple[str, str]] = field(default_factory=list)
    manifesto: str | None = None
    cancelado: bool = False
    avisos: list[str] = field(default_factory=list)
