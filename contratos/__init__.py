import os
import jinja2
from . import config as config_module
from . import db as db_module
from .migrations_auto import aplicar_migracoes_pendentes

def init_app(app):
    """Inicializa as configurações, banco e blueprints do módulo de contratos."""
    # Configurações do módulo de contratos
    app.config["STSPE_DATABASE_PATH"] = config_module.DATABASE_PATH
    app.config["STSPE_UPLOAD_FOLDER"] = config_module.UPLOAD_FOLDER
    app.config["STSPE_BACKUP_FOLDER"] = config_module.BACKUP_FOLDER
    app.config["DATABASE_PATH"] = config_module.DATABASE_PATH
    app.config["UPLOAD_FOLDER"] = config_module.UPLOAD_FOLDER
    app.config["BACKUP_FOLDER"] = config_module.BACKUP_FOLDER
    app.config["ALLOWED_EXTENSIONS_AT02"] = config_module.ALLOWED_EXTENSIONS_AT02
    app.config["ALLOWED_EXTENSIONS_WEBSSAS"] = config_module.ALLOWED_EXTENSIONS_WEBSSAS
    
    # Adicionar pasta de templates do módulo contratos ao searchpath do Jinja
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    if isinstance(app.jinja_loader, jinja2.FileSystemLoader):
        if template_dir not in app.jinja_loader.searchpath:
            app.jinja_loader.searchpath.append(template_dir)
    elif isinstance(app.jinja_loader, jinja2.ChoiceLoader):
        app.jinja_loader.loaders.append(jinja2.FileSystemLoader(template_dir))
    elif app.jinja_loader is not None:
        app.jinja_loader = jinja2.ChoiceLoader([
            app.jinja_loader,
            jinja2.FileSystemLoader(template_dir)
        ])

    # Criar diretórios de uploads e backups se não existirem
    os.makedirs(config_module.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config_module.BACKUP_FOLDER, exist_ok=True)

    db_module.init_app(app)

    with app.app_context():
        conn = db_module.get_db()
        aplicou = aplicar_migracoes_pendentes(conn)
        if aplicou:
            print("[contratos] Schema do banco atualizado automaticamente na inicialização.")
        
        # Garantir fontes de dados essenciais
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, granularidade, formato_arquivo) "
            "VALUES ('AT02', 'procedimento', 'csv')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, granularidade, formato_arquivo) "
            "VALUES ('WEBSSAS', 'indicador', 'xml')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, granularidade, formato_arquivo) "
            "VALUES ('VISITA_DOMICILIAR', 'indicador', 'csv')"
        )
        conn.execute(
            "UPDATE fontes_dados SET descricao='DTIC (REL_142)' WHERE nome='VISITA_DOMICILIAR' AND descricao IS NULL"
        )
        conn.execute(
            "UPDATE fontes_dados SET descricao='SIGA (AT-02)' WHERE nome='AT02' AND descricao IS NULL"
        )
        conn.execute(
            "UPDATE fontes_dados SET descricao='Websaass' WHERE nome='WEBSSAS' AND descricao IS NULL"
        )
        for nome, descricao in (
            ("AT08", "SIGA (AT-08)"), ("AT11", "SIGA (AT-11)"), ("AT39", "SIGA (AT-39)"),
            ("AT40", "SIGA (AT-40)"), ("AT48", "SIGA (AT-48)"), ("AT49", "SIGA (AT-49)"),
            ("AT57", "SIGA (AT-57)"), ("AT61", "SIGA (AT-61)"),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO fontes_dados (nome, descricao, granularidade, formato_arquivo) "
                "VALUES (?, ?, 'procedimento', 'csv')",
                (nome, descricao),
            )
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, descricao, granularidade, formato_arquivo) "
            "VALUES ('DTIC_REL134', 'DTIC (REL_134)', 'procedimento', 'csv')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, descricao, granularidade, formato_arquivo) "
            "VALUES ('DTIC_REL130', 'DTIC (REL_130)', 'procedimento', 'csv')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO fontes_dados (nome, descricao, granularidade, formato_arquivo) "
            "VALUES ('SISAD', 'SISAD', 'indicador', 'xlsx')"
        )
        for nome_categoria in ("PERTENCE", "CER", "NAO_PERTENCE"):
            conn.execute(
                "INSERT OR IGNORE INTO categorias_estabelecimento (nome) VALUES (?)",
                (nome_categoria,),
            )
        conn.commit()
        db_module.close_db()

    from .blueprints import backup, cadastros, importacao, painel, relatorios, vigencias

    # Registrar blueprints sob o prefixo /contratos
    app.register_blueprint(painel.bp)
    app.register_blueprint(importacao.bp)
    app.register_blueprint(vigencias.bp)
    app.register_blueprint(cadastros.bp)
    app.register_blueprint(relatorios.bp)
    app.register_blueprint(backup.bp)
    print("[contratos] Módulo Contrato de Gestão registrado com sucesso!")
