import os
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, jsonify, request, session, url_for
from concurrent.futures import ThreadPoolExecutor
from decorators import *
app = Flask(__name__)

load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
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


executor = ThreadPoolExecutor(max_workers=10)

def executar_bot(funcao_busca, mes, ano):
    p, context, page = su.bot_setup_page()
    funcao_busca(mes, ano, page, 1000, 1000)
    context.close()
    p.stop()


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
@admin_required
def alterar_senha():
    if request.method == "POST":
        


    return render_template("alterar-senha.html") """


@app.route("/gerar_relatorios", methods=["GET", "POST"])
def gerar_relatorios():
    if request.method == "GET":
        return render_template("gerar-relatorios.html")

    mes_competencia = request.form.get("mes_competencia", "Janeiro")
    ano_competencia = request.form.get("ano_competencia", "2026")

    funcoes = [
        sb.buscaAG04, sb.buscaAT02, sb.buscaAT03, sb.buscaFE02, 
        sb.buscaVG02, sb.buscaVG04, sb.buscaCG01, sb.buscaCG05, 
        sb.buscaCG06, sb.buscaGAC02
    ]

    for func in funcoes:
        executor.submit(executar_bot, func, [mes_competencia], [ano_competencia])

    return jsonify({"mensagem": f"Extração iniciada para {mes_competencia}/{ano_competencia}!"})


if __name__ == '__main__':
    app.run(debug=True)