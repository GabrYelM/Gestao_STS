import os
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, jsonify, request, session, url_for
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

gerenciador_tarefas = ThreadPoolExecutor(max_workers=1)

def executar_bot(funcao_busca, mes, ano):
    p, context, page = su.bot_setup_page()
    try:
        caminho = funcao_busca(mes, ano, page, 1000, 1000)
        return caminho
    except Exception as e:
        print(f"Erro no bot: {e}")
        return None
    finally:
        context.close()
        p.stop()

status_extracao = {"em_andamento": False, "concluido": False}

def processo_background(mes_competencia, ano_competencia, relatorio_escolhido="TODOS"):
    status_extracao["em_andamento"] = True
    status_extracao["concluido"] = False
    
    print(f"Iniciando fila para {mes_competencia[0]}/{ano_competencia[0]} - Relatório: {relatorio_escolhido}")
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
        return

    caminhos_baixados = []
    
    # FASE 1: DOWNLOADS EM PARALELO
    print("Fase 1: Disparando robôs de download em paralelo (max 4 por vez)...")
    with ThreadPoolExecutor(max_workers=4) as bot_executor:
        futuros = []
        for func_bot, func_etl in funcoes:
            futuro = bot_executor.submit(executar_bot, func_bot, mes_competencia, ano_competencia)
            futuros.append((futuro, func_etl))
            
        for futuro, func_etl in futuros:
            caminho = futuro.result() # Espera acabar
            if caminho:
                caminhos_baixados.append((caminho, func_etl))
                
    # FASE 2: ETL SEQUENCIAL
    print("Fase 2: Todos os downloads concluídos. Iniciando inserção no banco de dados...")
    for caminho, func_etl in caminhos_baixados:
        try:
            print(f"-> Subindo arquivo: {caminho}")
            func_etl(caminho)
        except Exception as e:
            print(f"Erro no ETL do arquivo {caminho}: {e}")
            
    print("100% CONCLUÍDO COM SUCESSO!")
    status_extracao["em_andamento"] = False
    status_extracao["concluido"] = True


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


@app.route("/gerar_relatorios", methods=["GET", "POST"])
# @login_required
def gerar_relatorios():
    if request.method == "GET":
        return render_template("gerar-relatorios.html")

    mes_competencia = request.form.get("mes_competencia", "Janeiro")
    ano_competencia = request.form.get("ano_competencia", "2026")
    relatorio_escolhido = request.form.get("relatorio_escolhido", "TODOS")

    gerenciador_tarefas.submit(processo_background, [mes_competencia], [ano_competencia], relatorio_escolhido)

    return jsonify({"mensagem": f"Extração iniciada para {mes_competencia}/{ano_competencia} ({relatorio_escolhido})! Os robôs estão baixando os arquivos."})

@app.route("/status_extracao")
def status_extracao_route():
    return jsonify(status_extracao)

@app.route("/producao", methods=["GET", "POST"])
# @login_required
def producao():
    tabela_html = None  # Começa vazio
    if request.method == "POST":
        # 1. Pega as opções que o usuário digitou/escolheu na tela
        indice = request.form.get("indice_relatorio")
        periodo = request.form.get("periodo")
        # 2. Um "if" simples para decidir qual função rodar
        try:
            if indice == '03':
                df = prod.gera_relatorio_03(periodo)
            elif indice == '04':
                df = prod.gera_relatorio_04(periodo)
            elif indice == '08':
                df = prod.gera_relatorio_08(periodo)
            elif indice == '10':
                df = prod.gera_relatorio_10(periodo)
            elif indice == '11':
                df = prod.gera_relatorio_11(periodo)
            elif indice == '13':
                df = prod.gera_relatorio_13(periodo)
            elif indice == '14':
                df = prod.gera_relatorio_14(periodo)
            else:
                df = None
            
            # 3. Transforma o resultado em HTML
            if df is not None:
                tabela_html = df.to_html(classes='table table-striped table-bordered table-hover')
                
        except Exception as e:
            # Caso o usuário digite um mês que não tem no banco, etc.
            tabela_html = f"<div class='alert alert-danger'>Erro ao gerar relatório: {e}</div>"
    return render_template("producao.html", tabela_html=tabela_html)


if __name__ == '__main__':
    app.run(debug=True)