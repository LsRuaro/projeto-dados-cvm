import requests
from pathlib import Path
from zipfile import ZipFile

# URL de coleta e pasta onde os dados serão salvos
BASE_URL = 'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip'

# Anos de coleta
ANO_INICIAL = 2010
ANO_FINAL = 2026

# Pastas onde serão salvos os dados
RAW_DIR = Path('raw')
ZIP_DIR = RAW_DIR / 'zip'
CSV_DIR = RAW_DIR / 'csv'

# Cria as pastas caso elas não existam
ZIP_DIR.mkdir(exist_ok=True)
CSV_DIR.mkdir(exist_ok=True)

# Estrutura de repetição para donwload dos arquivos
for ano in range(ANO_INICIAL, ANO_FINAL + 1):

    # Coloca o ano na url e nos arquivos
    url = BASE_URL.format(ano=ano)
    zip_file = ZIP_DIR / f'dfp_cia_aberta_{ano}.zip'
    pasta_ano = CSV_DIR / str(ano)

    ''' Download '''

    # Verifica se o arquivo já existe
    if zip_file.exists():
        print(f'{ano}: já existe.')

    else:

        print(f'\n{ano}: baixando...')

        # Baixa os arquivos
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        # Salva os arquivos
        zip_file.write_bytes(response.content)

        print(f'{ano}: download concluído.')

    ''' Extração '''

    # Verifica se pasta do ano já existe
    if pasta_ano.exists() and any(pasta_ano.iterdir()):
        print(f'{ano}: arquivo já extraído.')

    else:

        # Cria a pasta
        pasta_ano.mkdir(exist_ok=True)

        print(f'{ano}: extraindo...')

        # Extrai o zip para a pasta
        with ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(pasta_ano)

        print(f'{ano}: extração concluída.')

