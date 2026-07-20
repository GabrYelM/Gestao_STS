import os
from dotenv import load_dotenv

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

def download_bi(page, click_timeout=1000, timeout_geral=1000):
    with page.expect_download() as info_download:
        page.get_by_text("CSV ponto e vírgula").click(timeout=click_timeout)

    download = info_download.value
    nome_original = download.suggested_filename

    save_path = fr"C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS\{nome_original}"

    os.makedirs("C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS", exist_ok=True)
    download.save_as(save_path)