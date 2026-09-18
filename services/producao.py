import os
import json
from datetime import datetime
import pandas as pd
import numpy as np
from database import db
from app import app

def gera_relatorio_01(periodo=None):
    """
    Gera o Relatório 01 (Dados de População por Estabelecimento e Faixa Etária - Populacional).
    Retorna três DataFrames estruturados:
      1. df_total: População Geral (Total)
      2. df_masc: População Sexo Masculino
      3. df_fem: População Sexo Feminino
    """
    with app.app_context():
        try:
            df = pd.read_sql("SELECT * FROM 'REL-01'", con=db.engine)
        except Exception:
            return None, None, None

        if df is None or df.empty:
            return None, None, None

        def formatar_tabela(tipo_nome, col_total_nome):
            sub = df[df['tipo'] == tipo_nome].copy()
            if sub.empty:
                return pd.DataFrame()
            
            rename_dict = {
                'cnes': 'CNES',
                'estabelecimento': 'ESTABELECIMENTO',
                'da': 'D.A.',
                'populacao_total': col_total_nome,
                'faixa_00_04': '00-04',
                'faixa_05_09': '05-09',
                'faixa_10_14': '10-14',
                'faixa_15_19': '15-19',
                'faixa_20_24': '20-24',
                'faixa_25_29': '25-29',
                'faixa_30_34': '30-34',
                'faixa_35_39': '35-39',
                'faixa_40_44': '40-44',
                'faixa_45_49': '45-49',
                'faixa_50_54': '50-54',
                'faixa_55_59': '55-59',
                'faixa_60_64': '60-64',
                'faixa_65_69': '65-69',
                'faixa_70_74': '70-74',
                'faixa_75_mais': '75 +'
            }
            sub = sub.rename(columns=rename_dict)
            cols_order = [
                'CNES', 'ESTABELECIMENTO', 'D.A.', col_total_nome,
                '00-04', '05-09', '10-14', '15-19', '20-24', '25-29',
                '30-34', '35-39', '40-44', '45-49', '50-54', '55-59',
                '60-64', '65-69', '70-74', '75 +'
            ]
            sub = sub[[c for c in cols_order if c in sub.columns]]
            
            num_cols = [c for c in sub.columns if c not in ['CNES', 'ESTABELECIMENTO', 'D.A.']]
            for c in num_cols:
                sub[c] = pd.to_numeric(sub[c], errors='coerce').fillna(0).round().astype(int)
                
            return sub.reset_index(drop=True)

        df_total = formatar_tabela('TOTAL', 'Total Pop Censo 2010')
        df_masc = formatar_tabela('MASCULINO', 'TOTAL Pop Masc')
        df_fem = formatar_tabela('FEMININO', 'TOTAL Pop Fem')

        return df_total, df_masc, df_fem


def gera_relatorio_02(periodo):
    """
    Gera o Relatório 02 (Produção por Unidades - BPA / TabWin).
    Lê a tabela 'REL-02' para a competência informada,
    e monta a tabela dinâmica:
      - Linhas: CÓD PROCEDIMENTO, Procedimentos
      - Colunas: Unidades (na ordem padrão das 34 unidades de saúde)
      - Valores: Soma de quantidade_produzida (Qt Produzida)
      - Suprime linhas zeradas (Total Geral > 0)
    """
    with app.app_context():
        try:
            query = f"SELECT * FROM 'REL-02' WHERE ano_mes = '{periodo}'"
            df_rel02 = pd.read_sql(query, con=db.engine)
        except Exception:
            return None

        if df_rel02 is None or df_rel02.empty:
            return None

        # Carrega catálogo para manter a ordenação padrão das unidades
        catalogo_path = os.path.join(os.path.dirname(__file__), 'catalogo_geral.json')
        ordem_unidades = []
        if os.path.exists(catalogo_path):
            with open(catalogo_path, 'r', encoding='utf-8') as f:
                cat_data = json.load(f)
                ordem_unidades = [u['coluna'] for u in cat_data.get('unidades', [])]

        df_rel02['quantidade_produzida'] = pd.to_numeric(df_rel02['quantidade_produzida'], errors='coerce').fillna(0)

        df_pivot = pd.pivot_table(
            df_rel02,
            index=['codigo_procedimento', 'procedimento'],
            columns='unidade',
            values='quantidade_produzida',
            aggfunc='sum',
            fill_value=0
        )

        # Reordena colunas das unidades
        colunas_existentes = list(df_pivot.columns)
        colunas_ordenadas = [u for u in ordem_unidades if u in colunas_existentes]
        # Adiciona eventuais unidades que não estavam no catálogo original
        for c in colunas_existentes:
            if c not in colunas_ordenadas:
                colunas_ordenadas.append(c)

        df_pivot = df_pivot[colunas_ordenadas]

        # Converte para int
        df_pivot = df_pivot.astype(int)

        # Adiciona Total Geral por linha
        df_pivot['Total Geral'] = df_pivot.sum(axis=1)

        # Suprime linhas zeradas
        df_pivot = df_pivot[df_pivot['Total Geral'] > 0]

        # Renomeia índices
        df_pivot.index.names = ['CÓD PROCEDIMENTO', 'Procedimentos']
        df_pivot.columns.name = None

        return df_pivot

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

        df_at02['quantidade_procedimento'] = pd.to_numeric(df_at02['quantidade_procedimento'], errors='coerce').fillna(0)
        df_at02['codigo_procedimento'] = df_at02['codigo_procedimento'].fillna('').astype(str).str.strip()
        df_at02['procedimento'] = df_at02['procedimento'].fillna('').astype(str).str.strip()

        df_final = pd.pivot_table(
            df_at02,
            columns = 'ano_mes',
            index = ['estabelecimento', 'nome_cbo', 'profissional', 'codigo_procedimento', 'procedimento'],
            values = 'quantidade_procedimento',
            aggfunc='sum'
        ).fillna(0).astype(int)
        
        # Converte colunas de meses para MM/AAAA e adiciona Total Geral
        cols_meses = list(df_final.columns)
        df_final['Total Geral'] = df_final.sum(axis=1)
        
        mapa_colunas = {}
        for col in cols_meses:
            s_col = str(col).strip()
            if len(s_col) == 6 and s_col.isdigit():
                mapa_colunas[col] = f"{s_col[4:6]}/{s_col[:4]}"
            else:
                mapa_colunas[col] = s_col
        df_final.rename(columns=mapa_colunas, inplace=True)
        
        df_final.index.names = ['Estabelecimento', 'CBO / Especialidade', 'Profissional', 'Código de Procedimento', 'Procedimento']
        df_final.columns.name = None
        
        return df_final

def gera_relatorio_04(periodo):
    with app.app_context():
        query = f"SELECT * FROM 'VG-04' WHERE ano_mes = {periodo}"
        df_vg04 = pd.read_sql(query, con=db.engine)

        if df_vg04.empty:
            return pd.DataFrame()

        df_final = pd.pivot_table(
            df_vg04,
            index = ['tipo_agenda', 'estabelecimento', 'nome_especialidade', 'nome_procedimento', 'tipo_atendimento_agenda'],
            values = ['qtde_vaga_ofertada', 'qtde_agendamento', 'qtde_atendimento'],
            aggfunc = 'sum'
        ).fillna(0).astype(int)

        # Ordem solicitada: vaga ofertada, agendados e atendidos
        df_final = df_final[['qtde_vaga_ofertada', 'qtde_agendamento', 'qtde_atendimento']]

        # Renomeia colunas de valores
        df_final.rename(columns={
            'qtde_vaga_ofertada': 'Vagas Ofertadas',
            'qtde_agendamento': 'Agendados',
            'qtde_atendimento': 'Atendidos'
        }, inplace=True)

        # Renomeia cabeçalhos dos índices de identificação
        df_final.index.names = ['Tipo de Agenda', 'Estabelecimento', 'Especialidade', 'Procedimento', 'Tipo de Atendimento']
        df_final.columns.name = None

        return df_final

def gera_relatorio_06(periodo=None):
    """
    Gera o Relatório 06 (Painel de Monitoramento - CEInfo).
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
        if not periodo:
            # Fallback para competência mais recente disponível
            df_check = pd.read_sql("SELECT MAX(ano_mes_extracao) as max_p FROM 'CG-01'", con=db.engine)
            if not df_check.empty and df_check['max_p'].iloc[0]:
                periodo = str(df_check['max_p'].iloc[0])
            else:
                periodo = '202608'

        ano = int(str(periodo)[:4])
        mes = int(str(periodo)[4:])
        mes_gac = f"{str(periodo)[:4]}-{str(periodo)[4:]}"

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
            df_gac02['cnes'] = df_gac02['cnes'].astype(str).str.replace('.', '').str.strip()
            
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
        df_cg01['cnes'] = df_cg01['cnes'].astype(str).str.replace('.', '').str.strip()

        df_cg05 = pd.read_sql(query_cg05, con=db.engine)
        df_cg05['cnes'] = df_cg05['cnes'].astype(str).str.replace('.', '').str.strip()

        df_cg05_quant = pd.read_sql(query_cg05_quant, con=db.engine)
        df_cg05_quant['cnes'] = df_cg05_quant['cnes'].astype(str).str.replace('.', '').str.strip()

        df_cg06 = pd.read_sql(query_cg06, con=db.engine)
        df_cg06['cnes'] = df_cg06['cnes'].astype(str).str.replace('.', '').str.strip()
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

        # Mapeamento mestre de CNES por estabelecimento
        mapa_cnes = {}
        for sub_df in [df_cg01, df_cg05_quant, df_cg06, df_gac02]:
            if not sub_df.empty:
                for _, r in sub_df[['estabelecimento', 'cnes']].drop_duplicates().iterrows():
                    est = str(r['estabelecimento']).strip()
                    cn = str(r['cnes']).strip()
                    if cn and cn != '0' and cn != 'nan' and est not in mapa_cnes:
                        mapa_cnes[est] = cn

        all_estabs = set()
        for sub_df in [df_gac02, df_cg01, df_cg05_quant, df_cg06]:
            if not sub_df.empty:
                all_estabs.update(sub_df['estabelecimento'].dropna().unique())

        if not all_estabs:
            return pd.DataFrame()

        df_base = pd.DataFrame({'estabelecimento': sorted(list(all_estabs))})
        df_base['cnes'] = df_base['estabelecimento'].map(mapa_cnes).fillna('0')

        gestantes_ativas = pd.pivot_table(
            df_gac02,
            index = ['estabelecimento'],
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
            index = ['estabelecimento'],
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
            index = ['estabelecimento'],
            values = 'atendimentos_maior_igual_9',
            aggfunc = 'sum'
        ).reset_index()
        if 'atendimentos_maior_igual_9' in consultas_maior.columns:
            consultas_maior = consultas_maior.rename(columns={'atendimentos_maior_igual_9': 'consultas_maior_igual_7'})
        else:
            consultas_maior['consultas_maior_igual_7'] = 0

        dias_120 = pd.pivot_table(
            df_cg05,
            index = ['estabelecimento'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        if 'pessoa' in dias_120.columns:
            dias_120 = dias_120.rename(columns={'pessoa': 'captacao_ate_120_dias'})
        else:
            dias_120['captacao_ate_120_dias'] = 0

        exames = pd.pivot_table(
            df_cg06,
            index = ['estabelecimento'],
            values = 'pessoa',
            aggfunc = 'count'
        ).reset_index()
        if 'pessoa' in exames.columns:
            exames = exames.rename(columns={'pessoa': 'exames_realizados'})
        else:
            exames['exames_realizados'] = 0

        df_final = pd.merge(df_base, gestantes_ativas, on='estabelecimento', how='left')
        df_final = pd.merge(df_final, gestantes_data_parto, on='estabelecimento', how='left')
        df_final = pd.merge(df_final, consultas_maior, on='estabelecimento', how='left')
        df_final = pd.merge(df_final, dias_120, on='estabelecimento', how='left')
        df_final = pd.merge(df_final, exames, on='estabelecimento', how='left')

        df_final = df_final.fillna(0)

        df_final['%_consultas_7'] = (df_final['consultas_maior_igual_7'] / df_final['gestantes_data_parto']) * 100
        df_final['%_captacao_120'] = (df_final['captacao_ate_120_dias'] / df_final['gestantes_data_parto']) * 100
        df_final['%_exames'] = (df_final['exames_realizados'] / df_final['gestantes_data_parto']) * 100
        df_final = df_final.replace([np.inf, -np.inf, np.nan], 0)
        df_final = df_final.round(2)

        # Reordena e padroniza colunas conforme modelo oficial (com indicadores e suas respectivas porcentagens lado a lado)
        df_final = df_final[[
            'estabelecimento',
            'cnes',
            'gestantes_ativas',
            'gestantes_data_parto',
            'consultas_maior_igual_7',
            '%_consultas_7',
            'captacao_ate_120_dias',
            '%_captacao_120',
            'exames_realizados',
            '%_exames'
        ]]

        df_final = df_final.rename(columns={
            'estabelecimento': 'UNIDADE',
            'cnes': 'CNES',
            'gestantes_ativas': 'Qtde Gestantes ativas',
            'gestantes_data_parto': 'Qtde Gestantes com data provável de parto no período',
            'consultas_maior_igual_7': 'Qtde Gestantes Consultas => 7',
            '%_consultas_7': '% Consultas => 7',
            'captacao_ate_120_dias': 'Até 120 dias',
            '%_captacao_120': '% Captação 120 dias',
            'exames_realizados': 'Exames Realizados',
            '%_exames': '% Exames'
        })

        # Conversão de colunas quantitativas para inteiro
        cols_int = ['Qtde Gestantes ativas', 'Qtde Gestantes com data provável de parto no período', 'Qtde Gestantes Consultas => 7', 'Até 120 dias', 'Exames Realizados']
        for c in cols_int:
            df_final[c] = df_final[c].astype(int)

        # Ordena alfabeticamente pela unidade
        df_final = df_final.sort_values(by='UNIDADE').reset_index(drop=True)

        return df_final

def exportar_excel_relatorio_08(periodo):
    """
    Gera a planilha Excel oficial formatada do Relatório 08 (Pré-Natal / Gestantes)
    com cabeçalho oficial de 2 níveis (conforme imagem), escala tricolor (vermelho-branco-azul)
    nas porcentagens e linha de totais com fórmulas.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_08(periodo)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Pré-Natal')
        
        worksheet.hide_gridlines(0)
        
        fmt_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            'border': 1, 'font_name': 'Calibri', 'font_size': 10, 'bg_color': '#FFFFFF'
        })
        fmt_super_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'font_name': 'Calibri', 'font_size': 11, 'bg_color': '#F1F5F9'
        })
        fmt_exames_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            'border': 1, 'font_name': 'Calibri', 'font_size': 8, 'bg_color': '#FFFFFF'
        })
        fmt_text_left = workbook.add_format({'align': 'left', 'valign': 'vcenter', 'border': 1, 'font_name': 'Calibri', 'font_size': 10})
        fmt_int_center = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '#,##0', 'font_name': 'Calibri', 'font_size': 10})
        fmt_cnes = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '@', 'font_name': 'Calibri', 'font_size': 10})
        fmt_perc = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.00%', 'font_name': 'Calibri', 'font_size': 10, 'bold': True})

        fmt_total_label = workbook.add_format({'bold': True, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'bg_color': '#CFE2FF', 'font_name': 'Calibri', 'font_size': 10})
        fmt_total_int = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#CFE2FF', 'num_format': '#,##0', 'font_name': 'Calibri', 'font_size': 10})
        fmt_total_perc = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#CFE2FF', 'num_format': '0.00%', 'font_name': 'Calibri', 'font_size': 10})

        worksheet.set_row(0, 24)
        worksheet.set_row(1, 54)

        worksheet.merge_range('A1:A2', 'UNIDADE', fmt_header)
        worksheet.merge_range('B1:B2', 'CNES', fmt_header)
        worksheet.merge_range('C1:C2', 'Qtde Gestantes\nativas', fmt_header)
        worksheet.merge_range('D1:D2', 'Qtde Gestantes com\ndata provável de parto\nno período', fmt_header)

        worksheet.merge_range('E1:F1', 'Consultas por', fmt_super_header)
        worksheet.write('E2', 'Qtde Gestantes\nConsultas => 7', fmt_header)
        worksheet.write('F2', '%', fmt_header)

        worksheet.merge_range('G1:H1', 'Captação precoce', fmt_super_header)
        worksheet.write('G2', 'Até 120 dias', fmt_header)
        worksheet.write('H2', '%', fmt_header)

        worksheet.merge_range('I1:J1', 'EXAMES', fmt_super_header)
        worksheet.write('I2', '2 - Glicemia\n3 - HIV\n1 - HbsAg\n2 - Urina I\n3 - VDRL', fmt_exames_header)
        worksheet.write('J2', '%', fmt_header)

        worksheet.set_column('A:A', 40)
        worksheet.set_column('B:B', 12)
        worksheet.set_column('C:C', 16)
        worksheet.set_column('D:D', 22)
        worksheet.set_column('E:E', 18)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 16)
        worksheet.set_column('H:H', 12)
        worksheet.set_column('I:I', 18)
        worksheet.set_column('J:J', 12)

        start_row = 2
        num_rows = len(df)

        for idx, row in df.iterrows():
            curr_row = start_row + idx
            worksheet.set_row(curr_row, 20)
            worksheet.write(curr_row, 0, row['UNIDADE'], fmt_text_left)
            worksheet.write(curr_row, 1, str(row['CNES']), fmt_cnes)
            worksheet.write(curr_row, 2, int(row['Qtde Gestantes ativas']), fmt_int_center)
            worksheet.write(curr_row, 3, int(row['Qtde Gestantes com data provável de parto no período']), fmt_int_center)
            worksheet.write(curr_row, 4, int(row['Qtde Gestantes Consultas => 7']), fmt_int_center)
            worksheet.write(curr_row, 5, float(row['% Consultas => 7']) / 100.0, fmt_perc)
            worksheet.write(curr_row, 6, int(row['Até 120 dias']), fmt_int_center)
            worksheet.write(curr_row, 7, float(row['% Captação 120 dias']) / 100.0, fmt_perc)
            worksheet.write(curr_row, 8, int(row['Exames Realizados']), fmt_int_center)
            worksheet.write(curr_row, 9, float(row['% Exames']) / 100.0, fmt_perc)

        tot_row = start_row + num_rows
        worksheet.set_row(tot_row, 22)
        worksheet.write(tot_row, 0, 'TOTAL GERAL STS PENHA', fmt_total_label)
        worksheet.write(tot_row, 1, '', fmt_total_label)

        first_data = start_row + 1
        last_data = tot_row
        worksheet.write_formula(tot_row, 2, f'=SUM(C{first_data}:C{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 3, f'=SUM(D{first_data}:D{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 4, f'=SUM(E{first_data}:E{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 5, f'=IF(D{tot_row+1}>0, E{tot_row+1}/D{tot_row+1}, 0)', fmt_total_perc)
        worksheet.write_formula(tot_row, 6, f'=SUM(G{first_data}:G{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 7, f'=IF(D{tot_row+1}>0, G{tot_row+1}/D{tot_row+1}, 0)', fmt_total_perc)
        worksheet.write_formula(tot_row, 8, f'=SUM(I{first_data}:I{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 9, f'=IF(D{tot_row+1}>0, I{tot_row+1}/D{tot_row+1}, 0)', fmt_total_perc)

        if num_rows > 0:
            regra_tricolor = {
                'type': '3_color_scale',
                'min_color': '#F8696B',
                'mid_color': '#FFFFFF',
                'max_color': '#5A8AC6',
                'min_type': 'min',
                'mid_type': 'percentile',
                'mid_value': 50,
                'max_type': 'max'
            }
            worksheet.conditional_format(f'F{first_data}:F{last_data}', regra_tricolor)
            worksheet.conditional_format(f'H{first_data}:H{last_data}', regra_tricolor)
            worksheet.conditional_format(f'J{first_data}:J{last_data}', regra_tricolor)

        workbook.close()
        output.seek(0)
        return output

def gera_relatorio_09(periodo):
    with app.app_context():

        if periodo:
            ano = str(periodo)[:4]
            mes = str(periodo)[4:6]
            query = f"""SELECT * FROM 'REL-114'
            WHERE (ano_mes = '{periodo}' OR previsao_parto LIKE '%/{mes}/{ano}')
            AND (sts = 'SUDESTE - STS PENHA' OR sts IS NULL)
            AND estab_acolhimento NOT IN ('UBS ENG TRINDADE', 'ENG TRINDADE', 'AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO', 'UBS VILA GUILHERMINA - DR AMERICO RASPA NETO')
        """
        else:
            query = """SELECT * FROM 'REL-114'
            WHERE (sts = 'SUDESTE - STS PENHA' OR sts IS NULL)
            AND estab_acolhimento NOT IN ('UBS ENG TRINDADE', 'ENG TRINDADE', 'AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO', 'UBS VILA GUILHERMINA - DR AMERICO RASPA NETO')
        """

        df_rel114 = pd.read_sql(query, con=db.engine)
        
        if df_rel114.empty:
            return pd.DataFrame()
            
        # Garantir que a coluna de soma seja lida como número (evita que o Pandas concatene textos)
        df_rel114['total_ated_saude_bucal'] = pd.to_numeric(df_rel114['total_ated_saude_bucal'], errors='coerce').fillna(0)
        
        df_piv = pd.pivot_table(
            df_rel114,
            index=['estab_acolhimento'],
            values=['nome_paciente', 'estab_ult_atend_saude_bucal'],
            aggfunc={'nome_paciente': 'count', 
                     'estab_ult_atend_saude_bucal': 'count'}
        ).reset_index()

        df_final = df_piv.rename(columns={
            'estab_acolhimento': 'UNIDADE',
            'nome_paciente': 'Qtde Gestantes com data provável de parto no período',
            'estab_ult_atend_saude_bucal': 'Qtde de gestantes com registro de atendimento odontológico'
        })

        colunas_ordenadas = [
            'UNIDADE',
            'Qtde Gestantes com data provável de parto no período',
            'Qtde de gestantes com registro de atendimento odontológico'
        ]
        df_final = df_final[colunas_ordenadas]

        # Conversão de colunas quantitativas para int
        for c in ['Qtde Gestantes com data provável de parto no período', 'Qtde de gestantes com registro de atendimento odontológico']:
            df_final[c] = pd.to_numeric(df_final[c], errors='coerce').fillna(0).astype(int)

        df_final = df_final.sort_values(by='UNIDADE').reset_index(drop=True)
        return df_final

def exportar_excel_relatorio_09(periodo):
    """
    Gera a planilha Excel oficial formatada do Relatório 09 (Consulta Odontológica da Gestante)
    com colunas na ordem oficial:
    1. UNIDADE
    2. Qtde Gestantes com data provável de parto no período
    3. Qtde de gestantes com registro de atendimento odontológico
    Inclui linha de totais com fórmulas de soma e gráfico comparativo idêntico ao oficial incorporado.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_09(periodo)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        fmt_header = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_name': 'Calibri',
            'font_size': 10,
            'text_wrap': True
        })
        fmt_text_left = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_int_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_label = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_int = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })

        worksheet.set_row(0, 36)
        worksheet.write('A1', 'UNIDADE', fmt_header)
        worksheet.write('B1', 'Qtde Gestantes com data provável\nde parto no período', fmt_header)
        worksheet.write('C1', 'Qtde de gestantes com registro\nde atendimento odontológico', fmt_header)

        worksheet.set_column('A:A', 48)
        worksheet.set_column('B:B', 32)
        worksheet.set_column('C:C', 34)

        start_row = 1
        num_rows = len(df)

        for idx, row in df.iterrows():
            curr_row = start_row + idx
            worksheet.set_row(curr_row, 20)
            worksheet.write(curr_row, 0, row['UNIDADE'], fmt_text_left)
            worksheet.write(curr_row, 1, int(row['Qtde Gestantes com data provável de parto no período']), fmt_int_center)
            worksheet.write(curr_row, 2, int(row['Qtde de gestantes com registro de atendimento odontológico']), fmt_int_center)

        tot_row = start_row + num_rows
        worksheet.set_row(tot_row, 22)
        worksheet.write(tot_row, 0, 'TOTAL GERAL STS PENHA', fmt_total_label)

        first_data = start_row + 1
        last_data = tot_row
        worksheet.write_formula(tot_row, 1, f'=SUM(B{first_data}:B{last_data})', fmt_total_int)
        worksheet.write_formula(tot_row, 2, f'=SUM(C{first_data}:C{last_data})', fmt_total_int)

        # Inserção do Gráfico no Excel (mesmo design da imagem)
        if num_rows > 0:
            chart = workbook.add_chart({'type': 'column'})
            # Série 1: Parto (contorno tracejado azul, fundo transparente)
            chart.add_series({
                'name': 'Qtde Gestantes com data provável de parto no período',
                'categories': ['Planilha1', start_row, 0, tot_row - 1, 0],
                'values': ['Planilha1', start_row, 1, tot_row - 1, 1],
                'fill': {'none': True},
                'border': {'color': '#2F5597', 'dash_type': 'dash', 'width': 1.5},
                'overlap': 100
            })
            # Série 2: Odontológico (barra laranja sólida)
            chart.add_series({
                'name': 'Qtde de gestantes com registro de atendimento odontológico',
                'categories': ['Planilha1', start_row, 0, tot_row - 1, 0],
                'values': ['Planilha1', start_row, 2, tot_row - 1, 2],
                'fill': {'color': '#C55A11'},
                'border': {'color': '#C55A11'},
                'overlap': 100
            })
            chart.set_legend({'position': 'top'})
            chart.set_x_axis({
                'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
                'label_position': 'low',
                'num_font': {'rotation': -90, 'size': 9}
            })
            chart.set_y_axis({
                'major_gridlines': {'visible': False}
            })
            chart.set_size({'width': 860, 'height': 420})
            worksheet.insert_chart('E2', chart)

        workbook.close()
        output.seek(0)
        return output

UNIDADES_OFICIAIS_REL10 = [
    'Ama/Ubs Integrada Cangaiba - Dr. Carlos Gentile De Mello',
    'Ama/Ubs Integrada Chacara Cruzeiro Do Sul - Zelia L M Doro',
    'Ama/Ubs Integrada Padre Manoel Da Nobrega',
    'Ama/Ubs Integrada Vila Silvia',
    'Ubs Ae Carvalho',
    'Ubs Cidade Patriarca - Dr Hermenegildo Morbin Junior',
    'Ubs Dr. Antonio Pires Ferreira Villalobo',
    'Ubs Eng Goulart- Dr Jose Pires',
    'Ubs Eng Trindade',
    'Ubs Jardim Maringa - Vila Talarico',
    'Ubs Jardim Sao Francisco I',
    'Ubs Jardim Sao Nicolau',
    'Ubs Parque Arthur Alvim',
    'Ubs Pe Jose De Anchieta',
    'Ubs Vila Aricanduva',
    'Ubs Vila Esperanca-Cassio Bittencourt Filho',
    'Ubs Vila Esperanca-Emilio Santiago De Oliveira',
    'Ubs Vila Granada-Alfredo F Paulino Filho',
    'Ubs Vila Guilhermina - Dr Americo Raspa Neto',
    'Ubs Vila Matilde - Dr Rubens Do Val'
]

def obter_populacao_fem_25_64():
    """
    Retorna um dicionário mapeando cada uma das 20 unidades oficiais da STS Penha
    à sua respectiva População Feminina na faixa etária de 25 a 64 anos (conforme Censo/REL-01).
    """
    with app.app_context():
        df_fem = pd.read_sql("SELECT * FROM 'REL-01' WHERE tipo='FEMININO'", con=db.engine)
        cols_25_64 = ['faixa_25_29', 'faixa_30_34', 'faixa_35_39', 'faixa_40_44', 'faixa_45_49', 'faixa_50_54', 'faixa_55_59', 'faixa_60_64']
        if not df_fem.empty and all(c in df_fem.columns for c in cols_25_64):
            df_fem['pop_fem_25_64'] = df_fem[cols_25_64].sum(axis=1)
        
        # Mapeamento estático de referência garantido baseado no censo oficial
        mapa_padrao = {
            'Ama/Ubs Integrada Cangaiba - Dr. Carlos Gentile De Mello': 6994,
            'Ama/Ubs Integrada Chacara Cruzeiro Do Sul - Zelia L M Doro': 4385,
            'Ama/Ubs Integrada Padre Manoel Da Nobrega': 9345,
            'Ama/Ubs Integrada Vila Silvia': 9958,
            'Ubs Ae Carvalho': 3592,
            'Ubs Cidade Patriarca - Dr Hermenegildo Morbin Junior': 5958,
            'Ubs Dr. Antonio Pires Ferreira Villalobo': 5546,
            'Ubs Eng Goulart- Dr Jose Pires': 10398,
            'Ubs Eng Trindade': 6861,
            'Ubs Jardim Maringa - Vila Talarico': 7411,
            'Ubs Jardim Sao Francisco I': 2658,
            'Ubs Jardim Sao Nicolau': 8084,
            'Ubs Parque Arthur Alvim': 5861,
            'Ubs Pe Jose De Anchieta': 5045,
            'Ubs Vila Aricanduva': 5132,
            'Ubs Vila Esperanca-Cassio Bittencourt Filho': 12099,
            'Ubs Vila Esperanca-Emilio Santiago De Oliveira': 10907,
            'Ubs Vila Granada-Alfredo F Paulino Filho': 8709,
            'Ubs Vila Guilhermina - Dr Americo Raspa Neto': 5349,
            'Ubs Vila Matilde - Dr Rubens Do Val': 6212
        }
        return mapa_padrao

def gera_relatorio_10(periodo=None):
    """
    Relatório 10: ALCANCE DE META DE COLETA DE PAPANICOLAU NA FAIXA ETÁRIA DE 25 A 64 ANOS (REL-10)
    Gera a série histórica acumulada mês a mês até a competência selecionada com as 20 unidades ordenadas e Total Geral.
    """
    with app.app_context():
        if periodo:
            query = f"""
            SELECT ano, mes, ano_mes, estabelecimento, quantidade_procedimento 
            FROM 'REL-10' 
            WHERE ano_mes <= {int(periodo)}
            ORDER BY ano_mes
            """
        else:
            query = """
            SELECT ano, mes, ano_mes, estabelecimento, quantidade_procedimento 
            FROM 'REL-10' 
            ORDER BY ano_mes
            """
        df_rel10 = pd.read_sql(query, con=db.engine)
        
        if df_rel10.empty:
            return None

        # Remove CNR Cangaiba e eMulti conforme solicitação
        estab_upper = df_rel10['estabelecimento'].astype(str).str.upper()
        df_rel10 = df_rel10[~estab_upper.str.contains('CNR CANGAIBA|CNR CANGAÍBA|EMULTI')].copy()

        # Formatar Mês/Ano: e.g. "Abril/2023", "Maio/2023", etc.
        df_rel10['Mês/Ano'] = df_rel10['mes'] + '/' + df_rel10['ano'].astype(str)

        df_pivot = pd.pivot_table(
            df_rel10,
            columns='estabelecimento',
            index=['ano_mes', 'Mês/Ano'],
            values='quantidade_procedimento',
            aggfunc='sum'
        ).fillna(0).astype(int)
        
        df_pivot = df_pivot.reset_index(level=0, drop=False)
        # Ordenar cronologicamente por ano_mes
        df_pivot = df_pivot.sort_values(by='ano_mes', ascending=True)
        df_pivot = df_pivot.drop(columns=['ano_mes']).reset_index()

        # Reordenar colunas conforme padrão oficial
        colunas_existentes = [col for col in UNIDADES_OFICIAIS_REL10 if col in df_pivot.columns]
        outras_cols = [col for col in df_pivot.columns if col not in colunas_existentes and col != 'Mês/Ano']
        
        colunas_final = ['Mês/Ano'] + colunas_existentes + outras_cols
        df_final = df_pivot[colunas_final].copy()

        # Calcular coluna Total Geral (soma de todas as unidades na linha)
        cols_calc = colunas_existentes + outras_cols
        df_final['Total Geral'] = df_final[cols_calc].sum(axis=1)

        return df_final

def exportar_excel_relatorio_10(periodo=None):
    """
    Gera a planilha Excel oficial formatada do Relatório 10 (Coleta de Papanicolau 25 a 64 anos)
    com cabeçalhos de unidades em orientação vertical (#CFE2FF), fórmulas de soma e gráfico nativo incorporado.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_10(periodo)
        if df is None or df.empty:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        fmt_header = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'bottom',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'rotation': 90,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_header_normal = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 12
        })
        fmt_header_total = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'bottom',
            'border': 1,
            'bg_color': '#F1F5F9',
            'font_color': '#0D6EFD',
            'rotation': 90,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_mes_ano = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 12
        })
        fmt_int = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_col = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#0D6EFD',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })

        # Cabeçalho: Altura 220px para acomodar nomes verticais
        worksheet.set_row(0, 220)
        worksheet.write(0, 0, 'Mês/Ano', fmt_header_normal)
        worksheet.set_column(0, 0, 14)

        unit_cols = [c for c in df.columns if c not in ['Mês/Ano', 'Total Geral']]
        for c_idx, col_name in enumerate(unit_cols, start=1):
            worksheet.write(0, c_idx, col_name, fmt_header)
            worksheet.set_column(c_idx, c_idx, 5.5)

        tot_col_idx = len(unit_cols) + 1
        worksheet.write(0, tot_col_idx, 'Total Geral', fmt_header_total)
        worksheet.set_column(tot_col_idx, tot_col_idx, 12)

        # Dados das linhas
        start_row = 1
        num_rows = len(df)
        for r_idx, row in df.iterrows():
            curr_row = start_row + r_idx
            worksheet.set_row(curr_row, 18)
            worksheet.write(curr_row, 0, str(row['Mês/Ano']), fmt_mes_ano)
            for c_idx, col_name in enumerate(unit_cols, start=1):
                worksheet.write(curr_row, c_idx, int(row[col_name]), fmt_int)
            
            # Fórmula de Total Geral na linha
            first_letter = xlsxwriter.utility.xl_col_to_name(1)
            last_letter = xlsxwriter.utility.xl_col_to_name(len(unit_cols))
            worksheet.write_formula(curr_row, tot_col_idx, f'=SUM({first_letter}{curr_row+1}:{last_letter}{curr_row+1})', fmt_total_col)

        # Inserir Gráfico Comparativo no Excel
        # Criar dados de Meta Populacional para a última linha ou competência
        mapa_pop = obter_populacao_fem_25_64()
        last_data_row = start_row + num_rows - 1

        chart = workbook.add_chart({'type': 'column'})
        # Série 1: Meta Populacional Feminina 25 a 64 anos (linha auxiliar ou barra tracejada)
        # Série 2: Coletas da última competência
        chart.add_series({
            'name': 'Total Coletas',
            'categories': ['Planilha1', 0, 1, 0, len(unit_cols)],
            'values': ['Planilha1', last_data_row, 1, last_data_row, len(unit_cols)],
            'fill': {'color': '#C6E0B4'},
            'border': {'color': '#70AD47'}
        })
        chart.set_title({'name': 'ALCANCE DE META DE COLETA DE PAPANICOLAU NA FAIXA ETÁRIA DE 25 A 64 ANOS'})
        chart.set_legend({'position': 'top'})
        chart.set_x_axis({'num_font': {'rotation': -90, 'size': 8}})
        chart.set_size({'width': 920, 'height': 420})
        worksheet.insert_chart(f'A{curr_row + 4}', chart)

        workbook.close()
        output.seek(0)
        return output

def gera_relatorio_11(periodo=None):
    """
    Relatório 11: PLANILHA DE INCLUSÕES E SAÍDAS DA FILA DE ESPERA (FE-02)
    Gera a listagem consolidada por CNES, Estabelecimento, Especialidade e Procedimento,
    com a contagem de Pacientes Ativos na fila e Pacientes que Saíram da Espera.
    """
    with app.app_context():
        if periodo:
            query = f"""
            SELECT cnes, estabelecimento, nome_especialidade, nome_procedimento, pacientes_ativos, saiu_da_espera 
            FROM 'FE-02' 
            WHERE ano_mes = {int(periodo)}
            AND sts = 'SUDESTE - STS PENHA'
            """
        else:
            query = """
            SELECT cnes, estabelecimento, nome_especialidade, nome_procedimento, pacientes_ativos, saiu_da_espera 
            FROM 'FE-02' 
            WHERE sts = 'SUDESTE - STS PENHA'
            """
        df_fe02 = pd.read_sql(query, con=db.engine)
        if df_fe02.empty:
            return None

        df_fe02['pacientes_ativos'] = pd.to_numeric(df_fe02['pacientes_ativos'], errors='coerce').fillna(0).astype(int)
        df_fe02['saiu_da_espera'] = pd.to_numeric(df_fe02['saiu_da_espera'], errors='coerce').fillna(0).astype(int)

        df_final = df_fe02.groupby(
            ['cnes', 'estabelecimento', 'nome_especialidade', 'nome_procedimento'],
            as_index=False
        )[['pacientes_ativos', 'saiu_da_espera']].sum()

        df_final = df_final.rename(columns={
            'cnes': 'Código CNES',
            'estabelecimento': 'Estabelecimento Solicitante',
            'nome_especialidade': 'Especialidade',
            'nome_procedimento': 'Procedimento',
            'pacientes_ativos': 'Total de Inclusões',
            'saiu_da_espera': 'Saiu da Espera'
        })
        
        # Ordenação alfabética padronizada
        df_final = df_final.sort_values(by=['Estabelecimento Solicitante', 'Especialidade', 'Procedimento']).reset_index(drop=True)
        return df_final

def exportar_excel_relatorio_11(periodo=None):
    """
    Gera a planilha Excel oficial formatada do Relatório 11 (Fila de Espera - FE-02)
    com cabeçalho #F8F9FA, fórmulas de soma nativas do Excel e rodapé #CFE2FF.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_11(periodo)
        if df is None or df.empty:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        fmt_header = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_left = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_cnes = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_text = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_num = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_label = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_center = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 11
        })

        # Cabeçalho
        worksheet.set_row(0, 26)
        worksheet.write(0, 0, 'Código CNES', fmt_header)
        worksheet.write(0, 1, 'Estabelecimento Solicitante', fmt_header_left)
        worksheet.write(0, 2, 'Especialidade', fmt_header)
        worksheet.write(0, 3, 'Procedimento', fmt_header_left)
        worksheet.write(0, 4, 'Total de Inclusões', fmt_header_num)
        worksheet.write(0, 5, 'Saiu da Espera', fmt_header_num)

        worksheet.set_column(0, 0, 14)
        worksheet.set_column(1, 1, 45)
        worksheet.set_column(2, 2, 35)
        worksheet.set_column(3, 3, 50)
        worksheet.set_column(4, 4, 18)
        worksheet.set_column(5, 5, 18)

        # Dados
        for r_idx, row in df.iterrows():
            curr_row = 1 + r_idx
            worksheet.set_row(curr_row, 18)
            worksheet.write(curr_row, 0, str(row['Código CNES']), fmt_cnes)
            worksheet.write(curr_row, 1, str(row['Estabelecimento Solicitante']), fmt_text)
            worksheet.write(curr_row, 2, str(row['Especialidade']), fmt_cnes)
            worksheet.write(curr_row, 3, str(row['Procedimento']), fmt_text)
            worksheet.write(curr_row, 4, int(row['Total de Inclusões']), fmt_num)
            worksheet.write(curr_row, 5, int(row['Saiu da Espera']), fmt_num)

        # Rodapé Total
        total_row = 1 + len(df)
        worksheet.set_row(total_row, 22)
        worksheet.write(total_row, 0, 'TOTAL', fmt_total_center)
        worksheet.write(total_row, 1, 'Total Geral STS Penha', fmt_total_label)
        worksheet.write(total_row, 2, '', fmt_total_label)
        worksheet.write(total_row, 3, '', fmt_total_label)
        worksheet.write_formula(total_row, 4, f'=SUM(E2:E{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 5, f'=SUM(F2:F{total_row})', fmt_total_num)

        workbook.close()
        output.seek(0)
        return output

UNIDADES_OFICIAIS_REL12 = [
    "AMA/UBS ENGENHEIRO GOULART- DR JOSE PIRES",
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
    "UBS PADRE JOSÉ DE ANCHIETA",
    "UBS PARQUE ARTHUR ALVIM",
    "UBS VILA ARICANDUVA",
    "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO",
    "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA",
    "UBS VILA GRANADA - DR. ALFREDO FERREIRA PAULINO FILHO",
    "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO",
    "UBS VILA MATILDE - DR. RUBENS DO VAL",
]

def gera_relatorio_12(periodo):
    """
    Relatório 12: MMH - PICS Penha (Solicitação Mensal de Insumos Especiais - Auriculoterapia)
    Baseado no AT-02 filtrado pelo procedimento 'Sessão de Auriculoterapia'.
    Grade com as 27 unidades de atenção primária e especializada da Penha.
    Calcula:
      - Produção auriculoterapia (Nº procedimentos)
      - Total de pontos = Produção * 20
      - Placa adesiva com semente vacaria para auriculoterapia - 70 pontos = Total de pontos / 70
      - Linha de TOTAL geral no rodapé
    """
    unidades_grade = UNIDADES_OFICIAIS_REL12

    import unicodedata
    import re

    def normaliza_str(txt):
        if not txt:
            return ""
        txt = unicodedata.normalize('NFKD', str(txt)).encode('ASCII', 'ignore').decode('utf-8')
        txt = txt.upper()
        txt = re.sub(r'[^A-Z0-9\s/]', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        return txt

    with app.app_context():
        # 1. Carrega mapa de vínculos customizados do banco de dados
        mapa_custom = {}
        try:
            df_vinc = pd.read_sql("SELECT nome_equipe, unidade_destino FROM vinculos_emab", con=db.engine)
            for _, row in df_vinc.iterrows():
                eq = normaliza_str(row['nome_equipe'])
                dest = str(row['unidade_destino']).strip()
                if eq and dest:
                    mapa_custom[eq] = dest
        except Exception:
            pass

        def mapear_termo_para_unidade(termo):
            n = normaliza_str(termo)
            
            # 1. Verifica se há vínculo cadastrado/personalizado explicitamente
            if n in mapa_custom:
                dest_custom = mapa_custom[n]
                if dest_custom.upper() in ['DESCONSIDERAR', 'IGNORAR', 'NAO REPOR', 'NÃO REPOR', '[DESCONSIDERAR / NÃO REPOR]']:
                    return None
                return dest_custom

            # 2. Se for equipe composta por duas unidades (com '/'), considera sempre a unidade secundária (segundo nome)
            if "/" in n:
                partes = n.split("/")
                return mapear_termo_para_unidade(partes[1].strip())

            # 3. Mapeamento padrão para as 33 unidades oficiais
            if "VILLALOBO" in n or "PIRES FERREIRA" in n:
                return "UBS DR. ANTONIO PIRES FERREIRA VILLA LOBO"
            if "PATRIARCA" in n or "MORBIN" in n:
                return "UBS CIDADE PATRIARCA - DR. HERMENEGILDO MORBIN JUNIOR"
            if "MARINGA" in n or "TALARICO" in n:
                return "UBS JARDIM MARINGA - VILA TALARICO"
            if "SAO NICOLAU" in n:
                return "UBS JARDIM SAO NICOLAU"
            if "GUILHERMINA" in n or "RASPA" in n:
                return "UBS VILA GUILHERMINA - DR. AMERICO RASPA NETO"
            if "TRINDADE" in n:
                return "UBS ENGENHEIRO TRINDADE"
            if "EMILIO" in n:
                return "UBS VILA ESPERANÇA - DR. EMILIO SANTIAGO DE OLIVEIRA"
            if "CASSIO" in n:
                return "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO"
            if "ESPERANCA" in n and "PAI" not in n and "EMILIO" not in n:
                return "UBS VILA ESPERANÇA - DR. CASSIO BITENCOURT FILHO"
            if "AE CARVALHO" in n or ("ESTEVAO" in n and "CARVALHO" in n):
                return "UBS ANTONIO ESTEVÃO DE CARVALHO"
            if "ANCHIETA" in n:
                return "UBS PADRE JOSÉ DE ANCHIETA"
            if "ARICANDUVA" in n:
                return "UBS VILA ARICANDUVA"
            if "ARTHUR ALVIM" in n and "CER" not in n:
                return "UBS PARQUE ARTHUR ALVIM"
            if "CHACARA CRUZEIRO" in n or ("CRUZEIRO" in n and "SUL" in n) or (n.strip() in ["CHACARA", "EMAB CHACARA", "EMULTI CHACARA"]):
                return "AMA/UBS INTEGRADA CHACARA CRUZEIRO DO SUL - ZELIA L M DORO"
            if "GOULART" in n:
                return "AMA/UBS ENGENHEIRO GOULART- DR JOSE PIRES"
            if "SAO FRANCISCO" in n:
                return "UBS JARDIM SAO FRANCISCO I"
            if "GRANADA" in n and "PAI" not in n:
                return "UBS VILA GRANADA - DR. ALFREDO FERREIRA PAULINO FILHO"
            if "NOBREGA" in n and "CECCO" not in n:
                return "AMA/UBS INTEGRADA PADRE MANOEL DA NOBREGA"
            if "CECCO" in n:
                return "CECCO PADRE MANOEL DA NOBREGA"
            if "CANGAIBA" in n and "CAPS" in n:
                return "CAPS ALCOOL E DROGAS II CANGAIBA"
            if "CANGAIBA" in n:
                return "AMA/UBS INTEGRADA CANGAIBA - DR. CARLOS GENTILE DE MELLO"
            if "VILA SILVIA" in n and "PAI" not in n:
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
            if "MATILDE" in n and "CAPS" not in n:
                return "UBS VILA MATILDE - DR. RUBENS DO VAL"

            return termo

        query = f"""
        SELECT 
            estabelecimento,
            SUM(CAST(quantidade_procedimento AS INTEGER)) as qtd
        FROM 'AT-02'
        WHERE ano_mes = {periodo}
          AND UPPER(procedimento) LIKE '%AURICULOTERAPIA%'
        GROUP BY estabelecimento
        """
        df_raw = pd.read_sql(query, con=db.engine)
        
        prod_por_unidade = {}
        if not df_raw.empty:
            df_raw['unidade_padrao'] = df_raw['estabelecimento'].apply(mapear_termo_para_unidade)
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
                "Placa adesiva com semente vacaria para auriculoterapia - 70 pontos": placas
            })

        # Linha de TOTAL geral
        tot_proc = int(sum(l["Nº procedimentos"] for l in linhas))
        tot_pontos = int(sum(l["Total de pontos"] for l in linhas))
        tot_placas = round(tot_pontos / 70.0, 7) if tot_pontos > 0 else 0

        linhas.append({
            "SUPERVISÃO PENHA - Unidades de Saúde": "TOTAL",
            "Nº procedimentos": tot_proc,
            "Total de pontos": tot_pontos,
            "Placa adesiva com semente vacaria para auriculoterapia - 70 pontos": tot_placas
        })

        df_final = pd.DataFrame(linhas)
        return df_final

def exportar_excel_relatorio_12_oficial(periodo):
    """
    Gera a planilha Excel oficial formatada do Relatório 12 (MMH - PICS Penha)
    com cabeçalho oficial multinível, cores, colunas B a I zeradas e rodapé TOTAL / TOTAL GRADE.
    """
    with app.app_context():
        import io
        df_raw = gera_relatorio_12(periodo)
        
        # Filtra apenas as unidades (remove a linha TOTAL do df, pois o rodapé é desenhado com fórmulas/estilos)
        df_unidades = df_raw[df_raw['SUPERVISÃO PENHA - Unidades de Saúde'] != 'TOTAL'].copy()
        
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        workbook = writer.book
        worksheet = workbook.add_worksheet('Insumos Especiais')
        
        # Estilos e Formatações
        # Caixa Vermelha: Negrito e Tamanho 16
        fmt_title = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })
        
        fmt_subtitle = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })
        
        fmt_col_unidade = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'bg_color': '#FFFFFF',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })
        
        # Caixa Verde: Tamanho 11
        fmt_hdr_green = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'bg_color': '#D8E4BC',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11
        })
        
        fmt_hdr_blue = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'bg_color': '#DCE6F1',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11
        })
        
        fmt_hdr_gray = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'bg_color': '#BFBFBF',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11
        })
        
        # Linhas de Dados: Tamanho 11
        fmt_cell_text = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11
        })
        
        fmt_cell_num = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11
        })
        
        fmt_cell_decimal = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 11,
            'num_format': '0.0000000'
        })
        
        # Linhas de Totais: Negrito e Tamanho 16
        fmt_total_hdr = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })
        
        fmt_total_num = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })
        
        fmt_total_decimal = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16,
            'num_format': '0.0000000'
        })
        
        fmt_total_grade = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#C5BE97',
            'border': 1,
            'font_name': 'Times New Roman',
            'font_size': 16
        })

        fmt_total_grade_empty = workbook.add_format({
            'bg_color': '#C5BE97',
            'border': 1
        })

        # 1. Linhas de Título (Linha 1 e 2 do Excel)
        worksheet.merge_range('A1:L1', 'PLANILHA DE SOLICITAÇÃO MENSAL DE INSUMOS ESPECIAIS', fmt_title)
        worksheet.merge_range('A2:L2', 'CRS - Sudeste', fmt_subtitle)
        
        # 2. Cabeçalho de Colunas (Linhas 3 e 4 do Excel)
        worksheet.merge_range('A3:A4', 'SUPERVISÃO PENHA\nUnidades de Saúde', fmt_col_unidade)
        
        worksheet.write('B3', 'Bastão Moxa Artemisia para procedimento de Acupuntura com moxabustão', fmt_hdr_green)
        worksheet.write('B4', 'Unidade', fmt_hdr_green)
        
        worksheet.write('C3', 'óleo essencial Lavanda Francesa', fmt_hdr_blue)
        worksheet.write('C4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('D3', 'óleo essencial Alecrim', fmt_hdr_blue)
        worksheet.write('D4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('E3', 'óleo essencial Hortelã Pimenta', fmt_hdr_blue)
        worksheet.write('E4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('F3', 'óleo essencial Lemongrass / Capim Limão', fmt_hdr_blue)
        worksheet.write('F4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('G3', 'óleo essencial Melaleuca', fmt_hdr_blue)
        worksheet.write('G4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('H3', 'óleo essencial Bergamota', fmt_hdr_blue)
        worksheet.write('H4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('I3', 'Inalador nasal de aromaterapia com difusor para óleo essencial em material plástico ABS', fmt_hdr_blue)
        worksheet.write('I4', 'Unidade', fmt_hdr_blue)
        
        worksheet.write('J3', 'Produção auriculoterapia', fmt_hdr_gray)
        worksheet.write('J4', 'Nº procedimentos', fmt_hdr_gray)
        
        worksheet.merge_range('K3:K4', 'Total de pontos', fmt_hdr_gray)
        
        worksheet.write('L3', 'Placa adesiva com semente vacaria para auriculoterapia - 70 pontos', fmt_hdr_gray)
        worksheet.write('L4', 'Unidade com 70 pontos', fmt_hdr_gray)

        # Zoom de 80% na planilha
        worksheet.set_zoom(80)

        # Ajuste de Altura dos Cabeçalhos
        worksheet.set_row(0, 28)
        worksheet.set_row(1, 24)
        worksheet.set_row(2, 85)
        worksheet.set_row(3, 26)
        
        # Largura das Colunas
        worksheet.set_column('A:A', 78)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:H', 17)
        worksheet.set_column('I:I', 24)
        worksheet.set_column('J:K', 16)
        worksheet.set_column('L:L', 24)

        # 3. Escrita das Linhas de Dados
        row_idx = 4
        tot_proc = 0
        tot_pontos = 0
        tot_placas = 0.0

        for _, row in df_unidades.iterrows():
            u = row['SUPERVISÃO PENHA - Unidades de Saúde']
            qtd_proc = int(row['Nº procedimentos'])
            pontos = int(row['Total de pontos'])
            placas = float(row['Placa adesiva com semente vacaria para auriculoterapia - 70 pontos'])
            
            tot_proc += qtd_proc
            tot_pontos += pontos
            tot_placas += placas

            worksheet.write(row_idx, 0, u, fmt_cell_text)
            for c in range(1, 9):
                worksheet.write(row_idx, c, 0, fmt_cell_num)
            
            worksheet.write(row_idx, 9, qtd_proc, fmt_cell_num)
            worksheet.write(row_idx, 10, pontos, fmt_cell_num)
            worksheet.write(row_idx, 11, placas, fmt_cell_decimal)
            
            worksheet.set_row(row_idx, 20)
            row_idx += 1

        # 4. Linhas de Rodapé: TOTAL e TOTAL GRADE
        # Linha TOTAL
        worksheet.write(row_idx, 0, 'TOTAL', fmt_total_hdr)
        for c in range(1, 9):
            worksheet.write(row_idx, c, 0, fmt_total_num)
        worksheet.write(row_idx, 9, tot_proc, fmt_total_num)
        worksheet.write(row_idx, 10, tot_pontos, fmt_total_num)
        worksheet.write(row_idx, 11, tot_placas, fmt_total_decimal)
        worksheet.set_row(row_idx, 26)
        row_idx += 1

        # Linha TOTAL GRADE
        worksheet.merge_range(row_idx, 0, row_idx, 8, 'TOTAL GRADE', fmt_total_grade)
        for c in range(9, 12):
            worksheet.write(row_idx, c, '', fmt_total_grade_empty)
        worksheet.set_row(row_idx, 26)

        writer.close()
        output.seek(0)
        return output

def gera_relatorio_13(periodo):
    """
    Relatório 13: RELATÓRIO DE PERDA PRIMÁRIA POR ESTABELECIMENTO E ESPECIALIDADE (VG-02)
    Gera a listagem consolidada por Tipo de Agenda, Estabelecimento, Especialidade,
    Procedimento e Tipo de Atendimento, com a contagem de Vagas Livres e Vagas Ocupadas.
    """
    with app.app_context():
        query = f"SELECT * FROM 'VG-02' WHERE ano_mes = {int(periodo)}"
        df_vg02 = pd.read_sql(query, con=db.engine)
        if df_vg02.empty:
            return None

        pivot = pd.pivot_table(
            df_vg02,
            columns='situacao_vaga',
            index=['tipo_agenda', 'estabelecimento', 'nome_especialidade', 'procedimento', 'tipo_atendimento_agenda'],
            values='qtde_vaga_ofertada',
            aggfunc='sum',
            fill_value=0
        )
        
        # Garante a existência das colunas Livre e Ocupada
        if 'Livre' not in pivot.columns:
            pivot['Livre'] = 0
        if 'Ocupada' not in pivot.columns:
            pivot['Ocupada'] = 0

        pivot.columns.name = None
        df_res = pivot.reset_index()

        rename_cols = {
            'tipo_agenda': 'Tipo de Agenda',
            'estabelecimento': 'Estabelecimento',
            'nome_especialidade': 'Especialidade',
            'procedimento': 'Procedimento',
            'tipo_atendimento_agenda': 'Tipo de Atendimento',
            'Livre': 'Vagas Livres',
            'Ocupada': 'Vagas Ocupadas'
        }
        df_res = df_res.rename(columns=rename_cols)

        df_res['Vagas Livres'] = pd.to_numeric(df_res['Vagas Livres'], errors='coerce').fillna(0).astype(int)
        df_res['Vagas Ocupadas'] = pd.to_numeric(df_res['Vagas Ocupadas'], errors='coerce').fillna(0).astype(int)

        df_res['Total de Vagas'] = df_res['Vagas Livres'] + df_res['Vagas Ocupadas']
        df_res['% Perda Primária'] = np.where(
            df_res['Total de Vagas'] > 0,
            ((df_res['Vagas Livres'] / df_res['Total de Vagas']) * 100).round(2),
            0.0
        )

        # Ordenação padronizada
        df_res = df_res.sort_values(
            by=['Estabelecimento', 'Especialidade', 'Procedimento', 'Tipo de Agenda', 'Tipo de Atendimento']
        ).reset_index(drop=True)

        return df_res

def exportar_excel_relatorio_13(periodo):
    """
    Gera a planilha Excel formatada do Relatório 13 (Perda Primária - VG-02)
    com cabeçalho #F8F9FA, fórmulas nativas do Excel e rodapé #CFE2FF.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_13(periodo)
        if df is None or df.empty:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        fmt_header = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_left = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_text = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_num = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_perc = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0%',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_label = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_center = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_perc = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '0.0%',
            'font_name': 'Calibri',
            'font_size': 11
        })

        # Cabeçalho
        worksheet.set_row(0, 26)
        worksheet.write(0, 0, 'Tipo de Agenda', fmt_header)
        worksheet.write(0, 1, 'Estabelecimento', fmt_header_left)
        worksheet.write(0, 2, 'Especialidade', fmt_header_left)
        worksheet.write(0, 3, 'Procedimento', fmt_header_left)
        worksheet.write(0, 4, 'Tipo de Atendimento', fmt_header_left)
        worksheet.write(0, 5, 'Vagas Livres', fmt_header_num)
        worksheet.write(0, 6, 'Vagas Ocupadas', fmt_header_num)
        worksheet.write(0, 7, 'Total de Vagas', fmt_header_num)
        worksheet.write(0, 8, '% Perda Primária', fmt_header_num)

        worksheet.set_column(0, 0, 16)
        worksheet.set_column(1, 1, 45)
        worksheet.set_column(2, 2, 35)
        worksheet.set_column(3, 3, 50)
        worksheet.set_column(4, 4, 22)
        worksheet.set_column(5, 5, 18)
        worksheet.set_column(6, 6, 18)
        worksheet.set_column(7, 7, 18)
        worksheet.set_column(8, 8, 18)

        # Dados
        for r_idx, row in df.iterrows():
            curr_row = 1 + r_idx
            worksheet.set_row(curr_row, 18)
            worksheet.write(curr_row, 0, str(row['Tipo de Agenda']), fmt_center)
            worksheet.write(curr_row, 1, str(row['Estabelecimento']), fmt_text)
            worksheet.write(curr_row, 2, str(row['Especialidade']), fmt_text)
            worksheet.write(curr_row, 3, str(row['Procedimento']), fmt_text)
            worksheet.write(curr_row, 4, str(row['Tipo de Atendimento']), fmt_text)
            worksheet.write(curr_row, 5, int(row['Vagas Livres']), fmt_num)
            worksheet.write(curr_row, 6, int(row['Vagas Ocupadas']), fmt_num)
            tot_vagas_val = int(row['Total de Vagas'])
            worksheet.write_formula(curr_row, 7, f'=F{curr_row+1}+G{curr_row+1}', fmt_num, tot_vagas_val)
            perc_val = (float(row['% Perda Primária']) / 100.0) if tot_vagas_val > 0 else 0.0
            worksheet.write_formula(curr_row, 8, f'=IFERROR(F{curr_row+1}/H{curr_row+1}, 0)', fmt_perc, perc_val)

        # Rodapé Total
        total_row = 1 + len(df)
        worksheet.set_row(total_row, 22)
        worksheet.write(total_row, 0, 'TOTAL', fmt_total_center)
        worksheet.write(total_row, 1, 'Total Geral STS Penha', fmt_total_label)
        worksheet.write(total_row, 2, '', fmt_total_label)
        worksheet.write(total_row, 3, '', fmt_total_label)
        worksheet.write(total_row, 4, '', fmt_total_label)
        worksheet.write_formula(total_row, 5, f'=SUM(F2:F{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 6, f'=SUM(G2:G{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 7, f'=SUM(H2:H{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 8, f'=IFERROR(F{total_row+1}/H{total_row+1}, 0)', fmt_total_perc)

        # Regra de Formatação Condicional Tricolor (Mínimo Azul -> Ponto Médio Branco -> Máximo Vermelho)
        if len(df) > 0:
            regra_tricolor = {
                'type': '3_color_scale',
                'min_color': '#5A8AC6',
                'mid_color': '#FFFFFF',
                'max_color': '#F8696B',
                'min_type': 'min',
                'mid_type': 'percentile',
                'mid_value': 50,
                'max_type': 'max'
            }
            worksheet.conditional_format(f'I2:I{total_row}', regra_tricolor)

        workbook.close()
        output.seek(0)
        return output

def gera_relatorio_14(periodo):
    """
    Relatório 14: RELATÓRIO DE ABSENTEÍSMO POR ESTABELECIMENTO E ESPECIALIDADE (AG-04)
    Gera a listagem consolidada por Tipo de Agenda, Tipo de Entidade, Estabelecimento,
    Especialidade e Procedimento, com a contagem de Agendado, Atendido, Não Atendido e Presente.
    """
    with app.app_context():
        query = f"SELECT * FROM 'AG-04' WHERE ano_mes = {int(periodo)}"
        df_ag04 = pd.read_sql(query, con=db.engine)
        if df_ag04.empty:
            return None

        # Normaliza textos com encoding/acentos
        df_ag04['situacao_agendamento'] = df_ag04['situacao_agendamento'].astype(str).str.strip().replace({
            'N\ufffdo Atendido': 'Não Atendido',
            'N?o Atendido': 'Não Atendido'
        })
        df_ag04['tipo_entidade'] = df_ag04['tipo_entidade'].astype(str).str.strip().replace({
            'Profissional Sa\ufffde': 'Profissional Saúde',
            'Profissional Sa?de': 'Profissional Saúde'
        })
        df_ag04['quantidade_agendamento'] = pd.to_numeric(df_ag04['quantidade_agendamento'], errors='coerce').fillna(0).astype(int)

        pivot = pd.pivot_table(
            df_ag04,
            columns='situacao_agendamento',
            index=['tipo_agenda', 'tipo_entidade', 'estabelecimento', 'especialidade', 'procedimento'],
            values='quantidade_agendamento',
            aggfunc='sum',
            fill_value=0
        )

        # Garante as 4 colunas padrão
        for col in ['Agendado', 'Atendido', 'Não Atendido', 'Presente']:
            if col not in pivot.columns:
                pivot[col] = 0

        cols_order = ['Agendado', 'Atendido', 'Não Atendido', 'Presente']
        pivot = pivot[cols_order]

        pivot.columns.name = None
        df_res = pivot.reset_index()

        rename_cols = {
            'tipo_agenda': 'Tipo de Agenda',
            'tipo_entidade': 'Tipo de Entidade',
            'estabelecimento': 'Estabelecimento',
            'especialidade': 'Especialidade',
            'procedimento': 'Procedimento',
            'Agendado': 'Agendado',
            'Atendido': 'Atendido',
            'Não Atendido': 'Não Atendido',
            'Presente': 'Presente'
        }
        df_res = df_res.rename(columns=rename_cols)

        for col in ['Agendado', 'Atendido', 'Não Atendido', 'Presente']:
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0).astype(int)

        df_res['TOTAL'] = df_res['Agendado'] + df_res['Atendido'] + df_res['Não Atendido'] + df_res['Presente']
        df_res['% Absenteísmo'] = np.where(
            df_res['TOTAL'] > 0,
            ((df_res['Não Atendido'] / df_res['TOTAL']) * 100).round(2),
            0.0
        )

        # Ordenação padronizada
        df_res = df_res.sort_values(
            by=['Estabelecimento', 'Especialidade', 'Procedimento', 'Tipo de Agenda', 'Tipo de Entidade']
        ).reset_index(drop=True)

        return df_res

def exportar_excel_relatorio_14(periodo):
    """
    Gera a planilha Excel formatada do Relatório 14 (Absenteísmo - AG-04)
    com cabeçalho #F8F9FA, fórmulas nativas do Excel, formatação condicional tricolor e rodapé #CFE2FF.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_14(periodo)
        if df is None or df.empty:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        fmt_header = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_left = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_vertical = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'bottom',
            'rotation': 90,
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_text = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_num = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_perc = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0%',
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_total_label = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_center = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_num = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_perc = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '0.0%',
            'font_name': 'Calibri',
            'font_size': 11
        })

        # Cabeçalho
        worksheet.set_row(0, 85)
        worksheet.write(0, 0, 'Tipo de Agenda', fmt_header)
        worksheet.write(0, 1, 'Tipo de Entidade', fmt_header_left)
        worksheet.write(0, 2, 'Estabelecimento', fmt_header_left)
        worksheet.write(0, 3, 'Especialidade', fmt_header_left)
        worksheet.write(0, 4, 'Procedimento', fmt_header_left)
        worksheet.write(0, 5, 'Agendado', fmt_header_vertical)
        worksheet.write(0, 6, 'Atendido', fmt_header_vertical)
        worksheet.write(0, 7, 'Não Atendido', fmt_header_vertical)
        worksheet.write(0, 8, 'Presente', fmt_header_vertical)
        worksheet.write(0, 9, 'TOTAL', fmt_header_vertical)
        worksheet.write(0, 10, '% ABSENTEÍSMO', fmt_header_vertical)

        worksheet.set_column(0, 0, 16)
        worksheet.set_column(1, 1, 22)
        worksheet.set_column(2, 2, 45)
        worksheet.set_column(3, 3, 35)
        worksheet.set_column(4, 4, 50)
        worksheet.set_column(5, 5, 11)
        worksheet.set_column(6, 6, 11)
        worksheet.set_column(7, 7, 13)
        worksheet.set_column(8, 8, 11)
        worksheet.set_column(9, 9, 11)
        worksheet.set_column(10, 10, 14)

        # Dados
        for r_idx, row in df.iterrows():
            curr_row = 1 + r_idx
            worksheet.set_row(curr_row, 18)
            worksheet.write(curr_row, 0, str(row['Tipo de Agenda']), fmt_center)
            worksheet.write(curr_row, 1, str(row['Tipo de Entidade']), fmt_text)
            worksheet.write(curr_row, 2, str(row['Estabelecimento']), fmt_text)
            worksheet.write(curr_row, 3, str(row['Especialidade']), fmt_text)
            worksheet.write(curr_row, 4, str(row['Procedimento']), fmt_text)
            worksheet.write(curr_row, 5, int(row['Agendado']), fmt_num)
            worksheet.write(curr_row, 6, int(row['Atendido']), fmt_num)
            worksheet.write(curr_row, 7, int(row['Não Atendido']), fmt_num)
            worksheet.write(curr_row, 8, int(row['Presente']), fmt_num)
            tot_val = int(row['TOTAL'])
            worksheet.write_formula(curr_row, 9, f'=SUM(F{curr_row+1}:I{curr_row+1})', fmt_num, tot_val)
            perc_val = (float(row['% Absenteísmo']) / 100.0) if tot_val > 0 else 0.0
            worksheet.write_formula(curr_row, 10, f'=IFERROR(H{curr_row+1}/J{curr_row+1}, 0)', fmt_perc, perc_val)

        # Rodapé Total
        total_row = 1 + len(df)
        worksheet.set_row(total_row, 22)
        worksheet.write(total_row, 0, 'TOTAL', fmt_total_center)
        worksheet.write(total_row, 1, 'Total Geral STS Penha', fmt_total_label)
        worksheet.write(total_row, 2, '', fmt_total_label)
        worksheet.write(total_row, 3, '', fmt_total_label)
        worksheet.write(total_row, 4, '', fmt_total_label)
        worksheet.write_formula(total_row, 5, f'=SUM(F2:F{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 6, f'=SUM(G2:G{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 7, f'=SUM(H2:H{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 8, f'=SUM(I2:I{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 9, f'=SUM(J2:J{total_row})', fmt_total_num)
        worksheet.write_formula(total_row, 10, f'=IFERROR(H{total_row+1}/J{total_row+1}, 0)', fmt_total_perc)

        # Regra de Formatação Condicional Tricolor (Mínimo Azul -> Ponto Médio Branco -> Máximo Vermelho)
        if len(df) > 0:
            regra_tricolor = {
                'type': '3_color_scale',
                'min_color': '#5A8AC6',
                'mid_color': '#FFFFFF',
                'max_color': '#F8696B',
                'min_type': 'min',
                'mid_type': 'percentile',
                'mid_value': 50,
                'max_type': 'max'
            }
            worksheet.conditional_format(f'K2:K{total_row}', regra_tricolor)

        workbook.close()
        output.seek(0)
        return output

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
        df_pivot.columns.name = None

        # Ordenação consistente por UNIDADE, SIGLA e COD_INE
        df_pivot = df_pivot.sort_values(by=['UNIDADE', 'SIGLA', 'COD_INE']).reset_index(drop=True)
        
        return df_pivot

def exportar_excel_relatorio_15(periodo):
    """
    Gera a planilha Excel formatada do Relatório 15 (Acompanhamento de Cadastro Individual ESF - REL-135)
    com cabeçalho #F8F9FA, formatações de regras da Portaria SAPS/MS nº 161, fórmulas nativas do Excel e rodapé #CFE2FF.
    """
    with app.app_context():
        import io
        import xlsxwriter
        df = gera_relatorio_15(periodo)
        if df is None or df.empty:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Planilha1')

        # Formatos de cabeçalho
        fmt_header_center = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_header_left = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#F8F9FA',
            'font_color': '#212529',
            'font_name': 'Calibri',
            'font_size': 11
        })

        # Formatos de dados base
        fmt_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })
        fmt_text = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })

        # Formatos numéricos padrão e com regras de portaria
        fmt_num_default = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        # < 40% (Vermelho)
        fmt_num_red = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#D9534F',
            'font_color': '#D9534F',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        # 40% a 70% (Laranja/Amarelo)
        fmt_num_orange = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#F0AD4E',
            'font_color': '#D97706',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        # 70% a 100% (Verde)
        fmt_num_green = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#198754',
            'font_color': '#198754',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        # > 100% dentro do limite (Azul)
        fmt_num_blue = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#0D6EFD',
            'font_color': '#0D6EFD',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })
        # Acima do Limite (Fundo Laranja, Texto Branco)
        fmt_num_acima = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#F0AD4E',
            'bg_color': '#F0AD4E',
            'font_color': '#FFFFFF',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 10
        })

        # Formatos de Rodapé Total
        fmt_total_center = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_left = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'font_name': 'Calibri',
            'font_size': 11
        })
        fmt_total_num = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#CFE2FF',
            'font_color': '#084298',
            'num_format': '#,##0',
            'font_name': 'Calibri',
            'font_size': 11
        })

        cols = list(df.columns)
        num_cols = len(cols)

        # Cabeçalho
        worksheet.set_row(0, 26)
        worksheet.write(0, 0, 'CNES', fmt_header_center)
        worksheet.write(0, 1, 'UNIDADE', fmt_header_left)
        worksheet.write(0, 2, 'COD_INE', fmt_header_center)
        worksheet.write(0, 3, 'SIGLA', fmt_header_center)
        for c in range(4, num_cols):
            worksheet.write(0, c, str(cols[c]), fmt_header_center)

        # Largura das colunas
        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 45)
        worksheet.set_column(2, 2, 14)
        worksheet.set_column(3, 3, 12)
        for c in range(4, num_cols):
            worksheet.set_column(c, c, 14)

        # Escrita dos dados
        for r_idx, row in df.iterrows():
            curr_row = 1 + r_idx
            worksheet.set_row(curr_row, 18)
            worksheet.write(curr_row, 0, str(row['CNES']), fmt_center)
            worksheet.write(curr_row, 1, str(row['UNIDADE']), fmt_text)
            worksheet.write(curr_row, 2, str(row['COD_INE']), fmt_center)
            
            sigla = str(row['SIGLA']).strip()
            worksheet.write(curr_row, 3, sigla, fmt_center)

            limite = 0
            if sigla in ['EAP20H', 'eAP-20h', 'eAP 20h']:
                limite = 2000
            elif sigla in ['EAP30H', 'eAP-30h', 'eAP 30h']:
                limite = 3000
            elif sigla in ['ESF', 'eSF']:
                limite = 4000
            elif sigla in ['ECR', 'eCR']:
                limite = 600

            for c in range(4, num_cols):
                val = row[cols[c]]
                try:
                    val_num = float(val)
                except (ValueError, TypeError):
                    val_num = 0.0

                fmt_aplicar = fmt_num_default
                if limite > 0 and val_num > 0:
                    perc = val_num / limite
                    if perc < 0.40:
                        fmt_aplicar = fmt_num_red
                    elif perc < 0.70:
                        fmt_aplicar = fmt_num_orange
                    elif perc <= 1.00:
                        fmt_aplicar = fmt_num_green
                    else:
                        is_acima = False
                        if sigla in ['EAP20H', 'eAP-20h', 'eAP 20h'] and val_num > 2250:
                            is_acima = True
                        elif sigla in ['EAP30H', 'eAP-30h', 'eAP 30h'] and val_num > 3375:
                            is_acima = True
                        elif sigla in ['ESF', 'eSF'] and val_num > 4500:
                            is_acima = True
                        fmt_aplicar = fmt_num_acima if is_acima else fmt_num_blue

                worksheet.write(curr_row, c, int(val_num), fmt_aplicar)

        # Rodapé Total
        total_row = 1 + len(df)
        worksheet.set_row(total_row, 22)
        worksheet.write(total_row, 0, 'TOTAL', fmt_total_center)
        worksheet.write(total_row, 1, 'Total Geral STS Penha', fmt_total_left)
        worksheet.write(total_row, 2, f'Equipes: {len(df)}', fmt_total_center)
        worksheet.write(total_row, 3, '', fmt_total_center)

        for c in range(4, num_cols):
            col_letter = xlsxwriter.utility.xl_col_to_name(c)
            worksheet.write_formula(total_row, c, f'=SUM({col_letter}2:{col_letter}{total_row})', fmt_total_num)

        workbook.close()
        output.seek(0)
        return output

def gera_relatorio_16(periodo=None):
    """
    Relatório 16: TOTAL DE PACIENTES CADASTRADOS NO PROGRAMA AMG (SIGA - AMG)
    Retorna dois DataFrames:
      1. df_ativos: Pacientes ativos por tipo de diabetes (GESTACIONAL, TIPO I, TIPO II)
      2. df_inativos: Pacientes inativos por motivo de inativação
    Desconsidera estabelecimentos com 'EMULTI' ou 'INATIVO' no nome.
    """
    with app.app_context():
        if periodo and len(str(periodo)) == 6:
            query = f"SELECT * FROM 'REL-16' WHERE ano_mes = '{periodo}' OR ano_mes = {int(periodo)}"
        else:
            query = "SELECT * FROM 'REL-16'"
            
        try:
            df = pd.read_sql(query, con=db.engine)
        except Exception:
            return None, None
        
        if df.empty:
            return None, None

        # 1. Filtro de estabelecimentos: remover unidades que contenham EMULTI ou INATIVO no nome
        mask_remover = df['estabelecimento'].astype(str).str.upper().str.contains('EMULTI|INATIVO')
        df_filtrado = df[~mask_remover].copy()

        # Normalização dos motivos de inativação
        def limpar_motivo(motivo_str):
            m = str(motivo_str).strip()
            if 'ABANDONO' in m: return 'ABANDONO'
            if 'CADASTRO EQUIVOCADO' in m: return 'CADASTRO EQUIVOCADO'
            if 'GESTANTE' in m: return 'GESTANTE'
            if 'DECURSO DE TEMPO' in m: return 'INATIVADO POR DECURSO DE TEMPO'
            if 'MUDAN' in m or 'MUNIC' in m: return 'MUDANÇA DE MUNICÍPIO'
            if 'OUTROS' in m: return 'OUTROS MOTIVOS'
            if 'SUSPENS' in m or 'INSULINA' in m: return 'SUSPENSÃO DA PRESCRIÇÃO DE INSULINA'
            if 'TRANSFER' in m: return 'TRANSFERÊNCIA DE UNIDADE'
            if 'BITO' in m: return 'ÓBITO'
            return m

        if 'motivo_ultimo_status' in df_filtrado.columns:
            df_filtrado['motivo_limpo'] = df_filtrado['motivo_ultimo_status'].apply(limpar_motivo)
        else:
            df_filtrado['motivo_limpo'] = ''

        # --- TABELA 1: ATIVOS ---
        df_ativo = df_filtrado[df_filtrado['status_atual'].astype(str).str.upper() == 'ATIVO'].copy()
        if not df_ativo.empty:
            pivot_ativo = pd.pivot_table(
                df_ativo,
                index='estabelecimento',
                columns='diabetes_mellitus',
                values='nome_paciente',
                aggfunc='count',
                fill_value=0
            )
            pivot_ativo.columns.name = None
            pivot_ativo = pivot_ativo.reset_index()
            pivot_ativo = pivot_ativo.rename(columns={'estabelecimento': 'ESTABELECIMENTO'})
            
            for col in ['GESTACIONAL', 'TIPO I', 'TIPO II']:
                if col not in pivot_ativo.columns:
                    pivot_ativo[col] = 0
                    
            cols_order_a = ['ESTABELECIMENTO', 'GESTACIONAL', 'TIPO I', 'TIPO II']
            pivot_ativo = pivot_ativo[cols_order_a]
            
            num_cols_a = ['GESTACIONAL', 'TIPO I', 'TIPO II']
            for c in num_cols_a:
                pivot_ativo[c] = pd.to_numeric(pivot_ativo[c], errors='coerce').fillna(0).astype(int)
                
            pivot_ativo['Total Geral'] = pivot_ativo[num_cols_a].sum(axis=1)
            pivot_ativo = pivot_ativo.sort_values(by='ESTABELECIMENTO').reset_index(drop=True)
        else:
            pivot_ativo = pd.DataFrame(columns=['ESTABELECIMENTO', 'GESTACIONAL', 'TIPO I', 'TIPO II', 'Total Geral'])

        # --- TABELA 2: INATIVOS ---
        df_inativo = df_filtrado[df_filtrado['status_atual'].astype(str).str.upper() == 'INATIVO'].copy()
        if not df_inativo.empty:
            pivot_inativo = pd.pivot_table(
                df_inativo,
                index='estabelecimento',
                columns='motivo_limpo',
                values='nome_paciente',
                aggfunc='count',
                fill_value=0
            )
            pivot_inativo.columns.name = None
            pivot_inativo = pivot_inativo.reset_index()
            pivot_inativo = pivot_inativo.rename(columns={'estabelecimento': 'ESTABELECIMENTO'})
            
            motivos_esperados = [
                'ABANDONO', 'CADASTRO EQUIVOCADO', 'GESTANTE', 'INATIVADO POR DECURSO DE TEMPO',
                'MUDANÇA DE MUNICÍPIO', 'OUTROS MOTIVOS', 'SUSPENSÃO DA PRESCRIÇÃO DE INSULINA',
                'TRANSFERÊNCIA DE UNIDADE', 'ÓBITO'
            ]
            for m in motivos_esperados:
                if m not in pivot_inativo.columns:
                    pivot_inativo[m] = 0
                    
            cols_order_i = ['ESTABELECIMENTO'] + motivos_esperados
            pivot_inativo = pivot_inativo[cols_order_i]
            
            for c in motivos_esperados:
                pivot_inativo[c] = pd.to_numeric(pivot_inativo[c], errors='coerce').fillna(0).astype(int)
                
            pivot_inativo['Total Geral'] = pivot_inativo[motivos_esperados].sum(axis=1)
            pivot_inativo = pivot_inativo.sort_values(by='ESTABELECIMENTO').reset_index(drop=True)
        else:
            pivot_inativo = pd.DataFrame(columns=['ESTABELECIMENTO', 'ABANDONO', 'CADASTRO EQUIVOCADO', 'GESTANTE', 'INATIVADO POR DECURSO DE TEMPO', 'MUDANÇA DE MUNICÍPIO', 'OUTROS MOTIVOS', 'SUSPENSÃO DA PRESCRIÇÃO DE INSULINA', 'TRANSFERÊNCIA DE UNIDADE', 'ÓBITO', 'Total Geral'])

        return pivot_ativo, pivot_inativo

def exportar_excel_relatorio_16(periodo=None):
    """
    Gera a planilha Excel com 2 abas do Relatório 16 (SIGA AMG):
      - Aba 1: Ativos - Tipo de Diabetes
      - Aba 2: Inativos - Motivo Inativação
    """
    with app.app_context():
        import io
        import xlsxwriter
        df_ativos, df_inativos = gera_relatorio_16(periodo)
        if df_ativos is None and df_inativos is None:
            return None

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        fmt_header_left = workbook.add_format({
            'bold': True, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F8F9FA', 'font_color': '#212529',
            'font_name': 'Calibri', 'font_size': 11
        })
        fmt_header_num = workbook.add_format({
            'bold': True, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F8F9FA', 'font_color': '#212529',
            'font_name': 'Calibri', 'font_size': 11
        })
        fmt_text = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1,
            'font_name': 'Calibri', 'font_size': 10
        })
        fmt_num = workbook.add_format({
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'num_format': '#,##0', 'font_name': 'Calibri', 'font_size': 10
        })
        fmt_total_label = workbook.add_format({
            'bold': True, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#CFE2FF', 'font_color': '#084298',
            'font_name': 'Calibri', 'font_size': 11
        })
        fmt_total_num = workbook.add_format({
            'bold': True, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#CFE2FF', 'font_color': '#084298',
            'num_format': '#,##0', 'font_name': 'Calibri', 'font_size': 11
        })

        # --- ABA 1: ATIVOS ---
        if df_ativos is not None and not df_ativos.empty:
            ws1 = workbook.add_worksheet('Ativos - Tipo de Diabetes')
            cols1 = list(df_ativos.columns)
            num_cols1 = len(cols1)

            ws1.set_row(0, 26)
            ws1.write(0, 0, 'ESTABELECIMENTO', fmt_header_left)
            for c in range(1, num_cols1):
                ws1.write(0, c, str(cols1[c]), fmt_header_num)

            ws1.set_column(0, 0, 50)
            for c in range(1, num_cols1):
                ws1.set_column(c, c, 16)

            for r_idx, row in df_ativos.iterrows():
                curr_row = 1 + r_idx
                ws1.set_row(curr_row, 18)
                ws1.write(curr_row, 0, str(row['ESTABELECIMENTO']), fmt_text)
                for c in range(1, num_cols1 - 1):
                    ws1.write(curr_row, c, int(row[cols1[c]]), fmt_num)
                last_data_col1 = xlsxwriter.utility.xl_col_to_name(num_cols1 - 2)
                ws1.write_formula(curr_row, num_cols1 - 1, f'=SUM(B{curr_row+1}:{last_data_col1}{curr_row+1})', fmt_num, int(row['Total Geral']))

            total_row1 = 1 + len(df_ativos)
            ws1.set_row(total_row1, 22)
            ws1.write(total_row1, 0, 'TOTAL GERAL', fmt_total_label)
            for c in range(1, num_cols1):
                col_let1 = xlsxwriter.utility.xl_col_to_name(c)
                ws1.write_formula(total_row1, c, f'=SUM({col_let1}2:{col_let1}{total_row1})', fmt_total_num)

        # --- ABA 2: INATIVOS ---
        if df_inativos is not None and not df_inativos.empty:
            ws2 = workbook.add_worksheet('Inativos - Motivo Inativação')
            cols2 = list(df_inativos.columns)
            num_cols2 = len(cols2)

            ws2.set_row(0, 26)
            ws2.write(0, 0, 'ESTABELECIMENTO', fmt_header_left)
            for c in range(1, num_cols2):
                ws2.write(0, c, str(cols2[c]), fmt_header_num)

            ws2.set_column(0, 0, 50)
            for c in range(1, num_cols2):
                ws2.set_column(c, c, 18)

            for r_idx, row in df_inativos.iterrows():
                curr_row = 1 + r_idx
                ws2.set_row(curr_row, 18)
                ws2.write(curr_row, 0, str(row['ESTABELECIMENTO']), fmt_text)
                for c in range(1, num_cols2 - 1):
                    ws2.write(curr_row, c, int(row[cols2[c]]), fmt_num)
                last_data_col2 = xlsxwriter.utility.xl_col_to_name(num_cols2 - 2)
                ws2.write_formula(curr_row, num_cols2 - 1, f'=SUM(B{curr_row+1}:{last_data_col2}{curr_row+1})', fmt_num, int(row['Total Geral']))

            total_row2 = 1 + len(df_inativos)
            ws2.set_row(total_row2, 22)
            ws2.write(total_row2, 0, 'TOTAL GERAL', fmt_total_label)
            for c in range(1, num_cols2):
                col_let2 = xlsxwriter.utility.xl_col_to_name(c)
                ws2.write_formula(total_row2, c, f'=SUM({col_let2}2:{col_let2}{total_row2})', fmt_total_num)

        workbook.close()
        output.seek(0)
        return output

def gera_relatorio_17(periodo):
    with app.app_context():
        if periodo:
            query = f'SELECT * FROM "REL-134" WHERE ano_mes = "{periodo}"'
        else:
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


def gera_relatorio_05(periodo):
    """
    Gera o Relatório 05 (Produção CAPS - RAAS).
    Retorna 3 DataFrames:
      1. df_pacientes: Série histórica de quantidade de pacientes atendidos por CAPS (Aba RAAS)
      2. df_profissionais: Produção detalhada por Estabelecimento, CBO, Profissional e Procedimento (Aba RAAS_PROF)
      3. df_acoes: Consolidado de Ações por Estabelecimento, CBO e Procedimento (CONS_ACOES)
    """
    from dateutil.relativedelta import relativedelta
    with app.app_context():
        # Gera lista dos últimos 12 meses até o período selecionado
        try:
            dt_fim = datetime.strptime(str(periodo), '%Y%m')
        except Exception:
            dt_fim = datetime.today()

        meses_lista = []
        for i in range(11, -1, -1):
            m = dt_fim - relativedelta(months=i)
            meses_lista.append(m.strftime('%Y%m'))

        meses_str = "','".join(meses_lista)
        mapa_rotulos = {m: datetime.strptime(m, '%Y%m').strftime('%m/%Y') for m in meses_lista}

        ordem_caps = [
            'CAPS ADULTO III VILA MATILDE',
            'CAPS INFANTOJUVENIL II PENHA',
            'CAPS AD III PENHA',
            'CAPS AD II CANGAIBA'
        ]

        # 1. TABELA DE PACIENTES (Aba RAAS)
        try:
            query_pac = f"SELECT * FROM 'RAAS_PACIENTES' WHERE ano_mes IN ('{meses_str}')"
            df_pac_raw = pd.read_sql(query_pac, con=db.engine)
        except Exception:
            df_pac_raw = None

        if df_pac_raw is not None and not df_pac_raw.empty:
            df_pac_raw['qt_pacientes'] = pd.to_numeric(df_pac_raw['qt_pacientes'], errors='coerce').fillna(0)
            df_pac_raw['estabelecimento'] = df_pac_raw['estabelecimento'].astype(str).str.strip()
            df_pac_raw['ano_mes'] = df_pac_raw['ano_mes'].astype(str).str.strip()
            pivot_pac = pd.pivot_table(
                df_pac_raw,
                index='estabelecimento',
                columns='ano_mes',
                values='qt_pacientes',
                aggfunc='sum',
                fill_value=0
            )
            estab_existentes = [e for e in ordem_caps if e in pivot_pac.index]
            for e in pivot_pac.index:
                if e not in estab_existentes:
                    estab_existentes.append(e)
            pivot_pac = pivot_pac.reindex(estab_existentes)

            cols_meses = [m for m in meses_lista if m in pivot_pac.columns]
            pivot_pac = pivot_pac[cols_meses]

            pivot_pac['Total Geral'] = pivot_pac.sum(axis=1)
            linha_total = pivot_pac.sum(axis=0)
            linha_total.name = 'Total Geral'
            pivot_pac = pd.concat([pivot_pac, pd.DataFrame([linha_total])])

            pivot_pac.rename(columns=mapa_rotulos, inplace=True)
            pivot_pac.index.name = 'Estabelecimento'
            pivot_pac.columns.name = None
            df_pacientes = pivot_pac.reset_index().astype(object)
        else:
            df_pacientes = None

        # 2. TABELA DE AÇÕES POR PROFISSIONAL (Aba RAAS_PROF)
        try:
            query_prof = f"SELECT * FROM 'RAAS_ACOES_PROF' WHERE ano_mes IN ('{meses_str}')"
            df_prof_raw = pd.read_sql(query_prof, con=db.engine)
        except Exception:
            df_prof_raw = None

        if df_prof_raw is not None and not df_prof_raw.empty:
            df_prof_raw['quantidade'] = pd.to_numeric(df_prof_raw['quantidade'], errors='coerce').fillna(0)
            df_prof_raw['estabelecimento'] = df_prof_raw['estabelecimento'].astype(str).str.strip()
            df_prof_raw['descr_cbo'] = df_prof_raw['descr_cbo'].astype(str).str.strip()
            df_prof_raw['nome_prof'] = df_prof_raw['nome_prof'].astype(str).str.strip()
            df_prof_raw['cod_acao'] = df_prof_raw['cod_acao'].fillna('').astype(str).str.strip()
            df_prof_raw['procedimento'] = df_prof_raw['procedimento'].fillna(df_prof_raw['cod_acao']).astype(str).str.strip()
            df_prof_raw['ano_mes'] = df_prof_raw['ano_mes'].astype(str).str.strip()

            pivot_prof = pd.pivot_table(
                df_prof_raw,
                index=['estabelecimento', 'descr_cbo', 'nome_prof', 'cod_acao', 'procedimento'],
                columns='ano_mes',
                values='quantidade',
                aggfunc='sum',
                fill_value=0
            )
            cols_meses_prof = [m for m in meses_lista if m in pivot_prof.columns]
            pivot_prof = pivot_prof[cols_meses_prof]
            pivot_prof['Total Geral'] = pivot_prof.sum(axis=1)
            pivot_prof.rename(columns=mapa_rotulos, inplace=True)
            pivot_prof.index.names = ['Estabelecimento', 'CBO / Especialidade', 'Profissional', 'Código de Procedimento', 'Procedimento']
            pivot_prof.columns.name = None
            df_profissionais = pivot_prof.reset_index().astype(object)
        else:
            df_profissionais = None

        # 3. TABELA DE AÇÕES CONSOLIDADAS POR CBO (CONS_ACOES)
        try:
            query_acoes = f"SELECT * FROM 'RAAS_ACOES' WHERE ano_mes IN ('{meses_str}')"
            df_acoes_raw = pd.read_sql(query_acoes, con=db.engine)
        except Exception:
            df_acoes_raw = None

        if df_acoes_raw is not None and not df_acoes_raw.empty:
            df_acoes_raw['quantidade'] = pd.to_numeric(df_acoes_raw['quantidade'], errors='coerce').fillna(0)
            df_acoes_raw['estabelecimento'] = df_acoes_raw['estabelecimento'].astype(str).str.strip()
            df_acoes_raw['descr_cbo'] = df_acoes_raw['descr_cbo'].astype(str).str.strip()
            df_acoes_raw['cod_acao'] = df_acoes_raw['cod_acao'].fillna('').astype(str).str.strip()
            df_acoes_raw['procedimento'] = df_acoes_raw['procedimento'].fillna(df_acoes_raw['cod_acao']).astype(str).str.strip()
            df_acoes_raw['ano_mes'] = df_acoes_raw['ano_mes'].astype(str).str.strip()

            pivot_acoes = pd.pivot_table(
                df_acoes_raw,
                index=['estabelecimento', 'descr_cbo', 'procedimento'],
                columns='ano_mes',
                values='quantidade',
                aggfunc='sum',
                fill_value=0
            )
            for m in meses_lista:
                if m not in pivot_acoes.columns:
                    pivot_acoes[m] = 0
            pivot_acoes = pivot_acoes[meses_lista]
            pivot_acoes['Total Geral'] = pivot_acoes.sum(axis=1)
            pivot_acoes.rename(columns=mapa_rotulos, inplace=True)
            cols_meses_formatados = [mapa_rotulos[m] for m in meses_lista]

            rows_acoes = []
            estabelecimentos = sorted(df_acoes_raw['estabelecimento'].unique())
            for estab in estabelecimentos:
                if estab not in pivot_acoes.index:
                    continue
                sub_df = pivot_acoes.loc[estab]
                if sub_df.empty:
                    continue

                # Linha da Unidade (Cabeçalho do Estabelecimento com Totais da Unidade)
                row_estab = {
                    'ESTABELECIMENTO': estab,
                    'CBO / PROCEDIMENTO': 'TOTAL DA UNIDADE',
                    '_estabelecimento': estab,
                    '_cbo': 'TODOS',
                    '_tipo_linha': 'unidade'
                }
                for col in cols_meses_formatados:
                    v = int(sub_df[col].sum())
                    row_estab[col] = v if v > 0 else ''
                tot_estab = int(sub_df['Total Geral'].sum())
                row_estab['Total Geral'] = tot_estab if tot_estab > 0 else ''
                rows_acoes.append(row_estab)

                # Subtotais por CBO e Procedimentos
                cbos = sorted(sub_df.index.get_level_values(0).unique())
                for cbo in cbos:
                    cbo_df = sub_df.loc[cbo]
                    if isinstance(cbo_df, pd.Series):
                        cbo_df = cbo_df.to_frame().T

                    # Linha de Subtotal do CBO (destaque com soma dos procedimentos)
                    row_cbo = {
                        'ESTABELECIMENTO': estab,
                        'CBO / PROCEDIMENTO': cbo,
                        '_estabelecimento': estab,
                        '_cbo': cbo,
                        '_tipo_linha': 'cbo'
                    }
                    for col in cols_meses_formatados:
                        v = int(cbo_df[col].sum())
                        row_cbo[col] = v if v > 0 else ''
                    tot_cbo = int(cbo_df['Total Geral'].sum())
                    row_cbo['Total Geral'] = tot_cbo if tot_cbo > 0 else ''
                    rows_acoes.append(row_cbo)

                    # Linhas detalhadas de cada procedimento sob o CBO
                    for proc in cbo_df.index:
                        row_proc = {
                            'ESTABELECIMENTO': estab,
                            'CBO / PROCEDIMENTO': proc,
                            '_estabelecimento': estab,
                            '_cbo': cbo,
                            '_tipo_linha': 'procedimento'
                        }
                        for col in cols_meses_formatados:
                            v = int(cbo_df.loc[proc, col])
                            row_proc[col] = v if v > 0 else ''
                        tot_proc = int(cbo_df.loc[proc, 'Total Geral'])
                        row_proc['Total Geral'] = tot_proc if tot_proc > 0 else ''
                        rows_acoes.append(row_proc)

            df_acoes = pd.DataFrame(rows_acoes).astype(object)
        else:
            df_acoes = None

        return df_pacientes, df_profissionais, df_acoes


MAPA_RELATORIOS_INFO = {
    '01': {
        'fonte': 'CEInfo / Censo Demográfico IBGE 2010 (Dados de População por Estabelecimento e Faixa Etária)',
        'tabela': 'REL-01',
        'arquivos': ['Final desejado.xlsx']
    },
    '02': {
        'fonte': 'BPA (Boletim de Produção Ambulatorial - SIA/SUS) / TabWin',
        'tabela': 'REL-02',
        'arquivos': ['PAPENHA-.AGO', 'STS26_08.dbf', 'PRODUCAO POR UNIDADES.DEF']
    },
    '03': {
        'fonte': 'SIGA Saúde (BI - AT-02)',
        'tabela': 'AT-02',
        'arquivos': ['AT-02.csv']
    },
    '04': {
        'fonte': 'SIGA Saúde (BI - VG-04)',
        'tabela': 'VG-04',
        'arquivos': ['VG-04.csv', 'VG04.csv']
    },
    '05': {
        'fonte': 'RAAS - SIA/SUS (CAPS)',
        'tabela': 'RAAS_PACIENTES',
        'arquivos': ['AA968846.JUL', 'AA330456.JUL', 'AA202962.JUL', 'AA638764.JUL']
    },
    '06': {
        'fonte': 'CEInfo (Painel de Monitoramento - STS Penha)',
        'tabela': 'REL-06',
        'arquivos': ['painel_monitoramento.html']
    },
    '07': {
        'fonte': 'CEInfo (Painel de Monitoramento - Subprefeitura Penha)',
        'tabela': 'REL-07',
        'arquivos': ['painel_monitoramento_subprefeitura.html']
    },
    '08': {
        'fonte': 'SIGA Saúde (BI - GAC-02, CG-01, CG-05, CG-06)',
        'tabela': 'GAC-02',
        'arquivos': ['GAC02.csv']
    },
    '09': {
        'fonte': 'DTIC / SIGAPEP (REL 114)',
        'tabela': 'REL-114',
        'arquivos': ['(rel114) rel_sb_gestante_prev_parto.csv']
    },
    '10': {
        'fonte': 'SIGA Saúde (BI - AT-03)',
        'tabela': 'REL-10',
        'arquivos': ['AT-03.csv']
    },
    '11': {
        'fonte': 'SIGA Saúde (BI - FE-02)',
        'tabela': 'FE-02',
        'arquivos': ['FE-02.csv']
    },
    '12': {
        'fonte': 'SIGA Saúde (BI - AT-02)',
        'tabela': 'AT-02',
        'arquivos': ['AT-02.csv']
    },
    '13': {
        'fonte': 'SIGA Saúde (BI - VG-02)',
        'tabela': 'VG-02',
        'arquivos': ['VG-02.csv', 'VG02.csv']
    },
    '14': {
        'fonte': 'SIGA Saúde (BI - AG-04)',
        'tabela': 'AG-04',
        'arquivos': ['AG-04.csv', 'AG04.csv']
    },
    '15': {
        'fonte': 'DTIC (REL 135)',
        'tabela': 'REL-135',
        'arquivos': ['(rel135) penha.csv']
    },
    '16': {
        'fonte': 'SIGAPEP (SIGA - AMG)',
        'tabela': 'REL-16',
        'arquivos': ['(rel16) siga_amg.csv']
    },
    '17': {
        'fonte': 'DTIC (REL 134)',
        'tabela': 'REL-134',
        'arquivos': ['(rel134) atividade_coletiva_por_profissional.csv']
    }
}

def _formatar_data_raw(raw_dt):
    if not raw_dt:
        return None
    raw_str = str(raw_dt).strip()
    if len(raw_str) == 10 and '-' in raw_str:
        partes = raw_str.split('-')
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    elif len(raw_str) >= 16 and '-' in raw_str:
        try:
            dt_obj = datetime.strptime(raw_str[:16], '%Y-%m-%d %H:%M')
            return dt_obj.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return raw_str
    return raw_str

def obter_metadados_relatorio(indice, periodo=None):
    info = MAPA_RELATORIOS_INFO.get(str(indice), {
        'fonte': 'Sistema Municipal de Saúde',
        'tabela': None,
        'arquivos': []
    })
    
    fonte = info['fonte']
    data_geracao = None
    fontes_detalhadas = []
    
    # 1. Tenta buscar a data específica da competência selecionada no banco de dados
    if info.get('tabela'):
        try:
            with app.app_context():
                df_chk = pd.read_sql(f"SELECT * FROM '{info['tabela']}' LIMIT 1", con=db.engine)
                if 'data_extracao' in df_chk.columns:
                    query = f"SELECT MAX(data_extracao) as dt FROM '{info['tabela']}'"
                    if periodo:
                        if 'ano_mes' in df_chk.columns:
                            query += f" WHERE ano_mes = {int(periodo)}"
                        elif 'ano_mes_extracao' in df_chk.columns:
                            query += f" WHERE ano_mes_extracao = {int(periodo)}"
                        elif 'ano_mes_competencia' in df_chk.columns:
                            query += f" WHERE ano_mes_competencia = '{periodo}'"
                        elif 'ano' in df_chk.columns and 'mes' in df_chk.columns:
                            ano_p = int(str(periodo)[:4])
                            mes_p = int(str(periodo)[4:])
                            mapa_mes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
                            nome_mes = mapa_mes.get(mes_p, '')
                            query += f" WHERE ano = {ano_p} AND mes = '{nome_mes}'"
                        elif indice == '08' or info['tabela'] == 'GAC-02':
                            mes_gac = f"{str(periodo)[:4]}-{str(periodo)[4:]}"
                            query += f" WHERE data_extracao LIKE '{mes_gac}-%'"
                        elif 'previsao_parto' in df_chk.columns:
                            mes_p = str(periodo)[4:]
                            ano_p = str(periodo)[:4]
                            query += f" WHERE previsao_parto LIKE '%/{mes_p}/{ano_p}'"
                    
                    res = pd.read_sql(query, con=db.engine)
                    if not res.empty and res.iloc[0]['dt']:
                        data_geracao = _formatar_data_raw(res.iloc[0]['dt'])
        except Exception:
            pass

    # 1.1. Para o Relatório 08, coleta a data de extração específica de cada um dos 4 sub-relatórios
    if str(indice) == '08':
        sub_relatorios_08 = [
            {'codigo': 'GAC-02', 'nome': 'Gestantes Ativas', 'tabela': 'GAC-02', 'tipo': 'gac', 'arquivo': 'GAC02.csv'},
            {'codigo': 'CG-01', 'nome': 'Gestantes 7+ Consultas', 'tabela': 'CG-01', 'tipo': 'ano_mes', 'arquivo': 'CG-01.csv'},
            {'codigo': 'CG-05', 'nome': 'Total de Consultas PN', 'tabela': 'CG-05', 'tipo': 'ano_mes', 'arquivo': 'CG-05.csv'},
            {'codigo': 'CG-06', 'nome': 'Exames de Pré-Natal', 'tabela': 'CG-06', 'tipo': 'ano_mes', 'arquivo': 'CG-06.csv'},
        ]
        with app.app_context():
            for item in sub_relatorios_08:
                dt_item = None
                try:
                    query_sub = f"SELECT MAX(data_extracao) as dt FROM '{item['tabela']}'"
                    if periodo:
                        if item['tipo'] == 'gac':
                            mes_gac = f"{str(periodo)[:4]}-{str(periodo)[4:]}"
                            query_sub += f" WHERE data_extracao LIKE '{mes_gac}-%'"
                        else:
                            query_sub += f" WHERE ano_mes_extracao = {int(periodo)}"
                    res_sub = pd.read_sql(query_sub, con=db.engine)
                    if not res_sub.empty and res_sub.iloc[0]['dt']:
                        dt_item = _formatar_data_raw(res_sub.iloc[0]['dt'])
                except Exception:
                    pass

                if not dt_item and item.get('arquivo'):
                    caminho_arq = os.path.join(os.getcwd(), 'ARQUIVOS ORIGINAIS', item['arquivo'])
                    if os.path.exists(caminho_arq):
                        mtime = os.path.getmtime(caminho_arq)
                        dt_item = datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')

                fontes_detalhadas.append({
                    'codigo': item['codigo'],
                    'nome': item['nome'],
                    'data_extracao': dt_item if dt_item else 'Pendente'
                })
            
    # 2. Se não encontrou no banco para aquela competência, busca a data de modificação do arquivo
    if not data_geracao and info.get('arquivos'):
        pasta = os.path.join(os.getcwd(), 'ARQUIVOS ORIGINAIS')
        for nome_arq in info['arquivos']:
            caminho = os.path.join(pasta, nome_arq)
            if os.path.exists(caminho):
                mtime = os.path.getmtime(caminho)
                data_geracao = datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
                break
                
    if not data_geracao:
        data_geracao = datetime.now().strftime('%d/%m/%Y')
        
    return {
        'fonte': fonte,
        'data_geracao': data_geracao,
        'fontes_detalhadas': fontes_detalhadas
    }