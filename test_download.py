import traceback
import os
import services.utils as su
import services.bot as sb
import services.etl as etl

# Mapa ligando o nome do relatório às suas respectivas funções de Bot e ETL
MAPA_FUNCOES = {
    'AG04': (sb.buscaAG04, etl.processa_ag04),
    'AT02': (sb.buscaAT02, etl.processa_at02),
    'AT03': (sb.buscaAT03, etl.processa_at03),
    'FE02': (sb.buscaFE02, etl.processa_fe02),
    'VG02': (sb.buscaVG02, etl.processa_vg02),
    'VG04': (sb.buscaVG04, etl.processa_vg04),
    'CG01': (sb.buscaCG01, etl.processa_cg01),
    'CG05': (sb.buscaCG05, etl.processa_cg05),
    'CG06': (sb.buscaCG06, etl.processa_cg06),
    'GAC02': (sb.buscaGAC02, etl.processa_gac02)
}

def testar_bot(nome_relatorio, func_bot):
    print(f"\n[TESTE] Iniciando robô para baixar {nome_relatorio}...")
    ano = ["2026"]
    mes = ["Janeiro"]
    click_timeout = 10000
    timeout_geral = 1000

    try:
        p, context, page = su.bot_setup_page()
    except Exception as e:
        print("❌ Falha crítica ao tentar abrir o navegador:")
        print(traceback.format_exc())
        return None

    try:
        caminho = func_bot(mes, ano, page, click_timeout, timeout_geral)
        print(f"✅ SUCESSO! Download concluído em: {caminho}")
        return caminho
    except Exception as e:
        print("\n❌ ERRO DETECTADO DURANTE O DOWNLOAD:")
        print(traceback.format_exc())
        return None
    finally:
        context.close()
        p.stop()

def testar_etl(nome_relatorio, func_etl, caminho_especifico=None):
    print(f"\n[TESTE] Iniciando ETL para o relatório {nome_relatorio}...")
    
    # Se não foi passado um caminho (ex: fluxo completo), procuramos o arquivo na pasta
    if not caminho_especifico:
        pasta_origens = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'ARQUIVOS ORIGINAIS')
        caminho_especifico = os.path.join(pasta_origens, f"{nome_relatorio[:2]}-{nome_relatorio[2:]}.csv")
        
        # O nome do arquivo na prefeitura às vezes não tem o traço dependendo do arquivo (ex: CG01.csv vs AG-04.csv)
        if not os.path.exists(caminho_especifico):
            caminho_especifico = os.path.join(pasta_origens, f"{nome_relatorio}.csv")

    if not os.path.exists(caminho_especifico):
        print(f"❌ ERRO: O arquivo {caminho_especifico} não foi encontrado!")
        print("DICA: Baixe o arquivo usando a Opção 1 antes de testar o ETL isolado.")
        return

    try:
        func_etl(caminho_especifico)
        print("✅ SUCESSO! Dados limpos e inseridos no banco de dados!")
    except Exception as e:
        print("\n❌ ERRO DETECTADO DURANTE O ETL:")
        print(traceback.format_exc())


def menu_interativo():
    print("="*50)
    print("🤖 LABORATÓRIO DE TESTES ISOLADOS (STS)")
    print("="*50)
    
    # Escolha do relatório
    print("\nRelatórios Disponíveis:", ", ".join(MAPA_FUNCOES.keys()), "ou TODOS")
    relatorio = input("Digite o nome do relatório que deseja testar (ex: AG04 ou TODOS): ").strip().upper()
    
    if relatorio not in MAPA_FUNCOES and relatorio != 'TODOS':
        print("❌ Relatório inválido!")
        return

    # Escolha do teste
    print("\nO que você deseja testar?")
    print("[1] Apenas Download (Verificar se o robô está clicando certo)")
    print("[2] Apenas ETL (Testar a limpeza e a subida para o banco)")
    print("[3] Fluxo Completo (Download seguido de ETL)")
    opcao = input("Digite o número da opção (1/2/3): ").strip()

    if opcao not in ['1', '2', '3']:
        print("❌ Opção inválida!")
        return

    relatorios_para_testar = list(MAPA_FUNCOES.keys()) if relatorio == 'TODOS' else [relatorio]

    for rel in relatorios_para_testar:
        print(f"\n{'-'*40}")
        print(f"🔄 PROCESSANDO: {rel}")
        print(f"{'-'*40}")
        
        func_bot, func_etl = MAPA_FUNCOES[rel]

        if opcao == '1':
            testar_bot(rel, func_bot)
        
        elif opcao == '2':
            testar_etl(rel, func_etl)
            
        elif opcao == '3':
            caminho = testar_bot(rel, func_bot)
            if caminho:
                testar_etl(rel, func_etl, caminho)

if __name__ == '__main__':
    menu_interativo()
