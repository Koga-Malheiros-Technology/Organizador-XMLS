"""Fixtures e construtores de XML sintético para os testes."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

CNPJ_EMPRESA = "55364491000141"
CNPJ_FORNECEDOR = "11222333000181"
CNPJ_CLIENTE = "99888777000166"
CNPJ_SAT = "12345678000199"


@pytest.fixture(scope="session")
def fixtures() -> Path:
    if not FIXTURES.is_dir():
        pytest.skip("pasta tests/fixtures ausente")
    return FIXTURES


def chave(
    cnpj: str,
    aamm: str = "2406",
    serie: str = "1",
    numero: str = "1",
    cdiv: str = "1",
) -> str:
    """Monta uma chave de acesso de NF-e com 44 dígitos."""
    return (
        "35"
        + aamm
        + cnpj
        + "55"
        + serie.ljust(3, "0")
        + numero.ljust(9, "0")
        + "1"
        + cdiv
        + "9" * 8
    )


def nfe_xml(
    *,
    emit: str = CNPJ_EMPRESA,
    emit_nome: str = "EMPRESA TESTE",
    dest: str | None = CNPJ_CLIENTE,
    dest_nome: str = "CLIENTE",
    dest_cpf: bool = False,
    tp_nf: int = 1,
    nat_op: str = "VENDA DE MERCADORIA",
    dh_emi: str = "2024-06-15T10:00:00-03:00",
    chave_emitida: str | None = None,
    vnf: str = "1.234,56",
) -> bytes:
    numero_chave = chave_emitida or chave(emit)
    if dest_cpf or dest is None:
        destino_xml = f"<dest><CPF>12345678909</CPF><xNome>{dest_nome}</xNome></dest>"
    else:
        destino_xml = f"<dest><CNPJ>{dest}</CNPJ><xNome>{dest_nome}</xNome></dest>"

    corpo = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe versao="4.00" Id="NFe{numero_chave}">
      <ide>
        <cUF>35</cUF>
        <natOp>{nat_op}</natOp>
        <mod>55</mod>
        <serie>1</serie>
        <nNF>1</nNF>
        <dhEmi>{dh_emi}</dhEmi>
        <tpNF>{tp_nf}</tpNF>
      </ide>
      <emit><CNPJ>{emit}</CNPJ><xNome>{emit_nome}</xNome></emit>
      {destino_xml}
      <det><prod><xProd>ITEM TESTE</xProd><vProd>10,00</vProd></prod></det>
      <total><ICMSTot><vNF>{vnf}</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00"><infProt><chNFe>{numero_chave}</chNFe></infProt></protNFe>
</nfeProc>
"""
    return corpo.encode("utf-8")


def cfe_xml(
    *,
    emit: str = CNPJ_EMPRESA,
    emit_secundario: str = CNPJ_CLIENTE,
    cnpj_sat: str = CNPJ_SAT,
    dh_envio: str = "20240716100000",
    d_emi: str = "2024-07-16",
    v_cfe: str = "55,50",
) -> bytes:
    """Lote SAT com dois cupons; o CNPJ em <ide> é o provedor, não o emissor."""
    cupons = "".join(
        f"""
    <CFe>
      <infCFe versao="1.00" Id="CFe{chave(cnpj, '2407', numero=str(indice + 1))}">
        <ide>
          <cUF>35</cUF>
          <nserieSAT>1</nserieSAT>
          <nCFe>{indice + 1}</nCFe>
          <dEmi>{d_emi}</dEmi>
          <CNPJ>{cnpj_sat}</CNPJ>
        </ide>
        <emit><CNPJ>{cnpj}</CNPJ><xNome>EMPRESA {indice + 1}</xNome></emit>
        <dest><CPF>12345678909</CPF><xNome>CONSUMIDOR</xNome></dest>
        <vCFe>{v_cfe}</vCFe>
      </infCFe>
    </CFe>"""
        for indice, cnpj in enumerate((emit, emit_secundario))
    )
    corpo = f"""<?xml version="1.0" encoding="UTF-8"?>
<envCFe versao="1.00" xmlns="http://www.infoleg.com.br">
  <idLote>1</idLote>
  {cupons}
  <dhEnvio>{dh_envio}</dhEnvio>
</envCFe>
"""
    return corpo.encode("utf-8")


def nfse_xml(*, prestadora: str = CNPJ_EMPRESA) -> bytes:
    corpo = f"""<?xml version="1.0" encoding="UTF-8"?>
<ConsultarNfseServicoPrestadoResposta xmlns="http://www.abrasf.org.br/nfse.xsd">
  <Nfse>
    <Rps>
      <IdentificacaoRps><Numero>1</Numero><Serie>1</Serie></IdentificacaoRps>
      <DataEmissao>2024-03-11T14:00:00-03:00</DataEmissao>
      <Prestador><CpfCnpj><Cnpj>{prestadora}</Cnpj></CpfCnpj></Prestador>
      <Tomador><CpfCnpj><Cnpj>{CNPJ_CLIENTE}</Cnpj></CpfCnpj></Tomador>
      <ValorServicos>800,00</ValorServicos>
    </Rps>
  </Nfse>
</ConsultarNfseServicoPrestadoResposta>
"""
    return corpo.encode("utf-8")


def arquivo(destino: Path, nome: str, conteudo: bytes) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / nome
    caminho.write_bytes(conteudo)
    return caminho
