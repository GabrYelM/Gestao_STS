import pandas as pd
import numpy as np
from database import db
from app import app

def gera_relatorio_03(periodo):
    with app.app_context():

        query = f"SELECT * FROM 'AT-02' WHERE ano_mes = {periodo}"
        df_at02 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_at02,
            columns = 'ano_mes',
            index = ['estabelecimento', 'nome_cbo', 'profissional', 'procedimento'],
            values = 'quantidade_procedimento',
            aggfunc='sum'
        )
        #print(df_final)
        return df_final

def gera_relatorio_04(periodo):
    with app.app_context():
    
        query = f"SELECT * FROM 'VG-04' WHERE ano_mes = {periodo}"
        df_vg04 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_vg04,
            index = ['tipo_agenda', 'estabelecimento', 'nome_especialidade', 'nome_procedimento', 'tipo_atendimento_agenda'],
            values = ['qtde_vaga_ofertada', 'qtde_agendamento', 'qtde_atendimento'],
            aggfunc = 'sum'
        )
        #print(df_final)
        return df_final

def gera_relatorio_08(periodo):
    # precisa do gac02, cg01, cg05, cg06
    with app.app_context():

        ano = int(periodo[:4])
        mes = int(periodo[4:])

        query_gac02 = f"""SELECT * FROM 'GAC-02'
        WHERE estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """
        query_cg01 = f"""SELECT * FROM 'CG-01'
        WHERE estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """
        query_cg05 = f"""SELECT * FROM 'CG-05'
        WHERE estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        AND dias_acolhimento_dum BETWEEN 0 AND 120
        """
        query_cg05_quant = f"""SELECT * FROM 'CG-05'
        WHERE estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """
        query_cg06 = f"""SELECT * FROM 'CG-06'
        WHERE estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """

        df_gac02 = pd.read_sql(query_gac02, con=db.engine)
        df_gac02['cnes'] = df_gac02['cnes'].astype(str).str.replace('.', '')

        df_cg01 = pd.read_sql(query_cg01, con=db.engine)
        df_cg01['cnes'] = df_cg01['cnes'].astype(str).str.replace('.', '')

        df_cg05 = pd.read_sql(query_cg05, con=db.engine)
        df_cg05['cnes'] = df_cg05['cnes'].astype(str).str.replace('.', '')

        df_cg05_quant = pd.read_sql(query_cg05_quant, con=db.engine)
        df_cg05_quant['cnes'] = df_cg05_quant['cnes'].astype(str).str.replace('.', '')

        df_cg06 = pd.read_sql(query_cg06, con=db.engine)
        df_cg06['cnes'] = df_cg06['cnes'].astype(str).str.replace('.', '')
        colunas_exames = ['glicemia', 'hiv', 'hbsag', 'urina', 'vdrl']
        for col in colunas_exames:
            df_cg06[col] = pd.to_numeric(df_cg06[col], errors='coerce')
        df_cg06[colunas_exames] = df_cg06[colunas_exames].fillna(0)
        df_cg06 = df_cg06[
            (df_cg06['glicemia'] >= 2) &
            (df_cg06['hiv'] >= 3) &
            (df_cg06['hbsag'] >= 1) &
            (df_cg06['urina'] >= 2) &
            (df_cg06['vdrl'] >= 3)
        ]

        df_base = df_gac02[['estabelecimento', 'cnes']].drop_duplicates()

        gestantes_ativas = pd.pivot_table(
            df_gac02,
            index = ['estabelecimento', 'cnes'],
            values = 'qtde_consultas',
            aggfunc = 'count'
        ).reset_index()
        #print(gestantes_ativas)


        df_cg05_quant['data_previsao_parto'] = pd.to_datetime(df_cg05_quant['data_previsao_parto'], format='%d/%m/%Y', errors='coerce')
        df_cg05_quant = df_cg05_quant[
            (df_cg05_quant['data_previsao_parto'].dt.year == ano) & 
            (df_cg05_quant['data_previsao_parto'].dt.month == mes)
        ]
        gestantes_data_parto = pd.pivot_table(
            df_cg05_quant,
            index = ['estabelecimento', 'cnes'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        #print(gestantes_data_parto)

        df_cg01['atendimentos_maior_igual_9'] = pd.to_numeric(df_cg01['atendimentos_maior_igual_9'], errors='coerce')
        df_cg01['atendimentos_maior_igual_9'] = df_cg01['atendimentos_maior_igual_9'].fillna(0)
        consultas_maior = pd.pivot_table(
            df_cg01,
            index = ['estabelecimento', 'cnes'],
            values = 'atendimentos_maior_igual_9',
            aggfunc = 'sum'
        ).reset_index()
        #print(consultas_maior)

        dias_120 = pd.pivot_table(
            df_cg05,
            index = ['estabelecimento', 'cnes'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        #print(dias_120)

        exames = pd.pivot_table(
            df_cg06,
            index = ['estabelecimento', 'cnes'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        #print(exames)

        df_final = pd.merge(df_base, gestantes_ativas, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, gestantes_data_parto, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, consultas_maior, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, dias_120, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, exames, on=['cnes', 'estabelecimento'], how='left')

        df_final.columns = [
            'cnes', 
            'estabelecimento', 
            'gestantes_ativas',           # Veio do GAC02 (qtde_consultas)
            'gestantes_data_parto',       # Veio do CG05_quant (pessoa_x)
            'consultas_maior_igual_7',    # Veio do CG01 (qtde_gestantes)
            'captacao_ate_120_dias',      # Veio do CG05 normal (pessoa_y)
            'exames_realizados'           # Veio do CG06 (pessoa)
        ]
        df_final = df_final.fillna(0)

        df_final['%_consultas_7'] = (df_final['consultas_maior_igual_7'] / df_final['gestantes_data_parto']) * 100
        df_final['%_captacao_120'] = (df_final['captacao_ate_120_dias'] / df_final['gestantes_data_parto']) * 100
        df_final['%_exames'] = (df_final['exames_realizados'] / df_final['gestantes_data_parto']) * 100
        df_final = df_final.replace([np.inf, -np.inf, np.nan], 0)
        df_final = df_final.round(2)

        #print(df_final)
        return df_final

def gera_relatorio_10(periodo):

    mapa_mes = {
        '01': 'Janeiro',   '1': 'Janeiro',
        '02': 'Fevereiro', '2': 'Fevereiro',
        '03': 'Março',     '3': 'Março',
        '04': 'Abril',     '4': 'Abril',
        '05': 'Maio',      '5': 'Maio',
        '06': 'Junho',     '6': 'Junho',
        '07': 'Julho',     '7': 'Julho',
        '08': 'Agosto',    '8': 'Agosto',
        '09': 'Setembro',  '9': 'Setembro',
        '10': 'Outubro',
        '11': 'Novembro',
        '12': 'Dezembro'
    }

    ano = periodo[:4]
    cd_mes = periodo[4:]
    mes = mapa_mes.get(cd_mes)

    with app.app_context():
    
        query = f"""
        SELECT * FROM 'AT-03' 
        WHERE ano = {ano} AND mes = '{mes}'
        AND sts = 'SUDESTE - STS PENHA'
        AND estabelecimento NOT IN ('Sae Dst/Aids Penha')
        AND faixa_etaria IN ('20 a 24 anos', '25 a 29 anos', '30 a 34 anos', '35 a 39 anos', '40 a 44 anos', '45 a 49 anos', '50 a 54 anos', '55 a 59 anos', '60 a 64 anos')
        """
        df_at03 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_at03,
            columns = 'estabelecimento',
            index = 'mes',
            values = 'quantidade_procedimento',
            aggfunc='sum'
        )
        #print(df_final)
        return df_final

def gera_relatorio_11(periodo):
    with app.app_context():
    
        query = f"""SELECT * FROM 'FE-02' 
        WHERE ano_mes = {periodo}
        AND sts = 'SUDESTE - STS PENHA'
        """
        df_fe02 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_fe02,
            index = ['cnes', 'estabelecimento', 'nome_especialidade', 'nome_procedimento'],
            values = ['saiu_da_espera', 'pacientes_ativos'],
            aggfunc='sum'
        )
        #print(df_final)
        return df_final

def gera_relatorio_13(periodo):
    with app.app_context():
    
        query = f"""SELECT * FROM 'VG-02' WHERE ano_mes = {periodo}"""
        df_vg02 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_vg02,
            columns = 'situacao_vaga',
            index = ['tipo_agenda', 'estabelecimento', 'nome_especialidade', 'procedimento', 'tipo_atendimento_agenda'],
            values = 'qtde_vaga_ofertada',
            aggfunc='sum'
        )
        #print(df_final)
        return df_final

def gera_relatorio_14(periodo):
    with app.app_context():
    
        query = f"""SELECT * FROM 'AG-04' WHERE ano_mes = {periodo}"""
        df_vg02 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_vg02,
            columns = 'situacao_agendamento',
            index = ['tipo_agenda', 'tipo_entidade', 'estabelecimento', 'especialidade', 'procedimento'],
            values = 'quantidade_agendamento',
            aggfunc='sum'
        )
        print(df_final)
        #return df_final