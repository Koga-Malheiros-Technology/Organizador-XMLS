"""Janela principal do OrganizadorXML.

Regras de interface que não podem quebrar:
- o CNPJ é sempre a chave: sem ele (vazio ou inválido) Simular e Executar ficam
  desligados, mas "Detectar CNPJs" continua disponível;
- Simular e Executar são as únicas ações que demoram, e ambas rodam em uma
  thread para a janela não congelar;
- Executar só fica disponível depois de uma simulação do mesmo CNPJ.

Tkinter só pode ser tocado pela thread principal: por isso as opções das
caixas de seleção são copiadas para `self._opcoes` antes de abrir a thread, e
nenhuma variável do Tk é lida de dentro dela.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import config
from ..core.amostra import AMOSTRA_PADRAO, detectar_cnpjs, tamanho_amostra
from ..core.cnpj import mascara, problema, somente_digitos
from ..core.executor import MODO_COPIAR, executar, modo_manifesto, reverter
from ..core.planner import planejar
from ..core.rar import (
    Sem7Zip,
    extrair_xmls,
    localizar,
    temporarios_criados,
    temporarios_limpos,
)
from ..core.report import escrever_csv, escrever_json, resumo_textual
from ..core.scanner import listar_arquivos
from . import icone as ui_icone

NOME_PASTA_RELATORIOS = "_relatorios"


class Trabalho(threading.Thread):
    """Executa uma tarefa longa fora da thread da interface.

    A função recebe (notificar, cancelado) e devolve o resultado; qualquer
    exceção é repassada à janela em vez de morrer em silêncio.
    """

    def __init__(
        self,
        nome: str,
        funcao: Callable[[Callable[[float], None], Callable[[], bool]], object],
        eventos: queue.Queue,
    ) -> None:
        super().__init__(name=nome, daemon=True)
        self.funcao = funcao
        self.eventos = eventos
        self.cancelamento = threading.Event()
        self.resultado: object = None
        self.erro: BaseException | None = None

    def run(self) -> None:
        try:
            self.resultado = self.funcao(self._notificar, self.cancelamento.is_set)
        except BaseException as erro:  # noqa: BLE001 - repassado para a interface
            self.erro = erro
        finally:
            self.eventos.put(("fim", self))

    def _notificar(self, porcento: float) -> None:
        self.eventos.put(("progresso", float(porcento)))


class OrganizadorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Organizador de XMLs Fiscais")
        self.geometry("940x680")
        self.minsize(880, 620)
        self._aplicar_icone()

        self.preferencias = config.carregar()
        self.plano = None
        self._contexto_plano: tuple | None = None
        self._contexto_simulacao: tuple | None = None
        self.trabalho: Trabajo | None = None
        self.eventos: queue.Queue = queue.Queue()
        self._ao_terminar: Callable[[object], None] = lambda _resultado: None
        self._mascarando = False
        self._total_esperado = 0

        self.cnpj_var = tk.StringVar(value=config.cnpj_mascarado(self.preferencias.cnpj))
        self.lembrar_var = tk.BooleanVar(value=self.preferencias.lembrar_cnpj)
        self.origem_var = tk.StringVar(value=self.preferencias.origem)
        self.destino_var = tk.StringVar(value=self.preferencias.destino)
        self.rar_var = tk.BooleanVar(value=self.preferencias.extrair_rar)
        self.copiar_var = tk.BooleanVar(value=self.preferencias.copiar)
        self.duplicados_var = tk.BooleanVar(value=self.preferencias.mover_duplicados)
        self.nao_classificados_var = tk.BooleanVar(
            value=self.preferencias.mover_nao_classificados
        )
        self.cnpj_status = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto.")
        self.progresso_var = tk.DoubleVar(value=0.0)

        self._opcoes = self._ler_opcoes()
        self._montar()
        self._validar_cnpj()
        self.cnpj_entry.focus_set()

    # ------------------------------------------------------------------ janela

    def _aplicar_icone(self) -> None:
        """Usa o ícone do programa na janela e na barra de tarefas.

        Sem o arquivo (instalação por pip, por exemplo) a janela fica com o
        ícone padrão do Tk — nenhuma mensagem, porque isso não impede o uso.
        """
        caminho = ui_icone.caminho()
        if caminho is None:
            return
        try:
            self.iconbitmap(default=str(caminho))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ layout

    def _montar(self) -> None:
        raiz = ttk.Frame(self, padding=12)
        raiz.pack(fill="both", expand=True)

        empresa = ttk.LabelFrame(raiz, text="Empresa", padding=10)
        empresa.pack(fill="x")
        ttk.Label(empresa, text="CNPJ:").grid(row=0, column=0, sticky="w")
        self.cnpj_entry = ttk.Entry(
            empresa, textvariable=self.cnpj_var, width=22, justify="left"
        )
        self.cnpj_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        self.cnpj_entry.bind("<KeyRelease>", self._ao_digitar_cnpj)
        self.cnpj_entry.bind("<FocusOut>", lambda _e: self._validar_cnpj())
        ttk.Checkbutton(
            empresa, text="Lembrar CNPJ", variable=self.lembrar_var
        ).grid(row=0, column=2, sticky="w")
        ttk.Button(
            empresa, text="Esquecer salvo", command=self._esquecer_cnpj
        ).grid(row=0, column=3, sticky="w", padx=8)
        self.botao_detectar = ttk.Button(
            empresa, text="Detectar CNPJs", command=self._detectar
        )
        self.botao_detectar.grid(row=0, column=4, sticky="e")
        ttk.Label(
            empresa, textvariable=self.cnpj_status, foreground="#666666"
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        pastas = ttk.LabelFrame(raiz, text="Pastas", padding=10)
        pastas.pack(fill="x", pady=(10, 0))
        ttk.Label(pastas, text="Origem:").grid(row=0, column=0, sticky="w")
        ttk.Entry(pastas, textvariable=self.origem_var).grid(
            row=0, column=1, sticky="ew", padx=8
        )
        ttk.Button(
            pastas, text="Selecionar", command=lambda: self._escolher("origem")
        ).grid(row=0, column=2)
        ttk.Label(pastas, text="Destino:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(pastas, textvariable=self.destino_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0)
        )
        ttk.Button(
            pastas, text="Selecionar", command=lambda: self._escolher("destino")
        ).grid(row=1, column=2, pady=(8, 0))
        pastas.columnconfigure(1, weight=1)

        opcoes = ttk.LabelFrame(raiz, text="Opções", padding=10)
        opcoes.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            opcoes,
            text="Extrair arquivos .rar/.zip antes (usa 7-Zip)",
            variable=self.rar_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            opcoes,
            text="Mover duplicatas para _Duplicados",
            variable=self.duplicados_var,
        ).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(
            opcoes, text="Mover não classificados", variable=self.nao_classificados_var
        ).grid(row=0, column=2, sticky="w")
        # a cópia não muda o plano (os mesmos arquivos vão para os mesmos
        # lugares), então fica fora de `_ler_opcoes`: dá para simular uma vez e
        # escolher entre copiar e mover na hora de executar
        self.caixa_copiar = ttk.Checkbutton(
            opcoes,
            text="Copiar em vez de mover (os originais continuam na origem)",
            variable=self.copiar_var,
        )
        self.caixa_copiar.grid(row=1, column=0, sticky="w", pady=(8, 0))

        acoes = ttk.Frame(raiz)
        acoes.pack(fill="x", pady=(10, 0))
        self.botao_simular = ttk.Button(acoes, text="Simular", command=self._simular)
        self.botao_simular.pack(side="left")
        self.botao_executar = ttk.Button(acoes, text="Executar", command=self._executar)
        self.botao_executar.pack(side="left", padx=8)
        self.botao_reverter = ttk.Button(
            acoes, text="Reverter última execução", command=self._reverter
        )
        self.botao_reverter.pack(side="left")
        self.botao_cancelar = ttk.Button(
            acoes, text="Cancelar", command=self._cancelar, state="disabled"
        )
        self.botao_cancelar.pack(side="right")

        ttk.Progressbar(raiz, variable=self.progresso_var, maximum=100.0).pack(
            fill="x", pady=(10, 0)
        )
        ttk.Label(raiz, textvariable=self.status_var, foreground="#333333").pack(
            fill="x", pady=(4, 8)
        )

        self.log = tk.Text(raiz, wrap="word", height=22, state="disabled")
        barralho = ttk.Scrollbar(raiz, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=barralho.set)
        barralho.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        # trocar origem ou destino (inclusive digitando) invalida a simulação:
        # um plano calculado para uma pasta não pode ser executado em outra
        self.origem_var.trace_add("write", self._ao_mudar_pasta)
        self.destino_var.trace_add("write", self._ao_mudar_pasta)
        # o mesmo vale para as opções: o plano já filtrou duplicatas e não
        # classificados com base nelas
        for variavel in (
            self.rar_var,
            self.duplicados_var,
            self.nao_classificados_var,
        ):
            variavel.trace_add("write", self._ao_mudar_opcao)

    def _descartar_plano(self) -> None:
        """Esquece a simulação: o plano não vale mais para o contexto atual."""
        self.plano = None
        self._contexto_plano = None

    def _congelar_contexto(self, cnpj: str, origem: str, destino: str) -> None:
        self._descartar_plano()
        self._contexto_simulacao = (
            cnpj,
            caminho_chave(origem),
            caminho_chave(destino),
            dict(self._opcoes),
        )

    def _ao_mudar_pasta(self, *_args: object) -> None:
        self._descartar_plano()
        self._ajustar_botoes(self._cnpj_valido())

    def _ao_mudar_opcao(self, *_args: object) -> None:
        self._descartar_plano()
        self._ajustar_botoes(self._cnpj_valido())

    # ------------------------------------------------------------------- CNPJ

    def _ao_digitar_cnpj(self, _evento: object = None) -> None:
        if self._mascarando:
            return
        formatado = mascara(somente_digitos(self.cnpj_var.get())[:14])
        if formatado != self.cnpj_var.get():
            self._mascarando = True
            self.cnpj_var.set(formatado)
            self.cnpj_entry.icursor("end")
            self._mascarando = False
        self._validar_cnpj()

    def _cnpj_atual(self) -> str:
        return somente_digitos(self.cnpj_var.get())

    def _cnpj_valido(self) -> bool:
        """Um CNPJ só vale com os 14 dígitos certos: `problema('')` não acusa nada."""
        digitos = self._cnpj_atual()
        return len(digitos) == 14 and problema(self.cnpj_var.get()) is None

    def _validar_cnpj(self) -> None:
        if not self._cnpj_atual():
            self.cnpj_status.set("Informe o CNPJ da empresa (obrigatório).")
        elif not self._cnpj_valido():
            self.cnpj_status.set(problema(self.cnpj_var.get()) or "CNPJ inválido.")
        else:
            self.cnpj_status.set("CNPJ válido.")
        # o plano é de um CNPJ específico: simular para um e executar para outro
        # organizaria os arquivos pela empresa errada
        if self._contexto_plano is not None and self._contexto_plano[0] != self._cnpj_atual():
            self._descartar_plano()
            self._registrar("CNPJ mudou: simule de novo antes de executar.")
        self._ajustar_botoes(self._cnpj_valido())

    def _ajustar_botoes(self, cnpj_valido: bool) -> None:
        livre = cnpj_valido and not self._ocupado()
        self.botao_simular.configure(state="normal" if livre else "disabled")
        self.botao_executar.configure(
            state="normal" if livre and self._pode_executar() else "disabled"
        )
        self.botao_reverter.configure(state="disabled" if self._ocupado() else "normal")
        # só um trabalho por vez: dois workers trocariam self.trabalho e
        # misturariam os eventos de simulação com os de execução
        self.botao_detectar.configure(
            state="normal" if not self._ocupado() else "disabled"
        )

    def _pode_executar(self) -> bool:
        if self.plano is None or self._contexto_plano is None:
            return False
        return self._contexto_preservado(self._contexto_plano)

    def _contexto_preservado(self, contexto: tuple | None = None) -> bool:
        """O contexto do plano ainda é o que está na tela?"""
        if contexto is None:
            contexto = self._contexto_simulacao
        if contexto is None:
            return False
        cnpj, origem, destino, opcoes = contexto
        atual = (
            self._cnpj_atual(),
            caminho_chave(self.origem_var.get()),
            caminho_chave(self.destino_var.get()),
            self._ler_opcoes(),
        )
        return (cnpj, origem, destino, dict(opcoes)) == atual

    def _esquecer_cnpj(self) -> None:
        config.esquecer_cnpj()
        self.cnpj_var.set("")
        self.lembrar_var.set(False)
        self.plano = None
        self._validar_cnpj()
        self._registrar("CNPJ salvo foi apagado.")

    def _ler_opcoes(self) -> dict[str, bool]:
        """Cópia das opções lidas na thread principal."""
        return {
            "compactados": bool(self.rar_var.get()),
            "duplicados": bool(self.duplicados_var.get()),
            "nao_classificados": bool(self.nao_classificados_var.get()),
        }

    def _salvar_preferencias(self) -> None:
        self.preferencias.cnpj = somente_digitos(self.cnpj_var.get())
        self.preferencias.lembrar_cnpj = self.lembrar_var.get()
        self.preferencias.origem = self.origem_var.get()
        self.preferencias.destino = self.destino_var.get()
        self.preferencias.extrair_rar = self.rar_var.get()
        self.preferencias.copiar = self.copiar_var.get()
        self.preferencias.mover_duplicados = self.duplicados_var.get()
        self.preferencias.mover_nao_classificados = self.nao_classificados_var.get()
        config.salvar(self.preferencias)

    # ------------------------------------------------------------------ pastas

    def _escolher(self, alvo: str) -> None:
        variavel = self.origem_var if alvo == "origem" else self.destino_var
        escolhida = filedialog.askdirectory(
            title="Selecione a pasta com os XMLs" if alvo == "origem" else "Selecione o destino",
            initialdir=variavel.get() or None,
            mustexist=(alvo == "origem"),
        )
        if escolhida:
            variavel.set(escolhida)
            self.plano = None
            self._validar_cnpj()

    def _entradas(self) -> tuple[Path, Path, str] | None:
        if not self._cnpj_valido():
            messagebox.showwarning(
                "CNPJ", self.cnpj_status.get() or "Informe um CNPJ válido."
            )
            self.cnpj_entry.focus_set()
            return None
        origem = Path(self.origem_var.get().strip())
        destino = Path(self.destino_var.get().strip())
        if not origem.is_dir():
            messagebox.showwarning("Origem", f"Pasta inexistente:\n{origem}")
            return None
        if not self.destino_var.get().strip() or destino == origem:
            messagebox.showwarning(
                "Destino", "Escolha um destino diferente da pasta de origem."
            )
            return None
        if origem in destino.parents:
            messagebox.showwarning(
                "Destino",
                "O destino está dentro da origem: os arquivos voltariam a ser "
                "varidos na próxima execução.\nEscolha outra pasta.",
            )
            return None
        return origem, destino, somente_digitos(self.cnpj_var.get())

    # ------------------------------------------------------------- simulação

    def _simular(self) -> None:
        entradas = self._entradas()
        if entradas is None:
            return
        origem, destino, cnpj = entradas
        # um plano novo descarta as extrações de compactados da simulação anterior
        temporarios_limpos()
        self._salvar_preferencias()
        self._opcoes = self._ler_opcoes()
        # contexto congelado da simulação: se o usuário mexer em qualquer um
        # destes campos enquanto ela roda, o plano não serve mais
        self._congelar_contexto(cnpj, str(origem), str(destino))
        self._validar_cnpj()
        self._limpar_log()
        self._registrar(f"CNPJ: {mascara(cnpj)}")
        self._registrar(f"Origem: {origem}")
        self._registrar(f"Destino: {destino}")
        self._iniciar(
            "Simulação",
            lambda prog, canc: self._tarefa_simular(origem, destino, cnpj, prog, canc),
            self._plano_pronto,
        )

    def _tarefa_simular(self, origem: Path, destino: Path, cnpj: str, prog, canc):
        varredura = listar_arquivos(origem, destino)
        self.eventos.put(
            (
                "log",
                f"Varredura: {len(varredura.fiscais):,} XML(s), "
                f"{len(varredura.compactados):,} compactado(s), "
                f"{varredura.nao_fiscais:,} outros arquivos.",
            )
        )
        caminhos = list(varredura.fiscais)
        if self._opcoes["compactados"] and varredura.compactados:
            caminhos.extend(self._extrair_compactados(varredura.compactados))
        if canc():
            temporarios_limpos()
            return None, 0

        self._total_esperado = len(caminhos)

        def progresso(feitos: int) -> None:
            prog(100.0 * feitos / max(1, len(caminhos)))

        # as cópias extraídas de compactados precisam sobreviver até a execução, que é
        # quem as move: a limpeza acontece no fim de `_tarefa_executar`.
        plano = planejar(
            caminhos,
            cnpj,
            progresso=progresso,
            cancelar=canc,
            mover_duplicados=self._opcoes["duplicados"],
        )
        if not self._opcoes["nao_classificados"]:
            antes = len(plano.movimentos)
            plano.movimentos = [
                movimento
                for movimento in plano.movimentos
                if movimento.categoria.value != "_Nao_Classificados"
            ]
            self.eventos.put(
                (
                    "log",
                    f"Ignorados por opção: {antes - len(plano.movimentos):,} não classificado(s).",
                )
            )
        # escrever CSV/JSON na thread principal travaria a janela: num acervo
        # grande são centenas de milhares de linhas
        self.eventos.put(("log", "Gravando relatórios..."))
        relatorios = destino / NOME_PASTA_RELATORIOS
        escrever_csv(plano, relatorios / "movimentos.csv")
        escrever_json(
            plano,
            relatorios / "movimentos.json",
            {
                "origem": str(origem),
                "destino": str(destino),
                "cnpj": cnpj,
            },
        )
        return plano, len(caminhos), str(relatorios)

    def _extrair_compactados(self, compactados: list[str]) -> list[str]:
        if not localizar():
            self.eventos.put(
                ("log", "AVISO: 7-Zip não encontrado; arquivos .rar/.zip ignorados.")
            )
            return []
        extraidos: list[str] = []
        for indice, arquivo in enumerate(compactados, start=1):
            if self.trabalho and self.trabalho.cancelamento.is_set():
                break
            try:
                extraidos.extend(extrair_xmls(arquivo))
            except (Sem7Zip, OSError) as erro:
                self.eventos.put(
                    ("log", f"Compactado ignorado: {Path(arquivo).name} — {erro}")
                )
            if indice % 20 == 0:
                self.eventos.put(
                    ("log", f"Compactados {indice}/{len(compactados)} processados.")
                )
        self.eventos.put(
            ("log", f"XMLs extraídos de .rar/.zip: {len(extraidos):,}")
        )
        return extraidos

    def _plano_pronto(self, resultado: object) -> None:
        plano, total, relatorios = resultado  # type: ignore[misc]
        if plano is None:
            self._registrar("Simulação cancelada.")
            self.status_var.set("Simulação cancelada.")
            return
        if not self._contexto_preservado():
            # o usuário mexeu em CNPJ, pastas ou opções enquanto simulava
            self._descartar_plano()
            self._registrar(
                "Simulação descartada: mudou o contexto (CNPJ, pasta ou opção) "
                "durante o processamento."
            )
            self.status_var.set("Simulação descartada; simule de novo.")
            return
        self.plano = plano
        self._contexto_plano = self._contexto_simulacao
        self._registrar("")
        self._registrar(resumo_textual(plano, self.cnpj_var.get()))
        self._registrar("")
        self._registrar(f"Relatórios gravados em: {relatorios}")
        self._registrar("Nenhum arquivo foi movido. Confira e clique em Executar.")
        self.status_var.set(
            f"Simulação concluída: {len(plano.movimentos):,} arquivo(s) em {total:,} lido(s)."
        )

    # --------------------------------------------------------------- execução

    def _executar(self) -> None:
        if self.plano is None:
            return
        entradas = self._entradas()
        if entradas is None:
            return
        origem, destino, cnpj = entradas
        total = len(self.plano.movimentos)
        if not total:
            messagebox.showinfo(
                "Nada a fazer", "A simulação não encontrou arquivos a mover."
            )
            return
        copiar = bool(self.copiar_var.get())
        if not messagebox.askyesno(
            "Confirmar execução",
            f"{'Copiar' if copiar else 'Mover'} {total:,} arquivo(s) para:\n{destino}\n\n"
            + (
                "Os originais continuam na pasta de origem.\n"
                if copiar
                else "Os arquivos serão removidos da pasta de origem.\n"
            )
            + "Deseja continuar?",
        ):
            return
        self._salvar_preferencias()
        manifesto = self._caminho_manifesto(destino)
        self._total_esperado = total
        self._registrar("")
        self._registrar(
            f"Executando em modo {'cópia' if copiar else 'movimento'} "
            f"com manifesto em {manifesto}"
        )

        def tarefa(prog, canc):
            def progresso(feitos: int) -> None:
                prog(100.0 * feitos / max(1, total))

            # as cópias extraídas de compactados só podem ser apagadas depois de
            # copiadas; se algo falhar, o arquivo compactado de origem continua íntegro
            with temporarios_limpos():
                return executar(
                    self.plano,
                    destino,
                    manifesto,
                    contexto={
                        "cnpj": cnpj,
                        "origem": str(origem),
                        "extracoes": temporarios_criados(),
                    },
                    progresso=progresso,
                    cancelar=canc,
                    copiar=copiar,
                )

        self._iniciar("Execução", tarefa, self._execucao_pronta)

    def _caminho_manifesto(self, destino: Path) -> Path:
        pasta = destino / NOME_PASTA_RELATORIOS
        pasta.mkdir(parents=True, exist_ok=True)
        manifesto = pasta / "movimentos.jsonl"
        if manifesto.exists():
            marca = datetime.now().strftime("%Y%m%d-%H%M%S")
            manifesto = pasta / f"movimentos-{marca}.jsonl"
        return manifesto

    def _execucao_pronta(self, resultado: object) -> None:
        self.plano = None
        movidos = getattr(resultado, "movidos", 0)
        falhas = getattr(resultado, "falhas", [])
        verbo = "copiado" if bool(self.copiar_var.get()) else "movido"
        self._registrar("")
        self._registrar(
            f"Concluído: {movidos:,} {verbo}(s), {len(falhas):,} falha(s)."
            .replace(",", ".")
        )
        for caminho, erro in falhas[:20]:
            self._registrar(f"  FALHA {caminho}: {erro}")
        for aviso in getattr(resultado, "avisos", []):
            self._registrar(f"  AVISO {aviso}")
        self.status_var.set(
            f"Execução concluída: {movidos:,} {verbo}(s).".replace(",", ".")
        )
        if movidos:
            self._registrar("Use 'Reverter última execução' para desfazer.")

    # -------------------------------------------------------------- reversão

    def _reverter(self) -> None:
        destino = Path(self.destino_var.get().strip())
        pasta = destino / NOME_PASTA_RELATORIOS
        manifestos = sorted(
            pasta.glob("movimentos*.jsonl"), key=lambda p: p.stat().st_mtime
        )
        if not manifestos:
            messagebox.showinfo("Reverter", f"Nenhuma execução registrada em:\n{pasta}")
            return
        escolhido = self._escolher_manifesto(manifestos)
        if escolhido is None:
            return
        copia = modo_manifesto(escolhido) == MODO_COPIAR
        # em modo cópia reverter não devolve nada: apaga as cópias do destino
        alerta = (
            "\n\nEsta execução foi uma CÓPIA. Reverter vai APAGAR os arquivos do "
            "destino; os originais continuam onde estavam."
            if copia
            else ""
        )
        if not messagebox.askyesno(
            "Confirmar reversão",
            f"Devolver os arquivos de:\n{escolhido.name}{alerta}\n\nContinuar?",
        ):
            return
        self._limpar_log()
        self._registrar(
            f"Revertendo {escolhido.name} "
            f"({'apagando as cópias' if copia else 'devolvendo os arquivos'})"
        )
        self._total_esperado = contar_movimentos(escolhido)
        self._iniciar(
            "Reversão",
            lambda prog, canc: reverter(
                escolhido,
                progresso=lambda feitos: prog(
                    100.0 * feitos / max(1, self._total_esperado)
                ),
                cancelar=canc,
            ),
            self._reversao_pronta,
        )

    def _escolher_manifesto(self, manifestos: list[Path]) -> Path | None:
        janela = tk.Toplevel(self)
        janela.title("Reverter execução")
        escolhida: list[Path | None] = [None]

        ttk.Label(
            janela,
            text="Escolha a execução a ser revertida (CÓPIA apaga as cópias):",
            padding=10,
        ).pack(anchor="w")
        lista = tk.Listbox(janela, width=64, height=min(12, len(manifestos)))
        for indice, manifesto in enumerate(manifestos):
            quando = datetime.fromtimestamp(manifesto.stat().st_mtime)
            rotulo = "CÓPIA" if modo_manifesto(manifesto) == MODO_COPIAR else "MOVER"
            lista.insert(
                indice, f"{quando:%d/%m/%Y %H:%M:%S}  [{rotulo}]  {manifesto.name}"
            )
        lista.selection_set(len(manifestos) - 1)
        lista.pack(fill="both", expand=True, padx=10)

        def confirmar() -> None:
            selecao = lista.curselection()
            escolhida[0] = manifestos[selecao[0]] if selecao else manifestos[-1]
            janela.destroy()

        ttk.Button(janela, text="Reverter", command=confirmar).pack(pady=10)
        janela.bind("<Return>", lambda _e: confirmar())
        janela.bind("<Escape>", lambda _e: janela.destroy())
        janela.grab_set()
        janela.wait_window()
        return escolhida[0]

    def _reversao_pronta(self, resultado: object) -> None:
        movidos = getattr(resultado, "movidos", 0)
        falhas = getattr(resultado, "falhas", [])
        self._registrar("")
        self._registrar(f"Revertido: {movidos:,} arquivo(s), {len(falhas):,} falha(s).")
        for aviso in getattr(resultado, "avisos", []):
            self._registrar(f"  AVISO {aviso}")
        for caminho, erro in falhas[:20]:
            self._registrar(f"  FALHA {caminho}: {erro}")
        self.status_var.set(f"Reversão concluída: {movidos:,} arquivo(s).")

    # --------------------------------------------------------------- detecção

    def _detectar(self) -> None:
        origem = Path(self.origem_var.get().strip())
        if not origem.is_dir():
            messagebox.showwarning("Origem", f"Pasta inexistente:\n{origem}")
            return
        self._limpar_log()
        self._registrar("Procurando CNPJs numa amostra dos arquivos...")
        self._iniciar(
            "Detecção",
            lambda prog, canc: self._tarefa_detectar(origem, prog, canc),
            self._ao_detectar_pronto,
        )

    def _tarefa_detectar(self, origem: Path, prog, canc) -> list[tuple[str, int]]:
        varredura = listar_arquivos(origem)
        lidos, passo = tamanho_amostra(len(varredura.fiscais), AMOSTRA_PADRAO)
        self.eventos.put(
            (
                "log",
                f"{len(varredura.fiscais):,} XML(s) na pasta; "
                f"lendo {lidos} (um a cada {passo}).",
            )
        )
        self._total_esperado = lidos

        def progresso(feitos: int) -> None:
            prog(100.0 * feitos / max(1, lidos))

        return detectar_cnpjs(
            varredura.fiscais,
            limite=AMOSTRA_PADRAO,
            progresso=progresso,
            cancelar=canc,
        )

    def _ao_detectar_pronto(self, resultado: object) -> None:
        encontrados: list[tuple[str, int]] = resultado  # type: ignore[assignment]
        if not encontrados:
            self._registrar("Nenhum CNPJ encontrado na amostra.")
            self.status_var.set("Nenhum CNPJ encontrado.")
            return
        self._registrar("CNPJs encontrados (o mais frequente é o da sua empresa):")
        for cnpj, quantidade in encontrados:
            self._registrar(f"  {cnpj}   {quantidade:>7,} documento(s)".replace(",", "."))
        self.status_var.set(f"{len(encontrados)} CNPJ(s) distinto(s) na amostra.")

    # ------------------------------------------------------------------ infra

    def _ocupado(self) -> bool:
        return self.trabalho is not None

    def _cancelar(self) -> None:
        if self.trabalho is not None:
            self.trabalho.cancelamento.set()
            self.status_var.set("Cancelando...")

    def _iniciar(self, nome: str, funcao, ao_terminar) -> None:
        if self._ocupado():
            raise RuntimeError("já existe um trabalho em andamento")
        self._ao_terminar = ao_terminar
        self._total_esperado = 0
        self.progresso_var.set(0.0)
        self.trabalho = Trabalho(nome, funcao, self.eventos)
        self.botao_cancelar.configure(state="normal")
        self._ajustar_botoes(self._cnpj_valido())
        self.status_var.set(f"{nome} em andamento...")
        self.trabalho.start()
        self.after(80, self._drenar_eventos)

    def _drenar_eventos(self) -> None:
        while True:
            try:
                tipo, carga = self.eventos.get_nowait()
            except queue.Empty:
                self.after(80, self._drenar_eventos)
                return
            if tipo == "progresso":
                self.progresso_var.set(max(0.0, min(100.0, carga)))
            elif tipo == "log":
                self._registrar(carga)
            elif tipo == "fim":
                self._fim_do_trabalho(carga)
                return

    def _fim_do_trabalho(self, trabalho: Trabalho) -> None:
        self.trabalho = None
        self.botao_cancelar.configure(state="disabled")
        self.progresso_var.set(0.0)
        if trabalho.erro is not None:
            self._registrar(f"ERRO: {trabalho.erro}")
            self.status_var.set("Falhou.")
            messagebox.showerror("Erro", str(trabalho.erro))
            self._validar_cnpj()
            return
        try:
            self._ao_terminar(trabalho.resultado)
        except Exception as erro:  # noqa: BLE001
            self._registrar(f"ERRO ao finalizar: {erro}")
            messagebox.showerror("Erro", str(erro))
        self._validar_cnpj()

    def _registrar(self, texto: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{texto}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _limpar_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        if self._ocupado():
            if not messagebox.askyesno(
                "Sair", "Há um trabalho em andamento. Sair mesmo assim?"
            ):
                return
            self._cancelar()
        temporarios_limpos()
        self.destroy()


def contar_movimentos(manifesto: Path) -> int:
    with manifesto.open(encoding="utf-8") as arquivo:
        return sum(1 for linha in arquivo if '"movido"' in linha)


def caminho_chave(valor: str) -> str:
    """Normaliza um texto de pasta para comparação, ou "" se estiver vazio.

    O campo de pasta é texto cru, mas o contexto congelado passa por `Path`, que
    normaliza. Comparar os dois crus descartava a simulação sempre que o campo
    trazia barra final, barra invertida ou `\\.` — e é assim que o Explorador de
    Arquivos entrega o caminho de uma pasta. A normalização também absorve a
    diferença de caixa e de barra, que não muda a pasta apontada.
    """
    limpo = (valor or "").strip()
    if not limpo:
        return ""
    return os.path.normcase(os.path.abspath(limpo))


def main() -> None:
    app = OrganizadorApp()
    app.protocol("WM_DELETE_WINDOW", app._on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
