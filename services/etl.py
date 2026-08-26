# transforma os arquivos em tabelas no db
import pandas as pd
from datetime import datetime
from app import app
from database import db
from sqlalchemy import text
import models

import io

def read_clean_csv(caminho, primeira_coluna):
    """
    Lê o arquivo nativamente, ignora todo o lixo do cabeçalho da prefeitura,
    e entrega para o pandas apenas a partir da linha onde as colunas reais começam.
    Isso evita qualquer erro de parsing de aspas duplas ou linhas em branco.
    """
    with open(caminho, 'r', encoding='latin1', errors='ignore') as f:
        linhas = f.readlines()
        
    inicio = 0
    for i, linha in enumerate(linhas):
        if primeira_coluna in linha:
            inicio = i
            break
            
    conteudo_limpo = ''.join(linhas[inicio:])
    return pd.read_csv(io.StringIO(conteudo_limpo), sep=';')

def processa_ag04(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes1')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Nome_Tipo_Agenda1': 'tipo_agenda',
        'H1___Nome_Estabelecimento1': 'estabelecimento',
        'Código_CNES': 'cnes',
        'Nome_Especialidade1': 'especialidade',
        'Nome_Tipo_Atendimento_Agenda1': 'tipo_atendimento_agenda',
        'Nome_Procedimento1': 'procedimento',
        'Nome_Situação_Agendamento1': 'situacao_agendamento',
        'Nome_Tipo_Entidade1': 'tipo_entidade',
        'Quantidade_Agendamento1': 'quantidade_agendamento',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        periodo = df_limpo['ano_mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'AG-04' WHERE ano_mes = {periodo}"))
        db.session.commit()
        df_limpo.to_sql(name='AG-04', con=db.engine, if_exists='append', index=False)

    print('AG-04 carregado')

def processa_at02(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Código_CNES': 'cnes',
        'H1___Nome_Estabelecimento2': 'estabelecimento',
        'H1___Código_CMES': 'cmes',
        'Tipo_Estabelecimento': 'tipo_estabelecimento',
        'Código_CBO_no_SUS': 'cbo_no_sus',
        'Nome_CBO1': 'nome_cbo',
        'Nome_Especialidade2': 'especialidade',
        'Código_Procedimento': 'codigo_procedimento',
        'Nome_Procedimento2': 'procedimento',
        'Nome_Profissional_Siga1': 'profissional',
        'Quantidade_Procedimento2': 'quantidade_procedimento',
        'Contagem_Paciente2': 'contagem_paciente',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        periodo = df_limpo['ano_mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'AT-02' WHERE ano_mes = {periodo}"))
        db.session.commit()
        df_limpo.to_sql(name='AT-02', con=db.engine, if_exists='append', index=False)

    print('AT-02 carregado')

def processa_at03(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes')

    traduz_col = {
        'Número_Ano': 'ano',
        'Nome_Mes': 'mes',
        'H1___Nome_Nível_3': 'sts',
        'H1___Nome_Estabelecimento': 'estabelecimento',
        'Nome_Faixa_Etária': 'faixa_etaria',
        'Nome_CBO': 'nome_cbo',
        'Nome_Procedimento': 'nome_procedimento',
        'Sexo': 'sexo',
        'Quantidade_Procedimento': 'quantidade_procedimento',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        ano = df_limpo['ano'].iloc[0]
        mes = df_limpo['mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'AT-03' WHERE ano = {ano} AND mes = '{mes}'"))
        db.session.commit()
        df_limpo.to_sql(name='AT-03', con=db.engine, if_exists='append', index=False)

    print('AT-03 carregado')

def processa_fe02(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes6')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'H1___Nome_Nível_31': 'sts',
        'H1___Nome_Estabelecimento': 'estabelecimento',
        'Código_CNES': 'cnes',
        'Nome_Procedimento5': 'nome_procedimento',
        'Nome_Especialidade1': 'nome_especialidade',
        'Quantidade_de_Pacientes_que_Entraram_em_Espera_no_Mês6': 'entrou_em_espera',
        'Quantidade_de_Pacientes_que_Saíram_de_Espera_no_Mês6': 'saiu_da_espera',
        'Quantidade_Total_de_Pacientes_Ativos6': 'pacientes_ativos',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        periodo = df_limpo['ano_mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'FE-02' WHERE ano_mes = {periodo}"))
        db.session.commit()
        df_limpo.to_sql(name='FE-02', con=db.engine, if_exists='append', index=False)

    print('FE-02 carregado')

def processa_vg02(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Código_CNES': 'cnes',
        'H1___Nome_Estabelecimento1': 'estabelecimento',
        'Nome_Procedimento2': 'procedimento',
        'Nome_Especialidade2': 'nome_especialidade',
        'Nome_Tipo_Agenda': 'tipo_agenda',
        'Nome_Tipo_Atendimento_Agenda2': 'tipo_atendimento_agenda',
        'Nome_Situação_Vaga2': 'situacao_vaga',
        'Qtde_Vaga_Ofertada2': 'qtde_vaga_ofertada',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        periodo = df_limpo['ano_mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'VG-02' WHERE ano_mes = {periodo}"))
        db.session.commit()
        df_limpo.to_sql(name='VG-02', con=db.engine, if_exists='append', index=False)

    print('VG-02 carregado')

def processa_vg04(caminho, periodo=None):
    df = read_clean_csv(caminho, 'Nome_Mes_')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Nome_Tipo_Agenda_': 'tipo_agenda',
        'Nome_Tipo_Atendimento_Agenda': 'tipo_atendimento_agenda',
        'Nome_Procedimento_': 'nome_procedimento',
        'Nome_Especialidade_': 'nome_especialidade',
        'Código_CNES1': 'cnes',
        'H1___Nome_Estabelecimento_': 'estabelecimento',
        'Nome_Entidade_Completo_': 'entidade',
        'Qtde_Vaga_Ofertada_': 'qtde_vaga_ofertada',
        'Qtde_Agendamento_': 'qtde_agendamento',
        'Qtde_Atendimento_': 'qtde_atendimento',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    with app.app_context():
        periodo = df_limpo['ano_mes'].iloc[0]
        db.session.execute(text(f"DELETE FROM 'VG-04' WHERE ano_mes = {periodo}"))
        db.session.commit()
        df_limpo.to_sql(name='VG-04', con=db.engine, if_exists='append', index=False)

    print('VG-04 carregado')

def processa_cg01(caminho, periodo=None):
    df = read_clean_csv(caminho, 'nm_municipio3')

    traduz_col = {
        'nm_estabelecimento3': 'estabelecimento',
        'cd_cnes3': 'cnes',
        'qtde_gestantes3': 'qtde_gestantes',
        'qtde_atendimentos_maior_igual_9': 'atendimentos_maior_igual_9',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()
    
    if periodo:
        df_limpo['ano_mes_extracao'] = periodo

    with app.app_context():
        if periodo:
            db.session.execute(text(f"DELETE FROM 'CG-01' WHERE ano_mes_extracao = {periodo}"))
        else:
            db.session.execute(text("DELETE FROM 'CG-01'"))
        db.session.commit()
        df_limpo.to_sql(name='CG-01', con=db.engine, if_exists='append', index=False)

    print('CG-01 carregado')

def processa_cg05(caminho, periodo=None):
    df = read_clean_csv(caminho, 'nm_coordenadoria_regional')

    traduz_col = {
        'cd_cnes': 'cnes',
        'nm_estabelecimento': 'estabelecimento',
        'cd_cpf': 'cpf',
        'cd_cns': 'cns',
        'nm_pessoa': 'pessoa',
        'cd_sisprenatal': 'sisprenatal',
        'data_acolhimento': 'data_acolhimento',
        'data_ultima_menstruacao': 'data_ultima_menstruacao',
        'data_previsao_parto': 'data_previsao_parto',
        'dias_acolhimento_dum': 'dias_acolhimento_dum',
        'nr_semana_decorrido_ingresso': 'nr_semana_decorrido_ingresso',
        'qtde_consultas': 'qtde_consultas',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    if periodo:
        df_limpo['ano_mes_extracao'] = periodo

    with app.app_context():
        if periodo:
            db.session.execute(text(f"DELETE FROM 'CG-05' WHERE ano_mes_extracao = {periodo}"))
        else:
            db.session.execute(text("DELETE FROM 'CG-05'"))
        db.session.commit()
        df_limpo.to_sql(name='CG-05', con=db.engine, if_exists='append', index=False)

    print('CG-05 carregado')

def processa_cg06(caminho, periodo=None):
    df = read_clean_csv(caminho, 'nm_coordenadoria_regional')

    traduz_col = {
        'cd_cnes': 'cnes',
        'nm_estabelecimento': 'estabelecimento',
        'nm_pessoa': 'pessoa',
        'cd_sisprenatal': 'sisprenatal',
        'data_acolhimento': 'data_acolhimento',
        'DUM': 'dum',
        'data_previsao_parto': 'data_previsao_parto',
        'dias_acolhimento_dum': 'dias_acolhimento_dum',
        'nr_semana_decorrido_ingresso': 'nr_semana_decorrido_ingresso',
        'Glicemia': 'glicemia',
        'HIV': 'hiv',
        'HbsAg': 'hbsag',
        'Urina': 'urina',
        'Pesquisa_Strepto_B': 'pesquisa_strepto_b',
        'VDRL': 'vdrl',
        'TOTG_75g': 'totg_75g',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    if periodo:
        df_limpo['ano_mes_extracao'] = periodo

    with app.app_context():
        if periodo:
            db.session.execute(text(f"DELETE FROM 'CG-06' WHERE ano_mes_extracao = {periodo}"))
        else:
            db.session.execute(text("DELETE FROM 'CG-06'"))
        db.session.commit()
        df_limpo.to_sql(name='CG-06', con=db.engine, if_exists='append', index=False)

    print('CG-06 carregado')

def processa_gac02(caminho, periodo=None):
    df = read_clean_csv(caminho, 'municipio')

    traduz_col = {
        'cnes': 'cnes',
        'estabelecimento': 'estabelecimento',
        'cns': 'cns',
        'nome': 'nome',
        'dc_raca': 'dc_raca',
        'qtde_consultas': 'qtde_consultas',
    }

    df = df.rename(columns=traduz_col)
    # df = df.dropna(subset=['cnes']) # <- Descomente se quiser forçar remoção de lixo

    col = list(traduz_col.values())
    df_limpo = df[col].copy()

    hoje = datetime.today().strftime('%Y-%m-%d')
    mes_atual = datetime.today().strftime('%Y-%m')
    df_limpo['data_extracao'] = hoje

    with app.app_context():
        # Deleta do mesmo mês até o dia de hoje
        db.session.execute(text(f"DELETE FROM 'GAC-02' WHERE data_extracao LIKE '{mes_atual}-%' AND data_extracao <= '{hoje}'"))
        db.session.commit()
        df_limpo.to_sql(name='GAC-02', con=db.engine, if_exists='append', index=False)

    print('GAC-02 carregado')

def processa_rel114(caminho, periodo=None):
    df = pd.read_csv(caminho, sep=';', encoding='latin1', low_memory=False)
        
    traduz_col = {
        'CNES_ESTAB_ACOLHIMENTO': 'cnes_estab_acolhimento',
        'ESTAB_ACOLHIMENTO': 'estab_acolhimento',
        'CNS_PACIENTE': 'cns_paciente',
        'CPF_PACIENTE': 'cpf_paciente',
        'NR_SISPRENATAL': 'nr_sisprenatal',
        'NOME_PACIENTE': 'nome_paciente',
        'RACA': 'raca',
        'DATA_ACOLHIMENTO': 'data_acolhimento',
        'DATA_PREVISAO_PARTO': 'previsao_parto',
        'TOTAL_ATED_SAUDE_BUCAL': 'total_ated_saude_bucal',
        'CNES_ULT_ATEND_SAUDE_BUCAL': 'cnes_ult_atend_saude_bucal',
        'ESTAB_ULT_ATEND_SAUDE_BUCAL': 'estab_ult_atend_saude_bucal',
        'CNS_PROF': 'cns_prof',
        'NOME_PROF_SAUDE_BUCAL': 'profissional',
        'COD_CBO_PROF_SAUDE_BUCAL': 'cod_cbo',
        'CBO_PROF_SAUDE_BUCAL': 'cbo',
        'DATA_ULTIMO_ATENDIMENTO': 'data_ultimo_atendimento'
    }

    df = df.rename(columns=traduz_col)
    colunas_presentes = [col for col in traduz_col.values() if col in df.columns]
    df_limpo = df[colunas_presentes].copy()

    from datetime import timedelta
    # Calcula ano e mês do mês passado
    primeiro_dia = datetime.today().replace(day=1)
    mes_passado_obj = primeiro_dia - timedelta(days=1)
    ano_alvo = mes_passado_obj.strftime('%Y')
    mes_alvo = mes_passado_obj.strftime('%m')

    with app.app_context():
        try:
            # Remove apenas as linhas onde a previsão de parto seja do mês alvo
            db.session.execute(text(f"DELETE FROM 'REL-114' WHERE previsao_parto LIKE '%/{mes_alvo}/{ano_alvo}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        # Filtra o dataframe para subir estritamente as previsões de parto do mês alvo
        df_limpo = df_limpo[df_limpo['previsao_parto'].str.endswith(f"/{mes_alvo}/{ano_alvo}", na=False)]
        
        df_limpo.to_sql(name='REL-114', con=db.engine, if_exists='append', index=False)
    print('REL-114 carregado com sucesso!')

def processa_rel134(caminho, periodo=None):
    df = pd.read_csv(caminho, sep=';', encoding='latin1', low_memory=False)
        
    # Filtrado para manter apenas colunas essenciais para o Relatório 17 e histórico base, reduzindo o peso do BD
    traduz_col = {
        'nome_unidade': 'nome_unidade',
        'inep': 'inep',
        'nome_instituicao': 'nome_instituicao',
        'num_participantes': 'num_participantes',
        'temas_para_saude': 'temas_para_saude',
        'ano': 'ano',
        'mes': 'mes',
        'data_atividade': 'data_atividade'
    }

    df = df.rename(columns=traduz_col)
    colunas_presentes = [col for col in traduz_col.values() if col in df.columns]
    df_limpo = df[colunas_presentes].copy()

    hoje = datetime.today().strftime('%Y-%m-%d')
    mes_atual = datetime.today().strftime('%Y-%m')
    df_limpo['data_extracao'] = hoje

    with app.app_context():
        try:
            db.session.execute(text(f"DELETE FROM 'REL-134' WHERE data_extracao LIKE '{mes_atual}-%' AND data_extracao <= '{hoje}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        df_limpo.to_sql(name='REL-134', con=db.engine, if_exists='append', index=False)
    print('REL-134 carregado com sucesso!')

def processa_rel135(caminho, periodo=None):
    df = pd.read_csv(caminho, sep=';', encoding='latin1', low_memory=False)
        
    traduz_col = {
        'unidade': 'unidade', 
        'cnes': 'cnes',
        'cod_ine': 'cod_ine',
        'data_cadastro': 'data_cadastro',
        'nome_cidadao': 'nome_cidadao'
    }

    df = df.rename(columns=traduz_col)
    colunas_presentes = [col for col in traduz_col.values() if col in df.columns]
    df_limpo = df[colunas_presentes].copy()

    # 1. Filtra COD_INE removendo nulos e '-'
    df_limpo = df_limpo[df_limpo['cod_ine'].notna()]
    df_limpo['cod_ine'] = df_limpo['cod_ine'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.lstrip('0')
    df_limpo = df_limpo[df_limpo['cod_ine'] != '-']
    df_limpo = df_limpo[df_limpo['cod_ine'] != '']

    from datetime import datetime, timedelta
    
    # Descobre o mês passado
    hoje_obj = datetime.today()
    primeiro_dia_mes_atual = hoje_obj.replace(day=1)
    ultimo_dia_mes_passado = primeiro_dia_mes_atual - timedelta(days=1)
    
    ano_alvo = ultimo_dia_mes_passado.strftime('%Y')
    mes_alvo = ultimo_dia_mes_passado.strftime('%m')
    ano_mes_competencia = f"{ano_alvo}{mes_alvo}"
    
    # 2. Filtra DATA_CADASTRO (Remove dias após o fim da competência)
    # Primeiro transforma a coluna em data real (ignorando erros caso tenha sujeira)
    df_limpo['data_cadastro_dt'] = pd.to_datetime(df_limpo['data_cadastro'], format='%d/%m/%Y', errors='coerce')
    
    # Filtra mantendo apenas as datas menores ou iguais ao último dia do mês passado
    df_limpo = df_limpo[df_limpo['data_cadastro_dt'] <= ultimo_dia_mes_passado]
    
    # 3. Agrupa por UNIDADE, CNES e COD_INE, fazendo a contagem do NOME_CIDADAO
    df_resumo = df_limpo.groupby(['unidade', 'cnes', 'cod_ine']).agg(
        total_cadastros=('nome_cidadao', 'count')
    ).reset_index()
    
    # Adiciona a coluna do período
    df_resumo['ano_mes_competencia'] = ano_mes_competencia

    with app.app_context():
        try:
            # Deleta caso já tenha rodado a extração deste mesmo mês antes
            db.session.execute(text(f"DELETE FROM 'REL-135' WHERE ano_mes_competencia = '{ano_mes_competencia}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        df_resumo.to_sql(name='REL-135', con=db.engine, if_exists='append', index=False)
    print('REL-135 carregado e agrupado com sucesso!')
