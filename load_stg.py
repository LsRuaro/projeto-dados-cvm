from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import os

# Configuração

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

RAW_DIR = Path('raw/csv')

ANO_INICIAL = 2010
ANO_FINAL = 2026

DEMONSTRACOES = {
    'bpa': {'arquivo': 'dfp_cia_aberta_BPA_con_{ano}.csv'},
    'bpp': {'arquivo': 'dfp_cia_aberta_BPP_con_{ano}.csv'},
    'dfc': {'arquivo': 'dfp_cia_aberta_DFC_MI_con_{ano}.csv'},
    'dre': {'arquivo': 'dfp_cia_aberta_DRE_con_{ano}.csv'}
}

''' Leitura dos CSVs '''

print('Lendo CSVs.\n')

def ler_demonstracao(demonstracao):

    dfs = []

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

        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


df_bpa = ler_demonstracao('bpa')
df_bpp = ler_demonstracao('bpp')
df_dfc = ler_demonstracao('dfc')
df_dre = ler_demonstracao('dre')

''' Tratamento '''

print('Tratando bases.\n')

# Filtrar apenas demonstrações padronizadas
df_bpa = df_bpa[df_bpa['ST_CONTA_FIXA'] == 'S']
df_bpp = df_bpp[df_bpp['ST_CONTA_FIXA'] == 'S']
df_dfc = df_dfc[df_dfc['ST_CONTA_FIXA'] == 'S']
df_dre = df_dre[df_dre['ST_CONTA_FIXA'] == 'S']

# Filtra apenas último ano
df_bpa = df_bpa[df_bpa['ORDEM_EXERC'] == 'ÚLTIMO']
df_bpp = df_bpp[df_bpp['ORDEM_EXERC'] == 'ÚLTIMO']
df_dfc = df_dfc[df_dfc['ORDEM_EXERC'] == 'ÚLTIMO']
df_dre = df_dre[df_dre['ORDEM_EXERC'] == 'ÚLTIMO']

# Mantém versão mais recente de DFP
df_bpa = df_bpa.sort_values('VERSAO').drop_duplicates(
    subset=['CD_CVM','DT_REFER','CD_CONTA'],
    keep='last'
)

df_bpp = df_bpp.sort_values('VERSAO').drop_duplicates(
    subset=['CD_CVM','DT_REFER','CD_CONTA'],
    keep='last'
)

df_dfc = df_dfc.sort_values('VERSAO').drop_duplicates(
    subset=['CD_CVM','DT_REFER','CD_CONTA'],
    keep='last'
)

df_dre = df_dre.sort_values('VERSAO').drop_duplicates(
    subset=['CD_CVM','DT_REFER','CD_CONTA'],
    keep='last'
)

# Normaliza a escala da moeda
df_bpa.loc[df_bpa['ESCALA_MOEDA'] == 'UNIDADE', 'VL_CONTA'] /= 1000
df_bpa['ESCALA_MOEDA'] = 'MIL'

df_bpp.loc[df_bpp['ESCALA_MOEDA'] == 'UNIDADE', 'VL_CONTA'] /= 1000
df_bpp['ESCALA_MOEDA'] = 'MIL'

df_dfc.loc[df_dfc['ESCALA_MOEDA'] == 'UNIDADE', 'VL_CONTA'] /= 1000
df_dfc['ESCALA_MOEDA'] = 'MIL'

df_dre.loc[df_dre['ESCALA_MOEDA'] == 'UNIDADE', 'VL_CONTA'] /= 1000
df_dre['ESCALA_MOEDA'] = 'MIL'

# Remove colunas desnecessárias
drop_columns = ['GRUPO_DFP','ORDEM_EXERC','ST_CONTA_FIXA','VERSAO']
df_bpa = df_bpa.drop(columns = drop_columns)
df_bpp = df_bpp.drop(columns = drop_columns)
df_dfc = df_dfc.drop(columns = drop_columns)
df_dre = df_dre.drop(columns = drop_columns)

# Nome das colunas em minusculo
df_bpa.columns = df_bpa.columns.str.lower()
df_bpp.columns = df_bpp.columns.str.lower()
df_dfc.columns = df_dfc.columns.str.lower()
df_dre.columns = df_dre.columns.str.lower()


Path('processed_csv').mkdir(exist_ok=True)

df_bpa.to_csv(Path('processed_csv') / 'bpa.csv', index=False, encoding='utf-8-sig')
df_bpp.to_csv(Path('processed_csv') / 'bpp.csv', index=False, encoding='utf-8-sig')
df_dfc.to_csv(Path('processed_csv') / 'dfc.csv', index=False, encoding='utf-8-sig')
df_dre.to_csv(Path('processed_csv') / 'dre.csv', index=False, encoding='utf-8-sig')    

''' Carregamento no BD '''

print('Carregando no BD...\n')

# Colunas chave
colunas_chave = ['cd_cvm','dt_refer','cd_conta']
colunas_chave_sql = ', '.join(colunas_chave)

# Colunas
colunas_bp = ['cd_cvm','cnpj_cia','denom_cia','dt_refer','cd_conta','ds_conta','moeda','escala_moeda','vl_conta']
colunas_dfc_dre = ['cd_cvm','cnpj_cia','denom_cia','dt_ini_exerc','dt_refer','cd_conta','ds_conta','moeda','escala_moeda','vl_conta']

# Mapa tabela/DF/colunas
cargas = [
    ('stg_bpa', df_bpa, colunas_bp),
    ('stg_bpp', df_bpp, colunas_bp),
    ('stg_dfc', df_dfc, colunas_dfc_dre),
    ('stg_dre', df_dre, colunas_dfc_dre),
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

            registros = df[colunas].itertuples(index=False, name=None)

            execute_values(cur, query, registros, page_size=5000)

            print(f'{tabela} carregada.\n')
        
        conn.commit()

print('Carga concluída!')
