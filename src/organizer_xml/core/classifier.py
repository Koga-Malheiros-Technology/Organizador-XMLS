"""Regras que decidem a categoria de cada documento em relação ao CNPJ da empresa.

A ordem importa: a primeira regra que casar define a categoria, porque
tpNF=0 e "empresa é destinatária" se sobrepõem em devoluções de compra.
"""

from __future__ import annotations

from .cnpj import mascara, somente_digitos
from .models import Categoria, Decisao, ItemDocumento, TipoDocumento

PASTA_SEM_DATA = "_Sem_Data"


def classificar(item: ItemDocumento, cnpj_empresa: str) -> Decisao:
    empresa = somente_digitos(cnpj_empresa)
    ano = item.data.year if item.data else None
    mes = item.data.month if item.data else None
    sem_data = item.data is None

    if item.tipo is TipoDocumento.INVALIDO:
        return Decisao(
            categoria=Categoria.NAO_CLASSIFICADO,
            ano=ano,
            mes=mes,
            motivo=item.erro or "XML inválido ou truncado",
            sem_data=sem_data,
        )

    if item.tipo is TipoDocumento.DESCONHECIDO:
        return Decisao(
            categoria=Categoria.NAO_CLASSIFICADO,
            ano=ano,
            mes=mes,
            motivo=item.erro or "Documento não é XML fiscal reconhecido",
            sem_data=sem_data,
        )

    if item.tipo is TipoDocumento.CFE_LOTE:
        emitentes = item.emit_cnpjs or ((item.emit_cnpj,) if item.emit_cnpj else ())
        if empresa and empresa in emitentes:
            return Decisao(
                categoria=Categoria.CFE_SAT,
                ano=ano,
                mes=mes,
                motivo=f"Lote SAT com {len(emitentes)} emitente(s) da empresa",
                sem_data=sem_data,
            )
        return Decisao(
            categoria=Categoria.NAO_CLASSIFICADO,
            ano=ano,
            mes=mes,
            motivo="Lote SAT sem cupom emitido pela empresa",
            sem_data=sem_data,
        )

    emit = somente_digitos(item.emit_cnpj or "")
    dest = somente_digitos(item.dest_cnpj or "")

    if empresa and emit == empresa and dest == empresa:
        return Decisao(
            categoria=Categoria.NAO_CLASSIFICADO,
            ano=ano,
            mes=mes,
            motivo="Empresa aparece como emitente e destinatária (ambíguo)",
            sem_data=sem_data,
        )

    if empresa and dest == empresa:
        return Decisao(
            categoria=Categoria.ENTRADA,
            ano=ano,
            mes=mes,
            motivo="Empresa é a destinatária do documento",
            sem_data=sem_data,
        )

    if empresa and emit == empresa:
        if item.tp_nf == 0:
            return Decisao(
                categoria=Categoria.DEVOLUCAO,
                ano=ano,
                mes=mes,
                motivo=f"Devolução emitida pela empresa (tpNF=0, {item.nat_op or 'sem natOp'})",
                sem_data=sem_data,
            )
        return Decisao(
            categoria=Categoria.SAIDA,
            ano=ano,
            mes=mes,
            motivo="Empresa é a emitente do documento",
            sem_data=sem_data,
        )

    return Decisao(
        categoria=Categoria.NAO_CLASSIFICADO,
        ano=ano,
        mes=mes,
        motivo=_motivo_terceiro(emit, dest, item),
        sem_data=sem_data,
    )


def _motivo_terceiro(emit: str, dest: str, item: ItemDocumento) -> str:
    if emit:
        return f"Documento de terceiro (emitente {_formatar(emit)})"
    if dest:
        return f"Documento de terceiro (destinatário {_formatar(dest)})"
    if item.dest_cpf:
        return f"Documento de terceiro (destinatário CPF {item.dest_cpf})"
    return "Documento sem CNPJ de emitente ou destinatário"


def _formatar(cnpj: str) -> str:
    return mascara(cnpj) if cnpj else "-"
