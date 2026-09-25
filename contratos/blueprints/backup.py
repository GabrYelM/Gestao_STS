"""
Backup do banco SQLite.

Duas formas de uso:
  1. Download avulso: gera uma cópia consistente do banco (via API de
     backup do sqlite3, que funciona mesmo com o banco em uso) e manda
     direto para o navegador - útil para guardar uma cópia externa
     (pendrive, Google Drive, e-mail etc.).
  2. Backup salvo no servidor: cria uma cópia com carimbo de data/hora
     dentro da pasta BACKUP_FOLDER (por padrão, uma subpasta "backups" ao
     lado do banco). Fica disponível para download a qualquer momento e
     não depende de o usuário lembrar de salvar o arquivo baixado em
     algum lugar seguro.

Em ambos os casos, usa-se sqlite3 Connection.backup() em vez de copiar o
arquivo .db diretamente - copiar bytes de um arquivo SQLite que pode estar
com uma transação em aberto arrisca gerar uma cópia corrompida/inconsistente.
"""

import os
import sqlite3
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

bp = Blueprint("backup", __name__, url_prefix="/contratos/backup")


def _backup_folder():
    db_path = current_app.config.get("STSPE_DATABASE_PATH") or current_app.config.get("DATABASE_PATH")
    pasta = current_app.config.get("STSPE_BACKUP_FOLDER") or current_app.config.get("BACKUP_FOLDER") or (
        os.path.join(os.path.dirname(db_path), "backups") if db_path else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    )
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _gerar_backup_em(destino_path):
    """Gera uma cópia consistente do banco em destino_path usando a API
    de backup do sqlite3 (segura mesmo com o banco em uso)."""
    origem_path = current_app.config.get("STSPE_DATABASE_PATH") or current_app.config.get("DATABASE_PATH")
    origem = sqlite3.connect(origem_path)
    destino = sqlite3.connect(destino_path)
    try:
        with destino:
            origem.backup(destino)
    finally:
        origem.close()
        destino.close()


def _listar_backups():
    pasta = _backup_folder()
    itens = []
    for nome in os.listdir(pasta):
        if not nome.lower().endswith(".db"):
            continue
        caminho = os.path.join(pasta, nome)
        stat = os.stat(caminho)
        itens.append({
            "nome": nome,
            "tamanho_mb": round(stat.st_size / (1024 * 1024), 2),
            "criado_em": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "_mtime": stat.st_mtime,
        })
    itens.sort(key=lambda x: x["_mtime"], reverse=True)
    return itens


@bp.route("/")
def index():
    if request.args.get("partial") != "1":
        return redirect(url_for("cadastros.administracao", aba="backup"))
    db_path = current_app.config.get("STSPE_DATABASE_PATH") or current_app.config.get("DATABASE_PATH")
    db_existe = os.path.exists(db_path)
    db_tamanho_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2) if db_existe else 0
    db_modificado = (
        datetime.fromtimestamp(os.path.getmtime(db_path)).strftime("%d/%m/%Y %H:%M")
        if db_existe else "-"
    )
    return render_template("contratos/backup.html",
        backups=_listar_backups(),
        db_path=db_path,
        db_tamanho_mb=db_tamanho_mb,
        db_modificado=db_modificado,
        backup_folder=_backup_folder(),
        partial=request.args.get("partial") == "1",
    )


@bp.route("/baixar_agora")
def baixar_agora():
    """Gera o backup num arquivo temporário e envia direto para download,
    sem deixar cópia na pasta de backups do servidor."""
    import tempfile

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _gerar_backup_em(tmp_path)
        with open(tmp_path, "rb") as f:
            conteudo = f.read()
    finally:
        os.remove(tmp_path)

    nome_arquivo = f"stspe_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    return Response(
        conteudo,
        mimetype="application/x-sqlite3",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@bp.route("/criar", methods=["POST"])
def criar():
    """Cria um backup com carimbo de data/hora dentro da pasta de backups
    no servidor (não baixa nada - fica disponível para download depois)."""
    nome_arquivo = f"stspe_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    destino_path = os.path.join(_backup_folder(), nome_arquivo)
    try:
        _gerar_backup_em(destino_path)
        flash(f"Backup criado com sucesso: {nome_arquivo}", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível criar o backup: {exc}", "erro")
    return redirect(url_for("backup.index"))


@bp.route("/baixar/<nome_arquivo>")
def baixar(nome_arquivo):
    nome_seguro = secure_filename(nome_arquivo)
    caminho = os.path.join(_backup_folder(), nome_seguro)
    if not os.path.exists(caminho):
        flash("Arquivo de backup não encontrado.", "erro")
        return redirect(url_for("backup.index"))
    return send_file(caminho, as_attachment=True, download_name=nome_seguro)


@bp.route("/excluir/<nome_arquivo>", methods=["POST"])
def excluir(nome_arquivo):
    nome_seguro = secure_filename(nome_arquivo)
    caminho = os.path.join(_backup_folder(), nome_seguro)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
            flash(f"Backup {nome_seguro} excluído.", "sucesso")
        else:
            flash("Arquivo de backup não encontrado.", "erro")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível excluir: {exc}", "erro")
    return redirect(url_for("backup.index"))
