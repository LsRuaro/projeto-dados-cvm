

''' Configuração '''


from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não encontrada no arquivo .env")


''' Leitura dos CSVs '''


RAW_DIR = Path('raw/csv')

ANO_INICIAL = 2010
ANO_FINAL = 2026

# Mapeamento dos nomes dos arquivos da CVM
DEMONSTRACOES = {
    'bpa': {'arquivo': 'dfp_cia_aberta_BPA_con_{ano}.csv'},
    'bpp': {'arquivo': 'dfp_cia_aberta_BPP_con_{ano}.csv'},
    'dfc': {'arquivo': 'dfp_cia_aberta_DFC_MI_con_{ano}.csv'},
    'dre': {'arquivo': 'dfp_cia_aberta_DRE_con_{ano}.csv'}
}

def ler_demonstracao(demonstracao: str):

    dfs_anuais = []

    for ano in range(ANO_INICIAL, ANO_FINAL + 1):

        arquivo = RAW_DIR / str(ano) / DEMONSTRACOES[demonstracao]['arquivo'].format(ano=ano)

        if not arquivo.exists():
            print(f'{arquivo}: não encontrado')
            continue

        df = pd.read_csv(
            arquivo, 
            sep=';', 
            encoding='latin-1'
        )

        dfs_anuais.append(df)

    return pd.concat(dfs_anuais, ignore_index=True)

dfs = {}

print('Lendo CSVs.\n')

for dem in DEMONSTRACOES:
    dfs[dem] = ler_demonstracao(dem)


''' Tratamento '''


def tratar_dataframe(nome: str, df: pd.DataFrame):
    
    # Filtrar apenas demonstrações padronizadas
    df = df[df['ST_CONTA_FIXA'] == 'S']

    # Filtra apenas último ano
    df = df[df['ORDEM_EXERC'] == 'ÚLTIMO']

    # Mantém versão mais recente de DFP
    df['VERSAO'] = pd.to_numeric(df['VERSAO'], errors='coerce')
    df = df.sort_values('VERSAO').drop_duplicates(
    subset=['CD_CVM','DT_REFER','CD_CONTA'],
    keep='last'
    )

    # Normaliza a escala da moeda
    df.loc[df['ESCALA_MOEDA'] == 'UNIDADE', 'VL_CONTA'] /= 1000
    df['ESCALA_MOEDA'] = 'MIL'

    # Remove colunas desnecessárias
    drop_columns = ['GRUPO_DFP','ORDEM_EXERC','ST_CONTA_FIXA','VERSAO']
    df = df.drop(columns = drop_columns)

    # Nome das colunas em minusculo
    df.columns = df.columns.str.lower()

    # Cria uma pasta com csvs tratados
    Path('processed_csv').mkdir(exist_ok=True)
    df.to_csv(Path('processed_csv') / f'{nome}.csv', index=False, encoding='utf-8-sig')

    return df

print('Tratando bases.\n')

for dem in dfs:
    dfs[dem] = tratar_dataframe(dem, dfs[dem])


''' Carregamento no BD '''


print('Carregando no banco de dados.\n')

# Colunas chave
colunas_chave = ['cd_cvm','dt_refer','cd_conta']
colunas_chave_sql = ', '.join(colunas_chave)

# Colunas
colunas_bp = ['cd_cvm','cnpj_cia','denom_cia','dt_refer','cd_conta','ds_conta','moeda','escala_moeda','vl_conta']
colunas_dfc_dre = ['cd_cvm','cnpj_cia','denom_cia','dt_ini_exerc','dt_refer','cd_conta','ds_conta','moeda','escala_moeda','vl_conta']

# Mapa tabela/DF/colunas
cargas = [
    ('stg_bpa', dfs['bpa'], colunas_bp),
    ('stg_bpp', dfs['bpp'], colunas_bp),
    ('stg_dfc', dfs['dfc'], colunas_dfc_dre),
    ('stg_dre', dfs['dre'], colunas_dfc_dre),
]

# Carregando dados

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        for tabela, df, colunas in cargas:
            print(f'Carregando {tabela}.')

            colunas_sql = ', '.join(colunas)
            update_sql = ', '.join(f'{c} = EXCLUDED.{c}' for c in colunas if c not in colunas_chave)

            query = f"""
                INSERT INTO {tabela} ({colunas_sql})
                VALUES %s
                ON CONFLICT ({colunas_chave_sql})
                DO UPDATE SET {update_sql}
            """

            df_banco = df[colunas].where(pd.notnull(df[colunas]), None)
            registros = df_banco.itertuples(index=False, name=None)

            execute_values(cur, query, registros, page_size=5000)

            print(f'{tabela} carregada.\n')
        
        conn.commit()

print('Carga concluída!')
