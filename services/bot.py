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
    # Pelo o que pesquisei, seria mehor nao usar o page.wait_for_load_state("networkidle") porque ela poderia
    # deixar lento o código já que as funções já esperam automaticamente o carregamento da página.

    # Usei o Enter para ir para a próxima etapa, tudo funciona bem até clicar em "Aplicar", ele clica automaticamente por causa do "Enter"
    # Ele fica "Carregando" infinitamente e não carrega o relatório, não alterei mais nada, só fiquei rodando, e do nada tudo parou de funcionar, nem a página carregava mais
    # Acho que deve ser por acessar muitas vezes a página, deve voltar ao normal mais tarde.
    print("Coletando relatório mensal...")
    page.goto("http://bisaude.prodam/sites/siga/Relatrio/Forms/current.aspx")
    page.get_by_text("Agendamentos").click()

    page.get_by_text("AG-04 Perda Secundária por Executante").click()

    page.get_by_title("Parâmetro de relatório Data Agendada.Número Ano").click()
    page.get_by_text(ano).click(timeout=5000)
    page.keyboard.press("Enter")

    page.get_by_title("Parâmetro de relatório Data Agendada.Nome Mes").click()
    page.get_by_text(mes).click(timeout=5000)
    page.keyboard.press("Enter")
    
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde do Executante.H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=5000)
    page.keyboard.press("Enter")

    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do Estabelecimento para pesquisa").fill("$$")
    page.keyboard.press("Enter")

    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde do Executante.H1 - Nome Estabelecimento").click()
    page.get_by_text("All", exact=True).click(timeout=5000)
    page.keyboard.press("Enter")

    
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.keyboard.press("Enter")

    page.get_by_title("Parâmetro de relatório Procedimento.Nome Procedimento").click()
    page.get_by_text("All", exact=True).click(timeout=5000)
    page.keyboard.press("Enter")

    page.wait_for_load_state("networkidle")

    """ page.get_by_text("Ações").click()
    page.get_by_text("Exportar").click() """

    input("pressione enter no terminal para finalizar")
    

if __name__ == '__main__':
    p, browser, page = bot_setup_page()

    try:
        buscaAG04("Janeiro", "2026", page)

    finally:
        print("-------Fechando-------")
        browser.close()
        p.stop()