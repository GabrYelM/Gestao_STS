# transforma os arquivos em tabelas no db
import pandas as pd
from app import app
from database import db
import models

import io

def read_clean_csv(caminho, primeira_coluna):
    """
    Lê o arquivo nativamente, ignora todo o lixo do cabeçalho da prefeitura,
    e entrega para o pandas apenas a partir da linha onde as colunas reais começam.
    Isso evita qualquer erro de parsing de aspas duplas ou linhas em branco.
    """
    with open(caminho, 'r', encoding='utf-8-sig', errors='ignore') as f:
        linhas = f.readlines()
        
    inicio = 0
    for i, linha in enumerate(linhas):
        if primeira_coluna in linha:
            inicio = i
            break
            
    conteudo_limpo = ''.join(linhas[inicio:])
    return pd.read_csv(io.StringIO(conteudo_limpo), sep=';')

def processa_ag04(caminho):
    """
    Função ETL para AG-04
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes1')

    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Nome_Tipo_Agenda1': 'tipo_agenda',
        'H1___Nome_Nível_21': 'coordenadoria',
        'H1___Nome_Nível_31': 'supervisao',
        'H1___Nome_Estabelecimento1': 'estabelecimento',
        'Código_CNES': 'cnes',
        'Nome_Especialidade1': 'especialidade',
        'Nome_Tipo_Atendimento_Agenda1': 'tipo_atendimento',
        'Nome_Procedimento1': 'procedimento',
        'Nome_Situação_Agendamento1': 'situacao_agendamento',
        'Nome_Tipo_Entidade1': 'entidade',
        'Quantidade_Agendamento1': 'quantidade_agendamento'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = ['ano_mes', 'tipo_agenda', 'coordenadoria', 'supervisao', 'estabelecimento', 'cnes', 'especialidade', 'tipo_atendimento', 'procedimento', 'situacao_agendamento', 'entidade', 'quantidade_agendamento']
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='AG-04', con=db.engine, if_exists='append', index=False)

    print("AG-04 carregado")

def processa_at02(caminho):
    """
    Função ETL para AT-02
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes')
    
    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Código_CNES': 'cnes',
        'H1___Nome_Estabelecimento2': 'estabelecimento',
        'H1___Código_CMES': 'cmes',
        'H1___Nome_Nível_2': 'coordenadoria',
        'H1___Nome_Nível_3': 'supervisao',
        'Tipo_Estabelecimento': 'tipo_estabelecimento',
        'Código_CBO_no_SUS': 'cbo_no_sus',
        'Nome_CBO1': 'nome_cbo',
        'Nome_Especialidade2': 'especialidade',
        'Código_Procedimento': 'cod_procedimento',
        'Nome_Procedimento2': 'procedimento',
        'Nome_Profissional_Siga1': 'profissional',
        'Quantidade_Procedimento2': 'quantidade_procedimento',
        'Contagem_Paciente2': 'contagem_paciente'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = ['ano_mes', 'cnes', 'estabelecimento', 'cmes', 'coordenadoria', 'supervisao', 'tipo_estabelecimento', 'cbo_no_sus', 'nome_cbo', 'especialidade', 'cod_procedimento', 'procedimento', 'profissional', 'quantidade_procedimento', 'contagem_paciente']
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='AT-02', con=db.engine, if_exists='append', index=False)

    print("AT-02 carregado")

def processa_at03(caminho):
    """
    Função ETL para AT-03
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes')
        
    traduz_col = {
        'Número_Ano': 'ano', 
        'Nome_Mes': 'mes',
        'H1___Nome_Nível_3': 'coordenadoria', 
        'H1___Nome_Estabelecimento': 'estabelecimento',
        'Nome_Faixa_Etária': 'faixa_etaria',
        'Nome_CBO': 'nome_cbo',
        'Nome_Procedimento': 'procedimento',
        'Sexo': 'sexo',
        'Quantidade_Procedimento': 'quantidade_procedimento'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df['nome_cbo'] = df['nome_cbo'].fillna('SEM CBO')
    df['procedimento'] = df['procedimento'].fillna('SEM PROCEDIMENTO')

    col = ['ano', 'mes', 'coordenadoria', 'estabelecimento', 'faixa_etaria', 'nome_cbo', 'procedimento', 'sexo', 'quantidade_procedimento']
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='AT-03', con=db.engine, if_exists='append', index=False)

    print("AT-03 carregado")

def processa_cg01(caminho):
    """
    Função ETL para CG-01
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'nm_municipio3')
        
    traduz_col = {
        'nm_coordenadoria_regional3': 'coordenadoria',
        'nm_supervisao_tecnica3': 'supervisao',
        'cd_cnes3': 'cnes',
        'qtde_gestantes3': 'quantidade_gestante',
        'qtde_atendimentos_maior_igual_9': 'quantidade_atendimento_maior_igual'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = ['coordenadoria', 'supervisao', 'cnes', 'quantidade_gestante', 'quantidade_atendimento_maior_igual']
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='CG-01', con=db.engine, if_exists='append', index=False)

    print("CG-01 carregado")

def processa_cg05(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'nm_coordenadoria_regional')
        
    traduz_col = {
        'nm_coordenadoria_regional': 'coordenadoria',
        'nm_supervisao_tecnica': 'supervisao',
        'cd_cnes': 'cnes',
        'nm_estabelecimento': 'estabelecimento',
        'cd_cpf': 'cpf',
        'cd_cns': 'cns',
        'nm_pessoa': 'nome_pessoa',
        'cd_sisprenatal': 'sisprenatal',
        'data_acolhimento': 'data_acolhimento',
        'data_ultima_menstruacao': 'data_ultima_menstruacao',
        'data_previsao_parto': 'data_previsao_parto',
        'dias_acolhimento_dum': 'dias_acolhimento_dum',
        'nr_semana_decorrido_ingresso': 'semanas_decorridas_ingresso',
        'qtde_consultas': 'quantidade_consultas'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='CG-05', con=db.engine, if_exists='append', index=False)

    print("CG-05 carregado")

def processa_cg06(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'nm_coordenadoria_regional')
        
    traduz_col = {
        'nm_coordenadoria_regional': 'coordenadoria',
        'nm_supervisao_tecnica': 'supervisao',
        'cd_cnes': 'cnes',
        'nm_estabelecimento': 'estabelecimento',
        'nm_pessoa': 'nome_pessoa',
        'cd_sisprenatal': 'sisprenatal',
        'data_acolhimento': 'data_acolhimento',
        'DUM': 'dum',
        'data_previsao_parto': 'data_previsao_parto',
        'dias_acolhimento_dum': 'dias_acolhimento_dum',
        'nr_semana_decorrido_ingresso': 'semanas_decorridas_ingresso',
        'Glicemia': 'glicemia',
        'HIV': 'hiv',
        'HbsAg': 'hbsag',
        'Urina': 'urina',
        'Pesquisa_Strepto_B': 'strepto',
        'VDRL': 'vdrl',
        'TOTG_75g': 'totg_75g'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='CG-06', con=db.engine, if_exists='append', index=False)

    print("CG-06 carregado")

def processa_fe02(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes6')
        
    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'H1___Nome_Nível_2': 'coordenadoria',
        'H1___Nome_Nível_31': 'supervisao',
        'H1___Nome_Estabelecimento': 'estabelecimento',
        'Código_CNES': 'cnes',
        'Nome_Procedimento5': 'procedimento',
        'Nome_Especialidade1': 'especialidade',
        'Quantidade_de_Pacientes_que_Entraram_em_Espera_no_Mês6': 'qtd_entraram_espera',
        'Quantidade_de_Pacientes_que_Saíram_de_Espera_no_Mês6': 'qtd_sairam_espera',
        'Quantidade_Total_de_Pacientes_Ativos6': 'qtd_ativos'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='FE-02', con=db.engine, if_exists='append', index=False)

    print("FE-02 carregado")

def processa_gac02(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'municipio')
        
    traduz_col = {
        'coordenadoria_regional': 'coordenadoria',
        'supervisao_tecnica1': 'supervisao',
        'cnes': 'cnes',
        'estabelecimento': 'estabelecimento',
        'cns': 'cns',
        'nome': 'nome',
        'dc_raca': 'raca',
        'qtde_consultas': 'qtde_consultas'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='GAC-02', con=db.engine, if_exists='append', index=False)

    print("GAC-02 carregado")

def processa_vg02(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes')
        
    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Código_CNES': 'cnes',
        'H1___Nome_Estabelecimento1': 'estabelecimento',
        'Nome_Procedimento2': 'procedimento',
        'Nome_Especialidade2': 'especialidade',
        'Nome_Tipo_Agenda': 'tipo_agenda',
        'Nome_Tipo_Atendimento_Agenda2': 'tipo_atendimento',
        'Nome_Situação_Vaga2': 'situacao_vaga',
        'Qtde_Vaga_Ofertada2': 'qtde_vaga_ofertada'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='VG-02', con=db.engine, if_exists='append', index=False)

    print("VG-02 carregado")

def processa_vg04(caminho):
    """
    Função ETL para 
    """

    # 1. Extract
    df = read_clean_csv(caminho, 'Nome_Mes_')
        
    traduz_col = {
        'Número_Ano_Mes__AAAAMM_': 'ano_mes',
        'Nome_Tipo_Agenda_': 'tipo_agenda',
        'Nome_Tipo_Atendimento_Agenda': 'tipo_atendimento',
        'Nome_Procedimento_': 'procedimento',
        'Nome_Especialidade_': 'especialidade',
        'H1___Nome_Nível_2_': 'coordenadoria',
        'H1___Nome_Nível_3_': 'supervisao',
        'Código_CNES1': 'cnes',
        'H1___Nome_Estabelecimento_': 'estabelecimento',
        'Nome_Entidade_Completo_': 'entidade',
        'Qtde_Vaga_Ofertada_': 'qtde_vaga_ofertada',
        'Qtde_Agendamento_': 'qtde_agendamento',
        'Qtde_Atendimento_': 'qtde_atendimento'
    }

    # 2. Transform
    df = df.rename(columns=traduz_col)

    df = df.dropna(subset=['cnes'])

    col = list(traduz_col.values())
    df_limpo = df[col]

    # 3. Load
    with app.app_context():
        df_limpo.to_sql(name='VG-04', con=db.engine, if_exists='append', index=False)

    print("VG-04 carregado")