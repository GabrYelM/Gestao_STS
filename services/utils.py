import os
from dotenv import load_dotenv
import calendar
import pandas as pd
import services.etl as etl 


# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()




def bot_setup_page():
    usuario = os.getenv("PORTAL_USUARIO")
    senha = os.getenv("PORTAL_SENHA")

    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()

    browser = p.chromium.launch(headless=False, channel="msedge", slow_mo=3000)
    context = browser.new_context(http_credentials={'username': usuario, 'password': senha}, accept_downloads=True)
    page = context.new_page()

    click_timeout = 0
    timeout_geral = 0

    print("-------Login com sucesso-------")
    return p, browser, page

def download_bi(page, click_timeout=60000, timeout_geral=1000):
    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    
    page.wait_for_load_state('networkidle', timeout=0)
    page.get_by_text("Ações").first.click(timeout=click_timeout)
    page.get_by_text("Exportar").click(timeout=click_timeout)

    with page.expect_download(timeout=0) as info_download:
        page.get_by_text("CSV ponto e vírgula").click(timeout=click_timeout)

    download = info_download.value
    nome_original = download.suggested_filename
    nome_final = nome_original.split()[0]

    save_path = fr"C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS\{nome_final}.csv"

    os.makedirs(r"C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS", exist_ok=True)
    download.save_as(save_path)

    print(f"-------Relatório {nome_original} Gerado")
    return save_path


def obter_inicio_e_fim_do_mes(nome_mes, ano_texto):

    meses_pt = {
        "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
        "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
        "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
    }
    
    numero_mes = meses_pt.get(nome_mes)
    ano = int(ano_texto)

    ultimo_dia = calendar.monthrange(ano, numero_mes)[1]

    data_inicio = f"01/{str(numero_mes).zfill(2)}/{ano}"
    data_fim = f"{ultimo_dia}/{str(numero_mes).zfill(2)}/{ano}"
    
    return data_inicio, data_fim

primeira_linha = {
                "AG-04": 15,
                "AT-02": 13,
                "AT-03": 12,
                "CG-01": 11,
                "CG-05": 5,
                "CG-06": 5,
                "FE-02": 11,
                "GAC02": 5,
                "VG-02": 15,
                "VG-04": 1
                }

def limpa_():
    
    pd.read_csv("AG-04 Perda Secundária por Executante.csv", sep=";", encoding="utf-8", header=15)