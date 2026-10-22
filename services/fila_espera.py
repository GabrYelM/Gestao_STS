import os
import re
import csv
import sqlite3
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database.db")
ARQUIVOS_LOCAIS_DIR = os.path.join(BASE_DIR, "ARQUIVOS ORIGINAIS", "Fila de espera")

# Lista oficial de CIDs Definidos e variantes clínicas válidas para cada Especialidade
CIDS_DEFINIDOS_PADRAO = [
    # 1. PNE
    {
        "especialidade": "Odontologia - Atendimento a Pacientes com Necessidades Especiais",
        "cbo_codigo": "223288",
        "cbo_nome": "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z741",
        "cid_descricao": "Necessidade de assistência para cuidados pessoais",
        "observacoes": "Acesso a usuários com necessidades especiais"
    },
    {
        "especialidade": "Odontologia - Atendimento a PNE - Anestesia Geral no HD",
        "cbo_codigo": "223288",
        "cbo_nome": "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais",
        "procedimento_codigo": "0414029941",
        "procedimento_nome": "Atendimento odontologico para PNE/ PCD sob anestesia geral/ Sedacao",
        "cid": "Z749",
        "cid_descricao": "Problema relacionado a dependência de cuidador, não especificado",
        "observacoes": "*Acesso somente por profissionais da Especialidade - Odontologia PNE"
    },

    # 2. Prótese
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K081",
        "cid_descricao": "Perda de dentes devida a acidente, extração ou doença periodontal",
        "observacoes": "Para atendimentos de usuários em unidades da Atenção Básica"
    },
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z463",
        "cid_descricao": "Ajuste e adaptação de próteses dentárias",
        "observacoes": "Casos complexos para reabilitação protética (CEO e CCO)."
    },
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K089",
        "cid_descricao": "Transtorno dos dentes e das estruturas de suporte, não especificado",
        "observacoes": "Quando necessário, para realização de PT Imediata (CEO e CCO)."
    },

    # 3. Prótese Sobre Implante
    {
        "especialidade": "Odontologia - Protese Sobre Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z458",
        "cid_descricao": "Ajuste e manejo de outros dispositivos implantáveis",
        "observacoes": "*Acesso somente por profissionais da Especialidade - Implantodontista"
    },
    {
        "especialidade": "Odontologia - Protese Sobre Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z508",
        "cid_descricao": "Cuidados envolvendo outros procedimentos de reabilitação",
        "observacoes": "Usado para manutenção da prótese sobre implante."
    },

    # 4. Implante
    {
        "especialidade": "Odontologia - Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K082",
        "cid_descricao": "Atrofia do rebordo alveolar",
        "observacoes": "Avaliação para reabilitação com implante"
    },
    {
        "especialidade": "Odontologia - Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "T859",
        "cid_descricao": "Complicação não especificada de prótese interna, implante ou enxerto",
        "observacoes": "Avaliação urgente de usuário em quadro álgico / infecção"
    },

    # 5. Prótese Parcial Fixa
    {
        "especialidade": "Odontologia Protese Parcial Fixa",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K039",
        "cid_descricao": "Doença dos tecidos duros dos dentes, não especificada",
        "observacoes": "Prótese Parcial Fixa"
    },

    # 6. Odontopediatria
    {
        "especialidade": "Odontopediatria",
        "cbo_codigo": "223236",
        "cbo_nome": "Cirurgião Dentista - Odontopediatra",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z001",
        "cid_descricao": "Exame de rotina da criança",
        "observacoes": "Exame e rotina infantil especializada"
    },
    {
        "especialidade": "Odontopediatria",
        "cbo_codigo": "223236",
        "cbo_nome": "Cirurgião Dentista - Odontopediatra",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K011",
        "cid_descricao": "Dentes inclusos e impactados",
        "observacoes": "Para dentes inclusos, retidos ou impactados em crianças"
    },

    # 7. Cirurgia Oral Menor (K011, K069, Q381, K098)
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K011",
        "cid_descricao": "Dentes inclusos e impactados",
        "observacoes": "Para dentes inclusos, retidos ou impactados e supranumerários (terceiros molares / cisos)"
    },
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K069",
        "cid_descricao": "Transtorno da gengiva e do rebordo alveolar sem dentes, não especificado",
        "observacoes": "Cirurgias pré-protéticas; Freio labial; Complicações de exodontias"
    },
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Q381",
        "cid_descricao": "Anquiloglossia",
        "observacoes": "Casos de anquiloglossia / frenectomia lingual"
    },
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K098",
        "cid_descricao": "Outros cistos da região oral, não classificados em outra parte",
        "observacoes": "Cistos e outras lesões intraósseas; Cirurgias parendodônticas"
    },

    # 8. Buco-Maxilo-Facial (Cirurgia & Trauma)
    {
        "especialidade": "Odontologia - Cirurgia E Traumatologia Buco-Maxilo-Facial",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K011",
        "cid_descricao": "Dentes inclusos e impactados",
        "observacoes": "Dentes inclusos/impactados de maior complexidade cirúrgica"
    },
    {
        "especialidade": "Odontologia - Cirurgia E Traumatologia Buco-Maxilo-Facial",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K076",
        "cid_descricao": "Transtornos da articulação temporomandibular",
        "observacoes": "Avaliação de ATM e deformidades dentofaciais cirúrgicas"
    },
    {
        "especialidade": "Odontologia - Cirurgia E Traumatologia Buco-Maxilo-Facial",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K098",
        "cid_descricao": "Outros cistos da região oral",
        "observacoes": "Cistos e tumores odontogênicos dos maxilares"
    },

    # 9. Dor Orofacial
    {
        "especialidade": "Odontologia - Dor Orofacial",
        "cbo_codigo": "223284",
        "cbo_nome": "Cirurgião Dentista - Disfunção Temporomandibular e Dor Orofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K076",
        "cid_descricao": "Transtornos da articulação temporomandibular",
        "observacoes": "DTM e dor orofacial crônica"
    },

    # 10. Periodontia (K055, K056, K051, K053, K05)
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K055",
        "cid_descricao": "Outras doenças periodontais",
        "observacoes": "Tratamento periodontal especializado"
    },
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K056",
        "cid_descricao": "Doença periodontal não especificada",
        "observacoes": "Doença periodontal avançada"
    },
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K053",
        "cid_descricao": "Periodontite crônica",
        "observacoes": "Periodontite crônica moderada a severa"
    },
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K051",
        "cid_descricao": "Gengivite crônica",
        "observacoes": "Gengivite crônica severa/hiperplásica"
    },
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K05",
        "cid_descricao": "Gengivite e doenças periodontais",
        "observacoes": "Categoria geral de periodontia"
    },

    # 11. Ortopedia / Ortodontia (K074, K072, K078, K07)
    {
        "especialidade": "Odontologia - Ortopedia/Ortodontia",
        "cbo_codigo": "223240",
        "cbo_nome": "Cirurgião Dentista - Ortodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K074",
        "cid_descricao": "Maloclusão, não especificada",
        "observacoes": "Avaliação ortodôntica"
    },
    {
        "especialidade": "Odontologia - Ortopedia/Ortodontia",
        "cbo_codigo": "223240",
        "cbo_nome": "Cirurgião Dentista - Ortodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K072",
        "cid_descricao": "Anomalias da relação entre as arcadas dentárias",
        "observacoes": "Classe II, Classe III, mordida aberta ou cruzada"
    },
    {
        "especialidade": "Odontologia - Ortopedia/Ortodontia",
        "cbo_codigo": "223240",
        "cbo_nome": "Cirurgião Dentista - Ortodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K078",
        "cid_descricao": "Outras anomalias dentofaciais",
        "observacoes": ""
    },
    {
        "especialidade": "Odontologia - Ortopedia/Ortodontia",
        "cbo_codigo": "223240",
        "cbo_nome": "Cirurgião Dentista - Ortodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K07",
        "cid_descricao": "Anomalias dentofaciais (inclusive a maloclusão)",
        "observacoes": "Categoria geral de ortodontia"
    },

    # 12. Estomatologia / Semiologia (K137, K136, K13, K100, K061)
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K137",
        "cid_descricao": "Outras lesões e as não especificadas da mucosa oral",
        "observacoes": "Lesões de boca e mucosa"
    },
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K136",
        "cid_descricao": "Hiperplasia irritativa da mucosa oral",
        "observacoes": "Lesões hiperplásicas"
    },
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K13",
        "cid_descricao": "Outras doenças do lábio e da mucosa oral",
        "observacoes": "Categoria geral de estomatologia"
    },
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K100",
        "cid_descricao": "Transtornos do desenvolvimento dos maxilares",
        "observacoes": "Alterações de desenvolvimento"
    },
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K061",
        "cid_descricao": "Fibromatose gengival / hipertrofia gengival",
        "observacoes": ""
    },

    # 13. Endodontia (K049, K041, K042, K040, K04)
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K049",
        "cid_descricao": "Outras doenças da polpa e dos tecidos periapicais e as não especificadas",
        "observacoes": "Tratamento de canal especializado"
    },
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K041",
        "cid_descricao": "Necrose da polpa",
        "observacoes": "Necrose pulpar / dente desvitalizado"
    },
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K042",
        "cid_descricao": "Degeneração da polpa",
        "observacoes": "Calcificações e degenerações pulpares"
    },
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K040",
        "cid_descricao": "Pulpite",
        "observacoes": "Pulpite irreversível"
    },
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K04",
        "cid_descricao": "Doenças da polpa e dos tecidos periapicais",
        "observacoes": "Categoria geral de endodontia"
    }
]

# Dicionário de normalização de Especialidade para CBO
ESPECIALIDADE_PARA_CBO_MAP = {
    "odontologiaatendimentoapacientescomnecessidadesespeciais": ("223288", "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais"),
    "odontologiaatendimentoapneanestesiageralnohd": ("223288", "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais"),
    "odontologiaprotese": ("223256", "Cirurgião Dentista - Protesista"),
    "odontologiaprotesesobreimplante": ("223224", "Cirurgião Dentista - Implantodontista"),
    "odontologiaimplante": ("223224", "Cirurgião Dentista - Implantodontista"),
    "odontologiaproteseparcialfixa": ("223256", "Cirurgião Dentista - Protesista"),
    "odontopediatria": ("223236", "Cirurgião Dentista - Odontopediatra"),
    "odontologiacirurgiaoralmenor": ("223268", "Cirurgião Dentista - Traumatologista Bucomaxilofacial"),
    "odontologiacirurgiaetraumatologiabucomaxilofacial": ("223268", "Cirurgião Dentista - Traumatologista Bucomaxilofacial"),
    "odontologiadororofacial": ("223284", "Cirurgião Dentista - Disfunção Temporomandibular e Dor Orofacial"),
    "odontologiaperiodontia": ("223248", "Cirurgião Dentista - Periodontista"),
    "odontologiaortopediaortodontia": ("223240", "Cirurgião Dentista - Ortodontista"),
    "odontologiaestomatologiasemiologia": ("223220", "Cirurgião Dentista - Estomatologista"),
    "odontologiaendodontia": ("223212", "Cirurgião Dentista - Endodontista")
}


# Mapeamento de sinônimos/variações de especialidade para a chave canônica da portaria
ESPECIALIDADE_SINONIMOS = {
    "odontologiacirurgiaetraumatologiabucomaxilofacial": "odontologiacirurgiaoralmenor",
    "odontologiaatendimentoapne": "odontologiaatendimentoapacientescomnecessidadesespeciais",
}


def normalizar_chave(texto):
    if not texto:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(texto).lower())


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Garante a existência das tabelas de Fila de Espera e carrega os CIDs padrão."""
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fila_cid_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especialidade TEXT NOT NULL,
                cbo_codigo TEXT,
                cbo_nome TEXT,
                procedimento_codigo TEXT,
                procedimento_nome TEXT,
                cid TEXT NOT NULL,
                cid_descricao TEXT,
                observacoes TEXT,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fila_espera_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_extracao TEXT,
                data_importacao TEXT DEFAULT (datetime('now', 'localtime')),
                arquivo_siga TEXT,
                arquivo_fr03 TEXT,
                arquivo_fr04 TEXT,
                total_fe INTEGER DEFAULT 0,
                total_fr INTEGER DEFAULT 0,
                ativo INTEGER DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fila_espera_nominal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lote_id INTEGER,
                data_inclusao TEXT,
                coordenadoria TEXT,
                supervisao TEXT,
                cnes_solicitante TEXT,
                nome_solicitante TEXT,
                protocolo TEXT,
                cns_paciente TEXT,
                prontuario TEXT,
                nome_paciente TEXT,
                data_nascimento TEXT,
                idade INTEGER,
                sexo TEXT,
                raca TEXT,
                peso TEXT,
                telefone_residencial TEXT,
                telefone_celular TEXT,
                endereco TEXT,
                cep TEXT,
                bairro TEXT,
                municipio_residencia TEXT,
                perfil_agenda TEXT,
                agenda TEXT,
                especialidade TEXT,
                codigo_procedimento TEXT,
                procedimento TEXT,
                tipo_atendimento TEXT,
                cns_profissional_solicitante TEXT,
                nome_profissional_solicitante TEXT,
                prioridade TEXT,
                cid TEXT,
                observacoes TEXT,
                login_operador TEXT,
                nome_operador TEXT,
                cbo_codigo TEXT,
                cid_status TEXT,
                cid_esperado TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fila_regulador_nominal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lote_id INTEGER,
                data_entrada_fila TEXT,
                numero_solicitacao TEXT,
                data_encaminhamento TEXT,
                nivel_2_solicitante TEXT,
                nivel_3_solicitante TEXT,
                estabelecimento_solicitante TEXT,
                profissional_solicitante TEXT,
                regulador_operador TEXT,
                especialidade TEXT,
                procedimento TEXT,
                prioridade TEXT,
                idade INTEGER,
                cns_paciente TEXT,
                nome_paciente TEXT,
                nome_mae TEXT,
                sexo TEXT,
                tm TEXT,
                codigo_cid TEXT,
                nome_cid TEXT,
                motivo_encaminhamento TEXT,
                regulador TEXT,
                situacao_fila_regulador TEXT,
                cbo_codigo TEXT,
                cid_status TEXT,
                cid_esperado TEXT
            )
        """)

        # Índices para alta performance de consulta e paginação
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fe_lote ON fila_espera_nominal(lote_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fe_estab ON fila_espera_nominal(nome_solicitante)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fe_espec ON fila_espera_nominal(especialidade)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fe_cid_status ON fila_espera_nominal(cid_status)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_lote ON fila_regulador_nominal(lote_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_estab ON fila_regulador_nominal(estabelecimento_solicitante)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_espec ON fila_regulador_nominal(especialidade)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_cid_status ON fila_regulador_nominal(cid_status)")

        # Carregar dados padrão de CIDs se tabela estiver vazia
        total_cids = conn.execute("SELECT COUNT(*) FROM fila_cid_config").fetchone()[0]
        if total_cids == 0:
            for item in CIDS_DEFINIDOS_PADRAO:
                conn.execute("""
                    INSERT INTO fila_cid_config (
                        especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome,
                        cid, cid_descricao, observacoes, ativo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    item["especialidade"], item["cbo_codigo"], item["cbo_nome"],
                    item["procedimento_codigo"], item["procedimento_nome"],
                    item["cid"], item["cid_descricao"], item["observacoes"]
                ))
    conn.close()


def carregar_mapa_regras_cid(conn=None):
    """
    Retorna regras para validação de CID baseadas na ESPECIALIDADE:
    1) esp_cids: dict { esp_norm: set(cids_limpos) }
    2) esp_esperados: dict { esp_norm: list(cids_originais) }
    3) esp_info: dict { esp_norm: {'cbo_codigo': ..., 'cbo_nome': ..., 'especialidade': ...} }
    """
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    rows = conn.execute("""
        SELECT especialidade, cbo_codigo, cbo_nome, cid, cid_descricao
        FROM fila_cid_config
        WHERE ativo = 1
    """).fetchall()

    esp_cids = {}
    esp_esperados = {}
    esp_info = {}

    for r in rows:
        esp_orig = r["especialidade"] or ""
        esp_norm = normalizar_chave(esp_orig)
        cbo = r["cbo_codigo"]

        if esp_norm:
            raw_cid = (r["cid"] or "").strip()
            # Suporta múltiplos CIDs separados por vírgula na mesma regra
            cids_na_regra = [c.strip() for c in re.split(r"[,;/]+", raw_cid) if c.strip()]
            for single_cid in cids_na_regra:
                cid_clean = re.sub(r"[^A-Z0-9]", "", single_cid.upper())
                if cid_clean:
                    esp_cids.setdefault(esp_norm, set()).add(cid_clean)
                    esp_esperados.setdefault(esp_norm, []).append(single_cid.upper())

            if esp_norm not in esp_info:
                esp_info[esp_norm] = {
                    "cbo_codigo": cbo,
                    "cbo_nome": r["cbo_nome"],
                    "especialidade": esp_orig
                }

    if should_close:
        conn.close()

    return esp_cids, esp_esperados, esp_info


def cid_match_item(informado_limpo, valido_limpo):
    """Compara dois códigos de CID normalizados, aceitando correspondência exata ou por categoria (3 caracteres)."""
    if not informado_limpo or not valido_limpo:
        return False
    if informado_limpo == valido_limpo:
        return True
    # Match por categoria CID de 3 dígitos (ex: K04 para K041 ou K049)
    if len(valido_limpo) == 3 and informado_limpo.startswith(valido_limpo):
        return True
    if len(informado_limpo) == 3 and valido_limpo.startswith(informado_limpo):
        return True
    return False


def validar_cid_linha(especialidade, cid_str, esp_cids, esp_esperados, esp_info=None):
    """
    Verifica se o CID informado está conforme a Especialidade da solicitação.
    Retorna tupla: (cbo_codigo, status, cid_esperado_str)
    status: 'CORRETO', 'INCORRETO' ou 'N/A'
    """
    esp_norm = normalizar_chave(especialidade)
    if not esp_norm:
        return None, "N/A", "-"

    target_key = esp_norm
    if target_key not in esp_cids and target_key in ESPECIALIDADE_SINONIMOS:
        target_key = ESPECIALIDADE_SINONIMOS[target_key]

    if target_key not in esp_cids:
        # Especialidade médica geral ou não configurada para auditoria
        return None, "N/A", "-"

    valid_set = esp_cids[target_key]
    esperados_list = esp_esperados.get(target_key, [])
    esperado_str = ", ".join(sorted(set(esperados_list)))

    info = (esp_info or {}).get(target_key, {})
    cbo_cod = info.get("cbo_codigo")

    cids_informados = [
        re.sub(r"[^A-Z0-9]", "", c)
        for c in re.split(r"[,;/]+", (cid_str or "").upper())
        if c.strip()
    ]

    if not cids_informados:
        return cbo_cod, "INCORRETO", esperado_str

    if any(any(cid_match_item(c, v) for v in valid_set) for c in cids_informados):
        return cbo_cod, "CORRETO", esperado_str
    else:
        return cbo_cod, "INCORRETO", esperado_str


def processar_arquivos_fila(caminho_siga, caminho_fr03, caminho_fr04, nome_siga="SIGA", nome_fr03="FR-03", nome_fr04="FR-04"):
    """
    Processa os 3 arquivos, cruza o FR-03 com o FR-04, aplica as regras de CBO e CID e salva no banco.
    """
    init_db()
    conn = get_db()

    esp_cids, esp_esperados, esp_info = carregar_mapa_regras_cid(conn)

    # 1. Carregar mapeamento do FR-04: Número_Solicitação_Atendimento -> Nome_Situação_Fila_Regulador
    mapa_fr04 = {}
    if caminho_fr04 and os.path.exists(caminho_fr04):
        with open(caminho_fr04, "r", encoding="latin1", errors="replace") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                if len(row) > 13 and row[13].strip().isdigit():
                    num_solic = row[13].strip()
                    situacao = row[8].strip() if len(row) > 8 else ""
                    mapa_fr04[num_solic] = situacao

    # 2. Criar Lote de Importação
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fila_espera_lotes (arquivo_siga, arquivo_fr03, arquivo_fr04)
        VALUES (?, ?, ?)
    """, (nome_siga, nome_fr03, nome_fr04))
    lote_id = cursor.lastrowid

    # 3. Processar SIGA (Fila de Espera - Pacientes Ativos)
    total_fe = 0
    fe_rows_to_insert = []
    if caminho_siga and os.path.exists(caminho_siga):
        with open(caminho_siga, "r", encoding="latin1", errors="replace") as f:
            reader = csv.reader(f, delimiter=";")
            header = None
            for row in reader:
                if not row or not any(row):
                    continue
                if header is None:
                    header = [c.strip() for c in row]
                    continue
                if len(row) < 30:
                    continue

                total_fe += 1

                # Mapeamento do SIGA CSV
                # Col 0: Coordenadoria, 1: Supervisao, 2: CNES, 3: Nome Estab, 4: Protocolo, 5: CNS,
                # 6: Prontuario, 7: Nome, 8: Dt Nasc, 9: Idade, 10: Sexo, 11: Raca, 12: Peso,
                # 13: Tel Res, 14: Tel Cel, 15: Endereco, 16: CEP, 17: Bairro, 18: Municipio,
                # 19: Perfil Agenda, 20: Agenda, 21: Especialidade, 22: Cod Proced, 23: Procedimento,
                # 24: Tipo Atendimento, 25: CNS Prof, 26: Nome Prof, 27: Data/Hora Inclusao,
                # 28: Prioridade, 29: CID, 30: Obs, 31: Login, 32: Nome Op
                especialidade = row[21].strip() if len(row) > 21 else ""
                cid_raw = row[29].strip() if len(row) > 29 else ""

                cbo_cod, cid_status, cid_esperado = validar_cid_linha(
                    especialidade, cid_raw, esp_cids, esp_esperados, esp_info
                )

                idade_val = None
                try:
                    idade_val = int(row[9].strip())
                except Exception:
                    pass

                fe_rows_to_insert.append((
                    lote_id,
                    row[27].strip() if len(row) > 27 else "", # Data/Hora Inclusao
                    row[0].strip() if len(row) > 0 else "",  # Coordenadoria
                    row[1].strip() if len(row) > 1 else "",  # Supervisao
                    row[2].strip() if len(row) > 2 else "",  # CNES
                    row[3].strip() if len(row) > 3 else "",  # Nome Estab
                    row[4].strip() if len(row) > 4 else "",  # Protocolo
                    row[5].strip() if len(row) > 5 else "",  # CNS Paciente
                    row[6].strip() if len(row) > 6 else "",  # Prontuario
                    row[7].strip() if len(row) > 7 else "",  # Nome Paciente
                    row[8].strip() if len(row) > 8 else "",  # Data Nasc
                    idade_val,                              # Idade
                    row[10].strip() if len(row) > 10 else "",# Sexo
                    row[11].strip() if len(row) > 11 else "",# Raca
                    row[12].strip() if len(row) > 12 else "",# Peso
                    row[13].strip() if len(row) > 13 else "",# Tel Res
                    row[14].strip() if len(row) > 14 else "",# Tel Cel
                    row[15].strip() if len(row) > 15 else "",# Endereco
                    row[16].strip() if len(row) > 16 else "",# CEP
                    row[17].strip() if len(row) > 17 else "",# Bairro
                    row[18].strip() if len(row) > 18 else "",# Municipio
                    row[19].strip() if len(row) > 19 else "",# Perfil Agenda
                    row[20].strip() if len(row) > 20 else "",# Agenda
                    especialidade,                           # Especialidade
                    row[22].strip() if len(row) > 22 else "",# Cod Proced
                    row[23].strip() if len(row) > 23 else "",# Procedimento
                    row[24].strip() if len(row) > 24 else "",# Tipo Atendimento
                    row[25].strip() if len(row) > 25 else "",# CNS Prof
                    row[26].strip() if len(row) > 26 else "",# Nome Prof
                    row[28].strip() if len(row) > 28 else "",# Prioridade
                    cid_raw,                                 # CID
                    row[30].strip() if len(row) > 30 else "",# Observacoes
                    row[31].strip() if len(row) > 31 else "",# Login Op
                    row[32].strip() if len(row) > 32 else "",# Nome Op
                    cbo_cod,
                    cid_status,
                    cid_esperado
                ))

                if len(fe_rows_to_insert) >= 5000:
                    cursor.executemany("""
                        INSERT INTO fila_espera_nominal (
                            lote_id, data_inclusao, coordenadoria, supervisao, cnes_solicitante,
                            nome_solicitante, protocolo, cns_paciente, prontuario, nome_paciente,
                            data_nascimento, idade, sexo, raca, peso, telefone_residencial,
                            telefone_celular, endereco, cep, bairro, municipio_residencia,
                            perfil_agenda, agenda, especialidade, codigo_procedimento,
                            procedimento, tipo_atendimento, cns_profissional_solicitante,
                            nome_profissional_solicitante, prioridade, cid, observacoes,
                            login_operador, nome_operador, cbo_codigo, cid_status, cid_esperado
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, fe_rows_to_insert)
                    fe_rows_to_insert = []

    if fe_rows_to_insert:
        cursor.executemany("""
            INSERT INTO fila_espera_nominal (
                lote_id, data_inclusao, coordenadoria, supervisao, cnes_solicitante,
                nome_solicitante, protocolo, cns_paciente, prontuario, nome_paciente,
                data_nascimento, idade, sexo, raca, peso, telefone_residencial,
                telefone_celular, endereco, cep, bairro, municipio_residencia,
                perfil_agenda, agenda, especialidade, codigo_procedimento,
                procedimento, tipo_atendimento, cns_profissional_solicitante,
                nome_profissional_solicitante, prioridade, cid, observacoes,
                login_operador, nome_operador, cbo_codigo, cid_status, cid_esperado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fe_rows_to_insert)

    # 4. Processar FR-03 cruzando com FR-04
    total_fr = 0
    fr_rows_to_insert = []
    if caminho_fr03 and os.path.exists(caminho_fr03):
        with open(caminho_fr03, "r", encoding="latin1", errors="replace") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                if not row or not any(row):
                    continue
                if len(row) > 10 and row[0].strip().isdigit():
                    total_fr += 1
                    num_solic = row[0].strip()
                    situacao = mapa_fr04.get(num_solic, "Pendente de Regulação")

                    especialidade = row[8].strip() if len(row) > 8 else ""
                    cid_raw = row[17].strip() if len(row) > 17 else ""

                    cbo_cod, cid_status, cid_esperado = validar_cid_linha(
                        especialidade, cid_raw, esp_cids, esp_esperados, esp_info
                    )

                    idade_val = None
                    try:
                        idade_val = int(row[11].strip())
                    except Exception:
                        pass

                    fr_rows_to_insert.append((
                        lote_id,
                        row[1].strip() if len(row) > 1 else "",  # Data Entrada Fila
                        num_solic,                               # Numero Solicitacao
                        row[2].strip() if len(row) > 2 else "",  # Data Encaminhamento
                        row[3].strip() if len(row) > 3 else "",  # Nivel 2 Solicitante
                        row[4].strip() if len(row) > 4 else "",  # Nivel 3 Solicitante
                        row[5].strip() if len(row) > 5 else "",  # Estabelecimento Solicitante
                        row[6].strip() if len(row) > 6 else "",  # Profissional Solicitante
                        row[7].strip() if len(row) > 7 else "",  # Regulador Operador
                        especialidade,                           # Especialidade
                        row[9].strip() if len(row) > 9 else "",  # Procedimento
                        row[10].strip() if len(row) > 10 else "",# Prioridade
                        idade_val,                               # Idade
                        row[12].strip() if len(row) > 12 else "",# CNS Paciente
                        row[13].strip() if len(row) > 13 else "",# Nome Paciente
                        row[14].strip() if len(row) > 14 else "",# Nome Mae
                        row[15].strip() if len(row) > 15 else "",# Sexo
                        row[16].strip() if len(row) > 16 else "",# TM
                        cid_raw,                                 # Codigo CID
                        row[18].strip() if len(row) > 18 else "",# Nome CID
                        row[19].strip() if len(row) > 19 else "",# Motivo Encaminhamento
                        row[20].strip() if len(row) > 20 else "",# Regulador
                        situacao,                                # Situacao Fila Regulador (FR-04)
                        cbo_cod,
                        cid_status,
                        cid_esperado
                    ))

                    if len(fr_rows_to_insert) >= 5000:
                        cursor.executemany("""
                            INSERT INTO fila_regulador_nominal (
                                lote_id, data_entrada_fila, numero_solicitacao, data_encaminhamento,
                                nivel_2_solicitante, nivel_3_solicitante, estabelecimento_solicitante,
                                profissional_solicitante, regulador_operador, especialidade,
                                procedimento, prioridade, idade, cns_paciente, nome_paciente,
                                nome_mae, sexo, tm, codigo_cid, nome_cid, motivo_encaminhamento,
                                regulador, situacao_fila_regulador, cbo_codigo, cid_status, cid_esperado
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, fr_rows_to_insert)
                        fr_rows_to_insert = []

    if fr_rows_to_insert:
        cursor.executemany("""
            INSERT INTO fila_regulador_nominal (
                lote_id, data_entrada_fila, numero_solicitacao, data_encaminhamento,
                nivel_2_solicitante, nivel_3_solicitante, estabelecimento_solicitante,
                profissional_solicitante, regulador_operador, especialidade,
                procedimento, prioridade, idade, cns_paciente, nome_paciente,
                nome_mae, sexo, tm, codigo_cid, nome_cid, motivo_encaminhamento,
                regulador, situacao_fila_regulador, cbo_codigo, cid_status, cid_esperado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fr_rows_to_insert)

    # Atualizar contadores do lote
    cursor.execute("""
        UPDATE fila_espera_lotes
        SET total_fe = ?, total_fr = ?
        WHERE id = ?
    """, (total_fe, total_fr, lote_id))

    conn.commit()
    conn.close()

    return {
        "lote_id": lote_id,
        "total_fe": total_fe,
        "total_fr": total_fr
    }


def carregar_arquivos_locais_pasta():
    """Busca automaticamente os arquivos SIGA, FR-03 e FR-04 na pasta ARQUIVOS ORIGINAIS/Fila de espera."""
    if not os.path.exists(ARQUIVOS_LOCAIS_DIR):
        return None, "Pasta ARQUIVOS ORIGINAIS/Fila de espera não encontrada."

    arquivos = os.listdir(ARQUIVOS_LOCAIS_DIR)
    siga_file = None
    fr03_file = None
    fr04_file = None

    for f in arquivos:
        fl = f.lower()
        if fl.endswith(".csv"):
            if "siga" in fl and "fila" in fl:
                siga_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)
            elif "fr-03" in fl:
                fr03_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)
            elif "fr-04" in fl:
                fr04_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)

    if not (siga_file or (fr03_file and fr04_file)):
        return None, "Não foram encontrados arquivos CSV válidos do SIGA ou FR-03/FR-04 na pasta."

    resumo = processar_arquivos_fila(
        siga_file, fr03_file, fr04_file,
        nome_siga=os.path.basename(siga_file) if siga_file else "Nenhum",
        nome_fr03=os.path.basename(fr03_file) if fr03_file else "Nenhum",
        nome_fr04=os.path.basename(fr04_file) if fr04_file else "Nenhum"
    )
    return resumo, None


def recalcular_validacoes_cid():
    """Recalcula a coluna de verificação cid_status e cid_esperado em todas as linhas baseado na Especialidade."""
    conn = get_db()
    esp_cids, esp_esperados, esp_info = carregar_mapa_regras_cid(conn)

    # 1. Recalcular Fila de Espera Nominal
    fe_rows = conn.execute("SELECT id, especialidade, cid, cbo_codigo FROM fila_espera_nominal").fetchall()
    fe_updates = []
    for r in fe_rows:
        cbo_cod, cid_status, cid_esperado = validar_cid_linha(
            r["especialidade"], r["cid"], esp_cids, esp_esperados, esp_info
        )
        cbo_final = r["cbo_codigo"] or cbo_cod
        fe_updates.append((cbo_final, cid_status, cid_esperado, r["id"]))

    if fe_updates:
        conn.executemany("""
            UPDATE fila_espera_nominal
            SET cbo_codigo = ?, cid_status = ?, cid_esperado = ?
            WHERE id = ?
        """, fe_updates)

    # 2. Recalcular Fila do Regulador Nominal
    fr_rows = conn.execute("SELECT id, especialidade, codigo_cid, cbo_codigo FROM fila_regulador_nominal").fetchall()
    fr_updates = []
    for r in fr_rows:
        cbo_cod, cid_status, cid_esperado = validar_cid_linha(
            r["especialidade"], r["codigo_cid"], esp_cids, esp_esperados, esp_info
        )
        cbo_final = r["cbo_codigo"] or cbo_cod
        fr_updates.append((cbo_final, cid_status, cid_esperado, r["id"]))

    if fr_updates:
        conn.executemany("""
            UPDATE fila_regulador_nominal
            SET cbo_codigo = ?, cid_status = ?, cid_esperado = ?
            WHERE id = ?
        """, fr_updates)

    conn.commit()
    conn.close()
    return len(fe_updates), len(fr_updates)


def obter_metricas_cards(lote_id=None):
    """Retorna estatísticas para os cards do topo do painel."""
    conn = get_db()
    where_fe = "WHERE lote_id = ?" if lote_id else ""
    where_fr = "WHERE lote_id = ?" if lote_id else ""
    params = [lote_id] if lote_id else []

    total_fe = conn.execute(f"SELECT COUNT(*) FROM fila_espera_nominal {where_fe}", params).fetchone()[0]
    total_fr = conn.execute(f"SELECT COUNT(*) FROM fila_regulador_nominal {where_fr}", params).fetchone()[0]

    fe_corretos = conn.execute(f"SELECT COUNT(*) FROM fila_espera_nominal WHERE cid_status = 'CORRETO' {'AND lote_id = ?' if lote_id else ''}", params).fetchone()[0]
    fe_incorretos = conn.execute(f"SELECT COUNT(*) FROM fila_espera_nominal WHERE cid_status = 'INCORRETO' {'AND lote_id = ?' if lote_id else ''}", params).fetchone()[0]
    fe_odonto = fe_corretos + fe_incorretos

    fr_corretos = conn.execute(f"SELECT COUNT(*) FROM fila_regulador_nominal WHERE cid_status = 'CORRETO' {'AND lote_id = ?' if lote_id else ''}", params).fetchone()[0]
    fr_incorretos = conn.execute(f"SELECT COUNT(*) FROM fila_regulador_nominal WHERE cid_status = 'INCORRETO' {'AND lote_id = ?' if lote_id else ''}", params).fetchone()[0]
    fr_odonto = fr_corretos + fr_incorretos

    # Último lote
    ultimo_lote = conn.execute("SELECT * FROM fila_espera_lotes ORDER BY id DESC LIMIT 1").fetchone()

    conn.close()
    return {
        "total_fe": total_fe,
        "total_fr": total_fr,
        "total_geral": total_fe + total_fr,
        "fe_odonto": fe_odonto,
        "fe_corretos": fe_corretos,
        "fe_incorretos": fe_incorretos,
        "fr_odonto": fr_odonto,
        "fr_corretos": fr_corretos,
        "fr_incorretos": fr_incorretos,
        "total_incorretos": fe_incorretos + fr_incorretos,
        "ultimo_lote": dict(ultimo_lote) if ultimo_lote else None
    }


def obter_resumo_fe(lote_id=None, estab_filtro=None, espec_filtro=None, status_cid_filtro=None):
    """
    Gera o Resumo da Fila de Espera (RESUMO_FE) agrupado por:
    (Estabelecimento Solicitante, Especialidade, Procedimento, CBO)
    com colunas Primeira Vez, Retorno, Reserva Técnica, Total e Verificação de CID.
    """
    conn = get_db()
    filtros = []
    params = []
    if lote_id:
        filtros.append("lote_id = ?")
        params.append(lote_id)
    if estab_filtro:
        filtros.append("nome_solicitante LIKE ?")
        params.append(f"%{estab_filtro}%")
    if espec_filtro:
        filtros.append("especialidade LIKE ?")
        params.append(f"%{espec_filtro}%")
    if status_cid_filtro:
        filtros.append("cid_status = ?")
        params.append(status_cid_filtro)

    where_clause = "WHERE " + " AND ".join(filtros) if filtros else ""

    query = f"""
        SELECT
            nome_solicitante AS estabelecimento,
            especialidade,
            procedimento,
            cbo_codigo,
            SUM(CASE WHEN lower(tipo_atendimento) LIKE '%primeira%' THEN 1 ELSE 0 END) AS primeira_vez,
            SUM(CASE WHEN lower(tipo_atendimento) LIKE '%retorno%' THEN 1 ELSE 0 END) AS retorno,
            SUM(CASE WHEN lower(tipo_atendimento) LIKE '%reserva%' THEN 1 ELSE 0 END) AS reserva_tecnica,
            COUNT(*) AS total,
            SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) AS cids_corretos,
            SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) AS cids_incorretos,
            SUM(CASE WHEN cid_status = 'N/A' THEN 1 ELSE 0 END) AS cids_na
        FROM fila_espera_nominal
        {where_clause}
        GROUP BY nome_solicitante, especialidade, procedimento, cbo_codigo
        ORDER BY nome_solicitante, especialidade, procedimento
    """

    rows = conn.execute(query, params).fetchall()
    resumo = []
    for r in rows:
        d = dict(r)
        corretos = d["cids_corretos"]
        incorretos = d["cids_incorretos"]
        total_cid_regras = corretos + incorretos

        if total_cid_regras == 0:
            d["status_cid"] = "N/A"
            d["badge_cid"] = "secondary"
        elif incorretos == 0:
            d["status_cid"] = "100% Correto"
            d["badge_cid"] = "success"
        else:
            d["status_cid"] = f"{incorretos} Incorreto(s)"
            d["badge_cid"] = "danger"

        resumo.append(d)

    conn.close()
    return resumo


def obter_resumo_fr(lote_id=None, estab_filtro=None, espec_filtro=None, status_cid_filtro=None):
    """
    Gera o Resumo da Fila do Regulador (RESUMO_FR) agrupado por:
    (Estabelecimento Solicitante, Especialidade, Procedimento, CBO)
    com colunas Alta, Média, Baixa, Total e Verificação de CID.
    """
    conn = get_db()
    filtros = []
    params = []
    if lote_id:
        filtros.append("lote_id = ?")
        params.append(lote_id)
    if estab_filtro:
        filtros.append("estabelecimento_solicitante LIKE ?")
        params.append(f"%{estab_filtro}%")
    if espec_filtro:
        filtros.append("especialidade LIKE ?")
        params.append(f"%{espec_filtro}%")
    if status_cid_filtro:
        filtros.append("cid_status = ?")
        params.append(status_cid_filtro)

    where_clause = "WHERE " + " AND ".join(filtros) if filtros else ""

    query = f"""
        SELECT
            estabelecimento_solicitante AS estabelecimento,
            especialidade,
            procedimento,
            cbo_codigo,
            SUM(CASE WHEN lower(prioridade) LIKE '%alta%' THEN 1 ELSE 0 END) AS alta,
            SUM(CASE WHEN lower(prioridade) LIKE '%m_dia%' OR lower(prioridade) LIKE '%media%' THEN 1 ELSE 0 END) AS media,
            SUM(CASE WHEN lower(prioridade) LIKE '%baixa%' THEN 1 ELSE 0 END) AS baixa,
            COUNT(*) AS total,
            SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) AS cids_corretos,
            SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) AS cids_incorretos,
            SUM(CASE WHEN cid_status = 'N/A' THEN 1 ELSE 0 END) AS cids_na
        FROM fila_regulador_nominal
        {where_clause}
        GROUP BY estabelecimento_solicitante, especialidade, procedimento, cbo_codigo
        ORDER BY estabelecimento_solicitante, especialidade, procedimento
    """

    rows = conn.execute(query, params).fetchall()
    resumo = []
    for r in rows:
        d = dict(r)
        corretos = d["cids_corretos"]
        incorretos = d["cids_incorretos"]
        total_cid_regras = corretos + incorretos

        if total_cid_regras == 0:
            d["status_cid"] = "N/A"
            d["badge_cid"] = "secondary"
        elif incorretos == 0:
            d["status_cid"] = "100% Correto"
            d["badge_cid"] = "success"
        else:
            d["status_cid"] = f"{incorretos} Incorreto(s)"
            d["badge_cid"] = "danger"

        resumo.append(d)

    conn.close()
    return resumo


def obter_estabelecimentos_e_especialidades():
    """Retorna listas únicas de estabelecimentos e especialidades para os selects de filtro."""
    conn = get_db()
    estabs_fe = [r[0] for r in conn.execute("SELECT DISTINCT nome_solicitante FROM fila_espera_nominal WHERE nome_solicitante IS NOT NULL AND nome_solicitante != '' ORDER BY 1").fetchall()]
    especs_fe = [r[0] for r in conn.execute("SELECT DISTINCT especialidade FROM fila_espera_nominal WHERE especialidade IS NOT NULL AND especialidade != '' ORDER BY 1").fetchall()]
    
    estabs_fr = [r[0] for r in conn.execute("SELECT DISTINCT estabelecimento_solicitante FROM fila_regulador_nominal WHERE estabelecimento_solicitante IS NOT NULL AND estabelecimento_solicitante != '' ORDER BY 1").fetchall()]
    especs_fr = [r[0] for r in conn.execute("SELECT DISTINCT especialidade FROM fila_regulador_nominal WHERE especialidade IS NOT NULL AND especialidade != '' ORDER BY 1").fetchall()]

    conn.close()
    todos_estabs = sorted(set(estabs_fe + estabs_fr))
    todas_especs = sorted(set(especs_fe + especs_fr))
    return todos_estabs, todas_especs


def exportar_excel_completo(lote_id=None):
    """
    Exporta uma planilha Excel com as 4 abas estruturadas idênticas ao modelo fornecido:
    1) Fila_Espera_Ativos_Nominal
    2) RESUMO_FE
    3) Fila_Regulador_Nominal
    4) RESUMO_FR
    5) CIDs_Definidos (aba explicativa da tabela de conferência)
    """
    wb = openpyxl.Workbook()
    # Remove aba padrao inicial
    wb.remove(wb.active)

    conn = get_db()
    where_fe = "WHERE lote_id = ?" if lote_id else ""
    where_fr = "WHERE lote_id = ?" if lote_id else ""
    params = [lote_id] if lote_id else []

    fonte_cabecalho_topo = Font(name="Calibri", size=11, bold=True, color="1F4E79")
    fonte_header_tabela = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    fill_header_azul = PatternFill(start_color="30407B", end_color="30407B", fill_type="solid")
    fill_header_verde = PatternFill(start_color="1E7E34", end_color="1E7E34", fill_type="solid")
    border_fina = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # ----------------------------------------------------
    # 1. ABA RESUMO_FE
    # ----------------------------------------------------
    ws_res_fe = wb.create_sheet(title="RESUMO_FE")
    ws_res_fe.append([])
    ws_res_fe.append(["FILA DE ESPERA (DADOS RESUMIDOS COM CONFERÊNCIA DE CID)"])
    ws_res_fe.cell(row=2, column=1).font = Font(name="Calibri", size=14, bold=True, color="30407B")
    ws_res_fe.append([])
    ws_res_fe.append(["Fonte: SIGAPEP - Relatório Operacional de Pacientes Ativos", "", "", "Data Extração: " + datetime.now().strftime("%d/%m/%Y %H:%M")])
    ws_res_fe.cell(row=4, column=1).font = Font(name="Calibri", size=9, italic=True)
    ws_res_fe.cell(row=4, column=4).font = Font(name="Calibri", size=9, italic=True)

    header_res_fe = ["Estabelecimento Solicitante", "Especialidade", "CBO", "Procedimento", "Primeira Vez", "Retorno", "Reserva Técnica", "Total", "Status CID", "CIDs Corretos", "CIDs Incorretos"]
    ws_res_fe.append(header_res_fe)
    for col_idx in range(1, len(header_res_fe) + 1):
        cell = ws_res_fe.cell(row=5, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_azul
        cell.alignment = Alignment(horizontal="center" if col_idx > 4 else "left", vertical="center")

    res_fe_dados = obter_resumo_fe(lote_id)
    for row_idx, r in enumerate(res_fe_dados, start=6):
        ws_res_fe.append([
            r["estabelecimento"], r["especialidade"], r["cbo_codigo"] or "", r["procedimento"],
            r["primeira_vez"] if r["primeira_vez"] > 0 else None,
            r["retorno"] if r["retorno"] > 0 else None,
            r["reserva_tecnica"] if r["reserva_tecnica"] > 0 else None,
            r["total"],
            r["status_cid"],
            r["cids_corretos"] if r["cids_corretos"] > 0 else None,
            r["cids_incorretos"] if r["cids_incorretos"] > 0 else None
        ])
        for c in range(1, len(header_res_fe) + 1):
            ws_res_fe.cell(row=row_idx, column=c).border = border_fina

    # ----------------------------------------------------
    # 2. ABA Fila_Espera_Ativos_Nominal (Completa)
    # ----------------------------------------------------
    ws_fe = wb.create_sheet(title="Fila_Espera_Ativos_Nominal")
    ws_fe.append(["PREFEITURA DO MUNICÍPIO DE SÃO PAULO"])
    ws_fe.append(["SECRETARIA MUNICIPAL DA SAÚDE – SMS"])
    ws_fe.append(["COORDENADORIA REGIONAL DE SAÚDE SUDESTE"])
    ws_fe.append(["SUPERVISÃO TÉCNICA DE SAÚDE PENHA"])
    ws_fe.append(["FILA DE ESPERA (LISTA NOMINAL DE PACIENTES ATIVOS)"])
    ws_fe.append([])
    ws_fe.append(["Fonte: SIGAPEP - Relatório Operacional"])
    ws_fe.append(["Data Extração: " + datetime.now().strftime("%d/%m/%Y")])
    ws_fe.append([])

    headers_fe_nom = [
        "Data/Hora da Inclusão", "Coordenadoria", "Supervisão", "CNES Estab. Solicitante", "Nome Estab. Solicitante",
        "Protocolo", "CNS Paciente", "Prontuario", "Nome Paciente", "Data de Nascimento", "Idade", "Sexo",
        "Raca", "Peso", "Telefone Residencial", "Telefone Celular", "Endereço", "CEP", "Bairro",
        "Município de Residência", "Perfil da Agenda", "Agenda", "Especialidade", "CBO", "Código do Procedimento",
        "Procedimento", "Tipo de Atendimento", "CNS Profissional Solicitante", "Nome Profissional Solicitante",
        "Prioridade", "CID", "Verificação CID", "CID Esperado", "Observações", "Login Operador Inclusão", "Nome Operador Inclusão"
    ]
    ws_fe.append(headers_fe_nom)
    for col_idx in range(1, len(headers_fe_nom) + 1):
        cell = ws_fe.cell(row=10, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_azul

    fe_query = f"""
        SELECT data_inclusao, coordenadoria, supervisao, cnes_solicitante, nome_solicitante,
               protocolo, cns_paciente, prontuario, nome_paciente, data_nascimento, idade, sexo,
               raca, peso, telefone_residencial, telefone_celular, endereco, cep, bairro,
               municipio_residencia, perfil_agenda, agenda, especialidade, cbo_codigo, codigo_procedimento,
               procedimento, tipo_atendimento, cns_profissional_solicitante, nome_profissional_solicitante,
               prioridade, cid, cid_status, cid_esperado, observacoes, login_operador, nome_operador
        FROM fila_espera_nominal
        {where_fe}
        ORDER BY data_inclusao DESC
    """
    for row in conn.execute(fe_query, params):
        ws_fe.append(list(row))

    # ----------------------------------------------------
    # 3. ABA RESUMO_FR
    # ----------------------------------------------------
    ws_res_fr = wb.create_sheet(title="RESUMO_FR")
    ws_res_fr.append([])
    ws_res_fr.append(["FILA DO REGULADOR (DADOS RESUMIDOS COM CONFERÊNCIA DE CID)"])
    ws_res_fr.cell(row=2, column=1).font = Font(name="Calibri", size=14, bold=True, color="30407B")
    ws_res_fr.append([])
    ws_res_fr.append(["Fonte: BISIGA - FR-03 e FR-04", "", "", "Data Extração: " + datetime.now().strftime("%d/%m/%Y %H:%M")])
    ws_res_fr.cell(row=4, column=1).font = Font(name="Calibri", size=9, italic=True)
    ws_res_fr.cell(row=4, column=4).font = Font(name="Calibri", size=9, italic=True)

    header_res_fr = ["Estabelecimento Solicitante", "Especialidade", "CBO", "Procedimento", "Alta", "Média", "Baixa", "Total", "Status CID", "CIDs Corretos", "CIDs Incorretos"]
    ws_res_fr.append(header_res_fr)
    for col_idx in range(1, len(header_res_fr) + 1):
        cell = ws_res_fr.cell(row=5, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_verde
        cell.alignment = Alignment(horizontal="center" if col_idx > 4 else "left", vertical="center")

    res_fr_dados = obter_resumo_fr(lote_id)
    for row_idx, r in enumerate(res_fr_dados, start=6):
        ws_res_fr.append([
            r["estabelecimento"], r["especialidade"], r["cbo_codigo"] or "", r["procedimento"],
            r["alta"] if r["alta"] > 0 else None,
            r["media"] if r["media"] > 0 else None,
            r["baixa"] if r["baixa"] > 0 else None,
            r["total"],
            r["status_cid"],
            r["cids_corretos"] if r["cids_corretos"] > 0 else None,
            r["cids_incorretos"] if r["cids_incorretos"] > 0 else None
        ])
        for c in range(1, len(header_res_fr) + 1):
            ws_res_fr.cell(row=row_idx, column=c).border = border_fina

    # ----------------------------------------------------
    # 4. ABA Fila_Regulador_Nominal (Completa)
    # ----------------------------------------------------
    ws_fr = wb.create_sheet(title="Fila_Regulador_Nominal")
    ws_fr.append(["PREFEITURA DO MUNICÍPIO DE SÃO PAULO"])
    ws_fr.append(["SECRETARIA MUNICIPAL DA SAÚDE – SMS"])
    ws_fr.append(["COORDENADORIA REGIONAL DE SAÚDE SUDESTE"])
    ws_fr.append(["SUPERVISÃO TÉCNICA DE SAÚDE PENHA"])
    ws_fr.append(["FILA DO REGULADOR (LISTA NOMINAL COM MOTIVO)"])
    ws_fr.append([])
    ws_fr.append(["Fonte: BISIGA - FR-03 e FR-04"])
    ws_fr.append(["Data Extração: " + datetime.now().strftime("%d/%m/%Y")])
    ws_fr.append([])

    headers_fr_nom = [
        "Data_Completa_entrada_fila", "Número_Solicitação_Atendimento", "Data_Completa_encaminhamento",
        "H1___Nome_Nível_2_solicitante", "H1___Nome_Nível_3_solicitante", "H1___Nome_Estabelecimento_solicitante",
        "Nome_Profissional_Siga_solicitante", "Nome_Profissional_regulador_operador", "Nome_Especialidade", "CBO",
        "Nome_Procedimento", "Nome_Prioridade_Fila_Regulador", "Idade", "Código_CNS_paciente", "Nome_Paciente",
        "Nome_Mae", "Sexo", "TM", "Código_CID", "Nome_CID", "Verificação CID", "CID Esperado",
        "Texto_Motivo_Encaminhamento", "Regulador", "Nome_Situação_Fila_Regulador"
    ]
    ws_fr.append(headers_fr_nom)
    for col_idx in range(1, len(headers_fr_nom) + 1):
        cell = ws_fr.cell(row=10, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_verde

    fr_query = f"""
        SELECT data_entrada_fila, numero_solicitacao, data_encaminhamento, nivel_2_solicitante,
               nivel_3_solicitante, estabelecimento_solicitante, profissional_solicitante,
               regulador_operador, especialidade, cbo_codigo, procedimento, prioridade, idade,
               cns_paciente, nome_paciente, nome_mae, sexo, tm, codigo_cid, nome_cid,
               cid_status, cid_esperado, motivo_encaminhamento, regulador, situacao_fila_regulador
        FROM fila_regulador_nominal
        {where_fr}
        ORDER BY data_entrada_fila DESC
    """
    for row in conn.execute(fr_query, params):
        ws_fr.append(list(row))

    # ----------------------------------------------------
    # 5. ABA CIDs_Definidos (Tabela Oficial de Referência)
    # ----------------------------------------------------
    ws_cids = wb.create_sheet(title="CIDs_Definidos")
    ws_cids.append(["TABELA DE CIDs DEFINIDOS (REFERÊNCIA DE CONFERÊNCIA SMS/STS)"])
    ws_cids.cell(row=1, column=1).font = Font(name="Calibri", size=13, bold=True, color="30407B")
    ws_cids.append([])
    headers_cids = ["Especialidade", "CBO", "Cargo / Categoria CBO", "Procedimento", "CID", "Descrição do CID", "Observações"]
    ws_cids.append(headers_cids)
    for col_idx in range(1, len(headers_cids) + 1):
        cell = ws_cids.cell(row=3, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_azul

    cids_rows = conn.execute("SELECT especialidade, cbo_codigo, cbo_nome, procedimento_nome, cid, cid_descricao, observacoes FROM fila_cid_config ORDER BY especialidade, cid").fetchall()
    for row in cids_rows:
        ws_cids.append(list(row))

    # Ajustar largura de colunas em todas as abas
    for ws in [ws_res_fe, ws_res_fr, ws_cids]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if "\n" in val_str:
                    val_str = val_str.split("\n")[0]
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

    conn.close()
    return wb
