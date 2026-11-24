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
import shutil
import sqlite3
import tempfile
import zipfile
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


def _validar_sqlite(caminho):
    """Confirma se o arquivo possui o cabeçalho mágico de um banco SQLite 3 válido."""
    if not os.path.exists(caminho) or os.path.getsize(caminho) < 100:
        return False
    with open(caminho, "rb") as f:
        header = f.read(16)
    return header == b"SQLite format 3\x00"


def _restaurar_db_de(origem_path):
    """Restaura o banco stspe.db a partir de origem_path com cópia de segurança prévia,
    limpeza de arquivos WAL/SHM/journal e aplicação de migrações pendentes."""
    from ..db import close_db, get_db
    from ..migrations_auto import aplicar_migracoes_pendentes

    if not _validar_sqlite(origem_path):
        raise ValueError("O arquivo selecionado não é um banco de dados SQLite válido.")

    destino_path = current_app.config.get("STSPE_DATABASE_PATH") or current_app.config.get("DATABASE_PATH")
    if not destino_path:
        raise ValueError("Caminho do banco de dados de contratos não configurado.")

    # 1. Backup automático de segurança antes de sobrescrever
    if os.path.exists(destino_path):
        nome_seg = f"stspe_pre_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
        _gerar_backup_em(os.path.join(_backup_folder(), nome_seg))

    # 2. Fecha conexão ativa no contexto Flask
    close_db()

    # 3. Remove sidecars SQLite (-wal, -shm, -journal) para evitar corrupção
    for sufixo in ("-wal", "-shm", "-journal"):
        sidecar = destino_path + sufixo
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
            except Exception:
                pass

    # 4. Copia de forma segura usando API backup do sqlite3 (ou shutil se necessário)
    shutil.copy2(origem_path, destino_path)

    # 5. Garante schema atualizado
    conn = get_db()
    aplicar_migracoes_pendentes(conn)
    conn.commit()


@bp.route("/restaurar/<nome_arquivo>", methods=["POST"])
def restaurar(nome_arquivo):
    """Restaura o banco de contratos a partir de um backup salvo no servidor."""
    nome_seguro = secure_filename(nome_arquivo)
    caminho = os.path.join(_backup_folder(), nome_seguro)
    if not os.path.exists(caminho):
        flash("Arquivo de backup não encontrado.", "erro")
        return redirect(url_for("backup.index"))
    try:
        _restaurar_db_de(caminho)
        flash(
            f"Backup '{nome_seguro}' restaurado com sucesso! (Uma cópia de segurança pré-restauração foi salva automaticamente.)",
            "sucesso",
        )
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível restaurar o backup: {exc}", "erro")
    return redirect(url_for("backup.index"))


@bp.route("/restaurar_upload", methods=["POST"])
def restaurar_upload():
    """Restaura o banco de contratos a partir de um arquivo .db ou .zip enviado pelo usuário."""
    arquivo = request.files.get("arquivo_backup")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo .db ou .zip para restaurar.", "erro")
        return redirect(url_for("backup.index"))

    nome_lower = arquivo.filename.lower()
    if not (nome_lower.endswith(".db") or nome_lower.endswith(".zip")):
        flash("Formato inválido. Envie um arquivo .db ou .zip contendo stspe.db.", "erro")
        return redirect(url_for("backup.index"))

    temp_dir = tempfile.mkdtemp()
    try:
        caminho_db = None
        if nome_lower.endswith(".zip"):
            zip_tmp = os.path.join(temp_dir, "upload.zip")
            arquivo.save(zip_tmp)
            with zipfile.ZipFile(zip_tmp, "r") as zf:
                candidatos = [m for m in zf.namelist() if os.path.basename(m).lower().endswith(".db")]
                alvo = next((m for m in candidatos if "stspe" in os.path.basename(m).lower()), None)
                if not alvo and len(candidatos) == 1:
                    alvo = candidatos[0]
                if alvo:
                    caminho_db = os.path.join(temp_dir, "stspe.db")
                    with open(caminho_db, "wb") as f_out:
                        f_out.write(zf.read(alvo))
        else:
            caminho_db = os.path.join(temp_dir, "stspe.db")
            arquivo.save(caminho_db)

        if not caminho_db or not os.path.exists(caminho_db):
            flash("O arquivo enviado não contém um banco de contratos (stspe.db) válido.", "erro")
            return redirect(url_for("backup.index"))

        _restaurar_db_de(caminho_db)
        flash(
            f"Backup '{arquivo.filename}' restaurado com sucesso! (Uma cópia de segurança pré-restauração foi salva automaticamente.)",
            "sucesso",
        )
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao restaurar backup: {exc}", "erro")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return redirect(url_for("backup.index"))
