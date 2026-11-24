"""Aplicação do plano: move os arquivos e registra tudo para reversão."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .models import Movimento, Plano, ResultadoExecucao

MODO_MOVER = "mover"
MODO_COPIAR = "copiar"


def executar(
    plano: Plano,
    destino: Path,
    manifesto: Path,
    contexto: dict | None = None,
    progresso: Callable[[int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    limpar_vazias: bool = True,
    copiar: bool = False,
) -> ResultadoExecucao:
    resultado = ResultadoExecucao(manifesto=str(manifesto))
    destino.mkdir(parents=True, exist_ok=True)
    manifesto.parent.mkdir(parents=True, exist_ok=True)

    pastas_origem: set[str] = set()
    registro = manifesto.open("a", encoding="utf-8")
    try:
        cabecalho = {
            "evento": "inicio",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "destino": str(destino),
            "total": len(plano.movimentos),
            "modo": MODO_COPIAR if copiar else MODO_MOVER,
            "contexto": contexto or {},
        }
        registro.write(json.dumps(cabecalho, ensure_ascii=False) + "\n")

        for indice, movimento in enumerate(plano.movimentos, start=1):
            if cancelar and cancelar():
                resultado.cancelado = True
                break

            origem = Path(movimento.origem)
            alvo = destino / movimento.destino_relativo
            try:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if alvo.exists():
                    alvo = _nome_livre(alvo)
                if copiar:
                    _copiar(origem, alvo)
                else:
                    shutil.move(os.fspath(origem), os.fspath(alvo))
            except OSError as erro:
                try:
                    if alvo.exists() and alvo.is_file():
                        alvo.unlink()
                except OSError:
                    pass
                resultado.falhas.append((movimento.origem, str(erro)))
                continue

            movimento.nome_final = alvo.name
            movimento.destino_relativo = os.path.relpath(alvo, destino)
            pastas_origem.add(os.fspath(origem.parent))
            registro.write(
                json.dumps(
                    {
                        "evento": "movido",
                        "origem": movimento.origem,
                        "destino": os.fspath(alvo),
                        "digest": movimento.digest,
                        "tamanho": movimento.tamanho,
                        "categoria": movimento.categoria.value,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            resultado.movidos += 1
            if progresso and indice % 200 == 0:
                registro.flush()
                progresso(indice)
        if progresso:
            progresso(len(plano.movimentos))
    finally:
        registro.write(
            json.dumps(
                {
                    "evento": "fim",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "movidos": resultado.movidos,
                    "falhas": len(resultado.falhas),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        registro.close()

    # no modo copiar a origem continua cheia: não há pasta vazia para remover, e
    # limpar por engano apagaria o que o usuário pediu para preservar
    if limpar_vazias and resultado.movidos and not copiar:
        limpar_pastas_vazias(pastas_origem, proteger=destino)
    return resultado


def _copiar(origem: Path, alvo: Path) -> None:
    """Copia o arquivo sem deixar XML quebrado no destino.

    Copia para um arquivo temporário na mesma pasta e só promove ao nome final
    depois que a cópia termina. Se falhar no meio, o alvo final nunca aparece
    parcialmente escrito; só o temporário é removido.
    """
    temporario = alvo.with_name(f".{alvo.name}.organizer-tmp-{os.getpid()}")
    try:
        shutil.copy2(origem, temporario)
        os.replace(os.fspath(temporario), os.fspath(alvo))
    except BaseException:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def modo_manifesto(manifesto: Path) -> str:
    """Modo da execução que gerou o manifesto: `copiar` ou `mover`.

    O cabeçalho é a primeira linha, então um manifesto com centenas de milhares de
    movimentos é lido em O(1) só para mostrar o modo na tela de reversão.
    Manifesto antigo ou ilegível devolve `mover`, que é o que eles eram.
    """
    try:
        with Path(manifesto).open(encoding="utf-8") as arquivo:
            registro = json.loads(arquivo.readline())
    except (OSError, json.JSONDecodeError):
        return MODO_MOVER
    if not isinstance(registro, dict) or registro.get("evento") != "inicio":
        return MODO_MOVER
    return registro.get("modo") or MODO_MOVER


def _nome_livre(alvo: Path) -> Path:
    sufixo = 2
    while True:
        candidato = alvo.with_name(f"{alvo.stem} ({sufixo}){alvo.suffix}")
        if not candidato.exists():
            return candidato
        sufixo += 1


def limpar_pastas_vazias(pastas: set[str], proteger: Path | None = None) -> int:
    removidas = 0
    protegido = os.path.abspath(os.fspath(proteger)) if proteger else None
    for pasta in sorted(pastas, key=len, reverse=True):
        alvo = os.path.abspath(pasta)
        if protegido and (alvo == protegido or alvo.startswith(protegido + os.sep)):
            continue
        try:
            os.rmdir(alvo)
            removidas += 1
        except OSError:
            pass
    return removidas


def reverter(
    manifesto: Path,
    progresso: Callable[[int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    verificar_tamanho: bool = True,
) -> ResultadoExecucao:
    resultado = ResultadoExecucao(manifesto=str(manifesto))
    registros: list[dict] = []
    cabecalho: dict = {}

    with Path(manifesto).open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if registro.get("evento") == "inicio":
                cabecalho = registro
            elif registro.get("evento") == "movido":
                registros.append(registro)

    if not registros:
        raise ValueError(f"Manifesto sem movimentos: {manifesto}")

    # manifestos anteriores a opção copiar não têm o campo: eram só movimento
    copiar = cabecalho.get("modo") == MODO_COPIAR
    extracoes = _raiz_extracoes(cabecalho)
    descartados = 0
    apagados = 0
    pastas_destino: set[str] = set()
    for indice, registro in enumerate(registros, start=1):
        if cancelar and cancelar():
            resultado.cancelado = True
            break

        origem = Path(registro["origem"])
        atual = Path(registro["destino"])
        if not atual.exists():
            resultado.falhas.append(
                (os.fspath(atual), "Arquivo não está mais no destino; revertido nada")
            )
            continue
        if verificar_tamanho:
            tamanho_esperado = registro.get("tamanho")
            if (
                isinstance(tamanho_esperado, int)
                and tamanho_esperado >= 0
                and atual.stat().st_size != tamanho_esperado
            ):
                resultado.falhas.append(
                    (
                        os.fspath(atual),
                        f"Tamanho divergente ({atual.stat().st_size} != {tamanho_esperado}); "
                        "arquivo alterado depois, não revertido",
                    )
                )
                continue

        if _dentro_de(origem, extracoes):
            # veio de um .rar extraído: a pasta temporária já foi apagada e o
            # .rar segue intacto, então o certo é descartar a cópia organizada
            try:
                atual.unlink()
            except OSError as erro:
                resultado.falhas.append((os.fspath(atual), str(erro)))
                continue
            resultado.movidos += 1
            descartados += 1
            pastas_destino.add(os.fspath(atual.parent))
            if progresso and indice % 200 == 0:
                progresso(indice)
            continue

        if copiar:
            # o original continua na origem, então reverter é apagar a cópia —
            # devolver o arquivo produziria um duplicado na origem
            try:
                atual.unlink()
            except OSError as erro:
                resultado.falhas.append((os.fspath(atual), str(erro)))
                continue
            resultado.movidos += 1
            apagados += 1
            pastas_destino.add(os.fspath(atual.parent))
            if progresso and indice % 200 == 0:
                progresso(indice)
            continue

        try:
            origem.parent.mkdir(parents=True, exist_ok=True)
            if origem.exists():
                origem = _nome_livre(origem)
            shutil.move(os.fspath(atual), os.fspath(origem))
        except OSError as erro:
            resultado.falhas.append((os.fspath(atual), str(erro)))
            continue

        resultado.movidos += 1
        pastas_destino.add(os.fspath(atual.parent))
        if progresso and indice % 200 == 0:
            progresso(indice)

    if progresso:
        progresso(len(registros))

    destino_raiz = cabecalho.get("destino")
    if destino_raiz:
        limpar_pastas_vazias(pastas_destino, proteger=Path(destino_raiz))
    if descartados:
        resultado.avisos.append(
            f"{descartados} arquivo(s) de extração de RAR foram descartados: "
            "a cópia original continua dentro do .rar"
        )
    if apagados:
        resultado.avisos.append(
            f"{apagados} cópia(s) apagada(s) do destino: "
            "os originais continuam na pasta de origem"
        )
    return resultado


def _raiz_extracoes(cabecalho: dict) -> list[str]:
    contexto = cabecalho.get("contexto") or {}
    bruto = contexto.get("extracoes") or []
    if isinstance(bruto, str):
        bruto = [bruto]
    return [os.path.abspath(str(item)) for item in bruto]


def _dentro_de(caminho: Path, raizes: list[str]) -> bool:
    alvo = os.path.abspath(os.fspath(caminho))
    return any(alvo == raiz or alvo.startswith(raiz + os.sep) for raiz in raizes)
