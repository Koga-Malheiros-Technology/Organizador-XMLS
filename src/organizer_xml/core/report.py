"""Geração dos relatórios de simulação e execução."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .cnpj import mascara
from .models import Plano

CAMPOS_CSV = (
    "categoria",
    "ano",
    "mes",
    "emit_cnpj",
    "dest_cnpj",
    "chave",
    "valor",
    "motivo",
    "origem",
    "destino",
)


def escrever_csv(plano: Plano, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS_CSV, delimiter=";")
        escritor.writeheader()
        for movimento in plano.movimentos:
            escritor.writerow(
                {
                    "categoria": movimento.categoria.value,
                    "ano": movimento.ano or "",
                    "mes": f"{movimento.mes:02d}" if movimento.mes else "",
                    "emit_cnpj": mascara(movimento.emit_cnpj)
                    if movimento.emit_cnpj
                    else "",
                    "dest_cnpj": mascara(movimento.dest_cnpj)
                    if movimento.dest_cnpj
                    else "",
                    "chave": movimento.chaves[0] if movimento.chaves else "",
                    "valor": f"{movimento.valor:.2f}" if movimento.valor else "",
                    "motivo": movimento.motivo,
                    "origem": movimento.origem,
                    "destino": movimento.destino_relativo,
                }
            )
    return caminho


def escrever_json(plano: Plano, caminho: Path, contexto: dict | None = None) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "contexto": contexto or {},
        "resumo": {
            "total": len(plano.movimentos),
            "por_categoria": plano.por_categoria(),
            "ignorados": plano.ignorados,
            "cnpjs_de_terceiros": plano.cnpjs_terceiros,
        },
        "por_ano_mes": [
            {
                "ano": ano,
                "mes": mes,
                "categorias": categorias,
                "valores": {
                    nome: round(valor, 2)
                    for nome, valor in plano.por_ano_mes_valor()
                    .get((ano, mes), {})
                    .items()
                },
            }
            for (ano, mes), categorias in plano.por_ano_mes().items()
        ],
        "movimentos": [
            {
                "categoria": movimento.categoria.value,
                "ano": movimento.ano,
                "mes": movimento.mes,
                "motivo": movimento.motivo,
                "emit_cnpj": movimento.emit_cnpj,
                "dest_cnpj": movimento.dest_cnpj,
                "chaves": list(movimento.chaves),
                "valor": movimento.valor,
                "tamanho": movimento.tamanho,
                "origem": movimento.origem,
                "destino": movimento.destino_relativo,
            }
            for movimento in plano.movimentos
        ],
    }
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho


def resumo_textual(plano: Plano, cnpj_empresa: str) -> str:
    linhas = [
        f"CNPJ informado: {mascara(cnpj_empresa)}",
        f"Total de arquivos a mover: {len(plano.movimentos):,}".replace(",", "."),
        "",
        "Por categoria:",
    ]
    for categoria, quantidade in sorted(
        plano.por_categoria().items(), key=lambda par: -par[1]
    ):
        linhas.append(f"  {categoria:<22} {quantidade:>9,}".replace(",", "."))

    linhas.append("")
    linhas.append("Por ano/mês:")
    for (ano, mes), categorias in plano.por_ano_mes().items():
        total = sum(categorias.values())
        detalhe = ", ".join(f"{nome}={qtd}" for nome, qtd in sorted(categorias.items()))
        linhas.append(f"  {ano}-{mes}: {total:>7,}  ({detalhe})".replace(",", "."))

    if plano.cnpjs_terceiros:
        linhas.append("")
        linhas.append("CNPJs de terceiros encontrados:")
        for cnpj, quantidade in plano.cnpjs_terceiros.items():
            linhas.append(f"  {cnpj}  {quantidade:,} documento(s)".replace(",", "."))

    if plano.erros:
        linhas.append("")
        linhas.append(f"Erros de leitura: {len(plano.erros)}")
        for origem, erro in plano.erros[:10]:
            linhas.append(f"  {origem}: {erro}")

    return "\n".join(linhas)
