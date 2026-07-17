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

    browser = p.chromium.launch(headless=False, channel="msedge", slow_mo=100)
    context = browser.new_context(http_credentials={'username': usuario, 'password': senha})
    page = context.new_page()

    print("-------Login com sucesso-------")
    return p, browser, page

def buscaAG04(mes, ano, page):
    print("Coletando relatório mensal...")
    page.goto("http://bisaude.prodam/sites/siga/Relatrio/Forms/current.aspx")
    page.get_by_text("Agendamentos").click()
    page.wait_for_load_state("networkidle")
    page.get_by_text("AG-04 Perda Secundária por Executante").click()
    page.wait_for_load_state("networkidle")
    page.get_by_title("Parâmetro de relatório Data Agendada.Número Ano").click()
    page.wait_for_load_state("networkidle")
    page.get_by_text(ano).click()
    page.wait_for_timeout(200)
    page.get_by_text("Data Agendada.Número Ano").click()
    page.wait_for_load_state("networkidle")
    page.get_by_title("Parâmetro de relatório Data Agendada.Nome Mes").click()
    page.get_by_text(mes).click()
    page.get_by_title("Data Agendada.Número Ano").click()









    input("pressione enter no terminal para finalizar")
    

if __name__ == '__main__':
    p, browser, page = bot_setup_page()

    try:
        buscaAG04("Janeiro", "2026", page)

    finally:
        print("-------Fechando-------")
        browser.close()
        p.stop()