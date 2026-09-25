import os
import sqlite3
from flask import current_app, g

def get_db():
    """Retorna a conexão SQLite do módulo de contratos da requisição atual."""
    if "contratos_db" not in g:
        db_path = current_app.config.get("STSPE_DATABASE_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stspe.db")
        g.contratos_db = sqlite3.connect(db_path)
        g.contratos_db.row_factory = sqlite3.Row
        g.contratos_db.execute("PRAGMA foreign_keys = ON")
    return g.contratos_db

def close_db(e=None):
    try:
        from flask import has_app_context
        if has_app_context():
            db = g.pop("contratos_db", None)
            if db is not None:
                db.close()
    except Exception:
        pass


def init_db_command_impl(app):
    """Cria o banco a partir do schema.sql se ele ainda não existir."""
    db_path = app.config.get("STSPE_DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stspe.db"))
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    if os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    with open(schema_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db_command_impl(app)
