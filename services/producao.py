import pandas as pd
from database import db
from app import app

def gera_relatorio_03(periodo):
    with app.app_context():

        query = f"SELECT * FROM 'AT-02' WHERE ano_mes = {periodo}"
        df_at02 = pd.read_sql(query, con=db.engine)

        df_final = pd.pivot_table(
            df_at02,
            columns = ['estabelecimento','cbo', 'profissional', 'procedimento'],
            index = 'estabelecimento',
            values = 'quantidade_procedimento',
            aggfunc='sum'
            )
        print(df_final)
        #return df_final