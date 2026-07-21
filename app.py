from flask import Flask, render_template, jsonify
from concurrent.futures import ThreadPoolExecutor
from services.utils import bot_setup_page 
from services.bot import (
    buscaAG04, buscaAT02, buscaAT03, buscaFE02, 
    buscaVG02, buscaVG04, buscaCG01, buscaCG05, 
    buscaCG06, buscaGAC02
)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)

def executar_bot(funcao_busca, mes, ano):
    p, context, page = bot_setup_page()
    funcao_busca(mes, ano, page, 1000, 1000)
    context.close()
    p.stop()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gerar_relatorios", methods=["POST"])
def gerar_relatorios():
    funcoes = [
        buscaAG04, buscaAT02, buscaAT03, buscaFE02, 
        buscaVG02, buscaVG04, buscaCG01, buscaCG05, 
        buscaCG06, buscaGAC02
    ]

    for func in funcoes:
        executor.submit(executar_bot, func, ["Janeiro"], ["2026"])

    return jsonify({"mensagem": "Extração iniciada!"})

if __name__ == '__main__':
    app.run(debug=True)