import os
import json
import io
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, jsonify, request, session, url_for
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
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

import services.utils as su
import services.bot as sb
import pandas as pd
import services.etl as etl
import services.producao as prod
from services.competencias import obter_competencias_por_relatorio, sincronizar_todas_competencias, registrar_competencia

gerenciador_tarefas = ThreadPoolExecutor(max_workers=1)

def executar_bot(funcao_busca, mes, ano, usuario, senha):
    p, context, page = su.bot_setup_page(usuario, senha)
    try:
        # click_timeout = 60000 (Espera inteligentemente até 60s o elemento aparecer)
        # timeout_geral = 100 (Dorme apenas 100ms em vez de 1 segundo a cada passo)
        caminho = funcao_busca(mes, ano, page, 60000, 100)
        return caminho
    except Exception as e:
        print(f"Erro no bot: {e}")
        return None
    finally:
        context.close()
        p.stop()

status_extracao = {"em_andamento": False, "concluido": False, "progresso": ""}

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

def processo_background(mes_inicio, ano_inicio, mes_fim, ano_fim, relatorio_escolhido, usuario, senha):
    status_extracao["em_andamento"] = True
    status_extracao["concluido"] = False
    status_extracao["progresso"] = "Iniciando fila..."
    
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

    if relatorio_escolhido == "TODOS":
        funcoes = list(todas_funcoes.values())
    else:
        funcoes = [todas_funcoes.get(relatorio_escolhido)]
        
    if None in funcoes:
        print("Relatório escolhido inválido.")
        status_extracao["em_andamento"] = False
        return

    gac02_func = None
    funcoes_loop = []
    for bot_f, etl_f in funcoes:
        if bot_f == sb.buscaGAC02:
            gac02_func = (bot_f, etl_f)
        else:
            funcoes_loop.append((bot_f, etl_f))

    MAPA_MESES = {
        "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
        "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
        "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
    }
    periodo_gac = f"{ano_inicio}{MAPA_MESES.get(mes_inicio, '01')}"

    if gac02_func:
        status_extracao["progresso"] = "Extraindo GAC02 (Snapshot Geral)..."
        try:
            bot_gac, etl_gac = gac02_func
            # Executa GAC02 1 única vez
            caminho_gac = executar_bot(bot_gac, mes_inicio, ano_inicio, usuario, senha)
            if caminho_gac:
                etl_gac(caminho_gac, periodo_gac)
        except Exception as e:
            print(f"Erro no GAC02: {e}")

    if relatorio_escolhido != "GAC02" and len(funcoes_loop) > 0:
        lista_periodos = gerar_lista_meses(mes_inicio, ano_inicio, mes_fim, ano_fim)

        for mes, ano in lista_periodos:
            status_extracao["progresso"] = f"Extraindo {mes}/{ano}..."
            print(f"Iniciando fila para {mes}/{ano}")
            
            caminhos_baixados = []
            
            with ThreadPoolExecutor(max_workers=4) as bot_executor:
                futuros = []
                for func_bot, func_etl in funcoes_loop:
                    futuro = bot_executor.submit(executar_bot, func_bot, mes, ano, usuario, senha)
                    futuros.append((futuro, func_etl))
                    
                for futuro, func_etl in futuros:
                    caminho = futuro.result()
                    if caminho:
                        caminhos_baixados.append((caminho, func_etl))
                        
            periodo = int(f"{ano}{MAPA_MESES.get(mes, '01')}")
            
            status_extracao["progresso"] = f"Gravando dados de {mes}/{ano} no BD..."
            for caminho, func_etl in caminhos_baixados:
                try:
                    func_etl(caminho, periodo)
                except Exception as e:
                    print(f"Erro no ETL do arquivo {caminho}: {e}")

        try:
            sincronizar_todas_competencias()
        except Exception:
            pass

    print("100% CONCLUÍDO COM SUCESSO!")
    status_extracao["em_andamento"] = False
    status_extracao["concluido"] = True


def processo_background_pm(usuario, senha, relatorio_escolhido="TODOS"):
    global status_extracao
    status_extracao["em_andamento"] = True
    status_extracao["concluido"] = False
    status_extracao["progresso"] = "Conectando ao Painel de Monitoramento 3.2..."
    status_extracao["status"] = "em_andamento"
    
    try:
        from services.utils import bot_setup_page
        from services.bot import buscaPainelMonitoramento
        from services.etl import processa_painel_monitoramento
        
        p, browser, page = bot_setup_page(usuario, senha)
        try:
            # 1. Extração de STS (Relatório 06)
            if relatorio_escolhido in ["TODOS", "REL06"]:
                status_extracao["progresso"] = "Extraindo Painel por STS (PENHA)..."
                html_sts = buscaPainelMonitoramento(usuario, senha, tipo_local="STS", page=page)
                if html_sts:
                    status_extracao["progresso"] = "Gravando dados de STS (REL-06) no BD..."
                    processa_painel_monitoramento(html_sts, tabela_db='REL-06', default_localidade='STS PENHA')
                    
            # 2. Extração de Subprefeitura (Relatório 07)
            if relatorio_escolhido in ["TODOS", "REL07"]:
                status_extracao["progresso"] = "Extraindo Painel por Subprefeitura (PENHA)..."
                html_subpref = buscaPainelMonitoramento(usuario, senha, tipo_local="Subprefeitura", page=page)
                if html_subpref:
                    status_extracao["progresso"] = "Gravando dados de Subprefeitura (REL-07) no BD..."
                    processa_painel_monitoramento(html_subpref, tabela_db='REL-07', default_localidade='Subprefeitura PENHA')
            
            try:
                sincronizar_todas_competencias()
            except Exception:
                pass
                    
            status_extracao["progresso"] = "Extração do Painel concluída com sucesso!"
            status_extracao["status"] = "sucesso"
        finally:
            browser.close()
            p.stop()
            
    except Exception as e:
        print(f"Erro na extração do Painel de Monitoramento: {e}")
        status_extracao["progresso"] = f"Erro: {e}"
        status_extracao["status"] = "erro"
        
    finally:
        status_extracao["em_andamento"] = False
        status_extracao["concluido"] = True


@app.route("/painel_monitoramento", methods=["GET", "POST"])
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
# @login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        senha_digitada = request.form.get("password")

        usuario = models.Usuario.query.filter_by(username=username).first()

        if usuario and usuario.check_senha(senha_digitada):
            session["usuario_id"] = usuario.id
            session["usuario_nome"] = usuario.username
            session["is_admin"] = usuario.is_admin

            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha incorretos. Tente novamente.", "error")

    if session.get("usuario_id"):
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


""" @app.route("/alterar_senha", methods=["GET", "POST"])
# @admin_required
def alterar_senha():
    if request.method == "POST":
        


    return render_template("alterar-senha.html") """


@app.route("/bi_producao", methods=["GET", "POST"])
def gerar_relatorios():
    if request.method == "GET":
        return render_template("bi-producao.html")

    mes_inicio = request.form.get("mes_inicio", "Janeiro")
    ano_inicio = request.form.get("ano_inicio", "2026")
    mes_fim = request.form.get("mes_fim", "Janeiro")
    ano_fim = request.form.get("ano_fim", "2026")
    relatorio_escolhido = request.form.get("relatorio_escolhido", "TODOS")
    usuario_bi = request.form.get("usuario_bi", "")
    senha_bi = request.form.get("senha_bi", "")

    # Testar credenciais usando Playwright (mesmo motor do robô para evitar erros de protocolo)
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
        print(f"Erro no teste prévio de credenciais: {e}")
        pass # Se der timeout na rede, prossegue e deixa o bot principal tentar lidar com a lentidão

    gerenciador_tarefas.submit(processo_background, mes_inicio, ano_inicio, mes_fim, ano_fim, relatorio_escolhido, usuario_bi, senha_bi)

    return jsonify({"mensagem": f"Autenticado! Extração iniciada de {mes_inicio}/{ano_inicio} até {mes_fim}/{ano_fim} ({relatorio_escolhido})!"})

@app.route("/status_extracao")
def status_extracao_route():
    return jsonify(status_extracao)


import io
from flask import send_file

@app.route("/download_excel/<indice>/<periodo>")
def download_excel(indice, periodo):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
        
    try:
        if indice == '02':
            df = prod.gera_relatorio_02(periodo)
        elif indice == '03':
            df = prod.gera_relatorio_03(periodo)
        elif indice == '04':
            df = prod.gera_relatorio_04(periodo)
        elif indice == '05':
            df_pac, df_prof, df_acoes = prod.gera_relatorio_05(periodo)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if df_pac is not None and not df_pac.empty:
                    df_pac.to_excel(writer, index=False, sheet_name='RAAS')
                if df_prof is not None and not df_prof.empty:
                    df_prof.to_excel(writer, index=False, sheet_name='RAAS_PROF')
                if df_acoes is not None and not df_acoes.empty:
                    df_acoes.to_excel(writer, index=False, sheet_name='CONS_ACOES')
            output.seek(0)
            return send_file(output, download_name=f"Relatorio_05_RAAS_CAPS_{periodo}.xlsx", as_attachment=True)
        elif indice == '08':
            df = prod.gera_relatorio_08(periodo)
        elif indice == '09':
            df = prod.gera_relatorio_09(periodo)
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
        elif indice == '15':
            df = prod.gera_relatorio_15(periodo)
        elif indice == '16':
            pivot_ativo, pivot_inativo = prod.gera_relatorio_16(periodo)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if pivot_ativo is not None and not pivot_ativo.empty:
                    pivot_ativo.to_excel(writer, index=False, sheet_name='Ativos - Por Tipo')
                if pivot_inativo is not None and not pivot_inativo.empty:
                    pivot_inativo.to_excel(writer, index=False, sheet_name='Inativos - Por Motivo')
            output.seek(0)
            return send_file(output, download_name=f"Relatorio_16_AMG_{periodo}.xlsx", as_attachment=True)
        elif indice == '17':
            df = prod.gera_relatorio_17(periodo)
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
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    tabela_html = None
    json_dados = None
    json_colunas = None
    indice = request.form.get("indice_relatorio") if request.method == "POST" else None
    
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
    periodo = request.form.get("periodo") if request.method == "POST" else None
    if not periodo or periodo not in [p[0] for p in periodos_disponiveis]:
        periodo = periodo_padrao

    fonte_dados = None
    data_geracao = None

    if request.method == "POST":
        # 1. Pega as opções que o usuário digitou/escolheu na tela
        indice = request.form.get("indice_relatorio")
        if not request.form.get("periodo"):
            periodo = periodo_padrao
        else:
            periodo = request.form.get("periodo")
        
        if indice:
            meta = prod.obter_metadados_relatorio(indice, periodo)
            fonte_dados = meta.get('fonte')
            data_geracao = meta.get('data_geracao')

        # 2. Um "if" simples para decidir qual função rodar
        try:
            if indice == '02':
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
                    colunas_acoes = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_acoes.columns]
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
                df_ativo, df_inativo = prod.gera_relatorio_16(periodo)
                json_dados_ativo = None
                json_colunas_ativo = None
                json_dados_inativo = None
                json_colunas_inativo = None
                
                if df_ativo is not None and not df_ativo.empty:
                    colunas_ativo = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_ativo.columns]
                    json_colunas_ativo = json.dumps(colunas_ativo)
                    json_dados_ativo = json.dumps(df_ativo.fillna("").to_dict(orient="records"))
                    
                if df_inativo is not None and not df_inativo.empty:
                    colunas_inativo = [{"data": str(col).replace(".", "\\."), "title": str(col)} for col in df_inativo.columns]
                    json_colunas_inativo = json.dumps(colunas_inativo)
                    json_dados_inativo = json.dumps(df_inativo.fillna("").to_dict(orient="records"))
                
                return render_template(
                    "producao.html",
                    tabela_html=tabela_html,
                    json_dados_ativo=json_dados_ativo,
                    json_colunas_ativo=json_colunas_ativo,
                    json_dados_inativo=json_dados_inativo,
                    json_colunas_inativo=json_colunas_inativo,
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

    return render_template(
        "producao.html",
        tabela_html=tabela_html,
        json_dados=json_dados,
        json_colunas=json_colunas,
        relatorio_selecionado=indice,
        periodo_selecionado=periodo,
        periodos_disponiveis=periodos_disponiveis,
        json_competencias_por_relatorio=json.dumps(mapa_competencias),
        fonte_dados=fonte_dados,
        data_geracao=data_geracao
    )



import zipfile
import os

@app.route("/upload_zip", methods=["GET", "POST"])
@app.route("/upload_dtic", methods=["GET", "POST"])
def upload_dtic():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
        
    mensagem = None
    if request.method == "POST":
        tipo_relatorio = request.form.get("tipo_relatorio")
        arquivos = request.files.getlist("arquivos")
        
        sucessos = 0
        for arquivo in arquivos:
            if not arquivo or not arquivo.filename:
                continue
            nome_arq = arquivo.filename
            nome_lower = nome_arq.lower()
            
            # 1. Arquivo .DBF do TabWin (Relatório 02 - Produção BPA)
            if nome_lower.endswith('.dbf'):
                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                caminho_final = os.path.join(pasta_destino, nome_arq)
                arquivo.save(caminho_final)
                
                from services.etl import processa_bpa_dbf
                try:
                    if processa_bpa_dbf(caminho_final):
                        sucessos += 1
                except Exception as e:
                    print(f"Erro ao processar DBF {nome_arq}: {e}")
                finally:
                    # Remove o arquivo .DBF bruto do disco após a gravação no banco SQLite
                    if os.path.exists(caminho_final):
                        try:
                            os.remove(caminho_final)
                        except Exception as err_rem:
                            print(f"Erro ao remover arquivo temporário {caminho_final}: {err_rem}")

            # 2. Arquivos RAAS das Unidades CAPS (Relatório 05)
            elif any(nome_lower.endswith(ext) for ext in ['.jul', '.ago', '.set', '.out', '.nov', '.dez', '.jan', '.fev', '.mar', '.abr', '.mai', '.jun', '.raas']) or (tipo_relatorio == "rel05") or (nome_lower.startswith('aa') and len(nome_lower) >= 8 and not nome_lower.endswith('.zip')):
                pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                caminho_final = os.path.join(pasta_destino, nome_arq)
                arquivo.save(caminho_final)
                
                from services.etl import processa_raas_arquivo
                try:
                    if processa_raas_arquivo(caminho_final):
                        sucessos += 1
                except Exception as e:
                    print(f"Erro ao processar RAAS {nome_arq}: {e}")
                finally:
                    if os.path.exists(caminho_final):
                        try:
                            os.remove(caminho_final)
                        except Exception as err_rem:
                            print(f"Erro ao remover arquivo temporário RAAS {caminho_final}: {err_rem}")

            # 3. Arquivos .ZIP do DTIC / SIGAPEP ou pacotes RAAS
            elif nome_lower.endswith('.zip'):
                nome_zip = nome_lower
                
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
                                    if processa_raas_arquivo(caminho_temp):
                                        sucessos += 1
                                except Exception as e:
                                    print(f"Erro ao processar RAAS do ZIP {nome_arq_zip}: {e}")
                                finally:
                                    if os.path.exists(caminho_temp):
                                        try:
                                            os.remove(caminho_temp)
                                        except Exception:
                                            pass
                    continue
                
                # Identifica por nome (regra das referências)
                
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
                
                if tipo_identificado:
                    # Salvar diretamente na pasta raiz ARQUIVOS ORIGINAIS
                    pasta_destino = os.path.join(os.getcwd(), "ARQUIVOS ORIGINAIS")
                    
                    with zipfile.ZipFile(arquivo, 'r') as zip_ref:
                        for nome_arq_zip in zip_ref.namelist():
                            if nome_arq_zip.endswith('.csv') or nome_arq_zip.endswith('.xls') or nome_arq_zip.endswith('.xlsx'):
                                ext = os.path.splitext(nome_arq_zip)[1]
                                nome_final = f"{tipo_identificado}{ext}"
                                caminho_final = os.path.join(pasta_destino, nome_final)
                                
                                # Extrai, filtra e salva o arquivo
                                with zip_ref.open(nome_arq_zip) as fonte:
                                    import pandas as pd
                                    
                                    # Definir regras de filtro baseadas no relatório
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
                                    
                                    if filtro_coluna:
                                        # Leitura em pedaços (chunks) para não estourar a memória
                                        first = True
                                        for chunk in pd.read_csv(fonte, sep=';', encoding='latin1', chunksize=50000, low_memory=False):
                                            if filtro_coluna in chunk.columns:
                                                chunk_filtrado = chunk[chunk[filtro_coluna] == filtro_valor]
                                                chunk_filtrado.to_csv(caminho_final, mode='w' if first else 'a', header=first, index=False, sep=';', encoding='latin1')
                                                first = False
                                            else:
                                                # Se a coluna não existir, salva tudo por segurança
                                                chunk.to_csv(caminho_final, mode='w' if first else 'a', header=first, index=False, sep=';', encoding='latin1')
                                                first = False
                                    else:
                                        # Sem filtro definido, extrai normalmente (copia o conteúdo)
                                        with open(caminho_final, "wb") as destino:
                                            destino.write(fonte.read())
                                
                                # Chama a função de ETL correspondente
                                from services.etl import processa_rel114, processa_rel134, processa_rel135, processa_rel16
                                try:
                                    if "(rel114)" in tipo_identificado:
                                        processa_rel114(caminho_final)
                                    elif "(rel134)" in tipo_identificado:
                                        processa_rel134(caminho_final)
                                    elif "(rel135)" in tipo_identificado:
                                        processa_rel135(caminho_final)
                                    elif "(rel16)" in tipo_identificado:
                                        processa_rel16(caminho_final)
                                except Exception as e:
                                    print(f"Erro ao processar ETL do {tipo_identificado}: {e}")
                                
        if sucessos > 0:
            try:
                sincronizar_todas_competencias()
            except Exception as e:
                print(f"Erro ao sincronizar competencias pós-upload: {e}")
                
        mensagem = f"{sucessos} arquivo(s) processado(s) com sucesso e importado(s) para o banco de dados!"
        
    return render_template("upload_dtic.html", mensagem=mensagem)


@app.route('/cadastros', methods=['GET', 'POST'])
def cadastros():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

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
                mensagem = f"Equipe {cod_ine} ({sigla}) salva com sucesso!"

        elif acao == 'excluir_equipe':
            cod_ine = request.form.get('cod_ine')
            if cod_ine:
                equipe = models.Equipe.query.get(cod_ine.strip())
                if equipe:
                    db.session.delete(equipe)
                    db.session.commit()
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

        if alterou:
            cat_data['profissionais'] = profissionais
            cat_data['procedimentos'] = procedimentos
            cat_data['cbos'] = cbos
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
        mensagem=mensagem
    )


@app.route('/equipes', methods=['GET', 'POST'])
def gerenciar_equipes():
    return redirect(url_for('cadastros'))


@app.route('/cadastros_raas', methods=['GET', 'POST'])
def cadastros_raas():
    return redirect(url_for('cadastros'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
