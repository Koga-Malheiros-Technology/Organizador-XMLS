"""Uso headless: útil para conferir a classificação antes de usar a interface."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .core.cnpj import problema, somente_digitos
from .core.executor import executar, reverter
from .core.planner import planejar
from .core.rar import (
    Sem7Zip,
    extrair_xmls,
    localizar,
    temporarios_criados,
    temporarios_limpos,
)
from .core.report import escrever_csv, escrever_json, resumo_textual
from .core.scanner import listar_arquivos


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organizer",
        description="Organiza XMLs de entrada e saída por ano e mês.",
    )
    # Não podem ser `required=True`: a reversão só precisa do manifesto.
    parser.add_argument("--origem", help="Pasta com os XMLs")
    parser.add_argument("--destino", help="Pasta de destino")
    parser.add_argument("--cnpj", help="CNPJ da empresa")
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Só simula: não move nada",
    )
    parser.add_argument(
        "--reverter",
        metavar="MANIFESTO",
        help="Desfaz uma execução a partir do arquivo de movimentos",
    )
    parser.add_argument("--profundidade", type=int, default=None)
    parser.add_argument(
        "--extrair-compactados",
        "--extrair-rar",
        dest="extrair_compactados",
        action="store_true",
        help="Extrai XMLs de .rar e .zip via 7-Zip antes de organizar",
    )
    parser.add_argument("--copiar", action="store_true", help="Copia em vez de mover")
    parser.add_argument("--nao-mover-duplicados", action="store_true")
    parser.add_argument("--nao-mover-nao-classificados", action="store_true")
    parser.add_argument("--relatorio", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    argumentos = parser.parse_args(argv)

    if argumentos.reverter:
        return _reverter(Path(argumentos.reverter))

    faltando = [
        nome
        for nome, valor in (
            ("--origem", argumentos.origem),
            ("--destino", argumentos.destino),
            ("--cnpj", argumentos.cnpj),
        )
        if not valor
    ]
    if faltando:
        parser.error(f"faltam argumentos obrigatórios: {', '.join(faltando)}")

    erro_cnpj = problema(argumentos.cnpj)
    if erro_cnpj:
        print(f"CNPJ inválido: {erro_cnpj}", file=sys.stderr)
        return 2

    origem = Path(argumentos.origem).expanduser().resolve()
    destino = Path(argumentos.destino).expanduser().resolve()
    if not origem.is_dir():
        print(f"Origem não existe ou não é pasta: {origem}", file=sys.stderr)
        return 2
    if destino == origem:
        print("Origem e destino são a mesma pasta.", file=sys.stderr)
        return 2
    if origem in destino.parents:
        print(
            "O destino está dentro da origem: os arquivos voltariam a ser "
            "lidos na próxima execução.",
            file=sys.stderr,
        )
        return 2
    if not os_pode_escrever(destino):
        print(f"Destino não pode ser gravado: {destino}", file=sys.stderr)
        return 2

    inicio = time.monotonic()
    varredura = listar_arquivos(
        origem,
        destino,
        profundidade=argumentos.profundidade,
    )
    print(
        f"Varredura: {len(varredura.fiscais):,} XML(s), "
        f"{len(varredura.compactados):,} compactado(s), "
        f"{varredura.nao_fiscais:,} outros em {time.monotonic() - inicio:.1f}s"
    )

    caminhos = list(varredura.fiscais)
    if argumentos.extrair_compactados and varredura.compactados:
        caminhos.extend(_extrair_compactados(varredura.compactados))

    with temporarios_limpos():
        return _organizar(
            argumentos, origem, destino, caminhos, time.monotonic()
        )


def _organizar(
    argumentos: argparse.Namespace,
    origem: Path,
    destino: Path,
    caminhos: list[str],
    inicio: float,
) -> int:
    plano = planejar(
        caminhos,
        argumentos.cnpj,
        progresso=_barra(len(caminhos)),
        mover_duplicados=not argumentos.nao_mover_duplicados,
        trabalhadores=argumentos.workers,
    )

    if argumentos.nao_mover_nao_classificados:
        antes = len(plano.movimentos)
        plano.movimentos = [
            movimento
            for movimento in plano.movimentos
            if movimento.categoria.value != "_Nao_Classificados"
        ]
        removidos = antes - len(plano.movimentos)
        if removidos:
            print(f"Ignorados por opção: {removidos:,} não classificado(s)")

    print()
    print(resumo_textual(plano, argumentos.cnpj))
    print(f"\nPlanejamento concluído em {time.monotonic() - inicio:.1f}s")

    destino_relatorio = argumentos.relatorio or (destino / "_relatorios")
    escrever_csv(plano, destino_relatorio / "movimentos.csv")
    escrever_json(
        plano,
        destino_relatorio / "movimentos.json",
        {
            "origem": str(origem),
            "destino": str(destino),
            "cnpj": somente_digitos(argumentos.cnpj),
        },
    )
    print(f"Relatórios: {destino_relatorio}")

    if argumentos.simular:
        print("\nSimulação: nenhum arquivo foi movido.")
        return 0

    if plano.movimentos:
        manifesto = destino_relatorio / "movimentos.jsonl"
        if manifesto.exists():
            marca = time.strftime("%Y%m%d-%H%M%S")
            manifesto = manifesto.with_name(f"movimentos-{marca}.jsonl")
        resultado = executar(
            plano,
            destino,
            manifesto,
            contexto={
                "cnpj": somente_digitos(argumentos.cnpj),
                "origem": str(origem),
                "extracoes": temporarios_criados(),
            },
            progresso=_barra(len(plano.movimentos)),
            copiar=argumentos.copiar,
        )
        verbo = "Copiados" if argumentos.copiar else "Movidos"
        resumo = f"\n{verbo}: {resultado.movidos:,} | Falhas: {len(resultado.falhas):,}"
        print(resumo.replace(",", "."))
        if argumentos.copiar:
            print("Os originais continuam na pasta de origem.")
        print(f"Reversão: python -m organizer_xml --reverter {manifesto}")
        for aviso in resultado.avisos:
            print(f"  AVISO {aviso}")
        for caminho, erro in resultado.falhas[:10]:
            print(f"  FALHA {caminho}: {erro}")
        return 1 if resultado.falhas else 0

    print("Nada a mover.")
    return 0


def _reverter(manifesto: Path) -> int:
    if not manifesto.is_file():
        print(f"Manifesto não encontrado: {manifesto}", file=sys.stderr)
        return 2
    resultado = reverter(manifesto)
    print(f"Revertidos: {resultado.movidos:,} | Falhas: {len(resultado.falhas):,}")
    for aviso in resultado.avisos:
        print(f"  AVISO {aviso}")
    for caminho, erro in resultado.falhas[:20]:
        print(f"  FALHA {caminho}: {erro}")
    return 1 if resultado.falhas else 0


def _extrair_compactados(compactados: list[str]) -> list[str]:
    if not localizar():
        print("AVISO: 7-Zip não encontrado; .rar/.zip ignorados.", file=sys.stderr)
        return []
    extraidos: list[str] = []
    for indice, arquivo in enumerate(compactados, start=1):
        try:
            extraidos.extend(extrair_xmls(arquivo))
        except (Sem7Zip, OSError) as erro:
            print(f"  Compactado ignorado {arquivo}: {erro}", file=sys.stderr)
        if indice % 20 == 0:
            print(f"  Compactado {indice}/{len(compactados)}")
    print(f"XMLs extraídos de .rar/.zip: {len(extraidos):,}")
    return extraidos


def _barra(total: int):
    if not total:
        return None
    inicio = time.monotonic()

    def reportar(feito: int) -> None:
        if not feito:
            return
        porcento = feito / total * 100
        decorrido = time.monotonic() - inicio
        taxa = feito / decorrido if decorrido else 0
        restante = (total - feito) / taxa if taxa else 0
        print(
            f"\r  {feito:,}/{total:,} ({porcento:5.1f}%) "
            f"{taxa:,.0f}/s  faltam {restante:,.0f}s".replace(",", "."),
            end="",
            flush=True,
        )
        if feito == total:
            print()

    return reportar


def os_pode_escrever(destino: Path) -> bool:
    try:
        destino.mkdir(parents=True, exist_ok=True)
        teste = destino / ".organizer_teste"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
    except OSError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
