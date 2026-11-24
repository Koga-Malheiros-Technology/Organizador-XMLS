# OrganizadorXML

Organiza arquivos XML de documentos fiscais brasileiros (NF-e, NFC-e via SAT/CFE e NFS-e)
em pastas de **ano / mês / categoria**, aplicando o CNPJ da sua empresa como critério
de classificação.

Por padrão os arquivos saem da pasta de origem e são **movidos** (não copiados) para uma
árvore organizada. Também dá para **copiar** em vez de mover, deixando os originais onde
estavam. Toda execução grava um manifesto que permite **reverter** o que foi feito — e o que
a reversão faz depende do modo: devolve o arquivo movido ou apaga a cópia.

```
Antes                                  Depois
notas/                                 destino/
  nfe_saida.XML                          2024/
  nfe_entrada.XML                          06/
  nfe_saida - copia.XML                      Saida/
  cfe_lote.xml                                  nfe_saida.XML
                                              06/
                                                Entrada/
                                                  nfe_entrada.XML
                                                _Duplicados/
                                                  nfe_saida - copia.XML
                                              07/
                                                _CFE_SAT/
                                                  cfe_lote.xml
```

## Requisitos

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recomendado; também funciona com `pip`)
- **7-Zip** — apenas para extrair arquivos `.rar`, opcional

O projeto **não tem dependências de runtime**. Toda a leitura de XML usa a biblioteca
padrão com regex tolerantes, e a interface usa Tkinter, que já vem com o Python no Windows.

## Instalação

```bash
uv sync
```

Isso instala o pacote em modo editável e cria os dois executáveis:

| Comando | O que faz |
| --- | --- |
| `organizer-gui` | Abre a janela (uso normal) |
| `organizer` | Linha de comando / automação |

Sem `uv`:

```bash
pip install -e .
```

## Uso

### Interface gráfica

```bash
uv run organizer-gui
```

O fluxo é sempre **Simular → conferir → Executar**:

1. Informe o CNPJ da empresa (ou clique em **Detectar CNPJs**, que lê uma amostra
   da pasta e sugere os CNPJs mais frequentes).
2. Escolha origem e destino.
3. Clique em **Simular**. Nada é movido: o programa mostra o que faria, por categoria
   e por ano/mês, e grava os relatórios.
4. Clique em **Executar** para aplicar de fato.

O botão **Executar** só fica disponível depois de uma simulação cujo contexto
(CNPJ, pastas e opções) ainda seja o que está na tela. Mexer em qualquer um deles
descarta o plano — um plano calculado para um CNPJ não pode ser aplicado a outro.
Apontar para a **mesma** pasta de outro jeito (barra final, barra invertida,
diferença de caixa) não conta como mudança.

A caixa **Copiar em vez de mover** é a única opção que **não** invalida a simulação:
copiar e mover organizam os mesmos arquivos nos mesmos lugares, só muda o que
acontece com o original. Dá para simular uma vez e decidir na hora de executar.

### Copiar em vez de mover

Marcar a caixa (ou passar `--copiar` no CLI) faz o programa **duplicar** cada XML
no destino em vez de tirá-lo da origem:

- os originais continuam onde estavam, com data de modificação preservada;
- pastas que ficaram vazias na origem **não** são removidas — não há motivo para
  apagar nada de um lugar que o usuário pediu para manter intacto;
- colisões de nome continuam ganhando sufixo (`nota.xml` → `nota (2).xml`), sem
  sobrescrever o que já existe no destino;
- arquivos que vieram de dentro de um `.rar` são copiados normalmente, e a extração
  temporária é descartada no fim como sempre.

A classificação, os relatórios e a estrutura de pastas são idênticos aos do modo mover.

### Linha de comando

```bash
# Conferir a classificação sem mover nada
uv run organizer --origem C:\XMLs --destino C:\Organizados --cnpj 55.364.491/0001-41 --simular

# Executar
uv run organizer --origem C:\XMLs --destino C:\Organizados --cnpj 55.364.491/0001-41

# Executar copiando, sem mexer na origem
uv run organizer --origem C:\XMLs --destino C:\Organizados --cnpj 55.364.491/0001-41 --copiar

# Desfazer a última execução
uv run organizer --reverter C:\Organizados\_relatorios\movimentos.jsonl
```

Saída real de uma simulação:

```
Varredura: 6 XML(s), 0 RAR, 0 outros em 0.1s
  6/6 (100.0%) 128/s  faltam 0s

CNPJ informado: 55.364.491/0001-41
Total de arquivos a mover: 6

Por categoria:
  _Devolucoes                    2
  Saida                          2
  _CFE_SAT                       1
  _Duplicados                    1

Por ano/mês:
  2021-08:       4  (Saida=1, _Devolucoes=2, _Duplicados=1)
  2022-01:       2  (Saida=1, _CFE_SAT=1)

CNPJs de terceiros encontrados:
  48.292.932/0001-81  1 documento(s)

Planejamento concluído em 1.4s
Relatórios: C:\Organizados\_relatorios

Simulação: nenhum arquivo foi movido.
```

#### Opções

| Flag | Efeito |
| --- | --- |
| `--simular` | Só mostra e grava relatórios; não move nada |
| `--reverter MANIFESTO` | Desfaz uma execução a partir do manifesto |
| `--profundidade N` | Limita a varredura a N níveis (1 = só a raiz da origem) |
| `--extrair-rar` | Extrai XMLs de `.rar` via 7-Zip antes de organizar |
| `--copiar` | Copia em vez de mover; os originais continuam na origem e a reversão passa a apagá-los |
| `--nao-mover-duplicados` | Deixa cópias idênticas onde estão, em vez de mandar para `_Duplicados` |
| `--nao-mover-nao-classificados` | Ignora documentos de terceiros e os não reconhecidos |
| `--relatorio PASTA` | Muda o destino dos relatórios (padrão: `<destino>/_relatorios`) |
| `--workers N` | Número de processos de leitura (padrão: todos os núcleos) |

## Como a classificação funciona

A ordem das regras importa: a primeira que casar define a categoria, porque `tpNF=0`
e "empresa é destinatária" se sobrepõem nas devoluções de compra.

| Situação do documento | Categoria |
| --- | --- |
| XML inválido ou truncado | `_Nao_Classificados` |
| Raiz não reconhecida | `_Nao_Classificados` |
| Lote SAT com cupom emitido pela empresa | `_CFE_SAT` |
| Lote SAT sem cupom da empresa | `_Nao_Classificados` |
| Empresa é emitente **e** destinatária | `_Nao_Classificados` (ambíguo) |
| Empresa é a destinatária | `Entrada` |
| Empresa é a emitente, `tpNF=0` | `_Devolucoes` |
| Empresa é a emitente, `tpNF=1` | `Saida` |
| Nenhum CNPJ é a empresa | `_Nao_Classificados` |
| Conteúdo idêntico a outro arquivo da mesma execução | `_Duplicados` |

Cada decisão vem com um **motivo** legível, que aparece no relatório:

```
Saida             Empresa é a emitente do documento
_Devolucoes       Devolução emitida pela empresa (tpNF=0, DEVOLUÇÃO)
_Nao_Classificados Documento de terceiro (emitente 48.292.932/0001-81)
_Duplicados       Conteúdo idêntico a outro arquivo da mesma execução
```

### Documentos sem data

Vão para `_Sem_Data/<categoria>/` em vez de `ano/mes/`. A data usada é, em ordem:
`dhEmi` → `dhRecbto` → as posições 3-6 da chave de acesso (AAMM).

### Duplicados

Arquivos com o mesmo SHA-1 na mesma execução são separados: o de **nome mais curto**
vai para a categoria normal e os outros para `_Duplicados`. Sem essa regra,
`nota.xml - copia.xml` venceria `nota.xml` só porque espaço ordena antes de ponto.

### Suportados

| Modelo | Raízes XML reconhecidas | Observações |
| --- | --- | --- |
| **NF-e** (55) | `nfeProc`, `NFe`, `infNFe` | Layouts 3.10 e 4.00. Lê a chave do `Id` ou do `protNFe` |
| **CFE** (59) | `envCFe`, `CFe`, `CFE`, `cfedoc`, `LoteCFe` | Cada cupom do lote é lido individualmente; o CNPJ em `ide` é o provedor do SAT, não o emissor |
| **NFS-e** | `NFSe`, `CompNfse`, `Rps`, `ConsultarNfseRpsResposta`, … | Padrões nacional (ABERT) e municipal (ABRASF) |

A detecção é feita pelo **elemento raiz**, antes de qualquer parse. Se o elemento raiz
não fecha, o documento é marcado como inválido em vez de ser interpretado pela metade.

> A entrada de NFS-e segue o padrão documentado e **não foi validada contra NFS-e real** —
> a base do cliente não tem nenhuma emissão desse modelo.

## Relatórios

Gravados em `<destino>/_relatorios/`:

| Arquivo | Conteúdo |
| --- | --- |
| `movimentos.csv` | Uma linha por arquivo. `;` como separador e `utf-8-sig`, para abrir direto no Excel |
| `movimentos.json` | Mesmo conteúdo + resumo por categoria, por ano/mês, valores e CNPJs de terceiros |
| `movimentos.jsonl` | **Manifesto da execução** (append). É o que permite reverter |

Os relatórios são escritos tanto na simulação quanto na execução. Na simulação existe
um `.csv`/`.json` sem o `.jsonl` correspondente, porque nada foi movido.

### Reversão

Cada execução real abre um `movimentos.jsonl` com um registro por arquivo movido
(`origem`, `destino`, `digest`, `tamanho`). O cabeçalho guarda o **modo** da execução
(`"modo": "mover"` ou `"copiar"`). Para desfazer:

```bash
uv run organizer --reverter C:\Organizados\_relatorios\movimentos.jsonl
```

O manifesto nunca é sobrescrito: se já existe um, o novo vira
`movimentos-AAAAMMDD-HHMMSS.jsonl`.

O que a reversão faz depende do modo registrado no cabeçalho:

| Modo | Reversão |
| --- | --- |
| `mover` | Devolve o arquivo do destino para a pasta de origem |
| `copiar` | **Apaga** a cópia do destino. O original já está na origem, então "devolver" criaria um duplicado |

Na interface, a lista de execuções mostra `[MOVER]` ou `[CÓPIA]` em cada linha, e
reverter uma cópia avisa explicitamente que os arquivos do destino serão apagados.
Manifestos antigos, gerados antes de a opção existir, não têm o campo `modo` e são
tratados como movimento — o comportamento de sempre.

A reversão é conservadora — cada arquivo só é mexido se ele **ainda estiver no destino**
com o **mesmo tamanho** registrado. Arquivo editado ou removido depois é pulado e
relatado como falha, em vez de ser sobrescrito ou apagado silenciosamente.

Arquivos que vieram de dentro de um `.rar` são apenas **descartados** na reversão
(excluídos da árvore organizada): a pasta temporária de extração já foi apagada e
o `.rar` de origem continua íntegro guardando a cópia original.

## Arquivos `.rar`

Desligado por padrão. Quando ligado, cada `.rar` é extraído para uma pasta temporária,
só os `.xml` são aproveitados e o resto é apagado. O `.rar` de origem **nunca é
modificado**, e as pastas temporárias são removidas ao final — inclusive se algo
falhar no meio ou se a operação for cancelada.

Requer o 7-Zip. Sem ele, o programa avisa e segue sem os `.rar`:

```bash
winget install 7zip.7zip
```

## Desempenho

A leitura é o gargalo e roda em paralelo: os arquivos são lidos em lotes de 400 e
distribuídos por `ProcessPoolExecutor`, um pool por execução.

Se o pool não puder ser criado **ou morrer no meio do caminho** (o que acontece
com o spawn em Windows quando um processo é morto), o programa retoma do ponto em
que parou em modo sequencial, sem reler o que já emitiu. Para forçar o modo
sequencial, use `--workers 1`.

```bash
# medir em uma cópia da base antes de rodar em produção
uv run organizer --origem C:\XMLs --destino C:\Teste --cnpj 55.364.491/0001-41 --simular
```

## Segurança

- **O destino nunca pode estar dentro da origem** — os arquivos voltariam a ser lidos
  na execução seguinte. A checagem existe no CLI e na interface.
- A subárvore do destino é **ignorada** durante a varredura.
- Se o destino já tiver um arquivo com o mesmo nome, o novo vira `nota (2).XML`.
- Pastas que ficaram vazias na origem são removidas ao final — **exceto** o destino,
  qualquer pasta dentro dele e o modo **copiar**, onde nada é removido da origem.
- Nada é apagado da origem além dos arquivos que foram movidos com sucesso.
- Uma cópia que falha no meio é removida do destino antes de ser registrada como
  falha: sobra no manifesto, o que a reversão apaga. Um arquivo truncado órfão
  não tem registro e não teria como ser desfeito.

## Preferências

A interface guarda CNPJ, últimas pastas e opções — incluindo a preferência
**copiar em vez de mover** — em:

```
%APPDATA%\OrganizerXML\config.json
```

O CNPJ só é salvo com "Lembrar CNPJ" marcado; **Esquecer salvo** o apaga.
Um arquivo de configuração corrompido é ignorado — o programa abre com o padrão.
Configurações de versões anteriores, sem o campo `copiar`, continuam carregando com
o padrão (mover).

## Distribuição

O cliente não precisa de Python: o programa vira **um `.exe` só**, com o
interpretador embutido. É o mesmo código, com o Tkinter e o `organizer_xml`
embutidos.

```powershell
.\build_exe.ps1              # gera os dois executáveis
.\build_exe.ps1 -SoGui       # só a interface
```

Saída:

| Arquivo | Para quê |
| --- | --- |
| `dist/OrganizadorXML.exe` | **Este é o arquivo para o cliente.** Interface gráfica, duplo clique e usa |
| `dist/OrganizadorXML-CLI.exe` | Versão de console, para automação e conferência por script |

O `.exe` da interface abre direto em `Simular → Executar`, sem nenhuma
instalação. Preferências e relatórios continuam funcionando igual
(`%APPDATA%\OrganizerXML\config.json`).

Três coisas que valem saber antes de mandar para o cliente:

- **O executável tem ícone próprio** (folha fiscal sobre fundo azul, com as
  cores das categorias) — e a janela do programa usa o mesmo ícone na barra
  de título e na barra de tarefas. Para trocar, edite
  `packaging/gerar_icone.py` e rode
  `uv run --group build python packaging/gerar_icone.py` — o `.ico` é
  regerado e entra na próxima compilação.
- **7-Zip continua opcional.** Sem ele, o programa avisa e segue sem os `.rar`;
  com ele (`winget install 7zip.7zip`), extrai.
- **A primeira abertura demora alguns segundos**: o Windows Defender/
  SmartScreen pode checar o arquivo antes de rodar. Sem certificado de
  assinatura, o Windows pode mostrar "O Windows protegeu seu PC" — é o
  aviso de executável não assinado, não um problema do programa. Assinar o
  `.exe` com certificado de código resolve.
- **A versão do executável** vem de `packaging/version_info.txt` (e de
  `version` no `pyproject.toml`). Ao publicar uma versão nova, atualize os
  dois para o mesmo número.

Como o planejador usa `ProcessPoolExecutor` (com `spawn` no Windows), as
entradas congeladas em `packaging/entry_*.py` chamam
`multiprocessing.freeze_support()` antes de qualquer outra coisa — sem isso,
cada worker abriria uma janela nova do aplicativo.

## Desenvolvimento

```bash
uv sync                 # instala com as dependências de teste
uv sync --group build   # instala também o PyInstaller
uv run pytest           # 161 testes, ~6s
uv run pytest -m gui    # só os 26 testes que sobem a janela do Tkinter
uv run pytest -m "not gui" -q
```

Os testes usam XMLs sintéticos montados em `tests/conftest.py` e, quando presentes,
amostras reais em `tests/fixtures/`. Essas amostras são **dados de cliente** e estão
no `.gitignore` — os testes que dependem delas pulam sozinhos se a pasta estiver vazia.

> O `.gitignore` espera um `tests/fixtures/README.md` como placeholder, que ainda
> não foi criado. Sem ele, uma pasta `tests/fixtures/` vazia não entra no git.

## Estrutura

```
src/organizer_xml/
├── cli.py              Linha de comando: argumentos, validações, barra de progresso
├── config.py           Preferências em %APPDATA%
├── core/
│   ├── scanner.py      Varredura recursiva, ignora a subárvore do destino
│   ├── detect.py       Tipo do documento pelo elemento raiz
│   ├── parsers/        nfe.py, cfe.py, nfse.py + common.py (decodificação, campos)
│   ├── classifier.py   Regras que decidem a categoria (a ordem importa)
│   ├── planner.py      Lê, classifica e resolve duplicatas → Plano. Não toca em arquivo
│   ├── executor.py     Aplica o plano e grava o manifesto; reversão
│   ├── report.py       CSV, JSON e o resumo em texto
│   ├── rar.py          Extração via 7-Zip, com limpeza garantida
│   ├── cnpj.py         Normalização, máscara e dígito verificador
│   ├── amostra.py      Detecção de CNPJ por amostragem espaçada
│   └── models.py       Categoria, TipoDocumento, ItemDocumento, Movimento, Plano
└── ui/
    ├── app.py           Janela do Tkinter
    └── icone.py         Acha o .ico da janela (no _MEIPASS ou no projeto)

packaging/
├── entry_gui.py        Entrada do executável congelado (interface)
├── entry_cli.py        Entrada do executável congelado (console)
├── OrganizadorXML.spec      Spec do PyInstaller: interface, um arquivo só
├── OrganizadorXML-CLI.spec  Spec do PyInstaller: console
├── gerar_icone.py     Desenha o ícone do executável
├── icone.ico          Ícone embutido no .exe (gerado por gerar_icone.py)
├── icone.png          Prévia do ícone
├── version_info.txt    Versão que aparece nas propriedades do .exe
└── LEIA-ME-cliente.txt Instruções que vão junto na distribuição
```

A separação entre `planner.py` e `executor.py` é o que torna a simulação confiável:
**nenhum arquivo é tocado durante o planejamento.** O plano é uma lista de intenções
que pode ser inspecionada, ajustada por opção e só então aplicada.

Copiar e mover produzem **o mesmo plano**, por isso a opção não entra no contexto
congelado da simulação: exigir nova simulação por causa disso só faria o usuário
varrer a pasta de novo à toa. O que muda entre os dois modos é o destino final de
cada arquivo, e esse é decidido na hora de executar.

## Decisões que valem saber

**Tkinter só na thread principal.** Simular e Executar rodam em uma thread separada,
então as opções são copiadas para um dicionário antes de abrir a thread e nenhuma
variável do Tk é lida de dentro dela. A comunicação volta por `queue.Queue`.

**A amostragem é espaçada, não uma fatia do começo.** `Detectar CNPJs` lê um a cada
N arquivos em vez dos primeiros 200 — os primeiros costuma ser o mesmo lote e não
dizem nada sobre o resto da base. A contagem é por documento, não por ocorrência:
uma NF-e de saída para a própria empresa cita o CNPJ duas vezes e não pode pesar
mais na sugestão que um documento que cita uma vez.

**A decodificação é tolerante.** O código detecta BOM, UTF-16 e cai para latin-1.
Um XML malformado não derruba a execução: ele vira `_Nao_Classificados` com o motivo.

**A detecção de tipo vem antes do parse.** O elemento raiz é procurado no texto
cru, então um XML que não é fiscal é descartado sem passar por nenhum parser —
mas o arquivo já foi lido inteiro para isso. Para acervos muito grandes, rode com
`--profundidade` ou em máquina com mais núcleos.