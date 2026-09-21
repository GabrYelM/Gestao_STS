import sys
import os
import json
import io

# Redireciona stdout e stderr para arquivo de log quando rodando com pythonw (evita crash por stdout=None no Windows)
if sys.stdout is None or sys.stderr is None:
    log_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'server.log')
    try:
        sys.stdout = open(log_file, 'a', encoding='utf-8', buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, jsonify, request, session, url_for
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
import threading
from decorators import *
app = Flask(__name__)

load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from database import db
db.init_app(app)

import models

with app.app_context():
    db.create_all()

    admin_existente = models.Usuario.query.filter_by(username="admin").first()
    normal_existente = models.Usuario.query.filter_by(username="normal").first()

    if not admin_existente:
        admin = models.Usuario(username="admin", is_admin=True)
        admin.hash_senha("admin")
        db.session.add(admin)
        db.session.commit()

    if not normal_existente:
        normal = models.Usuario(username="normal", is_admin=False)
        normal.hash_senha("normal")
        db.session.add(normal)
        db.session.commit()

    # Inicialização dos Vínculos EMAB / eMulti e Equipes a partir do catalogo_geral.json
    catalogo_path = os.path.join(basedir, 'services', 'catalogo_geral.json')
    cat_init = {}
    if os.path.exists(catalogo_path):
        try:
            with open(catalogo_path, 'r', encoding='utf-8') as f:
                cat_init = json.load(f)
        except Exception:
            pass

    # 1. Equipes do Catálogo Geral
    if models.Equipe.query.count() == 0 and 'equipes' in cat_init and cat_init['equipes']:
        for eq in cat_init['equipes']:
            if isinstance(eq, dict) and eq.get('cod_ine') and eq.get('sigla'):
                e_obj = models.Equipe(cod_ine=str(eq['cod_ine']), sigla=eq['sigla'], unidade=eq.get('unidade', ''))
                db.session.add(e_obj)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # 2. Vínculos EMAB / eMulti do Catálogo Geral ou Padrão Inicial
    if models.VinculoEmab.query.count() == 0:
        if 'vinculos_emab' in cat_init and cat_init['vinculos_emab']:
            for vinc in cat_init['vinculos_emab']:
                if isinstance(vinc, dict) and vinc.get('nome_equipe') and vinc.get('unidade_destino'):
                    v_obj = models.VinculoEmab(nome_equipe=vinc['nome_equipe'], unidade_destino=vinc['unidade_destino'], tipo=vinc.get('tipo', 'EMAB'))
                    db.session.add(v_obj)
        else:
            vinculos_iniciais = [
                ("Emab Ae Carvalho", "UBS ANTONIO ESTEVÃO DE CARVALHO", "EMAB"),
                ("Emab Ae Carvalho/Nobrega", "AMA/UBS INTEGRADA PADRE MANOEL DA NOBREGA", "EMAB"),
                ("Emab Anchieta", "UBS PADRE JOSÉ DE ANCHIETA", "EMAB"),
                ("Emab Anchieta/Villalobo", "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO", "EMAB"),
                ("Emab Aricanduva", "UBS VILA ARICANDUVA", "EMAB"),
                ("Emab Aricanduva/Sao Nicolau", "UBS JARDIM SAO NICOLAU", "EMAB"),
                ("Emab Arthur Alvim", "UBS PARQUE ARTHUR ALVIM", "EMAB"),
                ("Emab Arthur Alvim/Guilhermina", "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO", "EMAB"),
                ("Emab Chacara Cruzeiro Do Sul", "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO", "EMAB"),
                ("Emab Chacara/Patriarca", "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR", "EMAB"),
                ("Emab Esperanca", "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO", "EMAB"),
                ("Inativo - Emab Esperanca/Trindade", "UBS ENGENHEIRO TRINDADE", "EMAB"),
                ("Emab Sao Francisco", "UBS JARDIM SAO FRANCISCO I", "EMAB"),
                ("Emab Sao Francisco/Vila Silvia", "AMA/UBS INTEGRADA VILA SILVIA", "EMAB"),
                ("Emab Vila Matilde", "UBS VILA MATILDE - DR. RUBENS DO VAL", "EMAB"),
                ("Emab Vila Matilde/Maringa", "UBS JARDIM MARINGA - VILA TALARICO", "EMAB"),
                ("Emulti Ae Carvalho", "UBS ANTONIO ESTEVÃO DE CARVALHO", "eMulti"),
                ("Emulti Ae Carvalho/Nobrega", "AMA/UBS INTEGRADA PADRE MANOEL DA NOBREGA", "eMulti"),
                ("Emulti Anchieta", "UBS PADRE JOSÉ DE ANCHIETA", "eMulti"),
                ("Emulti Anchieta/Villalobo", "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO", "eMulti"),
                ("Emulti Aricanduva", "UBS VILA ARICANDUVA", "eMulti"),
                ("Emulti Aricanduva/Sao Nicolau", "UBS JARDIM SAO NICOLAU", "eMulti"),
                ("Emulti Arthur Alvim", "UBS PARQUE ARTHUR ALVIM", "eMulti"),
                ("Emulti Arthur Alvim/Guilhermina", "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO", "eMulti"),
                ("Emulti Chacara Cruzeiro Do Sul", "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO", "eMulti"),
                ("Emulti Chacara/Patriarca", "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR", "eMulti"),
                ("Emulti Eng Goulart", "AMA/UBS ENGENHEIRO GOULART- DR JOSE PIRES", "eMulti"),
                ("Emulti Eng Goulart/Cangaiba", "AMA/UBS INTEGRADA CANGAIBA - DR. CARLOS GENTILE DE MELLO", "eMulti"),
                ("Emulti Esperanca", "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO", "eMulti"),
                ("Emulti Esperanca/Emilio", "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA", "eMulti"),
                ("Emulti Granada/Trindade", "UBS ENGENHEIRO TRINDADE", "eMulti"),
                ("Emulti Sao Francisco", "UBS JARDIM SAO FRANCISCO I", "eMulti"),
                ("Emulti Sao Francisco/Vila Silvia", "AMA/UBS INTEGRADA VILA SILVIA", "eMulti"),
                ("Emulti Vila Matilde", "UBS VILA MATILDE - DR. RUBENS DO VAL", "eMulti"),
                ("Emulti Vila Matilde/Maringa", "UBS JARDIM MARINGA - VILA TALARICO", "eMulti")
            ]
            for nome, dest, tp in vinculos_iniciais:
                v = models.VinculoEmab(nome_equipe=nome, unidade_destino=dest, tipo=tp)
                db.session.add(v)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Inicialização dos Dados Populacionais Demográficos (Relatório 01 / Censo 2010) se vazio
    if models.REL01.query.count() == 0:
        caminho_pop = os.path.join(basedir, "ARQUIVOS ORIGINAIS", "Desejado", "Final desejado.xlsx")
        if os.path.exists(caminho_pop):
            try:
                import pandas as pd
                df_raw = pd.read_excel(caminho_pop, sheet_name='POP', header=None)
                faixas_cols = [
                    'faixa_00_04', 'faixa_05_09', 'faixa_10_14', 'faixa_15_19',
                    'faixa_20_24', 'faixa_25_29', 'faixa_30_34', 'faixa_35_39',
                    'faixa_40_44', 'faixa_45_49', 'faixa_50_54', 'faixa_55_59',
                    'faixa_60_64', 'faixa_65_69', 'faixa_70_74', 'faixa_75_mais'
                ]
                sections = [
                    ('TOTAL', 7, 27),
                    ('MASCULINO', 31, 51),
                    ('FEMININO', 55, 75)
                ]
                for tipo_nome, start_r, end_r in sections:
                    for r in range(start_r, end_r + 1):
                        cnes_val = str(df_raw.iloc[r, 1]).strip() if pd.notna(df_raw.iloc[r, 1]) else ''
                        if cnes_val.endswith('.0'): cnes_val = cnes_val[:-2]
                        estab_val = str(df_raw.iloc[r, 2]).strip() if pd.notna(df_raw.iloc[r, 2]) else ''
                        da_val = str(df_raw.iloc[r, 3]).strip() if pd.notna(df_raw.iloc[r, 3]) else ''
                        pop_tot = float(df_raw.iloc[r, 4]) if pd.notna(df_raw.iloc[r, 4]) else 0.0

                        kwargs = {
                            'tipo': tipo_nome,
                            'cnes': cnes_val,
                            'estabelecimento': estab_val,
                            'da': da_val,
                            'populacao_total': pop_tot
                        }
                        for i, col_name in enumerate(faixas_cols):
                            val = float(df_raw.iloc[r, 5 + i]) if pd.notna(df_raw.iloc[r, 5 + i]) else 0.0
                            kwargs[col_name] = val
                        obj = models.REL01(**kwargs)
                        db.session.add(obj)
                db.session.commit()
            except Exception as e:
                print(f"Erro ao inicializar dados populacionais do Relatório 01: {e}")
                db.session.rollback()

import services.utils as su
import services.bot as sb
import pandas as pd
import services.etl as etl
import services.producao as prod
from services.competencias import obter_competencias_por_relatorio, sincronizar_todas_competencias, registrar_competencia
import socket

def obter_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'

@app.context_processor
def inject_network_info():
    ip = obter_ip_local()
    port = 5000
    network_url = f"http://{ip}:{port}"
    return dict(ip_local=ip, porta=port, url_rede=network_url)

gerenciador_tarefas = ThreadPoolExecutor(max_workers=1)
evento_cancelar_extracao = threading.Event()

def executar_bot(funcao_busca, mes, ano, usuario, senha):
    if evento_cancelar_extracao.is_set():
        return None, "Interrompido por cancelamento"
    p, context, page = su.bot_setup_page(usuario, senha, default_timeout=60000)
    try:
        if evento_cancelar_extracao.is_set():
            return None, "Interrompido por cancelamento"
        caminho = funcao_busca(mes, ano, page, 60000, 100)
        return caminho, None
    except Exception as e:
        if evento_cancelar_extracao.is_set():
            return None, "Interrompido por cancelamento"
        nome_f = getattr(funcao_busca, '__name__', 'Bot')
        msg_erro = f"{nome_f} ({mes}/{ano}): {str(e)}"
        print(f"Erro no bot: {msg_erro}")
        return None, msg_erro
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            p.stop()
        except Exception:
            pass

status_extracao = {
    "em_andamento": False,
    "concluido": False,
    "cancelado": False,
    "cancelando": False,
    "progresso": "",
    "erros": [],
    "sucessos": [],
    "total_sucessos": 0,
    "total_erros": 0
}

def gerar_lista_meses(m_inicio, a_inicio, m_fim, a_fim):
    meses_ordem = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    try:
        idx_inicio = meses_ordem.index(m_inicio)
        idx_fim = meses_ordem.index(m_fim)
    except ValueError:
        return [(m_inicio, str(a_inicio))]
    
    ano_inicio_int = int(a_inicio)
    ano_fim_int = int(a_fim)
    
    lista = []
    for ano in range(ano_inicio_int, ano_fim_int + 1):
        start_idx = idx_inicio if ano == ano_inicio_int else 0
        end_idx = idx_fim if ano == ano_fim_int else 11
        for m in range(start_idx, end_idx + 1):
            lista.append((meses_ordem[m], str(ano)))
    return lista

MAPA_NOMES_RELATORIOS = {
    'AT02': 'AT-02 Quantidade de Pacientes e Procedimentos por Estabelecimento por mês',
    'AG04': 'AG-04 Perda Secundária por Executante',
    'AT03': 'AT-03 Atendimento por Procedimento segundo Sexo e Faixa Etária',
    'FE02': 'FE-02 Fila de Espera - Fluxo de Entrada Saida e Ativos de Procedimentos e Especialidades',
    'VG02': 'VG-02 Perda Primaria por Procedimento e Especialidade',
    'VG04': 'VG-04 Vagas Ofertadas por Tipo de Atendimento da Agenda por Unidade',
    'GAC02': 'GAC02 - Gestantes ativas',
    'CG01': 'CG01 - Gestantes com sete ou mais consultas',
    'CG05': 'CG05 - Lista nominal de gestantes com total de consultas de PN.rdl',
    'CG06': 'CG06 - Lista nominal de gestantes com exames realizados',
    'REL06': 'Painel de monitoramento PENHA',
    'REL07': 'Painel de monitoramento por estabelecimento',
    'RELATORIO_08': 'Relatório 08 - Gestantes (GAC02, CG01, CG05, CG06)',
    'CARGA_RELATORIO_08': 'Relatório 08 - Gestantes (GAC02, CG01, CG05, CG06)',
    'CARGA_COMPLETA_PM': 'Carga completa PM',
    'PM_TODOS': 'Carga completa PM',
    'CARGA_COMPLETA_BI': 'Carga completa BI',
    'TODOS': 'Carga completa BI',
    'CARGA_COMPLETA_BI_PM': 'Carga completa BI e PM',
}

def processo_background(mes_inicio, ano_inicio, mes_fim, ano_fim, relatorio_escolhido, usuario, senha, usuario_pm=None, senha_pm=None):
    global status_extracao, evento_cancelar_extracao
    evento_cancelar_extracao.clear()
    status_extracao["em_andamento"] = True
    status_extracao["concluido"] = False
    status_extracao["cancelado"] = False
    status_extracao["cancelando"] = False
    status_extracao["progresso"] = "Iniciando fila..."
    status_extracao["sucessos"] = []
    status_extracao["erros"] = []
    status_extracao["total_sucessos"] = 0
    status_extracao["total_erros"] = 0
    
    todas_funcoes = {
        'AG04': (sb.buscaAG04, etl.processa_ag04),
        'AT02': (sb.buscaAT02, etl.processa_at02),
        'AT03': (sb.buscaAT03, etl.processa_at03),
        'FE02': (sb.buscaFE02, etl.processa_fe02),
        'VG02': (sb.buscaVG02, etl.processa_vg02),
        'VG04': (sb.buscaVG04, etl.processa_vg04),
        'CG01': (sb.buscaCG01, etl.processa_cg01),
        'CG05': (sb.buscaCG05, etl.processa_cg05),
        'CG06': (sb.buscaCG06, etl.processa_cg06),
        'GAC02': (sb.buscaGAC02, etl.processa_gac02),
    }

    if relatorio_escolhido in ["TODOS", "CARGA_COMPLETA_BI", "CARGA_COMPLETA_BI_PM"]:
        itens_selecionados = list(todas_funcoes.items())
    elif relatorio_escolhido in ["RELATORIO_08", "CARGA_RELATORIO_08", "REL_08"]:
        funcoes_08 = ['GAC02', 'CG01', 'CG05', 'CG06']
        itens_selecionados = [(k, todas_funcoes[k]) for k in funcoes_08 if k in todas_funcoes]
    else:
        func = todas_funcoes.get(relatorio_escolhido)
        itens_selecionados = [(relatorio_escolhido, func)] if func else []
        
    if not itens_selecionados:
        print("Relatório escolhido inválido.")
        status_extracao["em_andamento"] = False
        status_extracao["concluido"] = True
        status_extracao["erros"].append({
            "codigo": "ERRO",
            "relatorio": "Geral",
            "competencia": "N/A",
            "motivo": "Relatório escolhido inválido."
        })
        return

    gac02_item = None
    funcoes_loop = []
    for chave, (bot_f, etl_f) in itens_selecionados:
        if chave == 'GAC02':
            gac02_item = (chave, bot_f, etl_f)
        else:
            funcoes_loop.append((chave, bot_f, etl_f))

    hoje = datetime.today()
    periodo_gac = f"{hoje.year}{str(hoje.month).zfill(2)}"

    sucessos_fila = []
    erros_fila = []

    lista_periodos = gerar_lista_meses(mes_inicio, ano_inicio, mes_fim, ano_fim) if relatorio_escolhido != "GAC02" else []

    # O GAC-02 é um snapshot em tempo real. Em rotinas de lote, só deve ser executado
    # se o usuário selecionou explicitamente GAC02 ou se o período do lote inclui o mês/ano corrente.
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    hoje_mes_nome = meses_pt.get(hoje.month)
    hoje_ano_str = str(hoje.year)
    periodo_contem_atual = any(m == hoje_mes_nome and str(a) == hoje_ano_str for m, a in lista_periodos)
    deve_extrair_gac = (relatorio_escolhido == "GAC02") or (gac02_item is not None and periodo_contem_atual)

    if gac02_item and deve_extrair_gac and not evento_cancelar_extracao.is_set():
        chave, bot_gac, etl_gac = gac02_item
        nome_rel = MAPA_NOMES_RELATORIOS.get(chave, chave)
        status_extracao["progresso"] = "Extraindo GAC02 (Snapshot Geral)..."
        try:
            caminho_gac, erro_gac = executar_bot(bot_gac, hoje.strftime('%B'), hoje.year, usuario, senha)
            if evento_cancelar_extracao.is_set():
                pass
            elif caminho_gac:
                etl_gac(caminho_gac, periodo_gac)
                sucessos_fila.append({
                    "codigo": chave,
                    "relatorio": nome_rel,
                    "competencia": hoje.strftime('%m/%Y'),
                    "periodo": int(periodo_gac),
                    "status": "Atualizado com sucesso"
                })
            elif erro_gac:
                erros_fila.append({
                    "codigo": chave,
                    "relatorio": nome_rel,
                    "competencia": hoje.strftime('%m/%Y'),
                    "periodo": int(periodo_gac),
                    "motivo": erro_gac
                })
        except Exception as e:
            print(f"Erro no GAC02: {e}")
            erros_fila.append({
                "codigo": chave,
                "relatorio": nome_rel,
                "competencia": hoje.strftime('%m/%Y'),
                "periodo": int(periodo_gac),
                "motivo": f"Erro no processamento (ETL): {str(e)}"
            })

    if relatorio_escolhido != "GAC02" and len(funcoes_loop) > 0 and not evento_cancelar_extracao.is_set():
        lista_periodos = gerar_lista_meses(mes_inicio, ano_inicio, mes_fim, ano_fim)

        for mes, ano in lista_periodos:
            if evento_cancelar_extracao.is_set():
                print("Interrupção da extração solicitada pelo usuário.")
                break
            status_extracao["progresso"] = f"Extraindo {mes}/{ano}..."
            print(f"Iniciando fila para {mes}/{ano}")
            
            periodo = int(f"{ano}{MAPA_MESES.get(mes, '01')}")
            
            with ThreadPoolExecutor(max_workers=4) as bot_executor:
                futuros = []
                for chave, func_bot, func_etl in funcoes_loop:
                    if evento_cancelar_extracao.is_set():
                        break
                    futuro = bot_executor.submit(executar_bot, func_bot, mes, ano, usuario, senha)
                    futuros.append((chave, futuro, func_etl))
                    
                for chave, futuro, func_etl in futuros:
                    if evento_cancelar_extracao.is_set():
                        break
                    nome_rel = MAPA_NOMES_RELATORIOS.get(chave, chave)
                    caminho, erro_bot = futuro.result()
                    if evento_cancelar_extracao.is_set():
                        break
                    if caminho:
                        try:
                            status_extracao["progresso"] = f"Gravando {chave} ({mes}/{ano}) no BD..."
                            func_etl(caminho, periodo)
                            sucessos_fila.append({
                                "codigo": chave,
                                "relatorio": nome_rel,
                                "competencia": f"{mes}/{ano}",
                                "periodo": periodo,
                                "status": "Atualizado com sucesso"
                            })
                        except Exception as e:
                            print(f"Erro no ETL de {chave} ({caminho}): {e}")
                            erros_fila.append({
                                "codigo": chave,
                                "relatorio": nome_rel,
                                "competencia": f"{mes}/{ano}",
                                "periodo": periodo,
                                "motivo": f"Erro no processamento (ETL): {str(e)}"
                            })
                    elif erro_bot and not evento_cancelar_extracao.is_set():
                        erros_fila.append({
                            "codigo": chave,
                            "relatorio": nome_rel,
                            "competencia": f"{mes}/{ano}",
                            "periodo": periodo,
                            "motivo": erro_bot
                        })

    if relatorio_escolhido == "CARGA_COMPLETA_BI_PM" and not evento_cancelar_extracao.is_set():
        status_extracao["progresso"] = "Extração do BI concluída. Iniciando Painel de Monitoramento..."
        u_pm = usuario_pm if usuario_pm else usuario
        s_pm = senha_pm if senha_pm else senha
        sucessos_pm, erros_pm = executar_extracao_pm_sync(u_pm, s_pm, "TODOS")
        sucessos_fila.extend(sucessos_pm)
        erros_fila.extend(erros_pm)

    try:
        sincronizar_todas_competencias()
    except Exception:
        pass

    status_extracao["sucessos"] = sucessos_fila
    status_extracao["erros"] = erros_fila
    status_extracao["total_sucessos"] = len(sucessos_fila)
    status_extracao["total_erros"] = len(erros_fila)

    if evento_cancelar_extracao.is_set():
        status_extracao["cancelado"] = True
        status_extracao["cancelando"] = False
        status_extracao["progresso"] = f"Extração cancelada pelo usuário com segurança ({len(sucessos_fila)} gravados antes da parada)."
    elif erros_fila and sucessos_fila:
        status_extracao["progresso"] = f"Concluído parcialmente ({len(sucessos_fila)} atualizados, {len(erros_fila)} falhas)."
    elif erros_fila and not sucessos_fila:
        status_extracao["progresso"] = f"Concluído com erro nas rotinas solicitadas."
    else:
        status_extracao["progresso"] = f"100% Concluído com sucesso ({len(sucessos_fila)} atualizados)!"

    status_extracao["em_andamento"] = False
    status_extracao["concluido"] = True


def executar_extracao_pm_sync(usuario, senha, relatorio_escolhido="TODOS"):
    sucessos_pm = []
    erros_pm = []
    try:
        from services.utils import bot_setup_page
        from services.bot import buscaPainelMonitoramento
        from services.etl import processa_painel_monitoramento
        
        # Painel de Monitoramento mantém timeout longo (600s = 10min)
        p, browser, page = bot_setup_page(usuario, senha, default_timeout=600000)
        try:
            # 1. Painel de monitoramento PENHA (Relatório 06)
            if not evento_cancelar_extracao.is_set() and relatorio_escolhido in ["TODOS", "CARGA_COMPLETA_PM", "PM_TODOS", "REL06"]:
                status_extracao["progresso"] = "Extraindo Painel de monitoramento PENHA..."
                html_sts = buscaPainelMonitoramento(usuario, senha, tipo_local="STS", page=page)
                if evento_cancelar_extracao.is_set():
                    pass
                elif html_sts:
                    status_extracao["progresso"] = "Gravando Painel PENHA (REL-06) no BD..."
                    processa_painel_monitoramento(html_sts, tabela_db='REL-06', default_localidade='STS PENHA')
                    sucessos_pm.append({
                        "codigo": "REL-06",
                        "relatorio": "Painel de monitoramento PENHA",
                        "competencia": "Série Histórica Completa",
                        "status": "Atualizado com sucesso"
                    })
                else:
                    erros_pm.append({
                        "codigo": "REL-06",
                        "relatorio": "Painel de monitoramento PENHA",
                        "competencia": "Série Histórica Completa",
                        "motivo": "Não foi possível extrair a tabela do Painel PENHA"
                    })
                    
            # 2. Painel de monitoramento por estabelecimento (Relatório 07)
            if not evento_cancelar_extracao.is_set() and relatorio_escolhido in ["TODOS", "CARGA_COMPLETA_PM", "PM_TODOS", "REL07"]:
                status_extracao["progresso"] = "Extraindo Painel de monitoramento por estabelecimento..."
                html_subpref = buscaPainelMonitoramento(usuario, senha, tipo_local="Subprefeitura", page=page)
                if evento_cancelar_extracao.is_set():
                    pass
                elif html_subpref:
                    status_extracao["progresso"] = "Gravando dados por estabelecimento (REL-07) no BD..."
                    processa_painel_monitoramento(html_subpref, tabela_db='REL-07', default_localidade='Subprefeitura PENHA')
                    sucessos_pm.append({
                        "codigo": "REL-07",
                        "relatorio": "Painel de monitoramento por estabelecimento",
                        "competencia": "Série Histórica Completa",
                        "status": "Atualizado com sucesso"
                    })
                else:
                    erros_pm.append({
                        "codigo": "REL-07",
                        "relatorio": "Painel de monitoramento por estabelecimento",
                        "competencia": "Série Histórica Completa",
                        "motivo": "Não foi possível extrair a tabela por estabelecimento"
                    })
        finally:
            try:
                browser.close()
            except Exception:
                pass
            try:
                p.stop()
            except Exception:
                pass
            
    except Exception as e:
        print(f"Erro na extração do Painel de Monitoramento: {e}")
        erros_pm.append({
            "codigo": "PM_GERAL",
            "relatorio": "Painel de Monitoramento",
            "competencia": "Geral",
            "motivo": str(e)
        })
    return sucessos_pm, erros_pm


def processo_background_pm(usuario, senha, relatorio_escolhido="TODOS"):
    global status_extracao, evento_cancelar_extracao
    evento_cancelar_extracao.clear()
    status_extracao["em_andamento"] = True
    status_extracao["concluido"] = False
    status_extracao["cancelado"] = False
    status_extracao["cancelando"] = False
    status_extracao["progresso"] = "Conectando ao Painel de Monitoramento..."
    status_extracao["status"] = "em_andamento"
    status_extracao["sucessos"] = []
    status_extracao["erros"] = []
    
    sucessos_pm, erros_pm = executar_extracao_pm_sync(usuario, senha, relatorio_escolhido)
    
    try:
        sincronizar_todas_competencias()
    except Exception:
        pass
            
    status_extracao["sucessos"] = sucessos_pm
    status_extracao["erros"] = erros_pm
    status_extracao["total_sucessos"] = len(sucessos_pm)
    status_extracao["total_erros"] = len(erros_pm)
    if evento_cancelar_extracao.is_set():
        status_extracao["cancelado"] = True
        status_extracao["cancelando"] = False
        status_extracao["progresso"] = f"Coleta cancelada pelo usuário com segurança ({len(sucessos_pm)} atualizados antes da parada)."
    elif erros_pm and sucessos_pm:
        status_extracao["progresso"] = f"Painel de Monitoramento concluído parcialmente ({len(sucessos_pm)} atualizados, {len(erros_pm)} falhas)."
    elif erros_pm and not sucessos_pm:
        status_extracao["progresso"] = f"Painel de Monitoramento concluído com falha ({len(erros_pm)} erros)."
    else:
        status_extracao["progresso"] = f"100% Concluído com sucesso ({len(sucessos_pm)} atualizados)!"
    status_extracao["status"] = "cancelado" if evento_cancelar_extracao.is_set() else ("sucesso" if not erros_pm else "parcial")
    status_extracao["em_andamento"] = False
    status_extracao["concluido"] = True


@app.route("/painel_monitoramento", methods=["GET", "POST"])
@admin_required
def painel_monitoramento_route():
    if request.method == "GET":
        return render_template("painel-monitoramento.html")
        
    data = request.get_json() or {}
    usuario_pm = data.get("usuario_pm", "")
    senha_pm = data.get("senha_pm", "")
    relatorio_escolhido = data.get("relatorio_escolhido", "TODOS")
    
    if not usuario_pm or not senha_pm:
        return jsonify({"erro": "Usuário e senha são obrigatórios."}), 400
        
    gerenciador_tarefas.submit(processo_background_pm, usuario_pm, senha_pm, relatorio_escolhido)
    
    return jsonify({"mensagem": "Extração do Painel de Monitoramento iniciada com sucesso!"})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_page = request.args.get("next") or request.form.get("next") or url_for("index")
    if request.method == "POST":
        username = request.form.get("username")
        senha_digitada = request.form.get("password")

        usuario = models.Usuario.query.filter_by(username=username).first()

        if usuario and usuario.check_senha(senha_digitada):
            session["usuario_id"] = usuario.id
            session["usuario_nome"] = usuario.username
            session["is_admin"] = usuario.is_admin

            flash(f"Login realizado com sucesso! Olá, {usuario.username}.", "success")
            return redirect(next_page)
        else:
            flash("Usuário ou senha incorretos. Tente novamente.", "error")

    if session.get("usuario_id") and session.get("is_admin"):
        return redirect(url_for("index"))

    return render_template("login.html", next=next_page)


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu do modo Administrador.", "info")
    return redirect(url_for("index"))


@app.route("/backup", methods=["GET"])
@admin_required
def tela_backup():
    from datetime import datetime
    db_path = os.path.join(basedir, 'database.db')
    
    tamanho_db_mb = 0
    data_modificacao = "N/A"
    if os.path.exists(db_path):
        tamanho_db_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        mtime = os.path.getmtime(db_path)
        data_modificacao = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y às %H:%M")
        
    return render_template(
        "backup.html",
        tamanho_db_mb=tamanho_db_mb,
        data_modificacao=data_modificacao
    )


@app.route("/admin/backup_db", methods=["GET"])
@admin_required
def backup_db():
    import zipfile, tempfile
    from datetime import datetime

    db_path = os.path.join(basedir, 'database.db')
    cat_path = os.path.join(basedir, 'services', 'catalogo_geral.json')

    if not os.path.exists(db_path):
        return jsonify({"erro": "Banco de dados não encontrado."}), 404

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = tempfile.gettempdir()
    zip_filename = f"Gestao_STS_backup_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        if os.path.exists(db_path):
            zf.write(db_path, arcname='database.db')
        if os.path.exists(cat_path):
            zf.write(cat_path, arcname='catalogo_geral.json')

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=zip_filename,
        mimetype="application/zip"
    )


@app.route("/admin/restaurar_backup", methods=["POST"])
@admin_required
def restaurar_backup():
    import zipfile, shutil, tempfile

    arquivo = request.files.get("arquivo_backup")
    if not arquivo or not arquivo.filename:
        flash("Nenhum arquivo de backup foi selecionado.", "error")
        return redirect(url_for("tela_backup"))

    filename = arquivo.filename.lower()
    if not (filename.endswith(".zip") or filename.endswith(".db")):
        flash("Formato de arquivo inválido. Selecione um arquivo .ZIP ou .DB.", "error")
        return redirect(url_for("tela_backup"))

    db_path = os.path.join(basedir, 'database.db')
    cat_path = os.path.join(basedir, 'services', 'catalogo_geral.json')
    temp_dir = tempfile.mkdtemp()

    try:
        temp_extracted_db = None
        temp_extracted_cat = None

        if filename.endswith(".zip"):
            with zipfile.ZipFile(arquivo, 'r') as zf:
                for member in zf.namelist():
                    base_name = os.path.basename(member)
                    if base_name == 'database.db':
                        temp_extracted_db = os.path.join(temp_dir, 'database.db')
                        with open(temp_extracted_db, 'wb') as f_out:
                            f_out.write(zf.read(member))
                    elif base_name == 'catalogo_geral.json':
                        temp_extracted_cat = os.path.join(temp_dir, 'catalogo_geral.json')
                        with open(temp_extracted_cat, 'wb') as f_out:
                            f_out.write(zf.read(member))
        else:
            temp_extracted_db = os.path.join(temp_dir, 'database.db')
            arquivo.save(temp_extracted_db)

        if not temp_extracted_db or not os.path.exists(temp_extracted_db):
            flash("O arquivo enviado não contém um banco de dados válido.", "error")
            return redirect(url_for("tela_backup"))

        # Libera conexões ativas do SQLAlchemy
        db.session.remove()
        db.engine.dispose()

        # Copia os arquivos restaurados
        shutil.copy2(temp_extracted_db, db_path)
        if temp_extracted_cat and os.path.exists(temp_extracted_cat):
            shutil.copy2(temp_extracted_cat, cat_path)

        # Sincroniza competências e recarrega banco
        sincronizar_todas_competencias()
        flash("Backup restaurado com sucesso! O banco de dados e os cadastros foram atualizados.", "success")
    except Exception as e:
        flash(f"Erro ao restaurar o backup: {str(e)}", "error")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return redirect(url_for("tela_backup"))


@app.route("/admin/expurgar_db", methods=["POST"])
@admin_required
def expurgar_db():
    try:
        import sqlite3
        db_path = os.path.join(basedir, 'database.db')

        # Fecha conexões ativas do SQLAlchemy
        db.session.remove()
        db.engine.dispose()

        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Obter todas as tabelas criadas no banco de dados
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tabelas = [row[0] for row in cursor.fetchall()]

            # Excluir dados de todas as tabelas de relatórios/dados (mantendo usuários e REL-01 para preservar acessos e base demográfica)
            for tab in tabelas:
                if tab not in ('usuarios', 'REL-01'):
                    cursor.execute(f'DELETE FROM "{tab}";')

            conn.commit()
            cursor.execute("VACUUM;")
            conn.close()

        # Sincroniza competências pós-limpeza (limpa competências órfãs)
        sincronizar_todas_competencias()

        flash("Banco de dados expurgado com sucesso! Todos os dados de produção foram apagados (base demográfica e usuários mantidos).", "success")
    except Exception as e:
        flash(f"Erro ao expurgar o banco de dados: {str(e)}", "error")

    return redirect(url_for("tela_backup"))


@app.route("/admin/desligar", methods=["POST"])
@admin_required
def desligar_servidor():
    def shutdown_process():
        import time, os
        time.sleep(1)
        os._exit(0)

    import threading
    threading.Thread(target=shutdown_process).start()
    return jsonify({"status": "ok", "mensagem": "O servidor do sistema foi encerrado com sucesso."})


""" @app.route("/alterar_senha", methods=["GET", "POST"])
# @admin_required
def alterar_senha():
    if request.method == "POST":
        


    return render_template("alterar-senha.html") """


@app.route("/bi_producao", methods=["GET", "POST"])
@admin_required
def gerar_relatorios():
    if request.method == "GET":
        return render_template("bi-producao.html")

    mes_inicio = request.form.get("mes_inicio", "Janeiro")
    ano_inicio = request.form.get("ano_inicio", "2026")
    mes_fim = request.form.get("mes_fim", "Janeiro")
    ano_fim = request.form.get("ano_fim", "2026")
    relatorio_escolhido = request.form.get("relatorio_escolhido", "TODOS")
    usuario_bi = request.form.get("usuario_bi", "").strip()
    senha_bi = request.form.get("senha_bi", "").strip()
    usuario_pm = request.form.get("usuario_pm", "").strip()
    senha_pm = request.form.get("senha_pm", "").strip()

    # 1. Apenas Painel de Monitoramento (CEInfo)
    if relatorio_escolhido in ["CARGA_COMPLETA_PM", "PM_TODOS", "REL06", "REL07"]:
        if not usuario_pm or not senha_pm:
            return jsonify({"erro": "Usuário e senha do Painel de Monitoramento são obrigatórios!"}), 400
        tipo_pm = "TODOS" if relatorio_escolhido in ["CARGA_COMPLETA_PM", "PM_TODOS"] else relatorio_escolhido
        gerenciador_tarefas.submit(processo_background_pm, usuario_pm, senha_pm, tipo_pm)
        nome_desc = MAPA_NOMES_RELATORIOS.get(relatorio_escolhido, relatorio_escolhido)
        return jsonify({"mensagem": f"Autenticado! Extração iniciada: {nome_desc}!"})

    # 2. Carga Completa BI e PM (ambas as credenciais necessárias)
    if relatorio_escolhido == "CARGA_COMPLETA_BI_PM":
        if not usuario_bi or not senha_bi:
            return jsonify({"erro": "Usuário e senha do BI são obrigatórios para a carga geral!"}), 400
        if not usuario_pm or not senha_pm:
            return jsonify({"erro": "Usuário e senha do Painel de Monitoramento são obrigatórios para a carga geral!"}), 400

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p_test:
                browser_test = p_test.chromium.launch(headless=True)
                context_test = browser_test.new_context(http_credentials={'username': usuario_bi, 'password': senha_bi})
                page_test = context_test.new_page()
                url_teste = 'https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx'
                resp = page_test.goto(url_teste, timeout=15000)
                if resp and resp.status == 401:
                    return jsonify({"erro": "Usuário ou senha do BI incorretos!"}), 401
        except Exception as e:
            print(f"Erro no teste prévio de credenciais BI: {e}")

        gerenciador_tarefas.submit(processo_background, mes_inicio, ano_inicio, mes_fim, ano_fim, relatorio_escolhido, usuario_bi, senha_bi, usuario_pm, senha_pm)
        return jsonify({"mensagem": "Autenticado! Carga completa (BI e PM) iniciada!"})

    # 3. Relatórios do BI (individuais ou Carga completa BI)
    if not usuario_bi or not senha_bi:
        return jsonify({"erro": "Usuário e senha do BI são obrigatórios!"}), 400

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p_test:
            browser_test = p_test.chromium.launch(headless=True)
            context_test = browser_test.new_context(http_credentials={'username': usuario_bi, 'password': senha_bi})
            page_test = context_test.new_page()
            url_teste = 'https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx'
            resp = page_test.goto(url_teste, timeout=15000)
            if resp and resp.status == 401:
                return jsonify({"erro": "Usuário ou senha do BI incorretos!"}), 401
    except Exception as e:
        print(f"Erro no teste prévio de credenciais BI: {e}")

    gerenciador_tarefas.submit(processo_background, mes_inicio, ano_inicio, mes_fim, ano_fim, relatorio_escolhido, usuario_bi, senha_bi)
    nome_desc = MAPA_NOMES_RELATORIOS.get(relatorio_escolhido, relatorio_escolhido)
    return jsonify({"mensagem": f"Autenticado! Extração iniciada de {mes_inicio}/{ano_inicio} até {mes_fim}/{ano_fim} ({nome_desc})!"})

@app.route("/status_extracao")
def status_extracao_route():
    return jsonify(status_extracao)

@app.route("/cancelar_extracao", methods=["POST"])
@admin_required
def cancelar_extracao_route():
    global status_extracao, evento_cancelar_extracao
    if not status_extracao.get("em_andamento", False):
        return jsonify({"mensagem": "Nenhuma extração em andamento no momento."}), 200
    
    evento_cancelar_extracao.set()
    status_extracao["cancelando"] = True
    status_extracao["progresso"] = "Interrupção solicitada. Finalizando tarefas ativas com segurança..."
    return jsonify({
        "status": "cancelando",
        "mensagem": "Cancelamento solicitado com sucesso! As tarefas em andamento serão concluídas e a fila será interrompida com segurança."
    })


import io
from flask import send_file

@app.route("/download_excel/<indice>", defaults={'periodo': 'geral'})
@app.route("/download_excel/<indice>/<periodo>")
def download_excel(indice, periodo):
    try:
        if indice == '01':
            df_total, df_masc, df_fem = prod.gera_relatorio_01()
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if df_total is not None and not df_total.empty:
                    df_total.to_excel(writer, index=False, sheet_name='População Geral')
                if df_masc is not None and not df_masc.empty:
                    df_masc.to_excel(writer, index=False, sheet_name='Sexo Masculino')
                if df_fem is not None and not df_fem.empty:
                    df_fem.to_excel(writer, index=False, sheet_name='Sexo Feminino')
            output.seek(0)
            return send_file(output, download_name=f"Relatorio_01_Populacional.xlsx", as_attachment=True)
        elif indice == '02':
            output = prod.exportar_excel_relatorio_02(periodo)
            return send_file(output, download_name=f"Relatorio_02_Producao_Geral_BPA_{periodo}.xlsx", as_attachment=True)
        elif indice == '03':
            output = prod.exportar_excel_relatorio_03(periodo)
            return send_file(output, download_name=f"Relatorio_03_Producao_Especialidade_SIGA_{periodo}.xlsx", as_attachment=True)
        elif indice == '04':
            output = prod.exportar_excel_relatorio_04(periodo)
            return send_file(output, download_name=f"Relatorio_04_Oferta_de_Vagas_BI_{periodo}.xlsx", as_attachment=True)
        elif indice == '05':
            output = prod.exportar_excel_relatorio_05(periodo)
            return send_file(output, download_name=f"Relatorio_05_RAAS_CAPS_{periodo}.xlsx", as_attachment=True)
        elif indice == '08':
            output = prod.exportar_excel_relatorio_08(periodo)
            return send_file(output, download_name=f"Relatorio_08_Pre_Natal_Penha_{periodo}.xlsx", as_attachment=True)
        elif indice == '09':
            output = prod.exportar_excel_relatorio_09(periodo)
            return send_file(output, download_name=f"Relatorio_09_Consulta_Odontologica_Gestante_{periodo}.xlsx", as_attachment=True)
        elif indice == '10':
            df = prod.gera_relatorio_10(periodo)
        elif indice == '11':
            output = prod.exportar_excel_relatorio_11(periodo)
            return send_file(output, download_name=f"Relatorio_11_Fila_de_Espera_FE02_{periodo}.xlsx", as_attachment=True)
        elif indice == '12':
            output = prod.exportar_excel_relatorio_12_oficial(periodo)
            return send_file(output, download_name=f"Relatorio_12_MMH_PICS_Penha_{periodo}.xlsx", as_attachment=True)
        elif indice == '13':
            output = prod.exportar_excel_relatorio_13(periodo)
            return send_file(output, download_name=f"Relatorio_13_Perda_Primaria_VG02_{periodo}.xlsx", as_attachment=True)
        elif indice == '14':
            output = prod.exportar_excel_relatorio_14(periodo)
            return send_file(output, download_name=f"Relatorio_14_Absenteismo_AG04_{periodo}.xlsx", as_attachment=True)
        elif indice == '15':
            output = prod.exportar_excel_relatorio_15(periodo)
            return send_file(output, download_name=f"Relatorio_15_Acompanhamento_Cadastro_ESF_{periodo}.xlsx", as_attachment=True)
        elif indice == '16':
            output = prod.exportar_excel_relatorio_16(periodo)
            return send_file(output, download_name=f"Relatorio_16_AMG_{periodo}.xlsx", as_attachment=True)
        elif indice == '17':
            output = prod.exportar_excel_relatorio_17(periodo)
            return send_file(output, download_name=f"Relatorio_17_Atividades_Coletivas_PSE_{periodo}.xlsx", as_attachment=True)
        else:
            df = None
            
        if df is None or df.empty:
            return "Sem dados", 404
            
        if isinstance(df.index, pd.MultiIndex) or df.index.name is not None:
            df = df.reset_index()
            
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Relatorio')
        output.seek(0)
        
        return send_file(output, download_name=f"Relatorio_{indice}_{periodo}.xlsx", as_attachment=True)
        
    except Exception as e:
        return str(e), 500


@app.route("/producao", methods=["GET", "POST"])
def producao():
    tabela_html = None
    json_dados = None
    json_colunas = None
    
    if request.method == "POST":
        indice = request.form.get("indice_relatorio")
        periodo = request.form.get("periodo")
    else:
        # Por padrão ao acessar a aba de relatórios, o Relatório 01 é pré-selecionado como rosto da visualização
        indice = request.args.get("indice_relatorio", "01")
        periodo = request.args.get("periodo")
    
    mapa_competencias = obter_competencias_por_relatorio()
    
    if indice and indice in mapa_competencias and mapa_competencias[indice]:
        periodos_disponiveis = mapa_competencias[indice]
    else:
        todos = set()
        for l in mapa_competencias.values():
            for p, txt in l:
                todos.add(p)
        ord_todos = sorted(list(todos), reverse=True)
        periodos_disponiveis = [(p, f"{p[4:6]}/{p[:4]}") for p in ord_todos] if ord_todos else [('202607', '07/2026')]
        
    periodo_padrao = periodos_disponiveis[0][0] if periodos_disponiveis else '202607'
    if not periodo or periodo not in [p[0] for p in periodos_disponiveis]:
        periodo = periodo_padrao

    fonte_dados = None
    data_geracao = None
    fontes_detalhadas = []

    if indice:
        meta = prod.obter_metadados_relatorio(indice, periodo)
        fonte_dados = meta.get('fonte')
        data_geracao = meta.get('data_geracao')
        fontes_detalhadas = meta.get('fontes_detalhadas', [])

        # 2. Executa a geração de dados do relatório selecionado
        try:
            if indice == '01':
                df_total, df_masc, df_fem = prod.gera_relatorio_01()
                json_dados_total = None
                json_colunas_total = None
                json_dados_masc = None
                json_colunas_masc = None
                json_dados_fem = None
                json_colunas_fem = None
                
                if df_total is not None and not df_total.empty:
                    colunas_tot = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_total.columns]
                    json_colunas_total = json.dumps(colunas_tot)
                    json_dados_total = json.dumps(df_total.fillna("").to_dict(orient="records"))
                    
                if df_masc is not None and not df_masc.empty:
                    colunas_masc = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_masc.columns]
                    json_colunas_masc = json.dumps(colunas_masc)
                    json_dados_masc = json.dumps(df_masc.fillna("").to_dict(orient="records"))

                if df_fem is not None and not df_fem.empty:
                    colunas_fem = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_fem.columns]
                    json_colunas_fem = json.dumps(colunas_fem)
                    json_dados_fem = json.dumps(df_fem.fillna("").to_dict(orient="records"))
                
                return render_template(
                    "producao.html",
                    tabela_html=tabela_html,
                    json_dados_total=json_dados_total,
                    json_colunas_total=json_colunas_total,
                    json_dados_masc=json_dados_masc,
                    json_colunas_masc=json_colunas_masc,
                    json_dados_fem=json_dados_fem,
                    json_colunas_fem=json_colunas_fem,
                    relatorio_selecionado=indice,
                    periodo_selecionado=periodo,
                    periodos_disponiveis=periodos_disponiveis,
                    json_competencias_por_relatorio=json.dumps(mapa_competencias),
                    fonte_dados=fonte_dados,
                    data_geracao=data_geracao,
                    fontes_detalhadas=fontes_detalhadas
                )
            elif indice == '02':
                df = prod.gera_relatorio_02(periodo)
            elif indice == '03':
                df = prod.gera_relatorio_03(periodo)
            elif indice == '04':
                df = prod.gera_relatorio_04(periodo)
            elif indice == '05':
                df_pac, df_prof, df_acoes = prod.gera_relatorio_05(periodo)
                json_dados_pac = None
                json_colunas_pac = None
                json_dados_prof = None
                json_colunas_prof = None
                json_dados_acoes = None
                json_colunas_acoes = None
                
                if df_pac is not None and not df_pac.empty:
                    colunas_pac = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_pac.columns]
                    json_colunas_pac = json.dumps(colunas_pac)
                    json_dados_pac = json.dumps(df_pac.fillna("").to_dict(orient="records"))
                    
                if df_prof is not None and not df_prof.empty:
                    colunas_prof = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_prof.columns]
                    json_colunas_prof = json.dumps(colunas_prof)
                    json_dados_prof = json.dumps(df_prof.fillna("").to_dict(orient="records"))

                if df_acoes is not None and not df_acoes.empty:
                    colunas_acoes = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_acoes.columns if not str(col).startswith('_')]
                    json_colunas_acoes = json.dumps(colunas_acoes)
                    json_dados_acoes = json.dumps(df_acoes.fillna("").to_dict(orient="records"))
                
                return render_template(
                    "producao.html",
                    tabela_html=tabela_html,
                    json_dados_pac=json_dados_pac,
                    json_colunas_pac=json_colunas_pac,
                    json_dados_prof=json_dados_prof,
                    json_colunas_prof=json_colunas_prof,
                    json_dados_acoes=json_dados_acoes,
                    json_colunas_acoes=json_colunas_acoes,
                    relatorio_selecionado=indice,
                    periodo_selecionado=periodo,
                    periodos_disponiveis=periodos_disponiveis,
                    json_competencias_por_relatorio=json.dumps(mapa_competencias),
                    fonte_dados=fonte_dados,
                    data_geracao=data_geracao
                )
            elif indice == '06':
                df = prod.gera_relatorio_06(periodo)
            elif indice == '07':
                df = prod.gera_relatorio_07(periodo)
            elif indice == '08':
                df = prod.gera_relatorio_08(periodo)
            elif indice == '10':
                df = prod.gera_relatorio_10(periodo)
            elif indice == '11':
                df = prod.gera_relatorio_11(periodo)
            elif indice == '12':
                df = prod.gera_relatorio_12(periodo)
            elif indice == '13':
                df = prod.gera_relatorio_13(periodo)
            elif indice == '14':
                df = prod.gera_relatorio_14(periodo)
            elif indice == '09':
                df = prod.gera_relatorio_09(periodo)
            elif indice == '15':
                df = prod.gera_relatorio_15(periodo)
            elif indice == '16':
                df_ativos, df_inativos = prod.gera_relatorio_16(periodo)
                json_dados_ativos = None
                json_colunas_ativos = None
                json_dados_inativos = None
                json_colunas_inativos = None
                
                if df_ativos is not None and not df_ativos.empty:
                    colunas_ativos = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_ativos.columns]
                    json_colunas_ativos = json.dumps(colunas_ativos)
                    json_dados_ativos = json.dumps(df_ativos.fillna("").to_dict(orient="records"))
                    
                if df_inativos is not None and not df_inativos.empty:
                    colunas_inativos = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_inativos.columns]
                    json_colunas_inativos = json.dumps(colunas_inativos)
                    json_dados_inativos = json.dumps(df_inativos.fillna("").to_dict(orient="records"))
                
                return render_template(
                    "producao.html",
                    tabela_html=tabela_html,
                    json_dados_ativos=json_dados_ativos,
                    json_colunas_ativos=json_colunas_ativos,
                    json_dados_inativos=json_dados_inativos,
                    json_colunas_inativos=json_colunas_inativos,
                    relatorio_selecionado=indice,
                    periodo_selecionado=periodo,
                    periodos_disponiveis=periodos_disponiveis,
                    json_competencias_por_relatorio=json.dumps(mapa_competencias),
                    fonte_dados=fonte_dados,
                    data_geracao=data_geracao
                )
            elif indice == '17':
                df = prod.gera_relatorio_17(periodo)
            else:
                df = None
            
            # 3. Transforma o resultado para JSON
            json_dados = None
            json_colunas = None
            if df is not None:
                if hasattr(df.columns, 'names'):
                    df.columns.names = [None] * len(df.columns.names)
                else:
                    df.columns.name = None

                if isinstance(df.index, pd.MultiIndex) or df.index.name is not None:
                    df = df.reset_index()
                
                # Prepara definições de colunas para o DataTables (escapa pontos para evitar erro de objeto aninhado no DataTables)
                colunas = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df.columns]
                json_colunas = json.dumps(colunas)
                
                # Preenche NaN com string vazia ou None
                df = df.fillna("")
                
                # Converte dados
                # to_dict(orient='records') gera uma lista de dicts
                dados = df.to_dict(orient="records")
                json_dados = json.dumps(dados)
                
        except Exception as e:
            tabela_html = f"<div class='alert alert-danger'>Erro ao gerar relatório: {e}</div>"

        mapa_pop_fem = prod.obter_populacao_fem_25_64() if indice == '10' else {}

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("format") == "json":
            return jsonify({
                "status": "success" if not tabela_html else "error",
                "mensagem_erro": tabela_html,
                "dados": json.loads(json_dados) if json_dados else [],
                "colunas": json.loads(json_colunas) if json_colunas else [],
                "pop_fem_25_64": mapa_pop_fem,
                "fonte_dados": fonte_dados,
                "data_geracao": data_geracao,
                "fontes_detalhadas": fontes_detalhadas,
                "relatorio_selecionado": indice,
                "periodo_selecionado": periodo
            })

    mapa_pop_fem = prod.obter_populacao_fem_25_64() if indice == '10' else {}

    return render_template(
        "producao.html",
        tabela_html=tabela_html,
        json_dados=json_dados,
        json_colunas=json_colunas,
        json_pop_fem_25_64=json.dumps(mapa_pop_fem),
        relatorio_selecionado=indice,
        periodo_selecionado=periodo,
        periodos_disponiveis=periodos_disponiveis,
        json_competencias_por_relatorio=json.dumps(mapa_competencias),
        fonte_dados=fonte_dados,
        data_geracao=data_geracao,
        fontes_detalhadas=fontes_detalhadas
    )

import zipfile
import os

@app.route("/upload_bi_manual", methods=["POST"])
@admin_required
def upload_bi_manual():
    relatorio = request.form.get("relatorio", "").strip()
    mes = request.form.get("mes", "Janeiro").strip()
    ano = request.form.get("ano", "2026").strip()
    arquivo = request.files.get("arquivo")

    if not arquivo or not arquivo.filename:
        return jsonify({"status": "error", "mensagem": "Nenhum arquivo foi selecionado para upload."}), 400

    if not relatorio:
        return jsonify({"status": "error", "mensagem": "Selecione o relatório correspondente para substituição."}), 400

    import services.etl as etl
    mapa_funcoes_etl = {
        'GAC02': etl.processa_gac02,
        'CG01': etl.processa_cg01,
        'CG05': etl.processa_cg05,
        'CG06': etl.processa_cg06,
        'AT02': etl.processa_at02,
        'AG04': etl.processa_ag04,
        'AT03': etl.processa_at03,
        'FE02': etl.processa_fe02,
        'VG02': etl.processa_vg02,
        'VG04': etl.processa_vg04,
    }

    etl_func = mapa_funcoes_etl.get(relatorio)
    if not etl_func:
        return jsonify({"status": "error", "mensagem": f"Relatório '{relatorio}' não suportado para upload direto."}), 400

    MAPA_MESES = {
        "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
        "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
        "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
    }
    periodo = f"{ano}{MAPA_MESES.get(mes, '01')}"

    pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
    os.makedirs(pasta_destino, exist_ok=True)
    caminho_temp = os.path.join(pasta_destino, f"upload_manual_{relatorio}_{periodo}_{arquivo.filename}")

    try:
        arquivo.save(caminho_temp)
        etl_func(caminho_temp, periodo)
        try:
            sincronizar_todas_competencias()
        except Exception:
            pass
        nome_rel = MAPA_NOMES_RELATORIOS.get(relatorio, relatorio)
        return jsonify({
            "status": "success",
            "mensagem": f"Arquivo '{arquivo.filename}' processado com sucesso! Os dados de {mes}/{ano} do relatório {nome_rel} foram substituídos no banco de dados."
        })
    except Exception as e:
        print(f"Erro no upload manual de {relatorio}: {e}")
        return jsonify({
            "status": "error",
            "mensagem": f"Erro ao processar o arquivo: {str(e)}"
        }), 500
    finally:
        if os.path.exists(caminho_temp):
            try:
                os.remove(caminho_temp)
            except Exception:
                pass

@app.route("/api/status_dtic/<periodo>", methods=["GET"])
@admin_required
def api_status_dtic(periodo):
    from services.competencias import (
        obter_competencia_automatica,
        obter_status_importacao_dtic,
        formatar_descricao_competencia
    )
    comp_auto_val, comp_auto_desc = obter_competencia_automatica()
    if periodo == "auto" or not periodo:
        periodo_ativo = comp_auto_val
        is_auto = True
    else:
        periodo_ativo = periodo
        is_auto = False
        
    periodo_ativo_desc = formatar_descricao_competencia(periodo_ativo)
    status = obter_status_importacao_dtic(periodo_ativo)
    
    return jsonify({
        "periodo_selecionado": periodo,
        "periodo_ativo": periodo_ativo,
        "periodo_ativo_desc": periodo_ativo_desc,
        "is_auto": is_auto,
        "comp_auto_val": comp_auto_val,
        "comp_auto_desc": comp_auto_desc,
        "status": status
    })

def _processar_arquivo_tabela_dtic(fonte_stream_ou_bytes, nome_original, tipo_identificado, ext, periodo_form, modo_estrito, desc_periodo_alvo):
    """
    Processa arquivos tabulares descompactados ou extraídos de ZIPs (CSV, XLS, XLSX) dos relatórios DTIC (114, 134, 135, 16).
    Aplica os filtros de supervisão quando aplicável e executa o ETL.
    Retorna (sucesso: bool, aviso: str or None, erro: str or None).
    """
    import pandas as pd
    from services.etl import processa_rel114, processa_rel134, processa_rel135, processa_rel16
    
    pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
    os.makedirs(pasta_destino, exist_ok=True)
    nome_final = f"{tipo_identificado}{ext}"
    caminho_final = os.path.join(pasta_destino, nome_final)
    
    filtro_coluna = None
    filtro_valor = None
    if "(rel114)" in tipo_identificado:
        filtro_coluna = "SUPERVISAO"
        filtro_valor = "SUDESTE - STS PENHA"
    elif "(rel134)" in tipo_identificado:
        filtro_coluna = "supervisao"
        filtro_valor = "SUDESTE - PENHA"
    elif "(rel16)" in tipo_identificado:
        filtro_coluna = "SUPERVISAO"
        filtro_valor = "SUDESTE - STS PENHA"

    try:
        if ext.lower() in ['.csv', '.txt']:
            if filtro_coluna:
                first = True
                for chunk in pd.read_csv(fonte_stream_ou_bytes, sep=';', encoding='latin1', chunksize=50000, low_memory=False):
                    if filtro_coluna in chunk.columns:
                        chunk_filtrado = chunk[chunk[filtro_coluna] == filtro_valor]
                        chunk_filtrado.to_csv(caminho_final, mode='w' if first else 'a', header=first, index=False, sep=';', encoding='latin1')
                        first = False
                    else:
                        chunk.to_csv(caminho_final, mode='w' if first else 'a', header=first, index=False, sep=';', encoding='latin1')
                        first = False
            else:
                if hasattr(fonte_stream_ou_bytes, 'save'):
                    fonte_stream_ou_bytes.save(caminho_final)
                elif hasattr(fonte_stream_ou_bytes, 'read'):
                    with open(caminho_final, "wb") as destino:
                        if hasattr(fonte_stream_ou_bytes, 'seek'):
                            fonte_stream_ou_bytes.seek(0)
                        destino.write(fonte_stream_ou_bytes.read())
                elif isinstance(fonte_stream_ou_bytes, (bytes, bytearray)):
                    with open(caminho_final, "wb") as destino:
                        destino.write(fonte_stream_ou_bytes)
        else:
            # Excel (.xlsx, .xls)
            if hasattr(fonte_stream_ou_bytes, 'save'):
                fonte_stream_ou_bytes.save(caminho_final)
            elif hasattr(fonte_stream_ou_bytes, 'read'):
                with open(caminho_final, "wb") as destino:
                    if hasattr(fonte_stream_ou_bytes, 'seek'):
                        fonte_stream_ou_bytes.seek(0)
                    destino.write(fonte_stream_ou_bytes.read())
            elif isinstance(fonte_stream_ou_bytes, (bytes, bytearray)):
                with open(caminho_final, "wb") as destino:
                    destino.write(fonte_stream_ou_bytes)
    except Exception as e:
        return False, None, f"Erro ao preparar arquivo '{nome_original}': {e}"

    # Executa ETL
    try:
        res_etl = False
        if "(rel114)" in tipo_identificado:
            res_etl = processa_rel114(caminho_final, periodo=periodo_form)
        elif "(rel134)" in tipo_identificado:
            res_etl = processa_rel134(caminho_final, periodo=periodo_form)
        elif "(rel135)" in tipo_identificado:
            res_etl = processa_rel135(caminho_final, periodo=periodo_form)
        elif "(rel16)" in tipo_identificado:
            res_etl = processa_rel16(caminho_final, periodo=periodo_form)

        if res_etl:
            return True, None, None
        elif modo_estrito and periodo_form:
            return False, f"O arquivo '{nome_original}' ({tipo_identificado}) não contém registros para a competência {desc_periodo_alvo}.", None
        else:
            return False, None, None
    except Exception as e:
        return False, None, f"Erro ao processar ETL de '{nome_original}': {e}"

@app.route("/upload_zip", methods=["GET", "POST"])
@app.route("/upload_dtic", methods=["GET", "POST"])
@admin_required
def upload_dtic():
    mensagem = None
    if request.method == "POST":
        tipo_relatorio = request.form.get("tipo_relatorio")
        periodo_form_raw = request.form.get("periodo_referencia") or request.form.get("periodo")
        modo_estrito = bool(request.form.get("forcar_competencia_estrita"))

        from services.competencias import formatar_descricao_competencia
        if periodo_form_raw == "auto" or not periodo_form_raw:
            periodo_form = None
            desc_periodo_alvo = "Automática"
            modo_estrito = False
        else:
            periodo_form = periodo_form_raw if modo_estrito else None
            desc_periodo_alvo = formatar_descricao_competencia(periodo_form_raw)

        arquivos = request.files.getlist("arquivos")
        
        sucessos = 0
        avisos = []
        erros = []

        for arquivo in arquivos:
            if not arquivo or not arquivo.filename:
                continue
            nome_arq = arquivo.filename
            nome_lower = nome_arq.lower()
            
            # 1. Arquivos de Produção BPA (Relatório 02)
            # Pode ser o arquivo bruto BPA (ex: PAPENHA-.AGO, PA*.JUL) ou o .DBF gerado no TabWin (ex: STS26_08.dbf)
            if nome_lower.endswith('.dbf'):
                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                caminho_final = os.path.join(pasta_destino, nome_arq)
                arquivo.save(caminho_final)
                
                from services.etl import processa_bpa_dbf
                try:
                    res_etl = processa_bpa_dbf(caminho_final, periodo=periodo_form)
                    if res_etl:
                        sucessos += 1
                    elif modo_estrito and periodo_form:
                        avisos.append(f"O arquivo '{nome_arq}' não contém dados para a competência {desc_periodo_alvo}.")
                except Exception as e:
                    erros.append(f"Erro ao processar DBF '{nome_arq}': {e}")
                    print(f"Erro ao processar DBF {nome_arq}: {e}")
                finally:
                    if os.path.exists(caminho_final):
                        try:
                            os.remove(caminho_final)
                        except Exception as err_rem:
                            print(f"Erro ao remover arquivo temporário {caminho_final}: {err_rem}")

            elif (tipo_relatorio == "rel02" and not nome_lower.endswith(('.zip', '.csv', '.xlsx', '.xls'))) or (nome_lower.startswith('pa') and not nome_lower.endswith(('.zip', '.csv', '.xlsx', '.xls'))):
                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                caminho_final = os.path.join(pasta_destino, nome_arq)
                arquivo.save(caminho_final)
                
                from services.etl import processa_bpa_pa
                try:
                    res_etl = processa_bpa_pa(caminho_final, periodo=periodo_form)
                    if res_etl:
                        sucessos += 1
                    elif modo_estrito and periodo_form:
                        avisos.append(f"O arquivo BPA '{nome_arq}' não contém registros para a competência {desc_periodo_alvo}.")
                except Exception as e:
                    erros.append(f"Erro ao processar BPA PA '{nome_arq}': {e}")
                    print(f"Erro ao processar BPA PA {nome_arq}: {e}")
                finally:
                    if os.path.exists(caminho_final):
                        try:
                            os.remove(caminho_final)
                        except Exception as err_rem:
                            print(f"Erro ao remover arquivo temporário {caminho_final}: {err_rem}")

            # 2. Arquivos RAAS das Unidades CAPS (Relatório 05)
            elif (tipo_relatorio == "rel05" and not nome_lower.endswith(('.zip', '.csv', '.xlsx', '.xls'))) or (nome_lower.startswith('aa') and len(nome_lower) >= 8 and not nome_lower.endswith('.zip')) or ("raas" in nome_lower and not nome_lower.endswith(('.zip', '.csv', '.xlsx', '.xls'))):
                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                caminho_final = os.path.join(pasta_destino, nome_arq)
                arquivo.save(caminho_final)
                
                from services.etl import processa_raas_arquivo
                try:
                    res_etl = processa_raas_arquivo(caminho_final, periodo=periodo_form)
                    if res_etl:
                        sucessos += 1
                    elif modo_estrito and periodo_form:
                        avisos.append(f"O arquivo RAAS '{nome_arq}' não contém registros para a competência {desc_periodo_alvo}.")
                except Exception as e:
                    erros.append(f"Erro ao processar RAAS '{nome_arq}': {e}")
                    print(f"Erro ao processar RAAS {nome_arq}: {e}")
                finally:
                    if os.path.exists(caminho_final):
                        try:
                            os.remove(caminho_final)
                        except Exception as err_rem:
                            print(f"Erro ao remover arquivo temporário RAAS {caminho_final}: {err_rem}")

            # 3. Arquivos Tabulares Descompactados (.CSV, .XLSX, .XLS, .TXT)
            elif nome_lower.endswith(('.csv', '.xlsx', '.xls')) or (nome_lower.endswith('.txt') and any(k in nome_lower for k in ['gestante', 'rel114', 'rel_114', 'penha', 'rel135', 'rel_135', 'amg', 'pacientes', 'rel16', 'rel_16', 'atividade', 'rel134', 'rel_134'])):
                tipo_identificado = None
                if (tipo_relatorio == "todos" or tipo_relatorio == "rel09") and ("rel_sb_gestante_prev_parto" in nome_lower or "gestante" in nome_lower or "rel114" in nome_lower or "rel_114" in nome_lower):
                    tipo_identificado = "(rel114) rel_sb_gestante_prev_parto"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel15") and ("penha" in nome_lower or "rel135" in nome_lower or "rel_135" in nome_lower):
                    tipo_identificado = "(rel135) penha"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel16") and ("amg" in nome_lower or "pacientes_cadastrados" in nome_lower or "pacientes cadastrados" in nome_lower or "rel16" in nome_lower or "rel_16" in nome_lower):
                    tipo_identificado = "(rel16) siga_amg"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel17") and ("atividade_coletiva_por_profissional" in nome_lower or "atividade_coletiva" in nome_lower or "atividade" in nome_lower or "rel134" in nome_lower or "rel_134" in nome_lower):
                    tipo_identificado = "(rel134) atividade_coletiva_por_profissional"
                elif tipo_relatorio == "rel09":
                    tipo_identificado = "(rel114) rel_sb_gestante_prev_parto"
                elif tipo_relatorio == "rel15":
                    tipo_identificado = "(rel135) penha"
                elif tipo_relatorio == "rel16":
                    tipo_identificado = "(rel16) siga_amg"
                elif tipo_relatorio == "rel17":
                    tipo_identificado = "(rel134) atividade_coletiva_por_profissional"

                if tipo_identificado:
                    ext = os.path.splitext(nome_arq)[1]
                    ok, av, er = _processar_arquivo_tabela_dtic(
                        arquivo, nome_arq, tipo_identificado, ext, periodo_form, modo_estrito, desc_periodo_alvo
                    )
                    if ok:
                        sucessos += 1
                    if av:
                        avisos.append(av)
                    if er:
                        erros.append(er)
                else:
                    avisos.append(f"O arquivo '{nome_arq}' não pôde ser identificado automaticamente. Selecione o tipo de relatório no menu.")

            # 4. Arquivos Compactados (.ZIP)
            elif nome_lower.endswith('.zip'):
                nome_zip = nome_lower
                
                # Identifica se é ZIP do BPA
                if "bpa" in nome_zip or tipo_relatorio == "rel02":
                    with zipfile.ZipFile(arquivo, 'r') as zip_ref:
                        for nome_arq_zip in zip_ref.namelist():
                            nl_zip = nome_arq_zip.lower()
                            if nl_zip.endswith('.dbf'):
                                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                                caminho_temp = os.path.join(pasta_destino, os.path.basename(nome_arq_zip))
                                with open(caminho_temp, "wb") as f_out:
                                    f_out.write(zip_ref.read(nome_arq_zip))
                                from services.etl import processa_bpa_dbf
                                try:
                                    res_etl = processa_bpa_dbf(caminho_temp, periodo=periodo_form)
                                    if res_etl:
                                        sucessos += 1
                                    elif modo_estrito and periodo_form:
                                        avisos.append(f"O arquivo '{nome_arq_zip}' (do ZIP '{nome_arq}') não contém dados para a competência {desc_periodo_alvo}.")
                                except Exception as e:
                                    erros.append(f"Erro ao processar DBF '{nome_arq_zip}': {e}")
                                    print(f"Erro ao processar DBF do ZIP {nome_arq_zip}: {e}")
                                finally:
                                    if os.path.exists(caminho_temp):
                                        try:
                                            os.remove(caminho_temp)
                                        except Exception:
                                            pass
                            elif os.path.basename(nl_zip).startswith('pa'):
                                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                                caminho_temp = os.path.join(pasta_destino, os.path.basename(nome_arq_zip))
                                with open(caminho_temp, "wb") as f_out:
                                    f_out.write(zip_ref.read(nome_arq_zip))
                                from services.etl import processa_bpa_pa
                                try:
                                    res_etl = processa_bpa_pa(caminho_temp, periodo=periodo_form)
                                    if res_etl:
                                        sucessos += 1
                                    elif modo_estrito and periodo_form:
                                        avisos.append(f"O arquivo '{nome_arq_zip}' (do ZIP '{nome_arq}') não contém dados para a competência {desc_periodo_alvo}.")
                                except Exception as e:
                                    erros.append(f"Erro ao processar BPA PA '{nome_arq_zip}': {e}")
                                    print(f"Erro ao processar BPA PA do ZIP {nome_arq_zip}: {e}")
                                finally:
                                    if os.path.exists(caminho_temp):
                                        try:
                                            os.remove(caminho_temp)
                                        except Exception:
                                            pass
                    continue
                
                # Identifica se é ZIP do RAAS
                if "raas" in nome_zip or tipo_relatorio == "rel05":
                    with zipfile.ZipFile(arquivo, 'r') as zip_ref:
                        for nome_arq_zip in zip_ref.namelist():
                            nl_zip = nome_arq_zip.lower()
                            if "_erro" in nl_zip or "_protocolo" in nl_zip:
                                continue
                            if any(nl_zip.endswith(ext) for ext in ['.jul', '.ago', '.set', '.out', '.nov', '.dez', '.jan', '.fev', '.mar', '.abr', '.mai', '.jun', '.raas', '.txt']) or os.path.basename(nl_zip).startswith('aa'):
                                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                                caminho_temp = os.path.join(pasta_destino, os.path.basename(nome_arq_zip))
                                with open(caminho_temp, "wb") as f_out:
                                    f_out.write(zip_ref.read(nome_arq_zip))
                                
                                from services.etl import processa_raas_arquivo
                                try:
                                    res_etl = processa_raas_arquivo(caminho_temp, periodo=periodo_form)
                                    if res_etl:
                                        sucessos += 1
                                    elif modo_estrito and periodo_form:
                                        avisos.append(f"O arquivo RAAS '{nome_arq_zip}' (do ZIP '{nome_arq}') não contém registros para a competência {desc_periodo_alvo}.")
                                except Exception as e:
                                    erros.append(f"Erro ao processar RAAS '{nome_arq_zip}': {e}")
                                    print(f"Erro ao processar RAAS do ZIP {nome_arq_zip}: {e}")
                                finally:
                                    if os.path.exists(caminho_temp):
                                        try:
                                            os.remove(caminho_temp)
                                        except Exception:
                                            pass
                    continue
                
                # Identifica por nome (regra das referências)
                tipo_identificado = None
                if (tipo_relatorio == "todos" or tipo_relatorio == "rel09") and "rel_sb_gestante_prev_parto" in nome_zip:
                    tipo_identificado = "(rel114) rel_sb_gestante_prev_parto"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel15") and "penha" in nome_zip:
                    tipo_identificado = "(rel135) penha"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel16") and ("amg" in nome_zip or "pacientes_cadastrados" in nome_zip or "pacientes cadastrados" in nome_zip):
                    tipo_identificado = "(rel16) siga_amg"
                elif (tipo_relatorio == "todos" or tipo_relatorio == "rel17") and "atividade_coletiva_por_profissional" in nome_zip:
                    tipo_identificado = "(rel134) atividade_coletiva_por_profissional"
                elif tipo_relatorio == "rel09":
                    tipo_identificado = "(rel114) rel_sb_gestante_prev_parto"
                elif tipo_relatorio == "rel15":
                    tipo_identificado = "(rel135) penha"
                elif tipo_relatorio == "rel16":
                    tipo_identificado = "(rel16) siga_amg"
                elif tipo_relatorio == "rel17":
                    tipo_identificado = "(rel134) atividade_coletiva_por_profissional"
                
                if tipo_identificado:
                    with zipfile.ZipFile(arquivo, 'r') as zip_ref:
                        for nome_arq_zip in zip_ref.namelist():
                            if nome_arq_zip.endswith(('.csv', '.xls', '.xlsx')):
                                ext = os.path.splitext(nome_arq_zip)[1]
                                with zip_ref.open(nome_arq_zip) as fonte:
                                    ok, av, er = _processar_arquivo_tabela_dtic(
                                        fonte, nome_arq_zip, tipo_identificado, ext, periodo_form, modo_estrito, desc_periodo_alvo
                                    )
                                    if ok:
                                        sucessos += 1
                                    if av:
                                        avisos.append(av)
                                    if er:
                                        erros.append(er)
                                
        for av in avisos:
            flash(av, "warning")
        for er in erros:
            flash(er, "danger")

        if sucessos > 0:
            try:
                sincronizar_todas_competencias()
            except Exception as e:
                print(f"Erro ao sincronizar competencias pós-upload: {e}")
            flash(f"{sucessos} arquivo(s) processado(s) com sucesso e importado(s) para o banco de dados!", "success")
        elif not avisos and not erros:
            flash("Nenhum arquivo válido foi encontrado para processamento.", "warning")
        
    from services.competencias import (
        obter_competencia_automatica,
        listar_competencias_disponiveis,
        obter_status_importacao_dtic,
        formatar_descricao_competencia
    )
    
    periodo_selecionado = request.args.get("periodo", "auto")
    comp_auto_val, comp_auto_desc = obter_competencia_automatica()
    
    if periodo_selecionado == 'auto' or not periodo_selecionado:
        periodo_ativo = comp_auto_val
    else:
        periodo_ativo = periodo_selecionado
        
    periodo_ativo_desc = formatar_descricao_competencia(periodo_ativo)
    status_dtic = obter_status_importacao_dtic(periodo_ativo)
    lista_competencias = listar_competencias_disponiveis()
    
    return render_template(
        "upload_dtic.html",
        mensagem=mensagem,
        periodo_selecionado=periodo_selecionado,
        periodo_ativo=periodo_ativo,
        periodo_ativo_desc=periodo_ativo_desc,
        comp_auto_val=comp_auto_val,
        comp_auto_desc=comp_auto_desc,
        status_dtic=status_dtic,
        lista_competencias=lista_competencias
    )


@app.route("/remover_competencia_arquivo", methods=["POST"])
@admin_required
def remover_competencia_arquivo():
    tipo_relatorio = request.form.get("tipo_relatorio")
    periodo = request.form.get("periodo")
    periodo_selecionado = request.form.get("periodo_selecionado", "auto")

    from services.competencias import remover_dados_competencia_dtic
    sucesso, msg = remover_dados_competencia_dtic(tipo_relatorio, periodo)
    if sucesso:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(url_for('upload_dtic', periodo=periodo_selecionado))


@app.route('/cadastros', methods=['GET', 'POST'])
@admin_required
def cadastros():
    catalogo_path = os.path.join(os.getcwd(), 'services', 'catalogo_geral.json')
    cat_data = {'cbos': {}, 'procedimentos': {}, 'profissionais': {}, 'unidades': []}
    if os.path.exists(catalogo_path):
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            cat_data = json.load(f)

    profissionais = cat_data.get('profissionais', {})
    procedimentos = cat_data.get('procedimentos', {})
    cbos = cat_data.get('cbos', {})

    mensagem = None

    if request.method == 'POST':
        acao = request.form.get('acao')
        alterou = False

        if acao == 'salvar_lote_pendentes' or 'lote' in request.form:
            # 1. Salva Equipes em Lote
            for key, val in request.form.items():
                if key.startswith('sigla_') and val and val.strip():
                    cod_ine = key.replace('sigla_', '').strip()
                    unidade = request.form.get(f'unidade_{cod_ine}')
                    sigla = val.strip()
                    equipe = models.Equipe.query.get(cod_ine)
                    if equipe:
                        equipe.sigla = sigla
                    else:
                        equipe = models.Equipe(cod_ine=cod_ine, sigla=sigla, unidade=unidade)
                        db.session.add(equipe)

                # 2. Salva Profissionais em Lote
                elif key.startswith('prof_') and val and val.strip():
                    cns = key.replace('prof_', '').strip()
                    nome = val.strip().upper()
                    profissionais[cns] = nome
                    alterou = True
                    try:
                        db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET nome_prof = :nome WHERE cns_prof = :cns"), {'nome': nome, 'cns': cns})
                    except Exception:
                        pass

                # 3. Salva Procedimentos em Lote
                elif key.startswith('proc_') and val and val.strip():
                    cod = key.replace('proc_', '').strip()
                    cod_10 = cod.zfill(10)
                    desc = val.strip().upper()
                    procedimentos[cod_10] = desc
                    alterou = True
                    try:
                        db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :cod OR cod_acao = :c10"), {'nome': desc, 'cod': cod, 'c10': cod_10})
                        db.session.execute(text("UPDATE 'RAAS_ACOES' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :cod OR cod_acao = :c10"), {'nome': desc, 'cod': cod, 'c10': cod_10})
                        db.session.execute(text('UPDATE "REL-02" SET procedimento = :nome, codigo_procedimento = :c10 WHERE codigo_procedimento = :cod OR codigo_procedimento = :c10'), {'nome': desc, 'cod': cod, 'c10': cod_10})
                    except Exception:
                        pass

                # 4. Salva CBOs em Lote
                elif key.startswith('cbo_') and val and val.strip():
                    cod = key.replace('cbo_', '').strip()
                    desc = val.strip().upper()
                    cbos[cod] = desc
                    alterou = True
                    try:
                        db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET descr_cbo = :nome WHERE co_cbo = :cod"), {'nome': desc, 'cod': cod})
                        db.session.execute(text("UPDATE 'RAAS_ACOES' SET descr_cbo = :nome WHERE co_cbo = :cod"), {'nome': desc, 'cod': cod})
                    except Exception:
                        pass

                # 5. Salva Vínculos EMAB / eMulti em Lote
                elif key.startswith('vinc_') and val and val.strip():
                    nome_equipe = key.replace('vinc_', '').strip()
                    unidade_destino = val.strip()
                    tipo = request.form.get(f'tipo_vinc_{nome_equipe}', 'EMAB')
                    vinc = models.VinculoEmab.query.filter_by(nome_equipe=nome_equipe).first()
                    if vinc:
                        vinc.unidade_destino = unidade_destino
                        vinc.tipo = tipo
                    else:
                        vinc = models.VinculoEmab(nome_equipe=nome_equipe, unidade_destino=unidade_destino, tipo=tipo)
                        db.session.add(vinc)
                    alterou = True

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

            mensagem = "Cadastros em lote salvos e propagados no banco de dados com sucesso!"

        elif acao == 'salvar_equipe':
            cod_ine = request.form.get('cod_ine')
            sigla = request.form.get('sigla')
            unidade = request.form.get('unidade')
            if cod_ine and sigla:
                cod_ine = cod_ine.strip()
                sigla = sigla.strip()
                equipe = models.Equipe.query.get(cod_ine)
                if equipe:
                    equipe.sigla = sigla
                    if unidade:
                        equipe.unidade = unidade.strip()
                else:
                    equipe = models.Equipe(cod_ine=cod_ine, sigla=sigla, unidade=unidade.strip() if unidade else "")
                    db.session.add(equipe)
                db.session.commit()
                alterou = True
                mensagem = f"Equipe {cod_ine} ({sigla}) salva com sucesso!"

        elif acao == 'excluir_equipe':
            cod_ine = request.form.get('cod_ine')
            if cod_ine:
                equipe = models.Equipe.query.get(cod_ine.strip())
                if equipe:
                    db.session.delete(equipe)
                    db.session.commit()
                    alterou = True
                    mensagem = f"Equipe {cod_ine} excluída do cadastro!"

        elif acao == 'salvar_prof' or acao == 'salvar_prof_modal':
            cns = request.form.get('cns') or request.form.get('codigo_chave')
            nome = request.form.get('nome') or request.form.get('valor')
            if cns and nome:
                cns = cns.strip()
                nome = nome.strip().upper()
                profissionais[cns] = nome
                alterou = True
                try:
                    db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET nome_prof = :nome WHERE cns_prof = :cns"), {'nome': nome, 'cns': cns})
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                mensagem = f"Profissional {nome} cadastrado com sucesso!"

        elif acao == 'salvar_proc' or acao == 'salvar_proc_modal':
            cod = request.form.get('codigo') or request.form.get('codigo_chave')
            desc = request.form.get('nome') or request.form.get('valor')
            if cod and desc:
                cod = cod.strip()
                cod_10 = cod.zfill(10)
                desc = desc.strip().upper()
                procedimentos[cod_10] = desc
                alterou = True
                try:
                    db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :cod OR cod_acao = :c10"), {'nome': desc, 'cod': cod, 'c10': cod_10})
                    db.session.execute(text("UPDATE 'RAAS_ACOES' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :cod OR cod_acao = :c10"), {'nome': desc, 'cod': cod, 'c10': cod_10})
                    db.session.execute(text('UPDATE "REL-02" SET procedimento = :nome, codigo_procedimento = :c10 WHERE codigo_procedimento = :cod OR codigo_procedimento = :c10'), {'nome': desc, 'cod': cod, 'c10': cod_10})
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                mensagem = f"Procedimento {cod_10} atualizado com sucesso!"

        elif acao == 'salvar_cbo' or acao == 'salvar_cbo_modal':
            cod = request.form.get('codigo') or request.form.get('codigo_chave')
            desc = request.form.get('descricao') or request.form.get('valor')
            if cod and desc:
                cod = cod.strip()
                desc = desc.strip().upper()
                cbos[cod] = desc
                alterou = True
                try:
                    db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET descr_cbo = :nome WHERE co_cbo = :cod"), {'nome': desc, 'cod': cod})
                    db.session.execute(text("UPDATE 'RAAS_ACOES' SET descr_cbo = :nome WHERE co_cbo = :cod"), {'nome': desc, 'cod': cod})
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                mensagem = f"CBO {cod} atualizado com sucesso!"

        elif acao == 'excluir_prof':
            cns = request.form.get('codigo_chave') or request.form.get('cns')
            if cns and cns in profissionais:
                nome_removido = profissionais.pop(cns)
                alterou = True
                mensagem = f"Profissional {nome_removido} ({cns}) excluído do cadastro!"

        elif acao == 'excluir_proc':
            cod = request.form.get('codigo_chave') or request.form.get('codigo')
            if cod:
                cod_10 = cod.strip().zfill(10)
                proc_removido = procedimentos.pop(cod_10, None) or procedimentos.pop(cod, None)
                if proc_removido:
                    alterou = True
                    mensagem = f"Procedimento {cod_10} - {proc_removido} excluído do cadastro!"

        elif acao == 'excluir_cbo':
            cod = request.form.get('codigo_chave') or request.form.get('codigo')
            if cod and cod in cbos:
                cbo_removido = cbos.pop(cod)
                alterou = True
                mensagem = f"CBO {cod} - {cbo_removido} excluído do cadastro!"

        elif acao == 'salvar_vinculo_emab' or acao == 'salvar_vinculo_modal':
            nome_equipe = request.form.get('nome_equipe') or request.form.get('codigo_chave')
            unidade_destino = request.form.get('unidade_destino') or request.form.get('valor')
            tipo = request.form.get('tipo', 'EMAB')
            if nome_equipe and unidade_destino:
                nome_equipe = nome_equipe.strip()
                unidade_destino = unidade_destino.strip()
                if 'EMULTI' in nome_equipe.upper():
                    tipo = 'eMulti'
                elif 'EMAB' in nome_equipe.upper():
                    tipo = 'EMAB'
                vinc = models.VinculoEmab.query.filter_by(nome_equipe=nome_equipe).first()
                if vinc:
                    vinc.unidade_destino = unidade_destino
                    vinc.tipo = tipo
                else:
                    vinc = models.VinculoEmab(nome_equipe=nome_equipe, unidade_destino=unidade_destino, tipo=tipo)
                    db.session.add(vinc)
                db.session.commit()
                alterou = True
                mensagem = f"Vínculo da equipe '{nome_equipe}' configurado para reposição em '{unidade_destino}' com sucesso!"

        elif acao == 'excluir_vinculo_emab':
            id_vinc = request.form.get('id')
            nome_equipe = request.form.get('nome_equipe') or request.form.get('codigo_chave')
            vinc = None
            if id_vinc:
                vinc = models.VinculoEmab.query.get(id_vinc)
            elif nome_equipe:
                vinc = models.VinculoEmab.query.filter_by(nome_equipe=nome_equipe.strip()).first()
            if vinc:
                nome_del = vinc.nome_equipe
                db.session.delete(vinc)
                db.session.commit()
                alterou = True
                mensagem = f"Vínculo da equipe '{nome_del}' removido com sucesso!"

        if alterou:
            cat_data['profissionais'] = profissionais
            cat_data['procedimentos'] = procedimentos
            cat_data['cbos'] = cbos
            try:
                cat_data['equipes'] = [
                    {'cod_ine': e.cod_ine, 'sigla': e.sigla, 'unidade': e.unidade}
                    for e in models.Equipe.query.order_by(models.Equipe.unidade, models.Equipe.sigla).all()
                ]
            except Exception:
                pass
            try:
                cat_data['vinculos_emab'] = [
                    {'nome_equipe': v.nome_equipe, 'unidade_destino': v.unidade_destino, 'tipo': v.tipo}
                    for v in models.VinculoEmab.query.order_by(models.VinculoEmab.nome_equipe).all()
                ]
            except Exception:
                pass

            with open(catalogo_path, 'w', encoding='utf-8') as f:
                json.dump(cat_data, f, ensure_ascii=False, indent=2)

    # 1. Equipes Mapeadas e Pendentes
    equipes = []
    pendentes_equipes = []
    try:
        equipes = pd.read_sql("SELECT * FROM equipes ORDER BY unidade, sigla", con=db.engine).to_dict('records')
        query_pend_eq = '''
            SELECT DISTINCT r.cod_ine, r.unidade, 'REL 135 (Cadastros Individuais)' AS origem
            FROM "REL-135" r 
            LEFT JOIN equipes e ON r.cod_ine = e.cod_ine 
            WHERE e.sigla IS NULL OR e.sigla = ''
            ORDER BY r.unidade, r.cod_ine
        '''
        pendentes_equipes = pd.read_sql(query_pend_eq, con=db.engine).to_dict('records')
    except Exception:
        pass

    # 2. Pendências de Profissionais
    pendentes_prof = []
    try:
        df_pend_prof = pd.read_sql("""
            SELECT DISTINCT cns_prof, estabelecimento, co_cbo, descr_cbo, 'RAAS CAPS (Relatório 05)' AS origem
            FROM 'RAAS_ACOES_PROF'
            WHERE nome_prof = cns_prof OR nome_prof IS NULL OR nome_prof = ''
            ORDER BY estabelecimento, descr_cbo
        """, con=db.engine)
        pendentes_prof = df_pend_prof.to_dict('records')
    except Exception:
        pass

    # 3. Pendências de Procedimentos (BPA TabWin, RAAS CAPS, SIGA AT-02)
    pendentes_proc = []
    try:
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            cat_atual = json.load(f)
        mapa_procs_atual = cat_atual.get('procedimentos', {})
    except Exception:
        mapa_procs_atual = {}

    try:
        df_raas_proc = pd.read_sql("""
            SELECT DISTINCT cod_acao, procedimento, 'RAAS CAPS (Relatório 05)' AS origem
            FROM 'RAAS_ACOES_PROF'
            WHERE procedimento = cod_acao OR procedimento LIKE 'Procedimento %' OR procedimento IS NULL OR procedimento = ''
        """, con=db.engine)
    except Exception:
        df_raas_proc = pd.DataFrame(columns=['cod_acao', 'procedimento', 'origem'])

    try:
        df_rel02_proc = pd.read_sql("""
            SELECT DISTINCT codigo_procedimento AS cod_acao, procedimento, 'BPA TabWin (Relatório 02)' AS origem
            FROM 'REL-02'
            WHERE procedimento = codigo_procedimento OR procedimento LIKE 'Procedimento %' OR procedimento IS NULL OR procedimento = ''
        """, con=db.engine)
    except Exception:
        df_rel02_proc = pd.DataFrame(columns=['cod_acao', 'procedimento', 'origem'])

    df_comb_proc = pd.concat([df_raas_proc, df_rel02_proc], ignore_index=True)
    if not df_comb_proc.empty:
        df_comb_proc['cod_acao_norm'] = df_comb_proc['cod_acao'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.zfill(10)
        
        linhas_pendentes = []
        for _, row in df_comb_proc.iterrows():
            c10 = row['cod_acao_norm']
            c_orig = str(row['cod_acao']).strip()
            
            # Se o procedimento com 10 dígitos já existe no catálogo, auto-cura na base!
            if c10 in mapa_procs_atual and mapa_procs_atual[c10]:
                nome_cat = mapa_procs_atual[c10]
                try:
                    db.session.execute(text("UPDATE 'REL-02' SET procedimento = :nome, codigo_procedimento = :c10 WHERE codigo_procedimento = :c10 OR codigo_procedimento = :c_orig"), {'nome': nome_cat, 'c10': c10, 'c_orig': c_orig})
                    db.session.execute(text("UPDATE 'RAAS_ACOES_PROF' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :c10 OR cod_acao = :c_orig"), {'nome': nome_cat, 'c10': c10, 'c_orig': c_orig})
                    db.session.execute(text("UPDATE 'RAAS_ACOES' SET procedimento = :nome, cod_acao = :c10 WHERE cod_acao = :c10 OR cod_acao = :c_orig"), {'nome': nome_cat, 'c10': c10, 'c_orig': c_orig})
                    db.session.commit()
                except Exception:
                    pass
            else:
                linhas_pendentes.append({
                    'cod_acao': c10,
                    'procedimento': row['procedimento'],
                    'origem': row['origem']
                })
        
        if linhas_pendentes:
            df_pend_final = pd.DataFrame(linhas_pendentes).drop_duplicates(subset=['cod_acao'])
            pendentes_proc = df_pend_final.to_dict('records')

    # 4. Pendências de CBOs
    pendentes_cbo = []
    try:
        df_pend_cbo = pd.read_sql("""
            SELECT DISTINCT co_cbo, descr_cbo, 'RAAS CAPS (Relatório 05)' AS origem
            FROM 'RAAS_ACOES_PROF'
            WHERE descr_cbo = co_cbo OR descr_cbo IS NULL OR descr_cbo = ''
            ORDER BY co_cbo
        """, con=db.engine)
        pendentes_cbo = df_pend_cbo.to_dict('records')
    except Exception:
        pass

    # 5. Vínculos EMAB / eMulti (PICS Penha)
    vinculos_emab = []
    estabelecimentos_at02_pics = []
    pendentes_vinculos = []
    try:
        vinculos_emab = models.VinculoEmab.query.order_by(models.VinculoEmab.nome_equipe).all()
        nomes_vinculos_existentes = {v.nome_equipe.strip().upper() for v in vinculos_emab}
        unidades_oficiais_upper = {u.strip().upper() for u in prod.UNIDADES_OFICIAIS_REL12}

        df_at02_est = pd.read_sql("""
            SELECT DISTINCT estabelecimento 
            FROM 'AT-02' 
            WHERE UPPER(procedimento) LIKE '%AURICULOTERAPIA%'
            ORDER BY estabelecimento
        """, con=db.engine)
        if not df_at02_est.empty:
            estabelecimentos_at02_pics = sorted(df_at02_est['estabelecimento'].dropna().unique().tolist())
            for est in estabelecimentos_at02_pics:
                est_str = str(est).strip()
                est_upper = est_str.upper()
                if est_upper not in nomes_vinculos_existentes:
                    if 'EMAB' in est_upper or 'EMULTI' in est_upper or '/' in est_upper or est_upper not in unidades_oficiais_upper:
                        tipo_sugerido = 'eMulti' if 'EMULTI' in est_upper else 'EMAB'
                        pendentes_vinculos.append({
                            'nome_equipe': est_str,
                            'tipo': tipo_sugerido,
                            'origem': 'AT-02 (SIGA Produção PICS)'
                        })
    except Exception as e:
        print(f"Erro ao carregar vínculos EMAB: {e}")

    return render_template(
        'cadastros.html',
        equipes=equipes,
        total_equipes=len(equipes),
        pendentes_equipes=pendentes_equipes,
        profissionais=profissionais,
        total_prof=len(profissionais),
        pendentes_prof=pendentes_prof,
        procedimentos=procedimentos,
        total_proc=len(procedimentos),
        pendentes_proc=pendentes_proc,
        cbos=cbos,
        total_cbo=len(cbos),
        pendentes_cbo=pendentes_cbo,
        vinculos_emab=vinculos_emab,
        total_vinculos=len(vinculos_emab),
        pendentes_vinculos=pendentes_vinculos,
        unidades_oficiais_rel12=prod.UNIDADES_OFICIAIS_REL12,
        estabelecimentos_at02_pics=estabelecimentos_at02_pics,
        mensagem=mensagem
    )


@app.route('/equipes', methods=['GET', 'POST'])
def gerenciar_equipes():
    return redirect(url_for('cadastros'))


@app.route('/cadastros_raas', methods=['GET', 'POST'])
def cadastros_raas():
    return redirect(url_for('cadastros'))


if __name__ == '__main__':
    try:
        from waitress import serve
        print("Iniciando servidor robusto de producao (Waitress) na porta 5000...")
        serve(app, host='0.0.0.0', port=5000, threads=8)
    except Exception as e:
        print(f"Waitress nao disponivel, iniciando Werkzeug: {e}")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
