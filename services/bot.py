from playwright.sync_api import sync_playwright
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

def buscaAG04(mes, ano, page, click_timeout=1000, timeout_geral=1000):
    print("Coletando relatório mensal...")

    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")
    page.get_by_text("Agendamentos").click()

    page.get_by_text("AG-04 Perda Secundária por Executante").click()

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Agendada.Número Ano").click()
    page.get_by_text(ano).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Agendada.Nome Mes").click()
    page.get_by_text(mes).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)
    
    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde do Executante.H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde do Executante.H1 - Nome Nível 3").click()
    page.get_by_text("SUDESTE - STS PENHA").click(timeout=click_timeout)
    page.get_by_text("All").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do Estabelecimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde do Executante.H1 - Nome Estabelecimento").click()
    page.get_by_text("All", exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Procedimento.Nome Procedimento").click()
    page.get_by_text("All", exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)

    page.wait_for_load_state('networkidle')
    page.get_by_text("Ações").first.click(timeout=click_timeout)
    page.get_by_text("Exportar").click(timeout=click_timeout)

    download_bi(page)

    input("pressione enter no terminal para finalizar")
    
def download_bi(page, click_timeout=1000, timeout_geral=1000):
    with page.expect_download() as info_download:
        page.get_by_text("CSV ponto e vírgula").click(timeout=click_timeout)

    download = info_download.value
    nome_original = download.suggested_filename

    save_path = fr"C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS\{nome_original}"

    os.makedirs("C:\.Projetos\Gestao_STS\ARQUIVOS ORIGINAIS", exist_ok=True)
    download.save_as(save_path)

if __name__ == '__main__':
    p, context, page = bot_setup_page()

    try:
        buscaAG04("Janeiro", "2026", page)
    finally:
        print("-------Fechando-------")
        context.close()
        p.stop()