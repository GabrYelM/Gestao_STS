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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    
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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
    df_limpo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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

    if periodo:
        ano_str = str(periodo)[:4]
        mes_str = str(periodo)[4:]
        data_referencia = f"{ano_str}-{mes_str}-01"
        mes_filtro = f"{ano_str}-{mes_str}"
    else:
        data_referencia = datetime.today().strftime('%Y-%m-%d')
        mes_filtro = datetime.today().strftime('%Y-%m')

    df_limpo['data_extracao'] = data_referencia

    with app.app_context():
        # Deleta do mesmo mês de competência antes de inserir
        db.session.execute(text(f"DELETE FROM 'GAC-02' WHERE data_extracao LIKE '{mes_filtro}-%'"))
        db.session.commit()
        df_limpo.to_sql(name='GAC-02', con=db.engine, if_exists='append', index=False)

    print(f'GAC-02 carregado para a competência {mes_filtro}')

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

def processa_rel16(caminho, periodo=None):
    df = pd.read_csv(caminho, sep=';', encoding='latin1', low_memory=False)
        
    traduz_col = {
        'STATUS_ATUAL': 'status_atual',
        'MOTIVO_ULTIMO_STATUS': 'motivo_ultimo_status',
        'DATA_ULTIMA_ATUALIZACAO': 'data_ultima_atualizacao',
        'CNS_PACIENTE': 'cns_paciente',
        'PRONTUARIO': 'prontuario',
        'NOME_PACIENTE': 'nome_paciente',
        'NASCIMENTO': 'nascimento',
        'SEXO': 'sexo',
        'IDADE': 'idade',
        'RACA': 'raca',
        'ANO_DIAGNOSTICO': 'ano_diagnostico',
        'DIABETES_MELLITUS': 'diabetes_mellitus',
        'TIPO_INSULINA': 'tipo_insulina',
        'AMG_NO_VEZES': 'amg_no_vezes',
        'DATA_INCLUSAO': 'data_inclusao',
        'CNES': 'cnes',
        'CMES': 'cmes',
        'ESTABELECIMENTO': 'estabelecimento',
        'COORDENADORIA': 'coordenadoria',
        'SUPERVISAO': 'supervisao',
        'OSS': 'oss'
    }

    df = df.rename(columns=traduz_col)
    colunas_presentes = [col for col in traduz_col.values() if col in df.columns]
    df_limpo = df[colunas_presentes].copy()

    hoje = datetime.today().strftime('%Y-%m-%d')
    mes_atual = datetime.today().strftime('%Y-%m')
    df_limpo['data_extracao'] = hoje

    with app.app_context():
        try:
            db.session.execute(text(f"DELETE FROM 'REL-16' WHERE data_extracao LIKE '{mes_atual}-%'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        df_limpo.to_sql(name='REL-16', con=db.engine, if_exists='append', index=False)
    print('REL-16 (SIGA - AMG) carregado com sucesso!')

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
    
    # Adiciona a coluna do período e data de extração
    df_resumo['ano_mes_competencia'] = ano_mes_competencia
    df_resumo['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    with app.app_context():
        try:
            # Deleta caso já tenha rodado a extração deste mesmo mês antes
            db.session.execute(text(f"DELETE FROM 'REL-135' WHERE ano_mes_competencia = '{ano_mes_competencia}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        df_resumo.to_sql(name='REL-135', con=db.engine, if_exists='append', index=False)
    print('REL-135 carregado e agrupado com sucesso!')

def processa_painel_monitoramento(html_content, tabela_db='REL-06', default_localidade='STS PENHA'):
    """
    Processa o HTML extraído do Painel de Monitoramento 3.2 (CEInfo).
    Suporta tabelas de unidade única (STS) e múltiplas unidades (Subprefeitura) identificadas pelas células cinzas (#d3d3d3).
    Funde os valores mensais com os sinais (+1, -1, 0, +2, -2, etc.) e a coluna de desempenho.
    Salva a matriz estruturada na tabela indicada ('REL-06' ou 'REL-07').
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = soup.find_all('table')
    if not tables:
        print("Nenhuma tabela encontrada no HTML do Painel de Monitoramento.")
        return False
        
    target_table = None
    for t in tables:
        texto_t = t.get_text()
        if 'Mês Ano' in texto_t or 'Sinais' in texto_t or 'Desempenho' in texto_t or 'Pref.Regional' in texto_t or 'STS' in texto_t:
            target_table = t
            break
    if not target_table:
        target_table = tables[-1]

    rows = target_table.find_all('tr')
    if len(rows) < 2:
        print("Tabela do Painel com linhas insuficientes.")
        return False

    # Mapeia dinamicamente a posição exata de cada coluna de mês (valores e sinais)
    mapa_colunas_mes = {}
    for r in rows:
        cells = r.find_all(['td', 'th'])
        if not cells:
            continue
        if cells[0].get_text(strip=True) == 'Mês Ano':
            for col_idx, c in enumerate(cells):
                txt = c.get_text(strip=True)
                if txt and txt not in ['Mês Ano', 'Sinais', 'Desempenho', 'Pref.Regional PENHA', 'Pref.Regional'] and col_idx not in mapa_colunas_mes:
                    mapa_colunas_mes[col_idx] = txt

    total_cols = max(len(r.find_all(['td', 'th'])) for r in rows if r.find_all(['td', 'th']))
    metade = total_cols // 2
    
    meses_valores = {}
    meses_sinais = {}
    for col_idx, mes in sorted(mapa_colunas_mes.items()):
        if col_idx < metade:
            meses_valores[mes] = col_idx
        else:
            meses_sinais[mes] = col_idx

    unidade_atual = default_localidade
    registros = []

    for r in rows:
        cells = r.find_all(['td', 'th'])
        if not cells:
            continue
            
        first_text = cells[0].get_text(strip=True)
        first_bg = (cells[0].get('bgcolor') or cells[0].get('style') or '').lower()
        
        # 1. Identifica cabeçalho de UNIDADE (célula cinza #d3d3d3)
        if '#d3d3d3' in first_bg or any(c in first_bg for c in ['#cccccc', '#e0e0e0', 'gray']):
            if first_text:
                unidade_atual = first_text
            continue
            
        desempenho = cells[-1].get_text(strip=True)
        
        # 2. Ignora linhas de cabeçalho residuais ou vazias
        if not first_text or first_text == 'Mês Ano' or desempenho == 'Desempenho' or any(x in first_text for x in ['Pref.Regional', 'Indicador', 'Local:', 'Série histórica']):
            continue
            
        if first_text in ['STS PENHA', 'PENHA', 'Pref.Regional PENHA', 'Subprefeitura PENHA', unidade_atual]:
            continue
            
        indicador = first_text
        
        for mes, col_val in meses_valores.items():
            col_sinal = meses_sinais.get(mes)
            
            val_text = cells[col_val].get_text(strip=True) if col_val < len(cells) else ""
            
            sinal_cell = cells[col_sinal] if (col_sinal and col_sinal < len(cells)) else None
            sinal_text = sinal_cell.get_text(strip=True) if sinal_cell else ""
            bg_color = (sinal_cell.get('bgcolor') or sinal_cell.get('style') or '').lower() if sinal_cell else ""
            
            # Reconhece sinais positivos (+1, +2, +3, verde) e negativos (-1, -2, -3, vermelho)
            if '+' in sinal_text or 'ccffcc' in bg_color or 'd1e7dd' in bg_color or 'd4edda' in bg_color:
                sinal_num = 1
            elif '-' in sinal_text or 'ff9999' in bg_color or 'f8d7da' in bg_color or 'f5c6cb' in bg_color:
                sinal_num = -1
            else:
                sinal_num = 0
                
            registros.append({
                'estabelecimento': unidade_atual,
                'indicador': indicador,
                'mes_ano': mes,
                'ordem_mes': col_val,
                'valor': val_text,
                'sinal': sinal_num,
                'desempenho': desempenho
            })

    if not registros:
        print(f"Nenhum registro extraído da tabela do Painel de Monitoramento ({tabela_db}).")
        return False

    df_resultado = pd.DataFrame(registros)
    df_resultado['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    with app.app_context():
        try:
            db.session.execute(text(f"DROP TABLE IF EXISTS '{tabela_db}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        df_resultado.to_sql(name=tabela_db, con=db.engine, if_exists='replace', index=False)
        print(f"{tabela_db} gravado com sucesso! Total de {len(df_resultado)} registros.")
        
    return True


def processa_bpa_dbf(caminho, periodo=None):
    """
    Processa arquivos .DBF do TabWin / BPAMAG (Relatório 02 - Produção por Unidades).
    Lê os campos:
      - PRD_UID: Código CNES da unidade
      - PRD_CMP: Competência (ex: '202608')
      - PRD_PA: Código do Procedimento
      - PRD_QT_P: Quantidade Produzida
    Relaciona com o catálogo de unidades e procedimentos e salva na tabela 'REL-02'.
    """
    import os
    import json
    from dbfread import DBF
    
    # Carrega catálogo
    catalogo_path = os.path.join(os.path.dirname(__file__), 'bpa_catalogo.json')
    unidades_map = {}
    procedimentos_map = {}
    if os.path.exists(catalogo_path):
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            cat_data = json.load(f)
            for u in cat_data.get('unidades', []):
                cnes_clean = str(u['cnes']).strip().zfill(7)
                unidades_map[cnes_clean] = u['coluna']
                unidades_map[str(int(cnes_clean))] = u['coluna']
            procedimentos_map = cat_data.get('procedimentos', {})

    table = DBF(caminho, encoding='latin1')
    df = pd.DataFrame(iter(table))
    
    if df.empty or 'PRD_UID' not in df.columns or 'PRD_PA' not in df.columns:
        print("Arquivo DBF inválido ou sem colunas essenciais.")
        return False

    # Normaliza campos
    df['cnes'] = df['PRD_UID'].astype(str).str.strip().str.replace('.0', '', regex=False).str.zfill(7)
    df['codigo_procedimento'] = df['PRD_PA'].astype(str).str.strip()
    df['quantidade_produzida'] = pd.to_numeric(df.get('PRD_QT_P', 0), errors='coerce').fillna(0)
    
    # 1. Identifica a competência alvo do arquivo (ex: STS26_07.dbf -> 202607)
    comp_alvo = None
    if periodo:
        comp_alvo = str(periodo).strip()
    else:
        import re
        nome_arq = os.path.basename(caminho)
        m = re.search(r'(?:STS|PRD)?(\d{2})_(\d{2})', nome_arq, re.IGNORECASE)
        if m:
            comp_alvo = f"20{m.group(1)}{m.group(2)}"
        else:
            m4 = re.search(r'(20\d{2})(\d{2})', nome_arq)
            if m4:
                comp_alvo = f"{m4.group(1)}{m4.group(2)}"

    # 2. Filtra estritamente a competência alvo (reproduz o filtro do TabWin 'Seleções ativas: Competência')
    # Isso evita que resíduos retroativos de meses anteriores (ex: 06 e 05 dentro do arquivo de 07) contaminem outros meses
    if 'PRD_CMP' in df.columns and df['PRD_CMP'].notna().any():
        df['PRD_CMP'] = df['PRD_CMP'].astype(str).str.strip()
        if comp_alvo:
            df = df[df['PRD_CMP'] == comp_alvo]
            df['ano_mes'] = comp_alvo
        else:
            comp_majoritaria = df['PRD_CMP'].value_counts().index[0]
            df = df[df['PRD_CMP'] == comp_majoritaria]
            df['ano_mes'] = comp_majoritaria
    elif comp_alvo:
        df['ano_mes'] = comp_alvo
    else:
        df['ano_mes'] = datetime.today().strftime('%Y%m')

    if df.empty:
        print(f"Nenhum registro encontrado no DBF para a competência {comp_alvo}.")
        return False

    # Resolve nome da unidade
    df['unidade'] = df['cnes'].map(unidades_map).fillna(df['PRD_UID'].astype(str))
    
    # Resolve nome do procedimento
    def resolver_nome_proc(cod):
        cod_str = str(cod).strip()
        if cod_str in procedimentos_map:
            return procedimentos_map[cod_str]
        cod_10d = cod_str.zfill(10)
        if cod_10d in procedimentos_map:
            return procedimentos_map[cod_10d]
        if len(cod_str) == 10:
            cod_8d = cod_str[1:9]
            if cod_8d in procedimentos_map:
                return procedimentos_map[cod_8d]
        cod_strip = cod_str.lstrip('0')
        if cod_strip in procedimentos_map:
            return procedimentos_map[cod_strip]
        return f"Procedimento {cod_str}"

    df['procedimento'] = df['codigo_procedimento'].apply(resolver_nome_proc)

    # Agrupa por competência, cnes, unidade, codigo_procedimento e procedimento
    df_agrupado = df.groupby(['ano_mes', 'cnes', 'unidade', 'codigo_procedimento', 'procedimento'], as_index=False)['quantidade_produzida'].sum()
    
    df_agrupado['data_extracao'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    with app.app_context():
        # Deleta registros anteriores da mesma competência para evitar duplicidade
        competencias = df_agrupado['ano_mes'].unique()
        for comp in competencias:
            try:
                db.session.execute(text(f"DELETE FROM 'REL-02' WHERE ano_mes = '{comp}'"))
                db.session.commit()
            except Exception:
                db.session.rollback()

        df_agrupado.to_sql(name='REL-02', con=db.engine, if_exists='append', index=False)
        print(f"REL-02 gravado com sucesso! {len(df_agrupado)} registros para competências {list(competencias)}.")

    return True


def processa_raas_arquivo(caminho, periodo=None):
    """
    Processa arquivos de exportação do RAAS (Registro das Ações Ambulatoriais de Saúde) das unidades CAPS.
    Lê as linhas:
      - Tipo 15 (Folha RAAS / Pacientes): Contagem de pacientes por CAPS e competência.
      - Tipo 16 (Ações Realizadas): Produção por Estabelecimento, CBO, CNS/Profissional e Procedimento SIGTAP.
    Grava nas tabelas SQLite:
      - 'RAAS_PACIENTES'
      - 'RAAS_ACOES_PROF'
      - 'RAAS_ACOES'
    """
    import os
    import json
    
    catalogo_path = os.path.join(os.path.dirname(__file__), 'raas_catalogo.json')
    cbos_map = {}
    proced_map = {}
    profs_map = {}
    estab_map = {
        '2029626': 'CAPS ADULTO III VILA MATILDE',
        '3304566': 'CAPS AD III PENHA',
        '6387640': 'CAPS INFANTOJUVENIL II PENHA',
        '9688463': 'CAPS AD II CANGAIBA'
    }
    
    if os.path.exists(catalogo_path):
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            cat = json.load(f)
            cbos_map = cat.get('cbos', {})
            proced_map = cat.get('procedimentos', {})
            profs_map = cat.get('profissionais', {})
            estab_map.update(cat.get('estabelecimentos', {}))

    linhas_15 = []
    linhas_16 = []

    with open(caminho, 'r', encoding='latin1', errors='ignore') as f:
        for linha in f:
            tipo = linha[:2]
            if tipo == '15':
                cmp = linha[4:10].strip()
                cnes = linha[10:17].strip()
                cns_pac = linha[17:32].strip()
                nome_pac = linha[50:80].strip()
                if cmp and cnes:
                    linhas_15.append({
                        'competencia': cmp,
                        'cnes': cnes,
                        'cns_paciente': cns_pac,
                        'nome_paciente': nome_pac
                    })
            elif tipo == '16':
                cmp = linha[4:10].strip()
                cnes = linha[10:17].strip()
                cns_pac = linha[17:32].strip()
                cod_acao = linha[40:50].strip()
                cod_cbo = linha[50:56].strip()
                cns_prof = linha[56:71].strip()
                dt_exec = linha[71:79].strip()
                qtde_str = linha[85:91].strip()
                try:
                    qtde = int(qtde_str)
                except Exception:
                    qtde = 1
                if cmp and cnes and cod_acao:
                    linhas_16.append({
                        'competencia': cmp,
                        'cnes': cnes,
                        'cns_paciente': cns_pac,
                        'cod_acao': cod_acao,
                        'cod_cbo': cod_cbo,
                        'cns_prof': cns_prof,
                        'dt_exec': dt_exec,
                        'qtde': qtde
                    })

    if not linhas_15 and not linhas_16:
        print(f"Nenhum registro RAAS (tipo 15 ou 16) encontrado no arquivo {caminho}.")
        return False

    hoje_ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    with app.app_context():
        # 1. Processa Pacientes (Linhas 15)
        if linhas_15:
            df15 = pd.DataFrame(linhas_15)
            # Agrupa quantidade de pacientes por competência e cnes
            df_pac = df15.groupby(['competencia', 'cnes'], as_index=False)['nome_paciente'].count()
            df_pac.rename(columns={'competencia': 'ano_mes', 'nome_paciente': 'qt_pacientes'}, inplace=True)
            df_pac['estabelecimento'] = df_pac['cnes'].map(estab_map).fillna(df_pac['cnes'].apply(lambda x: f"CAPS CNES {x}"))
            df_pac['data_extracao'] = hoje_ts

            for _, r in df_pac.iterrows():
                comp = r['ano_mes']
                cnes_val = r['cnes']
                try:
                    db.session.execute(text(f"DELETE FROM 'RAAS_PACIENTES' WHERE ano_mes = '{comp}' AND cnes = '{cnes_val}'"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            df_pac.to_sql(name='RAAS_PACIENTES', con=db.engine, if_exists='append', index=False)
            print(f"RAAS_PACIENTES gravado: {len(df_pac)} registros.")

        # 2. Processa Ações por Profissional (Linhas 16)
        if linhas_16:
            df16 = pd.DataFrame(linhas_16)
            df16['estabelecimento'] = df16['cnes'].map(estab_map).fillna(df16['cnes'].apply(lambda x: f"CAPS CNES {x}"))
            df16['descr_cbo'] = df16['cod_cbo'].map(cbos_map).fillna(df16['cod_cbo'])
            df16['procedimento'] = df16['cod_acao'].map(proced_map).fillna(df16['cod_acao'])
            df16['nome_prof'] = df16['cns_prof'].map(profs_map).fillna(df16['cns_prof'])

            # Agrupa produção por profissional
            df_prof = df16.groupby(
                ['competencia', 'cnes', 'estabelecimento', 'cod_cbo', 'descr_cbo', 'cns_prof', 'nome_prof', 'cod_acao', 'procedimento'],
                as_index=False
            )['qtde'].sum()
            df_prof.rename(columns={'competencia': 'ano_mes', 'cod_cbo': 'co_cbo', 'qtde': 'quantidade'}, inplace=True)
            df_prof['data_extracao'] = hoje_ts

            # Agrupa consolidado de ações por CBO
            df_acoes = df16.groupby(
                ['competencia', 'cnes', 'estabelecimento', 'cod_cbo', 'descr_cbo', 'cod_acao', 'procedimento'],
                as_index=False
            )['qtde'].sum()
            df_acoes.rename(columns={'competencia': 'ano_mes', 'cod_cbo': 'co_cbo', 'qtde': 'quantidade'}, inplace=True)
            df_acoes['data_extracao'] = hoje_ts

            # Limpa e grava no banco por competência e unidade
            competencias = df_prof['ano_mes'].unique()
            cnes_list = df_prof['cnes'].unique()
            for comp in competencias:
                for cnes_val in cnes_list:
                    try:
                        db.session.execute(text(f"DELETE FROM 'RAAS_ACOES_PROF' WHERE ano_mes = '{comp}' AND cnes = '{cnes_val}'"))
                        db.session.execute(text(f"DELETE FROM 'RAAS_ACOES' WHERE ano_mes = '{comp}' AND cnes = '{cnes_val}'"))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            df_prof.to_sql(name='RAAS_ACOES_PROF', con=db.engine, if_exists='append', index=False)
            df_acoes.to_sql(name='RAAS_ACOES', con=db.engine, if_exists='append', index=False)
            print(f"RAAS_ACOES_PROF ({len(df_prof)} reg) e RAAS_ACOES ({len(df_acoes)} reg) gravados.")

    return True

