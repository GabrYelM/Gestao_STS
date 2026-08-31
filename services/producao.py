import pandas as pd
import numpy as np
from database import db
from app import app

def gera_relatorio_03(periodo):
    with app.app_context():
        ano = int(str(periodo)[:4])
        mes = int(str(periodo)[4:])
        ano_ant = ano - 1
        periodo_ant = f"{ano_ant}{mes:02d}"

        query = f"SELECT * FROM 'AT-02' WHERE ano_mes BETWEEN {periodo_ant} AND {periodo}"
        df_at02 = pd.read_sql(query, con=db.engine)
        
        if df_at02.empty:
            return None

        df_final = pd.pivot_table(
            df_at02,
            columns = 'ano_mes',
            index = ['estabelecimento', 'nome_cbo', 'profissional', 'procedimento'],
            values = 'quantidade_procedimento',
            aggfunc='sum'
        ).fillna(0).astype(int).astype(int)
        
        # Rotaciona o texto dos meses para a vertical
        df_final.columns = [f'<div class="vertical-text">{col}</div>' for col in df_final.columns]
        
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

def gera_relatorio_06(periodo=None):
    """
    Gera o Relatório 06 (Painel de Monitoramento 3.2 - CEInfo).
    Funde a série histórica dos últimos 12 meses com os sinais mensais coloridos (+1 verde, -1 vermelho)
    e inclui a coluna de Desempenho.
    """
    with app.app_context():
        try:
            df = pd.read_sql("SELECT * FROM 'REL-06' ORDER BY rowid ASC", con=db.engine)
        except Exception:
            return None
            
        if df is None or df.empty:
            return None
            
        # Filtra linhas de cabeçalho residuais
        df = df[~df['indicador'].isin(['STS PENHA', 'PENHA', 'Pref.Regional PENHA']) & (df['desempenho'] != 'Desempenho')].copy()
        if df.empty:
            return None

        # Formata o valor com classe HTML para preencher o fundo da célula perfeitamente
        def formata_celula(row):
            val = str(row['valor']).strip()
            sinal = row['sinal']
            if not val or val == 'nan':
                return ""
            if sinal == 1:
                return f'<div class="pm-cell pm-green">{val}</div>'
            elif sinal == -1:
                return f'<div class="pm-cell pm-red">{val}</div>'
            else:
                return f'<div class="pm-cell">{val}</div>'

        df['celula_formatada'] = df.apply(formata_celula, axis=1)
        
        # Pega a ordem cronológica correta e seleciona apenas os últimos 12 meses
        meses_ordenados = df.sort_values('ordem_mes')['mes_ano'].unique().tolist()
        ultimos_12_meses = meses_ordenados[-12:] if len(meses_ordenados) >= 12 else meses_ordenados
        
        # Filtra o DataFrame apenas para os últimos 12 meses
        df_filtrado = df[df['mes_ano'].isin(ultimos_12_meses)].copy()
        
        # Formata os nomes das colunas como no padrão (ex: 'jul/25')
        def formata_nome_mes(m):
            partes = str(m).strip().split()
            if len(partes) == 2:
                return f"{partes[0].lower()}/{partes[1]}"
            return str(m).lower().replace(' ', '/')
            
        df_filtrado['mes_col'] = df_filtrado['mes_ano'].apply(formata_nome_mes)
        cols_ordenadas = [formata_nome_mes(m) for m in ultimos_12_meses]
        
        # Cria pivot com o indicador na linha e os 12 meses nas colunas
        df_pivot = df_filtrado.pivot(index='indicador', columns='mes_col', values='celula_formatada')
        df_pivot = df_pivot[[c for c in cols_ordenadas if c in df_pivot.columns]]
        
        # Adiciona a coluna de Desempenho
        df_desempenho = df[['indicador', 'desempenho']].drop_duplicates(subset=['indicador']).set_index('indicador')
        
        def formata_desempenho(val):
            val_str = str(val).strip()
            if not val_str or val_str == 'nan':
                return ""
            if 'Alerta' in val_str or 'abaixo' in val_str or 'Atenção' in val_str:
                return f'<div class="pm-cell pm-red fw-semibold">{val_str}</div>'
            elif 'Bom' in val_str or 'acima' in val_str:
                return f'<div class="pm-cell pm-green fw-semibold">{val_str}</div>'
            else:
                return f'<div class="pm-cell">{val_str}</div>'
                
        df_desempenho['Desempenho'] = df_desempenho['desempenho'].apply(formata_desempenho)
        
        df_final = df_pivot.join(df_desempenho['Desempenho'], how='left')
        df_final = df_final.reset_index()
        df_final = df_final.rename(columns={'indicador': 'Indicadores'})
        
        return df_final

def gera_relatorio_07(periodo=None):
    """
    Gera o Relatório 07 (Painel de Monitoramento por Subprefeitura - CEInfo).
    Funde a série histórica dos últimos 12 meses com os sinais mensais coloridos (+1 verde, -1 vermelho)
    e inclui a coluna de Desempenho.
    """
    with app.app_context():
        try:
            df = pd.read_sql("SELECT * FROM 'REL-07' ORDER BY rowid ASC", con=db.engine)
        except Exception:
            return None
            
        if df is None or df.empty:
            return None
            
        # Filtra linhas de cabeçalho residuais
        df = df[~df['indicador'].isin(['STS PENHA', 'PENHA', 'Pref.Regional PENHA', 'Subprefeitura PENHA']) & (df['desempenho'] != 'Desempenho')].copy()
        if df.empty:
            return None

        # Formata o valor com classe HTML para preencher o fundo da célula perfeitamente
        def formata_celula(row):
            val = str(row['valor']).strip()
            sinal = row['sinal']
            if not val or val == 'nan':
                return ""
            if sinal == 1:
                return f'<div class="pm-cell pm-green">{val}</div>'
            elif sinal == -1:
                return f'<div class="pm-cell pm-red">{val}</div>'
            else:
                return f'<div class="pm-cell">{val}</div>'

        df['celula_formatada'] = df.apply(formata_celula, axis=1)
        
        # Pega a ordem cronológica correta e seleciona apenas os últimos 12 meses
        meses_ordenados = df.sort_values('ordem_mes')['mes_ano'].unique().tolist()
        ultimos_12_meses = meses_ordenados[-12:] if len(meses_ordenados) >= 12 else meses_ordenados
        
        # Filtra o DataFrame apenas para os últimos 12 meses
        df_filtrado = df[df['mes_ano'].isin(ultimos_12_meses)].copy()
        
        # Formata os nomes das colunas como no padrão (ex: 'jul/25')
        def formata_nome_mes(m):
            partes = str(m).strip().split()
            if len(partes) == 2:
                return f"{partes[0].lower()}/{partes[1]}"
            return str(m).lower().replace(' ', '/')
            
        df_filtrado['mes_col'] = df_filtrado['mes_ano'].apply(formata_nome_mes)
        cols_ordenadas = [formata_nome_mes(m) for m in ultimos_12_meses]
        
        # Cria pivot com Estabelecimento e Indicador nas linhas e os 12 meses nas colunas
        df_pivot = df_filtrado.pivot_table(
            index=['estabelecimento', 'indicador'],
            columns='mes_col',
            values='celula_formatada',
            aggfunc='first'
        )
        df_pivot = df_pivot[[c for c in cols_ordenadas if c in df_pivot.columns]]
        
        # Adiciona a coluna de Desempenho
        df_desempenho = df[['estabelecimento', 'indicador', 'desempenho']].drop_duplicates(subset=['estabelecimento', 'indicador']).set_index(['estabelecimento', 'indicador'])
        
        def formata_desempenho(val):
            val_str = str(val).strip()
            if not val_str or val_str == 'nan':
                return ""
            if 'Alerta' in val_str or 'abaixo' in val_str or 'Atenção' in val_str:
                return f'<div class="pm-cell pm-red fw-semibold">{val_str}</div>'
            elif 'Bom' in val_str or 'acima' in val_str or 'Excelente' in val_str or 'Melhoria' in val_str:
                return f'<div class="pm-cell pm-green fw-semibold">{val_str}</div>'
            else:
                return f'<div class="pm-cell">{val_str}</div>'
                
        df_desempenho['Desempenho'] = df_desempenho['desempenho'].apply(formata_desempenho)
        
        df_final = df_pivot.join(df_desempenho['Desempenho'], how='left')
        df_final = df_final.reset_index()
        df_final = df_final.rename(columns={'estabelecimento': 'Estabelecimento', 'indicador': 'Indicadores'})
        
        return df_final

def gera_relatorio_08(periodo):
    # precisa do gac02, cg01, cg05, cg06
    with app.app_context():

        ano = int(periodo[:4])
        mes = int(periodo[4:])
        mes_gac = f"{periodo[:4]}-{periodo[4:]}"

        query_gac02 = f"""SELECT * FROM 'GAC-02'
        WHERE data_extracao = (
            SELECT MAX(data_extracao) 
            FROM 'GAC-02' 
            WHERE data_extracao LIKE '{mes_gac}-%'
        ) 
        AND estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """

        df_gac02 = pd.read_sql(query_gac02, con=db.engine)
        if not df_gac02.empty:
            df_gac02['cnes'] = df_gac02['cnes'].astype(str).str.replace('.', '')
            
        query_cg01 = f"""SELECT * FROM 'CG-01'
        WHERE ano_mes_extracao = {periodo} AND estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """
        query_cg05 = f"""SELECT * FROM 'CG-05'
        WHERE ano_mes_extracao = {periodo} AND estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        AND dias_acolhimento_dum BETWEEN 0 AND 120
        """
        query_cg05_quant = f"""SELECT * FROM 'CG-05'
        WHERE ano_mes_extracao = {periodo} AND estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """
        query_cg06 = f"""SELECT * FROM 'CG-06'
        WHERE ano_mes_extracao = {periodo} AND estabelecimento NOT IN ('SAE DST/AIDS PENHA')
        """

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

        bases_para_concat = []
        if not df_gac02.empty:
            bases_para_concat.append(df_gac02[['estabelecimento', 'cnes']])
        if not df_cg01.empty:
            bases_para_concat.append(df_cg01[['estabelecimento', 'cnes']])
        if not df_cg05_quant.empty:
            bases_para_concat.append(df_cg05_quant[['estabelecimento', 'cnes']])
        if not df_cg06.empty:
            bases_para_concat.append(df_cg06[['estabelecimento', 'cnes']])
            
        if bases_para_concat:
            df_base = pd.concat(bases_para_concat).drop_duplicates()
        else:
            df_base = pd.DataFrame(columns=['estabelecimento', 'cnes'])

        gestantes_ativas = pd.pivot_table(
            df_gac02,
            index = ['estabelecimento', 'cnes'],
            values = 'qtde_consultas',
            aggfunc = 'count'
        ).reset_index()
        if 'qtde_consultas' in gestantes_ativas.columns:
            gestantes_ativas = gestantes_ativas.rename(columns={'qtde_consultas': 'gestantes_ativas'})
        else:
            gestantes_ativas['gestantes_ativas'] = 0

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
        if 'pessoa' in gestantes_data_parto.columns:
            gestantes_data_parto = gestantes_data_parto.rename(columns={'pessoa': 'gestantes_data_parto'})
        else:
            gestantes_data_parto['gestantes_data_parto'] = 0

        df_cg01['atendimentos_maior_igual_9'] = pd.to_numeric(df_cg01['atendimentos_maior_igual_9'], errors='coerce')
        df_cg01['atendimentos_maior_igual_9'] = df_cg01['atendimentos_maior_igual_9'].fillna(0)

        consultas_maior = pd.pivot_table(
            df_cg01,
            index = ['estabelecimento', 'cnes'],
            values = 'atendimentos_maior_igual_9',
            aggfunc = 'sum'
        ).reset_index()
        if 'atendimentos_maior_igual_9' in consultas_maior.columns:
            consultas_maior = consultas_maior.rename(columns={'atendimentos_maior_igual_9': 'consultas_maior_igual_7'})
        else:
            consultas_maior['consultas_maior_igual_7'] = 0

        dias_120 = pd.pivot_table(
            df_cg05,
            index = ['estabelecimento', 'cnes'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        if 'pessoa' in dias_120.columns:
            dias_120 = dias_120.rename(columns={'pessoa': 'captacao_ate_120_dias'})
        else:
            dias_120['captacao_ate_120_dias'] = 0

        exames = pd.pivot_table(
            df_cg06,
            index = ['estabelecimento', 'cnes'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        if 'pessoa' in exames.columns:
            exames = exames.rename(columns={'pessoa': 'exames_realizados'})
        else:
            exames['exames_realizados'] = 0

        df_final = pd.merge(df_base, gestantes_ativas, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, gestantes_data_parto, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, consultas_maior, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, dias_120, on=['cnes', 'estabelecimento'], how='left')
        df_final = pd.merge(df_final, exames, on=['cnes', 'estabelecimento'], how='left')

        df_final = df_final.fillna(0)

        df_final['%_consultas_7'] = (df_final['consultas_maior_igual_7'] / df_final['gestantes_data_parto']) * 100
        df_final['%_captacao_120'] = (df_final['captacao_ate_120_dias'] / df_final['gestantes_data_parto']) * 100
        df_final['%_exames'] = (df_final['exames_realizados'] / df_final['gestantes_data_parto']) * 100
        df_final = df_final.replace([np.inf, -np.inf, np.nan], 0)
        df_final = df_final.round(2)

        #print(df_final)
        return df_final

def gera_relatorio_09(periodo):
    with app.app_context():

        if periodo:
            ano = periodo[:4]
            mes = periodo[4:]
            query = f"""SELECT * FROM 'REL-114'
            WHERE previsao_parto LIKE '%/{mes}/{ano}'
            AND estab_acolhimento NOT IN ('ENG TRINDADE', 'AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO', 'UBS VILA GUILHERMINA - DR AMERICO RASPA NETO')
        """
        else:
            query = "SELECT * FROM 'REL-114'"

        df_rel114 = pd.read_sql(query, con=db.engine)
        
        if df_rel114.empty:
            return pd.DataFrame()
            
        # Garantir que a coluna de soma seja lida como número (evita que o Pandas concatene textos)
        df_rel114['total_ated_saude_bucal'] = pd.to_numeric(df_rel114['total_ated_saude_bucal'], errors='coerce').fillna(0)
        
        df_final = pd.pivot_table(
            df_rel114,
            index = ['estab_acolhimento'],
            values = ['nome_paciente', 'estab_ult_atend_saude_bucal'],
            aggfunc = {'nome_paciente' : 'count', 
                       'estab_ult_atend_saude_bucal' : 'count'}
        )
        print(df_final)
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
        WHERE sts = 'SUDESTE - STS PENHA'
        AND estabelecimento NOT IN ('Sae Dst/Aids Penha')
        AND faixa_etaria IN ('20 a 24 anos', '25 a 29 anos', '30 a 34 anos', '35 a 39 anos', '40 a 44 anos', '45 a 49 anos', '50 a 54 anos', '55 a 59 anos', '60 a 64 anos')
        """
        df_at03 = pd.read_sql(query, con=db.engine)
        
        if df_at03.empty:
            return None

        mapa_inverso = {v: k for k, v in mapa_mes.items() if len(k) == 2}
        df_at03['mes_num'] = df_at03['mes'].map(mapa_inverso)
        df_at03 = df_at03.dropna(subset=['mes_num'])
        df_at03['ano_mes_int'] = (df_at03['ano'].astype(str) + df_at03['mes_num']).astype(int)
        
        # Filtra histórico até o selecionado
        df_at03 = df_at03[df_at03['ano_mes_int'] <= int(periodo)]
        df_at03 = df_at03.sort_values('ano_mes_int')
        df_at03['Mês/Ano'] = df_at03['mes'] + '/' + df_at03['ano'].astype(str)

        df_final = pd.pivot_table(
            df_at03,
            columns = 'estabelecimento',
            index = ['ano_mes_int', 'Mês/Ano'],
            values = 'quantidade_procedimento',
            aggfunc='sum'
        ).fillna(0).astype(int)
        
        df_final = df_final.reset_index(level=0, drop=True)
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

def gera_relatorio_12(periodo):
    """
    Relatório 12: PLANILHA DE SOLICITAÇÃO MENSAL DE INSUMOS ESPECIAIS (AURICULOTERAPIA)
    Baseado no AT-02 filtrado pelo procedimento 'Sessão de Auriculoterapia'.
    Calcula:
      - Produção auriculoterapia (Nº procedimentos)
      - Total de pontos = Produção * 20
      - Placa adesiva com semente vacaria para auriculoterapia - 70 pontos = Total de pontos / 70
    """
    unidades_grade = [
        "AMA/UBS ENGENHEIRO GOULART - DR JOSE PIRES",
        "AMA/UBS INTEGRADA CANGAIBA - DR. CARLOS GENTILE DE MELLO",
        "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO",
        "AMA/UBS INTEGRADA PADRE MANOEL DA NOBREGA",
        "AMA/UBS INTEGRADA VILA SILVIA",
        "CAPS ADULTO III VILA MATILDE",
        "CAPS ALCOOL E DROGAS II CANGAIBA",
        "CAPS ALCOOL E DROGAS III PENHA",
        "CAPS INFANTO JUVENIL III PENHA",
        "CECCO PADRE MANOEL DA NOBREGA",
        "CER III PENHA",
        "CER PARQUE ARTHUR ALVIM",
        "UBS ANTONIO ESTEVÃO DE CARVALHO",
        "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR",
        "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO",
        "UBS ENGENHEIRO TRINDADE",
        "UBS JARDIM MARINGA - VILA TALARICO",
        "UBS JARDIM SAO FRANCISCO I",
        "UBS JARDIM SAO NICOLAU",
        "UBS PADRE JOSE DE ANCHIETA",
        "UBS PARQUE ARTHUR ALVIM",
        "UBS VILA ARICANDUVA",
        "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO",
        "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA",
        "UBS VILA GRANADA - DR. ALFREDO FERREIRA PAULINO FILHO",
        "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO",
        "UBS VILA MATILDE - DR. RUBENS DO VAL",
    ]

    import unicodedata
    import re

    def normaliza_str(txt):
        if not txt:
            return ""
        txt = unicodedata.normalize('NFKD', str(txt)).encode('ASCII', 'ignore').decode('utf-8')
        txt = txt.upper()
        txt = re.sub(r'[^A-Z0-9\s]', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        return txt

    def mapear_unidade_rel12(nome_estab):
        n = normaliza_str(nome_estab)
        if "EMAB ANCHIETA VILLALOBO" in n or "VILLALOBO" in n:
            return "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO"
        if "EMAB CHACARA PATRIARCA" in n:
            return "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR"
        if "EMAB VILA MATILDE MARINGA" in n:
            return "UBS JARDIM MARINGA - VILA TALARICO"
        if "EMAB SAO FRANCISCO VILA SILVIA" in n:
            return "AMA/UBS INTEGRADA VILA SILVIA"
        if "EMAB ARTHUR ALVIM GUILHERMINA" in n:
            return "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO"
        if "EMAB ENG GOULART CANGAIBA" in n:
            return "AMA/UBS INTEGRADA CANGAIBA - DR. CARLOS GENTILE DE MELLO"
        if "EMAB ESPERANCA EMILIO" in n:
            return "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA"
        if "EMAB GRANADA TRINDADE" in n:
            return "UBS ENGENHEIRO TRINDADE"
            
        if "EMAB AE CARVALHO" in n:
            return "UBS ANTONIO ESTEVÃO DE CARVALHO"
        if "EMAB ANCHIETA" in n:
            return "UBS PADRE JOSE DE ANCHIETA"
        if "EMAB ARICANDUVA" in n:
            return "UBS VILA ARICANDUVA"
        if "EMAB ARTHUR ALVIM" in n:
            return "UBS PARQUE ARTHUR ALVIM"
        if "EMAB CHACARA CRUZEIRO" in n:
            return "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO"
        if "EMAB ENG GOULART" in n:
            return "AMA/UBS ENGENHEIRO GOULART - DR JOSE PIRES"
        if "EMAB ESPERANCA" in n:
            return "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO"
        if "EMAB SAO FRANCISCO" in n:
            return "UBS JARDIM SAO FRANCISCO I"
        if "EMAB VILA MATILDE" in n:
            return "UBS VILA MATILDE - DR. RUBENS DO VAL"
            
        if "CECCO" in n and "PADRE MANOEL" in n:
            return "CECCO PADRE MANOEL DA NOBREGA"
        if "PADRE MANOEL DA NOBREGA" in n:
            return "AMA/UBS INTEGRADA PADRE MANOEL DA NOBREGA"
        if "CANGAIBA" in n and "CAPS" in n:
            return "CAPS ALCOOL E DROGAS II CANGAIBA"
        if "CANGAIBA" in n:
            return "AMA/UBS INTEGRADA CANGAIBA - DR. CARLOS GENTILE DE MELLO"
        if "CHACARA CRUZEIRO" in n:
            return "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO"
        if "VILA SILVIA" in n and "PAI" in n:
            return "PAI VILA SILVIA"
        if "VILA SILVIA" in n:
            return "AMA/UBS INTEGRADA VILA SILVIA"
        if "CAPS" in n and "ADULTO" in n:
            return "CAPS ADULTO III VILA MATILDE"
        if "CAPS" in n and "PENHA" in n and ("INFANT" in n or "JUVENIL" in n):
            return "CAPS INFANTO JUVENIL III PENHA"
        if "CAPS" in n and "PENHA" in n:
            return "CAPS ALCOOL E DROGAS III PENHA"
        if "CER" in n and "ARTHUR ALVIM" in n:
            return "CER PARQUE ARTHUR ALVIM"
        if "CER" in n and "PENHA" in n:
            return "CER III PENHA"
        if "JARDIM NORDESTE" in n:
            return "AMA JARDIM NORDESTE"
        if "MAURICE PATE" in n:
            return "AMA MAURICE PATE"
        if "HOSPITAL DIA" in n:
            return "HOSPITAL DIA PENHA"
        if "PAI" in n and "ESPERANCA" in n:
            return "PAI VILA ESPERANÇA"
        if "PAI" in n and "GRANADA" in n:
            return "PAI VILA GRANADA"
        if "PAI" in n and "SILVIA" in n:
            return "PAI VILA SILVIA"
        if "AE CARVALHO" in n or "ESTEVAO DE CARVALHO" in n:
            return "UBS ANTONIO ESTEVÃO DE CARVALHO"
        if "PATRIARCA" in n:
            return "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR"
        if "VILLALOBO" in n:
            return "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO"
        if "TRINDADE" in n:
            return "UBS ENGENHEIRO TRINDADE"
        if "MARINGA" in n or "TALARICO" in n:
            return "UBS JARDIM MARINGA - VILA TALARICO"
        if "SAO FRANCISCO" in n:
            return "UBS JARDIM SAO FRANCISCO I"
        if "SAO NICOLAU" in n:
            return "UBS JARDIM SAO NICOLAU"
        if "ANCHIETA" in n:
            return "UBS PADRE JOSE DE ANCHIETA"
        if "ARTHUR ALVIM" in n:
            return "UBS PARQUE ARTHUR ALVIM"
        if "ARICANDUVA" in n:
            return "UBS VILA ARICANDUVA"
        if "CASSIO" in n:
            return "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO"
        if "EMILIO" in n:
            return "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA"
        if "GRANADA" in n:
            return "UBS VILA GRANADA - DR. ALFREDO FERREIRA PAULINO FILHO"
        if "GUILHERMINA" in n:
            return "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO"
        if "MATILDE" in n:
            return "UBS VILA MATILDE - DR. RUBENS DO VAL"
        if "GOULART" in n:
            return "AMA/UBS ENGENHEIRO GOULART - DR JOSE PIRES"
            
        return nome_estab

    with app.app_context():
        query = f"""
        SELECT 
            estabelecimento,
            SUM(quantidade_procedimento) as qtd
        FROM 'AT-02'
        WHERE ano_mes = {periodo}
          AND UPPER(procedimento) LIKE '%AURICULOTERAPIA%'
        GROUP BY estabelecimento
        """
        df_raw = pd.read_sql(query, con=db.engine)
        
        prod_por_unidade = {}
        if not df_raw.empty:
            df_raw['unidade_padrao'] = df_raw['estabelecimento'].apply(mapear_unidade_rel12)
            prod_por_unidade = df_raw.groupby('unidade_padrao')['qtd'].sum().to_dict()

        linhas = []
        for u in unidades_grade:
            qtd_proc = int(prod_por_unidade.get(u, 0))
            total_pontos = int(qtd_proc * 20)
            placas = round(total_pontos / 70.0, 7) if total_pontos > 0 else 0
            
            linhas.append({
                "SUPERVISÃO PENHA - Unidades de Saúde": u,
                "Nº procedimentos": qtd_proc,
                "Total de pontos": total_pontos,
                "Placa adesiva com semente vacaria (70 pontos)": placas
            })

        df_final = pd.DataFrame(linhas)
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
        #print(df_final)
        return df_final

def gera_relatorio_15(periodo):
    with app.app_context():
        # Busca todo o histórico até o período selecionado para montar o consolidado quadrimestral
        if periodo:
            query = f'''
                SELECT r.*, e.sigla 
                FROM "REL-135" r
                JOIN equipes e ON r.cod_ine = e.cod_ine
                WHERE r.ano_mes_competencia <= '{periodo}'
                AND e.sigla IN ('ESF', 'ECR', 'EAP20H', 'EAP30H')
            '''
        else:
            query = '''
                SELECT r.*, e.sigla 
                FROM "REL-135" r
                JOIN equipes e ON r.cod_ine = e.cod_ine
                WHERE e.sigla IN ('ESF', 'ECR', 'EAP20H', 'EAP30H')
            '''
            
        df = pd.read_sql(query, con=db.engine)
        
        if df.empty:
            return pd.DataFrame()
            
        # 1. Cria a tabela dinâmica cruzando histórico
        df_pivot = pd.pivot_table(
            df,
            index=['cnes', 'unidade', 'cod_ine', 'sigla'],
            columns='ano_mes_competencia',
            values='total_cadastros',
            aggfunc='sum'
        ).fillna(0).astype(int).reset_index()
        
        # 2. Aplica a regra de negócio Quadrimestral
        colunas = list(df_pivot.columns)
        anos = set([c[:4] for c in colunas if str(c).isnumeric() and len(str(c)) == 6])
        
        colunas_para_dropar = []
        colunas_para_renomear = {}
        
        for ano in anos:
            # Quadrimestre 1 (Jan, Fev, Mar, Abr)
            if f"{ano}04" in colunas:
                colunas_para_renomear[f"{ano}04"] = f"Q1/{ano}"
                colunas_para_dropar.extend([f"{ano}01", f"{ano}02", f"{ano}03"])
            # Quadrimestre 2 (Mai, Jun, Jul, Ago)
            if f"{ano}08" in colunas:
                colunas_para_renomear[f"{ano}08"] = f"Q2/{ano}"
                colunas_para_dropar.extend([f"{ano}05", f"{ano}06", f"{ano}07"])
            # Quadrimestre 3 (Set, Out, Nov, Dez)
            if f"{ano}12" in colunas:
                colunas_para_renomear[f"{ano}12"] = f"Q3/{ano}"
                colunas_para_dropar.extend([f"{ano}09", f"{ano}10", f"{ano}11"])
                
        # Remove os meses anteriores do quadrimestre fechado
        colunas_para_dropar = [c for c in colunas_para_dropar if c in df_pivot.columns]
        df_pivot = df_pivot.drop(columns=colunas_para_dropar)
        
        # Renomeia a coluna que fechou o quadrimestre
        df_pivot = df_pivot.rename(columns=colunas_para_renomear)
        
        # 3. Renomeia os meses restantes (quadrimestre aberto) para o formato MM/YYYY
        outras_renomeacoes = {}
        for c in df_pivot.columns:
            if str(c).isnumeric() and len(str(c)) == 6:
                outras_renomeacoes[c] = f"{str(c)[4:]}/{str(c)[:4]}"
                
        df_pivot = df_pivot.rename(columns=outras_renomeacoes)
        
        # 4. Formatações Finais
        df_pivot = df_pivot.rename(columns={'unidade': 'UNIDADE', 'cnes': 'CNES', 'cod_ine': 'COD_INE', 'sigla': 'SIGLA'})

        
        # Opcional: ordenar colunas (Unidade, INE, seguido por meses e quadrimestres em ordem temporal)
        # O pivot_table já as colocou ordenadas alfabeticamente/cronologicamente (202601 vem antes de 202602 etc)
        # Ao renomear, a ordem original das colunas foi preservada pelo Pandas!
        
        return df_pivot

def gera_relatorio_16(periodo=None):
    """
    Relatório 16: TOTAL DE PACIENTES CADASTRADOS NO PROGRAMA AMG (SIGA - AMG)
    Gera duas tabelas dinâmicas:
      1. Pacientes com STATUS_ATUAL = 'ATIVO'
      2. Pacientes com STATUS_ATUAL = 'INATIVO'
    """
    with app.app_context():
        query = 'SELECT * FROM "REL-16"'
        try:
            df = pd.read_sql(query, con=db.engine)
        except Exception:
            return None, None
        
        if df.empty:
            return None, None

        df_ativo = df[df['status_atual'].astype(str).str.upper() == 'ATIVO']
        df_inativo = df[df['status_atual'].astype(str).str.upper() == 'INATIVO']

        pivot_ativo = pd.pivot_table(
            df_ativo,
            index='estabelecimento',
            columns='diabetes_mellitus',
            values='nome_paciente',
            aggfunc='count',
            fill_value=0
        )
        if hasattr(pivot_ativo.columns, 'names'):
            pivot_ativo.columns.names = [None] * len(pivot_ativo.columns.names)
        else:
            pivot_ativo.columns.name = None
        pivot_ativo = pivot_ativo.reset_index()

        pivot_inativo = pd.pivot_table(
            df_inativo,
            index='estabelecimento',
            columns='motivo_ultimo_status',
            values='nome_paciente',
            aggfunc='count',
            fill_value=0
        )
        if hasattr(pivot_inativo.columns, 'names'):
            pivot_inativo.columns.names = [None] * len(pivot_inativo.columns.names)
        else:
            pivot_inativo.columns.name = None
        pivot_inativo = pivot_inativo.reset_index()

        return pivot_ativo, pivot_inativo

def gera_relatorio_17(periodo):
    with app.app_context():
        query = 'SELECT * FROM "REL-134"'
        df = pd.read_sql(query, con=db.engine)
        
        if df.empty:
            return pd.DataFrame()
        
        # Filtrar inep não nulo/vazio
        df = df[df['inep'].notna()]
        df = df[df['inep'].astype(str).str.strip() != '']
        df = df[df['inep'].astype(str).str.upper() != 'NONE']
        df = df[df['inep'].astype(str).str.upper() != 'NAN']
        df = df[df['inep'].astype(str).str.strip() != '-']
        
        # Garantir tipo numérico
        df['num_participantes'] = pd.to_numeric(df['num_participantes'], errors='coerce').fillna(0)
        
        # Tabela Dinâmica
        df_pivot = pd.pivot_table(
            df,
            index=['nome_unidade', 'inep', 'nome_instituicao'],
            columns='temas_para_saude',
            values='num_participantes',
            aggfunc='sum',
            fill_value=0
        )
        
        df_pivot = df_pivot.reset_index()
        return df_pivot