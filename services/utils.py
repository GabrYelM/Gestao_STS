import os
from dotenv import load_dotenv
import calendar
import pandas as pd


# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

def bot_setup_page(usuario, senha, headless=True, default_timeout=60000):
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()

    browser = p.chromium.launch(
        headless=headless,
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1366,768']
    )
    context = browser.new_context(
        http_credentials={'username': usuario, 'password': senha},
        accept_downloads=True,
        viewport={'width': 1366, 'height': 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    page.set_default_timeout(default_timeout)
    page.set_default_navigation_timeout(default_timeout)

    print("-------Navegador iniciado com sucesso-------")
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

    pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
    save_path = os.path.join(pasta_destino, f"{nome_final}.csv")

    os.makedirs(pasta_destino, exist_ok=True)
    download.save_as(save_path)

    print(f"-------Relatório {nome_original} Gerado")
    return save_path

def obter_inicio_e_fim_do_mes(nome_mes, ano_texto):
    meses_map = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }
    
    chave = str(nome_mes or "").strip().lower()
    if chave.isdigit():
        numero_mes = int(chave)
    else:
        numero_mes = meses_map.get(chave, 1)

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