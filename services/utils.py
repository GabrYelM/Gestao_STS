import os
from dotenv import load_dotenv
import calendar
import pandas as pd


# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de caminho de navegadores compartilhado para ambientes Windows multiusuário
basedir_proj = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    proj_browsers = os.path.join(basedir_proj, ".browsers")
    if os.path.exists(proj_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = proj_browsers


def obter_diretorio_navegadores():
    """
    Retorna o melhor caminho para os navegadores do Playwright.
    Prioriza .browsers no diretório do projeto para permitir compartilhamento entre
    diferentes usuários do Windows, ou busca em diretórios locais existentes.
    """
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and os.path.exists(os.environ["PLAYWRIGHT_BROWSERS_PATH"]):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pasta_projeto_browsers = os.path.join(raiz_projeto, ".browsers")
    if os.path.exists(pasta_projeto_browsers):
        return pasta_projeto_browsers

    usuarios_dir = r"C:\Users"
    if os.path.exists(usuarios_dir):
        for user_folder in ["x383959", "x546529"] + [d for d in os.listdir(usuarios_dir) if os.path.isdir(os.path.join(usuarios_dir, d))]:
            candidato = os.path.join(usuarios_dir, user_folder, "AppData", "Local", "ms-playwright")
            if os.path.exists(candidato):
                try:
                    if any("chromium" in f for f in os.listdir(candidato)):
                        return candidato
                except Exception:
                    pass

    return pasta_projeto_browsers


def auto_instalar_navegador():
    """
    Executa a auto-instalação silenciosa do Chromium caso não esteja presente.
    """
    import subprocess
    import sys
    diretorio = obter_diretorio_navegadores()
    os.makedirs(diretorio, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = diretorio
    print(f"[Playwright] Instalando/Verificando Chromium em: {diretorio}...")
    try:
        resultado = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=os.environ,
            capture_output=True,
            text=True,
            timeout=300
        )
        return resultado.returncode == 0
    except Exception as e:
        print(f"[Playwright] Falha ao tentar auto-instalar Chromium: {e}")
        return False


def launch_chromium_seguro(p, headless=True, timeout=60000):
    """
    Lança o navegador Chromium com camadas de redundância e auto-recuperação.
    Garante funcionamento em ambientes multiusuário do Windows e previne falhas de instalação.
    """
    diretorio = obter_diretorio_navegadores()
    if os.path.exists(diretorio):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = diretorio

    args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1366,768']

    try:
        return p.chromium.launch(headless=headless, args=args, timeout=timeout)
    except Exception as e1:
        msg1 = str(e1)
        if any(term in msg1 for term in ["Executable doesn't exist", "playwright install", "Looks like Playwright was just installed"]):
            print("[Playwright] Executável do navegador não encontrado. Tentando auto-recuperação...")
            
            sucesso = auto_instalar_navegador()
            if sucesso:
                try:
                    return p.chromium.launch(headless=headless, args=args, timeout=timeout)
                except Exception as e2:
                    print(f"[Playwright] Erro após tentativa de auto-instalação: {e2}")

            raise RuntimeError(
                "O navegador do robô (Chromium) não foi encontrado no sistema ou não pôde ser iniciado.\n"
                "Para solucionar definitivamente, execute o arquivo 'instalar.bat' na pasta do sistema."
            )
        else:
            raise e1


def bot_setup_page(usuario, senha, headless=True, default_timeout=60000):
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()

    browser = launch_chromium_seguro(p, headless=headless, timeout=default_timeout)
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