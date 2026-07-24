from playwright.sync_api import sync_playwright
from services.utils import bot_setup_page, download_bi, obter_inicio_e_fim_do_mes
import services.etl as etl

click_timeout = 10000
timeout_geral = 1000

def buscaAG04(mes, ano, page, click_timeout, timeout_geral):
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

    caminho = download_bi(page)
    etl.processa_ag04(caminho)

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

    caminho = download_bi(page)
    etl.processa_at02(caminho)

def buscaAT03(mes, ano, page, click_timeout, timeout_geral):
    '''quando for chamar esta função rodar em um laço de acordo com os meses e anos, deve ser gerado mes a mes'''
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Atendimentos").first.click()

    page.get_by_text("AT-03 Atendimento por Procedimento segundo Sexo e Faixa Etária").click()
    page.wait_for_timeout(timeout_geral)

    page.get_by_title("Parâmetro de relatório Número Ano").click()
    page.get_by_text(ano[0]).click(timeout=click_timeout)
    page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=click_timeout)

    page.wait_for_timeout(timeout_geral)
    page.get_by_title("Parâmetro de relatório Nome Mes").click()
    page.get_by_text(mes[0]).click(timeout=click_timeout)
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

    caminho = download_bi(page)
    etl.processa_at03(caminho)

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

    caminho = download_bi(page)
    etl.processa_fe02(caminho)

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
    etl.processa_vg02(caminho)

def buscaVG04(mes, ano, page, click_timeout, timeout_geral):
    print("Coletando relatório mensal...")
    page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")

    page.get_by_text("Vagas").first.click()

    page.get_by_text("VG-04 Vagas Ofertadas por Tipo de Atendimento da Agenda por Unidade").click()
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
    etl.processa_vg04(caminho)

def buscaCG01(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes[0], ano[0])

    print("Coletando relatório mensal...")
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
    etl.processa_cg01(caminho)

def buscaCG05(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes[0], ano[0])

    print("Coletando relatório mensal...")
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
    etl.processa_cg05(caminho)

def buscaCG06(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes[0], ano[0])

    print("Coletando relatório mensal...")
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
    etl.processa_cg06(caminho)

def buscaGAC02(mes, ano, page, click_timeout, timeout_geral):
    inicio, fim = obter_inicio_e_fim_do_mes(mes[0], ano[0])

    print("Coletando relatório mensal...")
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
    etl.processa_gac02(caminho)

if __name__ == '__main__':
    p, context, page = bot_setup_page()
    ano = ["2026"]
    mes = ["Janeiro"]

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
        input("Pressione enter no terminal para finalizar")

    finally:
        print("-------Fechando-------")
        context.close()
        p.stop()