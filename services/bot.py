from playwright.sync_api import sync_playwright
from utils import bot_setup_page, download_bi

click_timeout = 1000
timeout_geral = 1000

def buscaAG04(mes, ano, page, click_timeout=1000, timeout_geral=1000):
    print("Coletando relatório mensal...")

    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")
    page.get_by_text("Agendamentos").click()

    page.get_by_text("AG-04 Perda Secundária por Executante").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Data Agendada.Número Ano").click()
    for i in ano:    
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Agendada.Nome Mes").click()
    for i in mes:
        page.get_by_text(i).click(timeout=click_timeout)
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

    download_bi(page)

    input("Pressione enter no terminal para finalizar")


def buscaAT02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Atendimentos").first.click()

    page.get_by_text("AT-02 Quantidade de Pacientes e Procedimentos por Estabelecimento por mês").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    for i in ano:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    for i in mes:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 3").click()
    page.get_by_text("SUDESTE - STS PENHA").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 4").click()
    page.get_by_text("All").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do Estabelecimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Estabelecimento").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Especialidade").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Procedimento").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)

    download_bi(page)
    input("Pressione enter no terminal para finalizar")


def buscaAT03(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Atendimentos").first.click()

    page.get_by_text("AT-03 Atendimento por Procedimento segundo Sexo e Faixa Etária").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    for i in ano:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    for i in mes:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do Estabelecimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Estabelecimento").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)
    
    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Procedimento").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    page.wait_for_load_state("networkidle", timeout=180000)

    download_bi(page)
    input("Pressione enter no terminal para finalizar")

def buscaFE02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Fila Espera").first.click()

    page.get_by_text("FE-02 Fila de Espera - Fluxo de Entrada Saida e Ativos de Procedimentos e Especialidades").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    for i in ano:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    for i in mes:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    page.wait_for_load_state("networkidle", timeout=180000)

    download_bi(page)
    input("Pressione enter no terminal para finalizar")

def buscaVG02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Vagas").first.click()

    page.get_by_text("VG-02 Perda Primaria por Procedimento e Especialidade").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    for i in ano:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    for i in mes:
        page.get_by_text(i).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do Estabelecimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Estabelecimento").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    # TODO: Adicionar os filtros restantes para o relatório VG-02:
    # Nome Procedimento
    # Nome Especialidade
    # Nome Tipo Atendimento Agenda
    # Selecione o tipo de visualização
    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    page.wait_for_load_state("networkidle", timeout=180000)

    download_bi(page)
    input("Pressione enter no terminal para finalizar")

if __name__ == '__main__':
    p, context, page = bot_setup_page()
    ano = ["2026"]
    mes = ["Janeiro", "Fevereiro"]

    try:
        buscaVG02(mes, ano, page, click_timeout, timeout_geral)
    finally:
        print("-------Fechando-------")
        context.close()
        p.stop()