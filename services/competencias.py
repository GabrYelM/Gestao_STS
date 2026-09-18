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
    '01': [],
    '02': [('REL-02', 'ano_mes')],
    '03': [('AT-02', 'ano_mes')],
    '04': [('VG-04', 'ano_mes')],
    '05': [('RAAS_ACOES_PROF', 'ano_mes'), ('RAAS_PACIENTES', 'ano_mes'), ('RAAS_ACOES', 'ano_mes')],
    '06': [],
    '07': [],
    '08': [('GAC-02', 'data_extracao'), ('GAC-02', 'competencia')],
    '09': [('REL-114', 'ano_mes')],
    '10': [('REL-10', 'ano_mes'), ('AT-03', 'ano')],
    '11': [('FE-02', 'ano_mes')],
    '12': [('AT-02', 'ano_mes')],
    '13': [('AG-04', 'ano_mes')],
    '14': [('VG-02', 'ano_mes')],
    '15': [('REL-135', 'ano_mes_competencia')],
    '16': [('REL-16', 'ano_mes')],
    '17': [('REL-134', 'ano_mes')]
}

def formatar_descricao_competencia(competencia, relatorio_id=None):
    comp_str = str(competencia).strip().replace('-', '').replace('/', '')
    if len(comp_str) == 6 and comp_str.isdigit():
        ano = comp_str[:4]
        mes = comp_str[4:6]
        
        # Formatação quadrimestral específica para o Relatório 15 (REL-135)
        if relatorio_id is not None and str(relatorio_id).zfill(2) == '15':
            if mes == '04':
                return f"Q1/{ano}"
            elif mes == '08':
                return f"Q2/{ano}"
            elif mes == '12':
                return f"Q3/{ano}"
                
        return f"{mes}/{ano}"
    return comp_str

def normalizar_competencia(val):
    if val is None:
        return None
    val_raw = str(val).strip()
    if '/' in val_raw:
        partes = val_raw.split('/')
        if len(partes) == 3:
            # DD/MM/YYYY -> YYYYMM
            d, m, a = partes
            if len(a) == 4 and a.isdigit() and m.isdigit():
                a_i, m_i = int(a), int(m)
                if 2020 <= a_i <= 2035 and 1 <= m_i <= 12:
                    return f"{a}{m.zfill(2)}"
        elif len(partes) == 2:
            m, a = partes
            if len(a) == 4 and a.isdigit() and m.isdigit():
                a_i, m_i = int(a), int(m)
                if 2020 <= a_i <= 2035 and 1 <= m_i <= 12:
                    return f"{a}{m.zfill(2)}"
    v_str = val_raw.replace('-', '').replace('/', '')
    if len(v_str) == 6 and v_str.isdigit():
        ano = int(v_str[:4])
        mes = int(v_str[4:6])
        if 2020 <= ano <= 2035 and 1 <= mes <= 12:
            return v_str
    elif len(v_str) >= 8 and v_str[:6].isdigit():
        ano = int(v_str[:4])
        mes = int(v_str[4:6])
        if 2020 <= ano <= 2035 and 1 <= mes <= 12:
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
    
    rel_id = str(relatorio_id).zfill(2)
    desc = formatar_descricao_competencia(norm_comp, relatorio_id=rel_id)
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
            desc = formatar_descricao_competencia(norm_comp, relatorio_id=rel_id)
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
    Garante que competências obsoletas/removidas sejam expurgadas do catálogo indexado.
    """
    with _get_app_context():
        db.create_all()
        for rel_id, configs in MAPA_RELATORIO_TABELAS.items():
            periodos = set()
            for tab, col in configs:
                try:
                    if rel_id == '17' and tab == 'REL-134':
                        df = pd.read_sql(f'SELECT DISTINCT "{col}" as c FROM "{tab}" WHERE "{col}" IS NOT NULL AND inep IS NOT NULL AND inep NOT IN (\'-\', \'\', \'NONE\', \'NAN\')', con=db.engine)
                    else:
                        df = pd.read_sql(f'SELECT DISTINCT "{col}" as c FROM "{tab}" WHERE "{col}" IS NOT NULL', con=db.engine)
                    for v in df['c'].dropna():
                        norm = normalizar_competencia(v)
                        if norm:
                            periodos.add(norm)
                except Exception:
                    pass

            # Limpa competências obsoletas deste relatório na tabela indexada
            try:
                if periodos:
                    comps_sql = ",".join(f"'{p}'" for p in periodos)
                    db.session.execute(text(f"DELETE FROM relatorio_competencias WHERE relatorio_id = :rel_id AND competencia NOT IN ({comps_sql})"), {'rel_id': rel_id})
                else:
                    db.session.execute(text("DELETE FROM relatorio_competencias WHERE relatorio_id = :rel_id"), {'rel_id': rel_id})
                db.session.commit()
            except Exception as e:
                print(f"Erro ao limpar competencias obsoletas de {rel_id}: {e}")
                db.session.rollback()

            if periodos:
                registrar_competencias_lote(rel_id, periodos)

def obter_competencias_por_relatorio():
    """
    Retorna o dicionário de competências de cada relatório de forma instantânea (milissegundos),
    consultando unicamente a tabela indexada relatorio_competencias.
    """
    resultado = {
        '01': [], '02': [], '03': [], '04': [], '05': [], '06': [], '07': [],
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

def obter_competencia_automatica():
    """
    Retorna a competência do mês anterior em relação à data atual.
    Retorna: (comp_valor, comp_descricao), ex: ('202608', '08/2026')
    """
    from datetime import datetime, timedelta
    hoje = datetime.now()
    primeiro_dia_mes = datetime(hoje.year, hoje.month, 1)
    mes_anterior = primeiro_dia_mes - timedelta(days=1)
    comp_valor = mes_anterior.strftime('%Y%m')
    comp_desc = mes_anterior.strftime('%m/%Y')
    return comp_valor, comp_desc

def listar_competencias_disponiveis():
    """
    Lista todas as competências disponíveis para seleção na tela de importação:
    combina competências do banco de dados com os últimos 24 meses do calendário.
    """
    from datetime import datetime
    comps = set()
    try:
        with _get_app_context():
            rows = db.session.execute(text("SELECT DISTINCT competencia FROM relatorio_competencias WHERE relatorio_id IN ('02', '05', '09', '15', '16', '17')")).fetchall()
            for r in rows:
                if r[0] and len(str(r[0])) == 6:
                    comps.add(str(r[0]))
    except Exception:
        pass

    hoje = datetime.now()
    for i in range(24):
        mes = (hoje.month - 1 - i) % 12 + 1
        ano = hoje.year + (hoje.month - 1 - i) // 12
        comps.add(f"{ano}{str(mes).zfill(2)}")

    lista_ordenada = sorted(list(comps), reverse=True)
    return [(c, formatar_descricao_competencia(c)) for c in lista_ordenada]

MAPA_NOMES_DTIC = {
    'rel02': ('PAPENHA (BPA)', '02'),
    'rel05': ('Arquivos RAAS', '05'),
    'rel09': ('Rel 114', '09'),
    'rel17': ('Rel 134', '17'),
    'rel15': ('Rel 135', '15'),
    'rel16': ('SIGA - AMG', '16'),
}

def obter_status_importacao_dtic(periodo):
    """
    Verifica se cada um dos 6 relatórios DTIC/Sistemas possui dados importados
    na competência informada (formato YYYYMM).
    """
    periodo_str = str(periodo).strip()
    ano = periodo_str[:4]
    mes = periodo_str[4:6]
    mes_int = int(mes) if mes.isdigit() else 0
    mes_sem_zero = str(mes_int)
    periodo_int = int(periodo_str) if periodo_str.isdigit() else 0

    resultado = {}

    with _get_app_context():
        # 1. Rel 02 (BPA)
        try:
            r = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'REL-02'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot = r[0] if r else 0
            dt = r[1] if r and r[1] else None
            resultado['rel02'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel02'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

        # 2. Rel 05 (RAAS)
        try:
            r_pac = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'RAAS_PACIENTES'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            r_ac = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'RAAS_ACOES_PROF'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot_pac = r_pac[0] if r_pac else 0
            tot_ac = r_ac[0] if r_ac else 0
            tot = tot_pac + tot_ac
            dt = (r_pac[1] if r_pac and r_pac[1] else None) or (r_ac[1] if r_ac and r_ac[1] else None)
            resultado['rel05'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel05'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

        # 3. Rel 09 (Rel 114)
        try:
            r = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'REL-114'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot = r[0] if r else 0
            dt = r[1] if r and r[1] else None
            resultado['rel09'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel09'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

        # 4. Rel 17 (Rel 134)
        try:
            r = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'REL-134'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot = r[0] if r else 0
            dt = r[1] if r and r[1] else None
            resultado['rel17'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel17'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

        # 5. Rel 15 (Rel 135)
        try:
            r = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'REL-135'
                WHERE ano_mes_competencia = :periodo OR ano_mes_competencia = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot = r[0] if r else 0
            dt = r[1] if r and r[1] else None
            resultado['rel15'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel15'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

        # 6. Rel 16 (SIGA - AMG)
        try:
            r = db.session.execute(text("""
                SELECT COUNT(*) as total, MAX(data_extracao) as dt
                FROM 'REL-16'
                WHERE ano_mes = :periodo OR ano_mes = :periodo_int
            """), {'periodo': periodo_str, 'periodo_int': periodo_int}).fetchone()
            tot = r[0] if r else 0
            dt = r[1] if r and r[1] else None
            resultado['rel16'] = {'importado': tot > 0, 'total_registros': tot, 'data_importacao': dt}
        except Exception as e:
            resultado['rel16'] = {'importado': False, 'total_registros': 0, 'data_importacao': None, 'erro': str(e)}

    return resultado

def remover_dados_competencia_dtic(tipo_relatorio, periodo):
    """
    Remove do banco de dados os registros do relatório e competência especificados,
    atualiza a tabela relatorio_competencias e ressincroniza o catálogo.
    """
    if tipo_relatorio not in MAPA_NOMES_DTIC:
        return False, f"Tipo de relatório inválido: {tipo_relatorio}"

    nome_rel, rel_id = MAPA_NOMES_DTIC[tipo_relatorio]
    periodo_str = str(periodo).strip()
    if len(periodo_str) != 6 or not periodo_str.isdigit():
        return False, f"Competência inválida: {periodo}"

    ano = periodo_str[:4]
    mes = periodo_str[4:6]
    mes_int = int(mes)
    mes_sem_zero = str(mes_int)
    periodo_int = int(periodo_str)

    with _get_app_context():
        try:
            if tipo_relatorio == 'rel02':
                db.session.execute(text("DELETE FROM 'REL-02' WHERE ano_mes = :periodo OR ano_mes = :periodo_int"),
                                   {'periodo': periodo_str, 'periodo_int': periodo_int})
            elif tipo_relatorio == 'rel05':
                db.session.execute(text("DELETE FROM 'RAAS_PACIENTES' WHERE ano_mes = :periodo OR ano_mes = :periodo_int"),
                                   {'periodo': periodo_str, 'periodo_int': periodo_int})
                db.session.execute(text("DELETE FROM 'RAAS_ACOES_PROF' WHERE ano_mes = :periodo OR ano_mes = :periodo_int"),
                                   {'periodo': periodo_str, 'periodo_int': periodo_int})
                db.session.execute(text("DELETE FROM 'RAAS_ACOES' WHERE ano_mes = :periodo OR ano_mes = :periodo_int"),
                                   {'periodo': periodo_str, 'periodo_int': periodo_int})
            elif tipo_relatorio == 'rel09':
                db.session.execute(text("DELETE FROM 'REL-114' WHERE previsao_parto LIKE '%/' || :mes || '/' || :ano"),
                                   {'mes': mes, 'ano': ano})
            elif tipo_relatorio == 'rel17':
                db.session.execute(text("""
                    DELETE FROM 'REL-134'
                    WHERE data_extracao LIKE :ano || '-' || :mes || '-%'
                       OR (length(data_extracao)=10 AND substr(data_extracao, 7, 4) || substr(data_extracao, 4, 2) = :periodo)
                       OR (ano = :ano AND (mes = :mes OR mes = :mes_sem_zero))
                       OR (data_atividade LIKE '%/' || :mes || '/' || :ano)
                """), {'periodo': periodo_str, 'ano': ano, 'mes': mes, 'mes_sem_zero': mes_sem_zero})
            elif tipo_relatorio == 'rel15':
                db.session.execute(text("DELETE FROM 'REL-135' WHERE ano_mes_competencia = :periodo OR ano_mes_competencia = :periodo_int"),
                                   {'periodo': periodo_str, 'periodo_int': periodo_int})
            elif tipo_relatorio == 'rel16':
                db.session.execute(text("""
                    DELETE FROM 'REL-16'
                    WHERE data_extracao LIKE :ano || '-' || :mes || '-%'
                       OR (length(data_extracao)=10 AND substr(data_extracao, 7, 4) || substr(data_extracao, 4, 2) = :periodo)
                """), {'periodo': periodo_str, 'ano': ano, 'mes': mes})

            # Remove da tabela relatorio_competencias
            db.session.execute(text("DELETE FROM relatorio_competencias WHERE relatorio_id = :rel_id AND competencia = :periodo"),
                               {'rel_id': rel_id, 'periodo': periodo_str})
            db.session.commit()

            # Sincroniza competências
            sincronizar_todas_competencias()

            desc_comp = formatar_descricao_competencia(periodo_str)
            return True, f"Dados de {nome_rel} da competência {desc_comp} removidos com sucesso!"
        except Exception as e:
            db.session.rollback()
            return False, f"Erro ao remover dados de {nome_rel}: {str(e)}"

