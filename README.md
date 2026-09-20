# Pipeline de Dados CVM - Demonstrações Financeiras (DFP)

Pipeline automatizado em Python para extração, tratamento e carregamento (ETL) das Demonstrações Financeiras Padronizadas (DFP) de companhias abertas disponibilizadas pelo [Portal de Dados Abertos da CVM](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/).

---

## Contexto e Próximos Passos

Este repositório cobre as duas primeiras camadas de uma arquitetura de dados em três etapas:

- **raw** — arquivos brutos da CVM, baixados por ano e mantidos localmente fora do banco.
- **stg** — dados tratados e carregados no PostgreSQL, servindo como base histórica única e independente para análises específicas.
- **camada de consumo** — lógica específica de cada projeto que utiliza esta base, como análises de negócios e indicadores financeiros, análises estatísticas ou treinamento de modelos preditivos, todas consumindo os dados da `stg`.

A `stg` carrega **todas as empresas** que reportam à CVM, sem filtrar por setor, universo específico ou tipo de instituição (financeiras incluídas). Essa decisão é intencional: o objetivo é que esta base sirva como fundação reutilizável para diferentes análises, sem embutir premissas de nenhuma análise específica e sem precisar ser reconstruída a cada novo projeto. Cada consumidor define seu próprio recorte de empresas e suas próprias regras na `camada de consumo`.

**Próximos passos deste pipeline:**
- Avaliar a inclusão da Demonstração de Fluxo de Caixa pelo Método Direto (`DFC_MD`), hoje ausente para as empresas que não reportam pelo Método Indireto.

---

## Arquitetura

O pipeline é estruturado em três etapas principais:


### 1. Download e Extração das DFPs (`download_dfp.py`)

Responsável pelo download e extração dos dados públicos da CVM:

* **Download Automatizado:** Utiliza a biblioteca `requests` para fazer o download dos arquivos compactados (`.zip`) diretamente do site de dados abertos da CVM para os anos de 2010 a 2026 e salva os arquivos brutos baixados em `raw/zip/`.

* **Extração** Descompacta os múltiplos arquivos CSV para pastas separadas por ano (`raw/csv/{ano}/`).


### 2. Tratamento das Bases (`load_stg.py`)

Trata e consolida os dados contábeis históricos usando a biblioteca `Pandas`:

* **Padronização de Contas:** Filtra apenas demonstrações contábeis padronizadas pelo **Plano de Contas Padrão da CVM** (`ST_CONTA_FIXA == 'S'`).

* **Exercício Vigente:** Mantém apenas os registros do exercício social encerrado mais recente (`ORDEM_EXERC == 'ÚLTIMO'`), descartando duplicidades de comparações passadas.

* **Resolução de Retificações (Versão Mais Recente):** Empresas frequentemente publicam retificações de DFPs. O script ordena numericamente pelo campo `VERSAO` e retém apenas o último envio para cada chave `(CD_CVM, DT_REFER, CD_CONTA)`.

* **Padronização da Escala de Moeda:** Empresas reportam dados em `MIL` e em `UNIDADE`. O script padroniza os valores em `MIL` (dividindo por 1.000 valores em `UNIDADE`) e fixa a coluna `ESCALA_MOEDA` em `'MIL'`.

* **Limpeza e Exportação:** Remove colunas operacionais que não agregam valor analítico (`GRUPO_DFP`, `ORDEM_EXERC`, `ST_CONTA_FIXA`, `VERSAO`), converte os nomes das colunas para minúsculo e salva as bases consolidadas em `processed_csv/`.


### 3. Carregamento no Banco de Dados PostgreSQL (`load_stg.py`)

Realiza o carregamento (Upsert) dos dados tratados na camada de *Staging* do banco relacional:

* **Conexão:** Faz a conexão com o PostgreSQL utilizando a biblioteca `psycopg2`. Autenticação gerenciada via variável de ambiente `DATABASE_URL` carregada a partir do arquivo `.env`.

* **Upsert:** Utiliza `ON CONFLICT (cd_cvm, dt_refer, cd_conta) DO UPDATE SET ...`, permitindo reexecuções seguras sem duplicar registros ou quebrar a constraint de Chave Primária.

* **Carga Rápida:** Inserção feita em lotes através da função `execute_values` do `psycopg2`.

* **Tratamento de Nulos:** Converte valores `NaN` do Pandas para `None` (SQL `NULL`), evitando erros de tipos com datas e textos no PostgreSQL.

* **Tabelas de Destino:**
  * `stg_bpa`: Balanço Patrimonial Ativo
  * `stg_bpp`: Balanço Patrimonial Passivo
  * `stg_dfc`: Demonstração do Fluxo de Caixa (Método Indireto)
  * `stg_dre`: Demonstração do Resultado do Exercício

---

## Demonstrações Coletadas

| Sigla | Demonstração Contábil | Arquivo Fonte CVM | Tabela PostgreSQL |
| :---: | :--- | :--- | :--- |
| **BPA** | Balanço Patrimonial Ativo | `dfp_cia_aberta_BPA_con_{ano}.csv` | `stg_bpa` |
| **BPP** | Balanço Patrimonial Passivo | `dfp_cia_aberta_BPP_con_{ano}.csv` | `stg_bpp` |
| **DFC** | Fluxo de Caixa (Método Indireto) | `dfp_cia_aberta_DFC_MI_con_{ano}.csv` | `stg_dfc` |
| **DRE** | Demonstração do Resultado do Exercício | `dfp_cia_aberta_DRE_con_{ano}.csv` | `stg_dre` |

---

## Validação de Integridade dos Dados

Após a carga, foram executadas verificações para confirmar a integridade do parsing e mapear lacunas conhecidas na base (ver `notebooks/analise_processed_csv.ipynb`):

- **Consistência entre demonstrações**: contagem de empresas distintas e intervalo de datas comparados entre `stg_bpa`, `stg_bpp` e `stg_dre`, confirmando cobertura equivalente — 739 empresas, com dados de 2010-12-31 a 2026-03-31.

- **Identidade contábil (Ativo Total = Passivo Total)**: valores da conta `1` (Ativo Total) em `stg_bpa` comparados aos da conta `2` (Passivo Total) em `stg_bpp`, empresa a empresa e período a período. A identidade se confirma em toda a base, com apenas 2 divergências registradas em todo o histórico — ambas atribuíveis a arredondamento residual. Esse resultado é a evidência direta de que o parsing preserva a integridade dos dados originais da CVM.

- **Cobertura de `stg_dfc`**: a tabela de Fluxo de Caixa cobre 713 das 739 empresas presentes nas demais demonstrações. A lacuna foi investigada e está associada a empresas que reportam pelo Método Direto (`DFC_MD`), formato ainda não carregado — apenas o Método Indireto (`DFC_MI`) está coberto atualmente. Essa lacuna é conhecida e tratada como dívida técnica documentada: não compromete o uso da base para as demais análises, e pode ser resolvida futuramente carregando também o `DFC_MD`, sem necessidade de reprocessar as tabelas já existentes.

---

## 📁 Estrutura de Pastas

```text
Projeto Dados CVM/
├── notebooks/
│   └── analise_processed_csv.ipynb  # Notebook de validação e análise exploratória
├── processed_csv/                   # CSVs limpos e consolidados gerados pelo load_stg.py
├── raw/
│   ├── csv/{ano}/                   # CSVs brutos extraídos por ano
│   └── zip/                         # Arquivos .zip originais baixados da CVM
├── .env.exemple                     # Modelo de variáveis de ambiente
├── .gitignore                       # Ignora arquivos temporários, bases brutas e credenciais
├── download_dfp.py                  # Script da Etapa 1 (Download e descompactação)
├── load_stg.py                      # Script das Etapas 2 e 3 (Tratamento e carga no banco)
└── README.md                        # Documentação completa do projeto
```

---

## Como Executar o Projeto

### 1. Pré-requisitos
* Python 3.10 ou superior
* Banco de dados PostgreSQL ativo

### 2. Instalação das Dependências
Instale as bibliotecas necessárias:
```bash
pip install pandas psycopg2-binary requests python-dotenv
```

### 3. Configuração do Ambiente
Crie um arquivo `.env` na raiz do projeto (baseando-se no `.env.exemple`):
```env
DATABASE_URL=postgresql://usuario:senha@localhost:5432/nome_do_banco
```

### 4. Execução do Pipeline

#### Passo 1: Download e Extração dos Dados da CVM
Executa o download de todos os arquivos zip históricos da CVM e os descompacta nas pastas correspondentes:
```bash
python download_dfp.py
```

#### Passo 2: Tratamento e Carga no Banco de Dados
Lê os CSVs brutos, aplica todos os tratamentos, salva as bases consolidadas em `processed_csv/` e realiza o Upsert no PostgreSQL:
```bash
python load_stg.py
```
