import os
from playwright.sync_api import sync_playwright
from services.utils import bot_setup_page, download_bi, obter_inicio_e_fim_do_mes
import services.etl as etl

click_timeout = 10000
timeout_geral = 1000

def buscaAG04(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando AG04")

    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")
    page.get_by_text("Agendamentos").click()

    page.get_by_text("AG-04 Perda Secundária por Executante").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Data Agendada.Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Agendada.Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
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

    caminho = download_bi(page)
    return caminho

def buscaAT02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando AT02")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Atendimentos").first.click()

    page.get_by_text("AT-02 Quantidade de Pacientes e Procedimentos por Estabelecimento por mês").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
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

    caminho = download_bi(page)
    return caminho

def buscaAT03(mes, ano, page, click_timeout, timeout_geral):
    '''quando for chamar esta função rodar em um laço de acordo com os meses e anos, deve ser gerado mes a mes'''
    print("Coletando AT03")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Atendimentos").first.click()

    page.get_by_text("AT-03 Atendimento por Procedimento segundo Sexo e Faixa Etária").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
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
    page.get_by_text("Coleta De Material P/ Exame Citopatologico De Colo Uterino", exact=True).first.click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    page.wait_for_load_state("networkidle", timeout=180000)

    caminho = download_bi(page)
    return caminho

def buscaFE02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando FE02")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Fila Espera").first.click()

    page.get_by_text("FE-02 Fila de Espera - Fluxo de Entrada Saida e Ativos de Procedimentos e Especialidades").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Digite $$ para todos ou parte do nome do procedimento para pesquisa").fill("$$")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    caminho = download_bi(page)
    return caminho

def buscaVG02(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando VG02")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Vagas").first.click()

    page.get_by_text("VG-02 Perda Primaria por Procedimento e Especialidade").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 3").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.get_by_text("SUDESTE - STS PENHA").click(timeout=click_timeout)
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
    page.get_by_title("Parâmetro de relatório Selecione o tipo de visualização").select_option(value="2")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.locator("input[value='Aplicar']").click(timeout=click_timeout)
    page.wait_for_load_state("networkidle", timeout=180000)

    caminho = download_bi(page)
    return caminho

def buscaVG04(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando VG04")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Vagas").first.click()

    page.get_by_text("VG-04 Vagas Ofertadas por Tipo de Atendimento da Agenda por Unidade").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes, exact=True).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 2").click()
    page.get_by_text("COORD REGIONAL DE SAUDE SUDESTE").click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório H1 - Nome Nível 3").click()
    page.get_by_text("All", exact=True).first.click(timeout=click_timeout)
    page.get_by_text("SUDESTE - STS PENHA").click(timeout=click_timeout)
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

    caminho = download_bi(page)
    return caminho

def buscaCG01(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes, ano)

    print("Coletando CG01")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/maepaulistana/Paginas/Mae-Paulistana.aspx")

    page.get_by_text("Contrato de Gestão").first.click()

    with page.expect_popup() as info_new_page:
        page.get_by_text("CG01 - Gestantes com sete ou mais consultas").click()
        page.wait_for_timeout(timeout_geral)

    page = info_new_page.value
    page.wait_for_load_state()

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Início").fill(inicio)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Fim").fill(fim)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Coordenadoria Regional").select_option("COORD REGIONAL DE SAUDE SUDESTE")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Supervisão Técnica").select_option("SUDESTE - STS PENHA")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)


    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Tipo de Visualização").select_option("Estabelecimento")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    caminho = download_bi(page)
    return caminho

def buscaCG05(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes, ano)

    print("Coletando CG05")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/maepaulistana/Paginas/Mae-Paulistana.aspx")

    page.get_by_text("Contrato de Gestão").first.click()

    page.get_by_text("CG05 - Lista nominal de gestantes com total de consultas de PN.rdl").click()
    page.wait_for_timeout(timeout_geral)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Início").fill(inicio)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Fim").fill(fim)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Coordenadoria Regional").select_option("COORD REGIONAL DE SAUDE SUDESTE")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Supervisão Técnica").select_option("SUDESTE - STS PENHA")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde").select_option("(Todas as opções)")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    caminho = download_bi(page)
    return caminho

def buscaCG06(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes, ano)

    print("Coletando CG06")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/maepaulistana/Paginas/Mae-Paulistana.aspx")

    page.get_by_text("Contrato de Gestão").first.click()

    with page.expect_popup() as info_new_page:
        page.get_by_text("CG06 - Lista nominal de gestantes com exames realizados").click()
        page.wait_for_timeout(timeout_geral)

    page = info_new_page.value
    page.wait_for_load_state()

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Início").fill(inicio)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Data Previsão Parto - Fim").fill(fim)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Coordenadoria Regional").select_option("COORD REGIONAL DE SAUDE SUDESTE")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Supervisão Técnica").select_option("SUDESTE - STS PENHA")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde").select_option("(Todas as opções)")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    caminho = download_bi(page)
    return caminho

def buscaGAC02(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes, ano)

    print("Coletando GAC02")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/maepaulistana/Paginas/Mae-Paulistana.aspx")

    page.get_by_text("Gestantes - Acolhimento / Risco").first.click()

    with page.expect_popup() as info_new_page:
        page.get_by_text("GAC02 - Gestantes ativas").click()
        page.wait_for_timeout(timeout_geral)

    page = info_new_page.value
    page.wait_for_load_state()

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Coordenadoria Regional").select_option("COORD REGIONAL DE SAUDE SUDESTE")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Supervisão Técnica").select_option("SUDESTE - STS PENHA")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Estabelecimento de Saúde").select_option("(Todas as opções)")
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    caminho = download_bi(page)
    return caminho

def buscaPainelMonitoramento(usuario, senha, tipo_local="STS", page=None, click_timeout=60000, timeout_geral=1500):
    print(f"Iniciando coleta do Painel de Monitoramento 3.2 (CEInfo) - Modo: {tipo_local}...")
    
    # Configura tempo limite estendido (10 minutos) para relatórios pesados
    page.set_default_timeout(600000)
    page.set_default_navigation_timeout(600000)
    
    url_pm = "http://10.20.254.148/xampp/pm/"
    page.goto(url_pm, timeout=120000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(timeout_geral)

    print("Acessando 'Emissão de Relatórios'...")
    try:
        page.locator("text='Emissão de Relatórios'").first.click(timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(timeout_geral)
    except Exception as e:
        print(f"Nota ao clicar em Emissão de Relatórios (pode já estar na tela): {e}")
    
    # 1. Autenticação (se houver formulário de login na página)
    user_input = page.locator("input[name='login'], input[name='usuario'], input[name='user'], input[type='text']").first
    pass_input = page.locator("input[name='senha'], input[name='password'], input[type='password']").first
    
    try:
        if pass_input.is_visible(timeout=4000):
            print("Preenchendo formulário de login...")
            user_input.fill(usuario)
            pass_input.fill(senha)
            page.get_by_text("Ok").click()
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(timeout_geral)
    except Exception as e:
        print(f"Nota no formulário de login: {e}")

    # 2. Seleção dos Filtros no Painel
    print(f"Selecionando filtros do Painel de Monitoramento ({tipo_local})...")
    page.locator("input[type='radio'][value='Tudo']").click(timeout=30000)
    
    if tipo_local == "Subprefeitura":
        # Marca o radio button de Subprefeitura
        page.locator("input[type='radio'][value='Subprefeitura'], input[type='radio'][value='SubPrefeitura']").first.click(timeout=click_timeout)
        page.wait_for_timeout(timeout_geral)
        # Seleciona PENHA na lista de Subprefeitura
        try:
            chk = page.locator("input[type='checkbox'][id='checkunsp']")
            if chk.is_visible(timeout=2000) and not chk.is_checked():
                chk.click(timeout=click_timeout)
            page.locator("select[id='boxsp[]']").select_option(label="PENHA")
        except Exception:
            page.locator("option").filter(has_text="PENHA").click()
        print("Subprefeitura PENHA selecionada!")
    else:
        # Marca o radio button de STS (Supervisão Técnica de Saúde)
        page.locator("input[type='radio'][value='Supervisão Técnica de Saúde']").click(timeout=click_timeout)
        page.wait_for_timeout(timeout_geral)
        # Seleciona PENHA na lista de STS
        try:
            page.locator("select[id='boxst[]']").select_option(label="PENHA")
        except Exception:
            page.locator("option").filter(has_text="PENHA").click()
        print("STS PENHA selecionada!")
        
    page.wait_for_timeout(timeout_geral)

    # Conteúdo: Série, sinal mensal e desempenho
    page.locator("select[id='radcont']").select_option(value="Série e sinais")

    page.locator("input[id='checkpto'][value='sss']").click(timeout=click_timeout)
    page.wait_for_timeout(timeout_geral)

    # 3. Emitir Relatório
    print("Clicando no botão 'Emitir Relatório'...")
    page.locator("input[value='Emitir Relatório']").click(no_wait_after=True)
    
    # 4. Aguarda pacientemente o servidor da Prefeitura processar e carregar a tabela
    print("Aguardando carregamento da tabela de resultados (pode demorar alguns minutos)...")
    try:
        page.wait_for_selector("table", timeout=600000)
    except Exception:
        page.wait_for_load_state("domcontentloaded", timeout=600000)
        
    page.wait_for_timeout(3000)
    
    conteudo_html = page.content()
    
    nome_arquivo = "painel_monitoramento_subprefeitura.html" if tipo_local == "Subprefeitura" else "painel_monitoramento.html"
    pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
    os.makedirs(pasta_destino, exist_ok=True)
    caminho_salvo = os.path.join(pasta_destino, nome_arquivo)
    with open(caminho_salvo, "w", encoding="utf-8") as f:
        f.write(conteudo_html)
        
    print(f"Tabela do Painel de Monitoramento ({tipo_local}) extraída e salva com sucesso!")
    return conteudo_html

if __name__ == '__main__':
    p, context, page = bot_setup_page()
    ano = "2026"
    mes = "Janeiro"

    try:
        buscaAG04(mes, ano, page, click_timeout, timeout_geral)
        buscaAT02(mes, ano, page, click_timeout, timeout_geral)
        buscaAT03(mes, ano, page, click_timeout, timeout_geral)
        buscaFE02(mes, ano, page, click_timeout, timeout_geral)
        buscaVG02(mes, ano, page, click_timeout, timeout_geral)
        buscaVG04(mes, ano, page, click_timeout, timeout_geral)
        buscaCG01(mes, ano, page, click_timeout, timeout_geral)
        buscaCG05(mes, ano, page, click_timeout, timeout_geral)
        buscaCG06(mes, ano, page, click_timeout, timeout_geral)
        buscaGAC02(mes, ano, page, click_timeout, timeout_geral)

    finally:
        print("-------Fechando-------")
        context.close()
        p.stop()
