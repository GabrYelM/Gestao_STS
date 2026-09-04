import pandas as pd
from sqlalchemy import text
from flask import current_app, has_app_context
from database import db
import models

def _get_app_context():
    if has_app_context():
        import contextlib
        return contextlib.nullcontext()
    from app import app
    return app.app_context()

MAPA_RELATORIO_TABELAS = {
    '02': [('REL-02', 'ano_mes')],
    '03': [('AT-02', 'ano_mes')],
    '04': [('VG-04', 'ano_mes')],
    '05': [('RAAS_ACOES_PROF', 'ano_mes'), ('RAAS_PACIENTES', 'ano_mes'), ('RAAS_ACOES', 'ano_mes')],
    '06': [],
    '07': [],
    '08': [('GAC-02', 'data_extracao'), ('GAC-02', 'competencia')],
    '09': [('REL-114', 'ano_mes'), ('REL-114', 'data_extracao')],
    '10': [('REL-10', 'ano_mes'), ('AT-03', 'ano')],
    '11': [('FE-02', 'ano_mes')],
    '12': [('REL-12', 'ano_mes_extracao'), ('REL-12', 'data_extracao')],
    '13': [('AG-04', 'ano_mes')],
    '14': [('VG-02', 'ano_mes')],
    '15': [('REL-135', 'ano_mes_competencia')],
    '16': [('REL-16', 'data_extracao')],
    '17': [('REL-134', 'ano'), ('REL-134', 'data_extracao')]
}

def formatar_descricao_competencia(competencia):
    comp_str = str(competencia).strip().replace('-', '').replace('/', '')
    if len(comp_str) == 6 and comp_str.isdigit():
        ano = comp_str[:4]
        mes = comp_str[4:6]
        return f"{mes}/{ano}"
    return comp_str

def normalizar_competencia(val):
    if val is None:
        return None
    v_str = str(val).strip().replace('-', '').replace('/', '')
    if len(v_str) == 6 and v_str.isdigit():
        ano = int(v_str[:4])
        mes = int(v_str[4:6])
        if 2025 <= ano <= 2035 and 1 <= mes <= 12:
            return v_str
    elif len(v_str) >= 8 and v_str[:6].isdigit():
        ano = int(v_str[:4])
        mes = int(v_str[4:6])
        if 2025 <= ano <= 2035 and 1 <= mes <= 12:
            return v_str[:6]
    return None

def registrar_competencia(relatorio_id, competencia):
    """
    Registra uma competência para um relatório na tabela relatorio_competencias se ela ainda não existir.
    Execução ultra-rápida (O(1)).
    """
    norm_comp = normalizar_competencia(competencia)
    if not norm_comp:
        return False
    
    desc = formatar_descricao_competencia(norm_comp)
    rel_id = str(relatorio_id).zfill(2)
    try:
        with _get_app_context():
            sql = text("""
                INSERT OR IGNORE INTO relatorio_competencias (relatorio_id, competencia, descricao)
                VALUES (:rel_id, :comp, :desc)
            """)
            db.session.execute(sql, {'rel_id': rel_id, 'comp': norm_comp, 'desc': desc})
            db.session.commit()
            return True
    except Exception as e:
        print(f"Erro ao registrar competencia {competencia} para relatorio {relatorio_id}: {e}")
        return False

def registrar_competencias_lote(relatorio_id, lista_competencias):
    """
    Registra múltiplas competências em lote para um relatório.
    """
    if not lista_competencias:
        return
    rel_id = str(relatorio_id).zfill(2)
    registros = []
    for comp in lista_competencias:
        norm_comp = normalizar_competencia(comp)
        if norm_comp:
            desc = formatar_descricao_competencia(norm_comp)
            registros.append({'rel_id': rel_id, 'comp': norm_comp, 'desc': desc})
    
    if registros:
        try:
            with _get_app_context():
                sql = text("""
                    INSERT OR IGNORE INTO relatorio_competencias (relatorio_id, competencia, descricao)
                    VALUES (:rel_id, :comp, :desc)
                """)
                db.session.execute(sql, registros)
                db.session.commit()
        except Exception as e:
            print(f"Erro ao registrar lote de competencias: {e}")

def sincronizar_todas_competencias():
    """
    Varre as tabelas do banco de dados para sincronizar a tabela relatorio_competencias.
    Pode ser executada na inicialização ou após processos de carga em lote.
    """
    with _get_app_context():
        db.create_all()
        for rel_id, configs in MAPA_RELATORIO_TABELAS.items():
            periodos = set()
            for tab, col in configs:
                try:
                    df = pd.read_sql(f'SELECT DISTINCT "{col}" as c FROM "{tab}" WHERE "{col}" IS NOT NULL', con=db.engine)
                    for v in df['c'].dropna():
                        norm = normalizar_competencia(v)
                        if norm:
                            periodos.add(norm)
                except Exception:
                    pass
            if periodos:
                registrar_competencias_lote(rel_id, periodos)

def obter_competencias_por_relatorio():
    """
    Retorna o dicionário de competências de cada relatório de forma instantânea (milissegundos),
    consultando unicamente a tabela indexada relatorio_competencias.
    """
    resultado = {
        '02': [], '03': [], '04': [], '05': [], '06': [], '07': [],
        '08': [], '09': [], '10': [], '11': [], '12': [], '13': [],
        '14': [], '15': [], '16': [], '17': []
    }
    
    try:
        with _get_app_context():
            # Se a tabela ainda estiver vazia no primeiro carregamento, faz uma sincronização inicial
            total = db.session.execute(text("SELECT COUNT(*) FROM relatorio_competencias")).scalar()
            if not total or total == 0:
                sincronizar_todas_competencias()
            
            rows = db.session.execute(text("SELECT relatorio_id, competencia, descricao FROM relatorio_competencias ORDER BY competencia DESC")).fetchall()
            for row in rows:
                r_id = str(row[0]).zfill(2)
                comp = str(row[1])
                desc = str(row[2])
                if r_id not in resultado:
                    resultado[r_id] = []
                if (comp, desc) not in resultado[r_id]:
                    resultado[r_id].append((comp, desc))
                    
    except Exception as e:
        print(f"Erro ao obter competencias: {e}")
        
    return resultado
