import pandas as pd
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
            aggfunc='sum'
            )
        #print(df_final)
        return df_final

def gera_relatorio_08(periodo):
    # precisa do gac02, cg01, cg05, cg06
    # with app.app_context():
    
    #     query = f"SELECT * FROM '' WHERE ano_mes = {periodo}"
    #     df_ = pd.read_sql(query, con=db.engine)

    #     df_final = pd.pivot_table(
    #         df_,
    #         index = ['', '', '', '', ''],
    #         values = ['', '', ''],
    #         aggfunc='sum'
    #         )
    #   print(df_final)
        return # df_final

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

    ano = int(periodo) // 100
    print(ano)
    cd_mes = int(periodo) - (ano*100)
    print(cd_mes)
    mes = mapa_mes.get(str(cd_mes))
    print(mes)

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