from flask import Flask, render_template, jsonify, request
from concurrent.futures import ThreadPoolExecutor
import services.utils as su
import services.bot as sb

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)


def executar_bot(funcao_busca, mes, ano):
    p, context, page = su.bot_setup_page()
    funcao_busca(mes, ano, page, 1000, 1000)
    context.close()
    p.stop()


@app.route("/")
def index():
    return render_template("index.html")


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