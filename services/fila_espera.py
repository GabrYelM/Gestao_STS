import os
import re
import csv
import io
import zipfile
import sqlite3
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database.db")
ARQUIVOS_LOCAIS_DIR = os.path.join(BASE_DIR, "ARQUIVOS ORIGINAIS", "Fila de espera")

# Lista oficial de 20 CIDs Definidos e regras regulatórias (Especialidade + Procedimento -> CID)
CIDS_DEFINIDOS_PADRAO = [
    # 1. Odontologia - Atendimento a Pacientes com Necessidades Especiais
    {
        "especialidade": "Odontologia - Atendimento a Pacientes com Necessidades Especiais",
        "cbo_codigo": "223288",
        "cbo_nome": "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z741",
        "cid_descricao": "Necessidade de assistência para cuidados pessoais",
        "observacoes": ""
    },
    # 2. Odontologia - Atendimento a PNE - Anestesia Geral no HD
    {
        "especialidade": "Odontologia - Atendimento a PNE - Anestesia Geral no HD",
        "cbo_codigo": "223288",
        "cbo_nome": "Cirurgião Dentista - Odontologia para Pacientes com Necessidades Especiais",
        "procedimento_codigo": "0414029941",
        "procedimento_nome": "04.14.02.994-1 - Atendimento odontologico para PNE/ PCD sob anestesia geral/ Sedacao",
        "cid": "Z749",
        "cid_descricao": "Problema relacionado a dependência de cuidador, não especificado",
        "observacoes": "*Acesso somente por profissionais da Especialidade - Odontologia PNE"
    },
    # 3. Odontologia - Protese (K081)
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K081",
        "cid_descricao": "Perda de dentes devida a acidente, extração ou doença periodontal",
        "observacoes": "Para atendimentos de usuários em unidades da Atenção Básica"
    },
    # 4. Odontologia - Protese (Z463)
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z463",
        "cid_descricao": "Ajuste e adaptação de próteses dentárias",
        "observacoes": "Casos complexos para reabilitação protética. Atendimentos em Serviços de Especialidades (CEO e CCO)."
    },
    # 5. Odontologia - Protese (K089)
    {
        "especialidade": "Odontologia - Protese",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K089",
        "cid_descricao": "Transtorno dos dentes e das estruturas de suporte, não especificado",
        "observacoes": "Quando necessário, para realização de PT Imediata nos Serviços de Especialidades (CEO e CCO)."
    },
    # 6. Odontologia - Protese Sobre Implante (Z458)
    {
        "especialidade": "Odontologia - Protese Sobre Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z458",
        "cid_descricao": "Ajuste e manejo de outros dispositivos implantáveis",
        "observacoes": "*Acesso somente por profissionais da Especialidade - Implantodontista (implantodontista insere na FE e agenda retorno no mesmo CEO p/ confecção da prótese)"
    },
    # 7. Odontologia - Protese Sobre Implante (Z508)
    {
        "especialidade": "Odontologia - Protese Sobre Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z508",
        "cid_descricao": "Cuidados envolvendo outros procedimentos de reabilitação",
        "observacoes": "Usado para manutenção da prótese sobre implante. (AB insere na FE). Somente a usuários que realizaram a prótese nos serviços da Rede SMS"
    },
    # 8. Odontologia - Implante (K082)
    {
        "especialidade": "Odontologia - Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K082",
        "cid_descricao": "Atrofia do rebordo alveolar",
        "observacoes": ""
    },
    # 9. Odontologia - Implante (T859)
    {
        "especialidade": "Odontologia - Implante",
        "cbo_codigo": "223224",
        "cbo_nome": "Cirurgião Dentista - Implantodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "T859",
        "cid_descricao": "Complicação não especificada de prótese interna, implante ou enxerto",
        "observacoes": "Avaliação urgente de usuário em quadro álgico / infecção"
    },
    # 10. Odontologia Protese Parcial Fixa (K039)
    {
        "especialidade": "Odontologia Protese Parcial Fixa",
        "cbo_codigo": "223256",
        "cbo_nome": "Cirurgião Dentista - Protesista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K039",
        "cid_descricao": "Doença dos tecidos duros dos dentes, não especificada",
        "observacoes": ""
    },
    # 11. Odontopediatria (Z001)
    {
        "especialidade": "Odontopediatria",
        "cbo_codigo": "223236",
        "cbo_nome": "Cirurgião Dentista - Odontopediatra",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Z001",
        "cid_descricao": "Exame de rotina da criança",
        "observacoes": ""
    },
    # 12. Odontologia - Cirurgia Oral Menor (K011)
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K011",
        "cid_descricao": "Dentes inclusos e impactados",
        "observacoes": "Para dentes inclusos, retidos ou impactados e dentes supranumerários retidos ou impactados."
    },
    # 13. Odontologia - Cirurgia Oral Menor (K069)
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K069",
        "cid_descricao": "Transtorno da gengiva e do rebordo alveolar sem dentes, não especificado",
        "observacoes": "Cirurgias pré-protéticas; Freio labial que interfiram na estética e fonética; Complicações de exodontias envolvendo o seio maxilar, como deslocamento de raiz para o seio e comunicação buco sinusal"
    },
    # 14. Odontologia - Cirurgia Oral Menor (Q381)
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "Q381",
        "cid_descricao": "Anquiloglossia",
        "observacoes": "Casos de anquiloglossia"
    },
    # 15. Odontologia - Cirurgia Oral Menor (K098)
    {
        "especialidade": "Odontologia - Cirurgia Oral Menor",
        "cbo_codigo": "223268",
        "cbo_nome": "Cirurgião Dentista - Traumatologista Bucomaxilofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K098",
        "cid_descricao": "Outros cistos da região oral, não classificados em outra parte",
        "observacoes": "Cistos e outras lesões intraósseas; Cirurgias parendodônticas"
    },
    # 16. Odontologia - Dor Orofacial (K076)
    {
        "especialidade": "Odontologia - Dor Orofacial",
        "cbo_codigo": "223284",
        "cbo_nome": "Cirurgião Dentista - Disfunção Temporomandibular e Dor Orofacial",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K076",
        "cid_descricao": "Transtornos da articulação temporomandibular",
        "observacoes": ""
    },
    # 17. Odontologia - Periodontia (K055)
    {
        "especialidade": "Odontologia - Periodontia",
        "cbo_codigo": "223248",
        "cbo_nome": "Cirurgião Dentista - Periodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K055",
        "cid_descricao": "Outras doenças periodontais",
        "observacoes": ""
    },
    # 18. Odontologia - Ortopedia/Ortodontia (K074)
    {
        "especialidade": "Odontologia - Ortopedia/Ortodontia",
        "cbo_codigo": "223240",
        "cbo_nome": "Cirurgião Dentista - Ortodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K074",
        "cid_descricao": "Maloclusão, não especificada",
        "observacoes": ""
    },
    # 19. Odontologia Estomatologia/Semiologia (K137)
    {
        "especialidade": "Odontologia Estomatologia/Semiologia",
        "cbo_codigo": "223220",
        "cbo_nome": "Cirurgião Dentista - Estomatologista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K137",
        "cid_descricao": "Outras lesões e as não especificadas da mucosa oral",
        "observacoes": ""
    },
    # 20. Odontologia - Endodontia (K049)
    {
        "especialidade": "Odontologia - Endodontia",
        "cbo_codigo": "223212",
        "cbo_nome": "Cirurgião Dentista - Endodontista",
        "procedimento_codigo": "0301010048",
        "procedimento_nome": "03.01.01.004-8 - Consulta De Profissionais De Nivel Superior Na Atenção Especializada (Exceto Médico)",
        "cid": "K049",
        "cid_descricao": "Outras doenças da polpa e dos tecidos periapicais e as não especificadas",
        "observacoes": ""
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


def normalizar_proc_cod(cod_proc, nome_proc=""):
    """Extrai e normaliza o código do procedimento para cruzamento relacional."""
    cod_clean = re.sub(r"[^0-9]", "", str(cod_proc or ""))
    nome_str = str(nome_proc or "").lower()
    if "0414029941" in cod_clean or "0414029941" in nome_str or "anestesia" in nome_str or "sedacao" in nome_str:
        return "0414029941"
    if "0301010048" in cod_clean or "0301010048" in nome_str or "consulta" in nome_str or "atencao especializada" in nome_str:
        return "0301010048"
    if cod_clean:
        return cod_clean
    return ""


def carregar_mapa_regras_cid(conn=None):
    """
    Retorna regras relacionais para validação de CID baseadas em (ESPECIALIDADE, PROCEDIMENTO):
    1) rel_cids: dict { (esp_norm, proc_cod): set(cids_limpos) }
    2) rel_esperados: dict { (esp_norm, proc_cod): list(cids_originais) }
    3) rel_info: dict { (esp_norm, proc_cod): {'cbo_codigo': ..., 'cbo_nome': ..., 'procedimento_codigo': ..., 'procedimento_nome': ...} }
    4) esp_fallback_cids: dict { esp_norm: set(cids_limpos) }
    5) esp_fallback_esperados: dict { esp_norm: list(cids_originais) }
    6) esp_fallback_info: dict { esp_norm: {'cbo_codigo': ..., 'cbo_nome': ...} }
    """
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    rows = conn.execute("""
        SELECT especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome, cid, cid_descricao, observacoes
        FROM fila_cid_config
        WHERE ativo = 1
    """).fetchall()

    rel_cids = {}
    rel_esperados = {}
    rel_info = {}
    esp_fallback_cids = {}
    esp_fallback_esperados = {}
    esp_fallback_info = {}

    for r in rows:
        esp_orig = r["especialidade"] or ""
        esp_norm = normalizar_chave(esp_orig)
        if not esp_norm:
            continue

        proc_cod = normalizar_proc_cod(r["procedimento_codigo"], r["procedimento_nome"]) or "0301010048"
        raw_cid = (r["cid"] or "").strip()
        cids_na_regra = [c.strip() for c in re.split(r"[,;/]+", raw_cid) if c.strip()]

        key = (esp_norm, proc_cod)
        for single_cid in cids_na_regra:
            cid_clean = re.sub(r"[^A-Z0-9]", "", single_cid.upper())
            if cid_clean:
                rel_cids.setdefault(key, set()).add(cid_clean)
                rel_esperados.setdefault(key, []).append(single_cid.upper())

                esp_fallback_cids.setdefault(esp_norm, set()).add(cid_clean)
                esp_fallback_esperados.setdefault(esp_norm, []).append(single_cid.upper())

        info_dict = {
            "cbo_codigo": r["cbo_codigo"],
            "cbo_nome": r["cbo_nome"],
            "procedimento_codigo": proc_cod,
            "procedimento_nome": r["procedimento_nome"],
            "especialidade": esp_orig
        }
        if key not in rel_info:
            rel_info[key] = info_dict
        if esp_norm not in esp_fallback_info:
            esp_fallback_info[esp_norm] = info_dict

    if should_close:
        conn.close()

    return rel_cids, rel_esperados, rel_info, esp_fallback_cids, esp_fallback_esperados, esp_fallback_info


def validar_cid_linha(especialidade, cod_proc, nome_proc, cid_str, mapas_cid):
    """
    Verifica se o CID informado coincide exatamente com o(s) CID(s) indicado(s) na tabela
    de regras para o cruzamento relacional de (Especialidade, Procedimento).
    Retorna tupla: (cbo_codigo, status, cid_esperado_str)
    status: 'CORRETO', 'INCORRETO' ou 'N/A'
    """
    rel_cids, rel_esperados, rel_info, esp_fallback_cids, esp_fallback_esperados, esp_fallback_info = mapas_cid

    esp_norm = normalizar_chave(especialidade)
    if not esp_norm:
        return None, "N/A", "-"

    target_esp = esp_norm
    if target_esp not in esp_fallback_cids and target_esp in ESPECIALIDADE_SINONIMOS:
        target_esp = ESPECIALIDADE_SINONIMOS[target_esp]

    if target_esp not in esp_fallback_cids:
        # Especialidade médica geral ou não odontológica
        return None, "N/A", "-"

    proc_cod = normalizar_proc_cod(cod_proc, nome_proc)
    rel_key = (target_esp, proc_cod)

    if rel_key in rel_cids:
        valid_set = rel_cids[rel_key]
        esperados_list = rel_esperados.get(rel_key, [])
        info = rel_info.get(rel_key, {})
    else:
        # Fallback para regras da especialidade caso o procedimento esteja genérico ou não especificado
        valid_set = esp_fallback_cids[target_esp]
        esperados_list = esp_fallback_esperados.get(target_esp, [])
        info = esp_fallback_info.get(target_esp, {})

    esperado_str = ", ".join(sorted(set(esperados_list)))
    cbo_cod = info.get("cbo_codigo")

    cids_informados = [
        re.sub(r"[^A-Z0-9]", "", c)
        for c in re.split(r"[,;/]+", (cid_str or "").upper())
        if c.strip()
    ]

    if not cids_informados:
        return cbo_cod, "INCORRETO", esperado_str

    # Comparativo exato com o(s) CID(s) indicado(s) na tabela de regras
    if any(c in valid_set for c in cids_informados):
        return cbo_cod, "CORRETO", esperado_str
    else:
        return cbo_cod, "INCORRETO", esperado_str


def resolver_arquivo_ou_zip(caminho, destino_dir=None, tipo_esperado="siga"):
    """
    Se o caminho fornecido for um arquivo .ZIP, descompacta em destino_dir e
    retorna o caminho do arquivo CSV/TXT correspondente. Se já for CSV/TXT, retorna o próprio caminho.
    """
    if not caminho or not os.path.exists(caminho):
        return None, None

    if not (caminho.lower().endswith(".zip") or zipfile.is_zipfile(caminho)):
        return caminho, os.path.basename(caminho)

    if destino_dir is None:
        destino_dir = os.path.join(os.path.dirname(caminho), f"extracted_{int(datetime.now().timestamp())}")
    os.makedirs(destino_dir, exist_ok=True)

    extracted_files = []
    with zipfile.ZipFile(caminho, "r") as zf:
        for member in zf.infolist():
            filename = os.path.basename(member.filename)
            if not filename or filename.startswith(".") or filename.startswith("__MACOSX"):
                continue
            target_path = os.path.join(destino_dir, filename)
            with zf.open(member) as source, open(target_path, "wb") as target:
                target.write(source.read())
            extracted_files.append(target_path)

    if not extracted_files:
        return None, None

    if len(extracted_files) == 1:
        return extracted_files[0], os.path.basename(extracted_files[0])

    tipo_esperado = tipo_esperado.lower()
    for f in extracted_files:
        fn = os.path.basename(f).lower()
        if tipo_esperado == "siga" and ("siga" in fn or "fila" in fn or "operacional" in fn or "ativos" in fn):
            return f, os.path.basename(f)
        elif tipo_esperado == "fr03" and ("fr-03" in fn or "fr03" in fn or "motivo" in fn):
            return f, os.path.basename(f)
        elif tipo_esperado == "fr04" and ("fr-04" in fn or "fr04" in fn or "devolvidos" in fn):
            return f, os.path.basename(f)

    for f in extracted_files:
        fn = os.path.basename(f).lower()
        if fn.endswith(".csv") or fn.endswith(".txt"):
            return f, os.path.basename(f)

    return extracted_files[0], os.path.basename(extracted_files[0])


def extrair_e_identificar_pacote_zip(caminho_zip, destino_dir=None):
    """
    Recebe um arquivo .ZIP que pode conter 1 ou múltiplos relatórios (SIGA, FR-03, FR-04),
    descompacta e identifica automaticamente os caminhos de cada um.
    Retorna dict com chaves 'siga_path', 'siga_nome', 'fr03_path', 'fr03_nome', 'fr04_path', 'fr04_nome'.
    """
    if not caminho_zip or not os.path.exists(caminho_zip) or not zipfile.is_zipfile(caminho_zip):
        return None

    if destino_dir is None:
        destino_dir = os.path.join(os.path.dirname(caminho_zip), f"zip_pack_{int(datetime.now().timestamp())}")
    os.makedirs(destino_dir, exist_ok=True)

    extracted = []
    with zipfile.ZipFile(caminho_zip, "r") as zf:
        for member in zf.infolist():
            filename = os.path.basename(member.filename)
            if not filename or filename.startswith(".") or filename.startswith("__MACOSX"):
                continue
            target_path = os.path.join(destino_dir, filename)
            with zf.open(member) as source, open(target_path, "wb") as target:
                target.write(source.read())
            extracted.append(target_path)

    resultado = {
        "siga_path": None, "siga_nome": None,
        "fr03_path": None, "fr03_nome": None,
        "fr04_path": None, "fr04_nome": None
    }

    for f in extracted:
        fn = os.path.basename(f).lower()
        if fn.endswith(".csv") or fn.endswith(".txt"):
            if "siga" in fn or "fila" in fn or "operacional" in fn or "ativos" in fn:
                resultado["siga_path"] = f
                resultado["siga_nome"] = os.path.basename(f)
            elif "fr-03" in fn or "fr03" in fn or "motivo" in fn:
                resultado["fr03_path"] = f
                resultado["fr03_nome"] = os.path.basename(f)
            elif "fr-04" in fn or "fr04" in fn or "devolvidos" in fn:
                resultado["fr04_path"] = f
                resultado["fr04_nome"] = os.path.basename(f)

    if len(extracted) == 1 and not any(resultado.values()):
        resultado["siga_path"] = extracted[0]
        resultado["siga_nome"] = os.path.basename(extracted[0])

    return resultado


def processar_arquivos_fila(caminho_siga=None, caminho_fr03=None, caminho_fr04=None, nome_siga="SIGA", nome_fr03="FR-03", nome_fr04="FR-04"):
    """
    Processa os arquivos fornecidos (aceita .CSV, .TXT ou .ZIP descompactado automaticamente),
    cruza o FR-03 com o FR-04, aplica as regras de CBO e CID e salva no banco.
    Substitui integralmente os registros antigos das filas correspondentes pelos novos arquivos inseridos.
    """
    # 0. Descompacta automaticamente caso algum arquivo seja .ZIP
    if caminho_siga and os.path.exists(caminho_siga) and zipfile.is_zipfile(caminho_siga):
        res_siga, n_siga = resolver_arquivo_ou_zip(caminho_siga, tipo_esperado="siga")
        if res_siga:
            caminho_siga = res_siga
            nome_siga = n_siga or nome_siga

    if caminho_fr03 and os.path.exists(caminho_fr03) and zipfile.is_zipfile(caminho_fr03):
        res_fr03, n_fr03 = resolver_arquivo_ou_zip(caminho_fr03, tipo_esperado="fr03")
        if res_fr03:
            caminho_fr03 = res_fr03
            nome_fr03 = n_fr03 or nome_fr03

    if caminho_fr04 and os.path.exists(caminho_fr04) and zipfile.is_zipfile(caminho_fr04):
        res_fr04, n_fr04 = resolver_arquivo_ou_zip(caminho_fr04, tipo_esperado="fr04")
        if res_fr04:
            caminho_fr04 = res_fr04
            nome_fr04 = n_fr04 or nome_fr04

    init_db()
    conn = get_db()

    mapas_cid = carregar_mapa_regras_cid(conn)

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

    cursor = conn.cursor()

    # 2. Substituição Total: Expurga registros anteriores das filas que estão sendo carregadas
    if caminho_siga and os.path.exists(caminho_siga):
        cursor.execute("DELETE FROM fila_espera_nominal")

    if caminho_fr03 and os.path.exists(caminho_fr03):
        cursor.execute("DELETE FROM fila_regulador_nominal")

    # Limpa lotes antigos para manter apenas o lote mais recente ativo
    if (caminho_siga and os.path.exists(caminho_siga)) or (caminho_fr03 and os.path.exists(caminho_fr03)):
        cursor.execute("DELETE FROM fila_espera_lotes")

    # Criar novo Lote de Importação
    cursor.execute("""
        INSERT INTO fila_espera_lotes (arquivo_siga, arquivo_fr03, arquivo_fr04)
        VALUES (?, ?, ?)
    """, (nome_siga or "Não enviado", nome_fr03 or "Não enviado", nome_fr04 or "Não enviado"))
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
                cod_proc_fe = row[22].strip() if len(row) > 22 else ""
                nome_proc_fe = row[23].strip() if len(row) > 23 else ""
                cid_raw = row[29].strip() if len(row) > 29 else ""

                cbo_cod, cid_status, cid_esperado = validar_cid_linha(
                    especialidade, cod_proc_fe, nome_proc_fe, cid_raw, mapas_cid
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
                    proc_fr = row[9].strip() if len(row) > 9 else ""
                    cid_raw = row[17].strip() if len(row) > 17 else ""

                    cbo_cod, cid_status, cid_esperado = validar_cid_linha(
                        especialidade, "", proc_fr, cid_raw, mapas_cid
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

    # Atualizar contadores do lote (preservando contagem existente caso apenas um lado tenha sido enviado)
    if not (caminho_siga and os.path.exists(caminho_siga)):
        total_fe = conn.execute("SELECT COUNT(*) FROM fila_espera_nominal").fetchone()[0]
    if not (caminho_fr03 and os.path.exists(caminho_fr03)):
        total_fr = conn.execute("SELECT COUNT(*) FROM fila_regulador_nominal").fetchone()[0]

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
        if fl.endswith(".csv") or fl.endswith(".zip") or fl.endswith(".txt"):
            if "siga" in fl and ("fila" in fl or "ativos" in fl or "operacional" in fl):
                siga_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)
            elif "fr-03" in fl or "fr03" in fl:
                fr03_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)
            elif "fr-04" in fl or "fr04" in fl:
                fr04_file = os.path.join(ARQUIVOS_LOCAIS_DIR, f)

    if not (siga_file or (fr03_file and fr04_file)):
        return None, "Não foram encontrados arquivos válidos (.CSV ou .ZIP) do SIGA ou FR-03/FR-04 na pasta."

    resumo = processar_arquivos_fila(
        siga_file, fr03_file, fr04_file,
        nome_siga=os.path.basename(siga_file) if siga_file else "Nenhum",
        nome_fr03=os.path.basename(fr03_file) if fr03_file else "Nenhum",
        nome_fr04=os.path.basename(fr04_file) if fr04_file else "Nenhum"
    )
    return resumo, None


def recalcular_validacoes_cid():
    """Recalcula a coluna de verificação cid_status e cid_esperado em todas as linhas baseado no cruzamento relacional (Especialidade + Procedimento)."""
    conn = get_db()
    mapas_cid = carregar_mapa_regras_cid(conn)

    # 1. Recalcular Fila de Espera Nominal
    fe_rows = conn.execute("SELECT id, especialidade, codigo_procedimento, procedimento, cid, cbo_codigo FROM fila_espera_nominal").fetchall()
    fe_updates = []
    for r in fe_rows:
        cbo_cod, cid_status, cid_esperado = validar_cid_linha(
            r["especialidade"], r["codigo_procedimento"], r["procedimento"], r["cid"], mapas_cid
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
    fr_rows = conn.execute("SELECT id, especialidade, procedimento, codigo_cid, cbo_codigo FROM fila_regulador_nominal").fetchall()
    fr_updates = []
    for r in fr_rows:
        cbo_cod, cid_status, cid_esperado = validar_cid_linha(
            r["especialidade"], "", r["procedimento"], r["codigo_cid"], mapas_cid
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
    headers_cids = ["Especialidade", "CID", "Descrição do CID", "Observações", "Procedimento", "CBO"]
    ws_cids.append(headers_cids)
    for col_idx in range(1, len(headers_cids) + 1):
        cell = ws_cids.cell(row=3, column=col_idx)
        cell.font = fonte_header_tabela
        cell.fill = fill_header_azul

    cids_rows = conn.execute("SELECT especialidade, cid, cid_descricao, observacoes, coalesce(procedimento_nome, procedimento_codigo, ''), cbo_codigo FROM fila_cid_config ORDER BY especialidade, cid").fetchall()
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


def obter_unidades_auditadas_cid():
    """
    Retorna a lista de estabelecimentos que possuem registros auditados de CID (CORRETO ou INCORRETO),
    com contagem de corretos, incorretos e total para seleção do usuário no modal de exportação.
    """
    conn = get_db()
    query = """
        SELECT
            unidade,
            SUM(corretos) AS corretos,
            SUM(incorretos) AS incorretos,
            SUM(corretos + incorretos) AS total
        FROM (
            SELECT
                UPPER(TRIM(nome_solicitante)) AS unidade,
                SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) AS corretos,
                SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) AS incorretos
            FROM fila_espera_nominal
            WHERE cid_status IN ('CORRETO', 'INCORRETO') AND nome_solicitante IS NOT NULL AND nome_solicitante != ''
            GROUP BY UPPER(TRIM(nome_solicitante))

            UNION ALL

            SELECT
                UPPER(TRIM(estabelecimento_solicitante)) AS unidade,
                SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) AS corretos,
                SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) AS incorretos
            FROM fila_regulador_nominal
            WHERE cid_status IN ('CORRETO', 'INCORRETO') AND estabelecimento_solicitante IS NOT NULL AND estabelecimento_solicitante != ''
            GROUP BY UPPER(TRIM(estabelecimento_solicitante))
        )
        GROUP BY unidade
        ORDER BY unidade ASC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def sanitizar_nome_arquivo(nome):
    """Remove caracteres proibidos pelo sistema operacional em nomes de arquivos."""
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '_', str(nome or '')).strip()
    nome_limpo = re.sub(r'\s+', '_', nome_limpo)
    return nome_limpo[:60]


def gerar_workbook_unidade_auditada(unidade, status_filtro="TODOS"):
    """
    Gera um objeto openpyxl.Workbook contendo exclusivamente as linhas auditadas
    da unidade solicitante especificada, divididas em abas estruturadas:
    1) Resumo_Conformidade
    2) Fila_Espera_SIGA
    3) Fila_Regulador_FR
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove aba padrão

    conn = get_db()

    fonte_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    fill_header_azul = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    fill_header_verde = PatternFill(start_color="196F3D", end_color="196F3D", fill_type="solid")
    fill_correto = PatternFill(start_color="E8F8F5", end_color="E8F8F5", fill_type="solid")
    fill_incorreto = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")
    font_correto = Font(name="Calibri", size=9, bold=True, color="145A32")
    font_incorreto = Font(name="Calibri", size=9, bold=True, color="922B21")
    font_normal = Font(name="Calibri", size=9)
    border_fina = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    where_status_fe = "AND cid_status IN ('CORRETO', 'INCORRETO')"
    where_status_fr = "AND cid_status IN ('CORRETO', 'INCORRETO')"
    if status_filtro == "CORRETO":
        where_status_fe = "AND cid_status = 'CORRETO'"
        where_status_fr = "AND cid_status = 'CORRETO'"
    elif status_filtro == "INCORRETO":
        where_status_fe = "AND cid_status = 'INCORRETO'"
        where_status_fr = "AND cid_status = 'INCORRETO'"

    # ----------------------------------------------------
    # 1. ABA RESUMO DE CONFORMIDADE DA UNIDADE
    # ----------------------------------------------------
    ws_res = wb.create_sheet(title="Resumo_Conformidade")
    ws_res.append([f"AUDITORIA DE CIDs DEFINIDOS - {unidade}"])
    ws_res.cell(row=1, column=1).font = Font(name="Calibri", size=13, bold=True, color="1F4E79")
    ws_res.append([f"Data Extração/Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Filtro: {status_filtro}"])
    ws_res.cell(row=2, column=1).font = Font(name="Calibri", size=9, italic=True, color="555555")
    ws_res.append([])

    headers_res = ["Especialidade", "Procedimento", "CBO", "Origem (Fila)", "Total Auditados", "CIDs Corretos", "CIDs Incorretos", "% Conformidade"]
    ws_res.append(headers_res)
    for col_idx in range(1, len(headers_res) + 1):
        cell = ws_res.cell(row=4, column=col_idx)
        cell.font = fonte_header
        cell.fill = fill_header_azul
        cell.alignment = Alignment(horizontal="center", vertical="center")

    res_query = f"""
        SELECT
            especialidade, procedimento, coalesce(cbo_codigo, '') as cbo, origem,
            total, corretos, incorretos
        FROM (
            SELECT
                especialidade, procedimento, cbo_codigo, 'Fila de Espera (SIGA)' as origem,
                count(*) as total,
                SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) as corretos,
                SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) as incorretos
            FROM fila_espera_nominal
            WHERE UPPER(TRIM(nome_solicitante)) = UPPER(TRIM(?))
              {where_status_fe}
            GROUP BY especialidade, procedimento, cbo_codigo

            UNION ALL

            SELECT
                especialidade, procedimento, cbo_codigo, 'Fila Regulador (FR)' as origem,
                count(*) as total,
                SUM(CASE WHEN cid_status = 'CORRETO' THEN 1 ELSE 0 END) as corretos,
                SUM(CASE WHEN cid_status = 'INCORRETO' THEN 1 ELSE 0 END) as incorretos
            FROM fila_regulador_nominal
            WHERE UPPER(TRIM(estabelecimento_solicitante)) = UPPER(TRIM(?))
              {where_status_fr}
            GROUP BY especialidade, procedimento, cbo_codigo
        )
        ORDER BY especialidade, origem
    """
    res_rows = conn.execute(res_query, (unidade, unidade)).fetchall()
    tot_geral = 0
    tot_corretos = 0
    tot_incorretos = 0
    for row_idx, r in enumerate(res_rows, start=5):
        tot = r[4]
        corr = r[5]
        inc = r[6]
        tot_geral += tot
        tot_corretos += corr
        tot_incorretos += inc
        pct = f"{(corr / tot * 100):.1f}%" if tot > 0 else "0.0%"
        ws_res.append([r[0], r[1], r[2], r[3], tot, corr, inc, pct])
        for col_idx in range(1, len(headers_res) + 1):
            cell = ws_res.cell(row=row_idx, column=col_idx)
            cell.font = font_normal
            cell.border = border_fina
            if col_idx in [5, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center")

    if res_rows:
        row_tot = len(res_rows) + 5
        pct_tot = f"{(tot_corretos / tot_geral * 100):.1f}%" if tot_geral > 0 else "0.0%"
        ws_res.append(["TOTAL DA UNIDADE", "-", "-", "-", tot_geral, tot_corretos, tot_incorretos, pct_tot])
        for col_idx in range(1, len(headers_res) + 1):
            cell = ws_res.cell(row=row_tot, column=col_idx)
            cell.font = Font(name="Calibri", size=10, bold=True, color="1F4E79")
            cell.border = border_fina
            cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            if col_idx in [5, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center")

    # ----------------------------------------------------
    # 2. ABA FILA DE ESPERA (SIGA)
    # ----------------------------------------------------
    ws_fe = wb.create_sheet(title="Fila_Espera_SIGA")
    headers_fe = [
        "Data Inclusão", "Estabelecimento Solicitante", "Especialidade", "CBO",
        "Código Procedimento", "Procedimento", "Tipo Atendimento", "Protocolo",
        "Nome Paciente", "CNS Paciente", "Idade", "Sexo", "Prioridade",
        "CID Informado", "Conferência CID", "CID Esperado (Regra)", "Observações"
    ]
    ws_fe.append(headers_fe)
    for col_idx in range(1, len(headers_fe) + 1):
        cell = ws_fe.cell(row=1, column=col_idx)
        cell.font = fonte_header
        cell.fill = fill_header_azul
        cell.alignment = Alignment(horizontal="center", vertical="center")

    fe_query = f"""
        SELECT
            data_inclusao, nome_solicitante, especialidade, coalesce(cbo_codigo, ''),
            coalesce(codigo_procedimento, ''), coalesce(procedimento, ''),
            coalesce(tipo_atendimento, ''), coalesce(protocolo, ''),
            nome_paciente, cns_paciente, idade, sexo, prioridade,
            cid, cid_status, coalesce(cid_esperado, ''), coalesce(observacoes, '')
        FROM fila_espera_nominal
        WHERE UPPER(TRIM(nome_solicitante)) = UPPER(TRIM(?))
          {where_status_fe}
        ORDER BY especialidade, nome_paciente
    """
    fe_rows = conn.execute(fe_query, (unidade,)).fetchall()
    for row_idx, r in enumerate(fe_rows, start=2):
        ws_fe.append(list(r))
        status_val = r[14]
        for col_idx in range(1, len(headers_fe) + 1):
            cell = ws_fe.cell(row=row_idx, column=col_idx)
            cell.font = font_normal
            cell.border = border_fina
        cell_status = ws_fe.cell(row=row_idx, column=15)
        if status_val == "CORRETO":
            cell_status.fill = fill_correto
            cell_status.font = font_correto
        elif status_val == "INCORRETO":
            cell_status.fill = fill_incorreto
            cell_status.font = font_incorreto

    # ----------------------------------------------------
    # 3. ABA FILA DO REGULADOR (FR-03/04)
    # ----------------------------------------------------
    ws_fr = wb.create_sheet(title="Fila_Regulador_FR")
    headers_fr = [
        "Data Entrada Fila", "Número Solicitação", "Estabelecimento Solicitante",
        "Especialidade", "CBO", "Procedimento", "Prioridade",
        "Nome Paciente", "CNS Paciente", "Idade", "Sexo",
        "Código CID Informado", "Nome CID", "Motivo Encaminhamento",
        "Situação Regulação (FR-04)", "Conferência CID", "CID Esperado (Regra)"
    ]
    ws_fr.append(headers_fr)
    for col_idx in range(1, len(headers_fr) + 1):
        cell = ws_fr.cell(row=1, column=col_idx)
        cell.font = fonte_header
        cell.fill = fill_header_verde
        cell.alignment = Alignment(horizontal="center", vertical="center")

    fr_query = f"""
        SELECT
            data_entrada_fila, numero_solicitacao, estabelecimento_solicitante,
            especialidade, coalesce(cbo_codigo, ''), coalesce(procedimento, ''), prioridade,
            nome_paciente, cns_paciente, idade, sexo,
            codigo_cid, coalesce(nome_cid, ''), coalesce(motivo_encaminhamento, ''),
            coalesce(situacao_fila_regulador, ''), cid_status, coalesce(cid_esperado, '')
        FROM fila_regulador_nominal
        WHERE UPPER(TRIM(estabelecimento_solicitante)) = UPPER(TRIM(?))
          {where_status_fr}
        ORDER BY especialidade, nome_paciente
    """
    fr_rows = conn.execute(fr_query, (unidade,)).fetchall()
    for row_idx, r in enumerate(fr_rows, start=2):
        ws_fr.append(list(r))
        status_val = r[15]
        for col_idx in range(1, len(headers_fr) + 1):
            cell = ws_fr.cell(row=row_idx, column=col_idx)
            cell.font = font_normal
            cell.border = border_fina
        cell_status = ws_fr.cell(row=row_idx, column=16)
        if status_val == "CORRETO":
            cell_status.fill = fill_correto
            cell_status.font = font_correto
        elif status_val == "INCORRETO":
            cell_status.fill = fill_incorreto
            cell_status.font = font_incorreto

    # Autoajuste de colunas e congelamento de painéis
    for ws in [ws_res, ws_fe, ws_fr]:
        ws.freeze_panes = "A2" if ws != ws_res else "A5"
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                v = str(cell.value or "")
                if "\n" in v:
                    v = v.split("\n")[0]
                if len(v) > max_len:
                    max_len = len(v)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 48)

    conn.close()
    return wb


def gerar_exportacao_auditoria_cids(unidades_selecionadas, status_filtro="TODOS"):
    """
    Gera a exportação de auditoria de CIDs por unidade:
    - Se 1 unidade: retorna BytesIO do arquivo individual .xlsx.
    - Se 2 ou mais unidades: empacota todas as planilhas individuais em um arquivo .zip.
    Retorna tupla: (BytesIO, nome_arquivo, mimetype)
    """
    if not unidades_selecionadas:
        todas = obter_unidades_auditadas_cid()
        unidades_selecionadas = [u["unidade"] for u in todas]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Caso 1: Apenas 1 unidade selecionada -> Download direto do XLSX
    if len(unidades_selecionadas) == 1:
        unidade = unidades_selecionadas[0]
        wb = gerar_workbook_unidade_auditada(unidade, status_filtro)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        nome_arq = f"Auditoria_CIDs_{sanitizar_nome_arquivo(unidade)}_{timestamp}.xlsx"
        return output, nome_arq, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Caso 2: Múltiplas unidades -> Download de ZIP com 1 arquivo por unidade
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for unidade in unidades_selecionadas:
            wb = gerar_workbook_unidade_auditada(unidade, status_filtro)
            unit_buffer = io.BytesIO()
            wb.save(unit_buffer)
            nome_unit = f"Auditoria_CIDs_{sanitizar_nome_arquivo(unidade)}.xlsx"
            zf.writestr(nome_unit, unit_buffer.getvalue())

    zip_buffer.seek(0)
    nome_zip = f"Auditoria_CIDs_Por_Unidade_{timestamp}.zip"
    return zip_buffer, nome_zip, "application/zip"


def obter_nominal_fe_json(estab_filtro=None, espec_filtro=None, status_cid_filtro=None):
    """
    Retorna todos os registros da Fila de Espera Nominal em formato JSON/dict
    otimizado para DataTables com renderização rápida no navegador e suporte ao Excel Filter.
    """
    conn = get_db()
    filtros = []
    params = []
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
            data_inclusao, nome_solicitante, especialidade, cbo_codigo, procedimento,
            tipo_atendimento, protocolo, nome_paciente, cns_paciente, prioridade,
            cid, cid_status, cid_esperado
        FROM fila_espera_nominal
        {where_clause}
        ORDER BY data_inclusao DESC
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = []
    for r in rows:
        status_cid = r["cid_status"] or "N/A"
        if status_cid == "CORRETO":
            badge = '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="bi bi-check-circle me-1"></i>Correto</span>'
        elif status_cid == "INCORRETO":
            badge = f'<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1" title="Esperado: {r["cid_esperado"]}"><i class="bi bi-x-circle me-1"></i>Incorreto</span>'
        else:
            badge = '<span class="badge bg-secondary-subtle text-secondary border px-2 py-1">N/A</span>'

        cbo_badge = f'<span class="badge bg-light text-dark border font-monospace">{r["cbo_codigo"]}</span>' if r["cbo_codigo"] else '<span class="text-muted">-</span>'
        cid_badge = f'<span class="badge bg-light text-primary border font-monospace fw-bold">{r["cid"]}</span>' if r["cid"] else '-'

        data.append([
            r["data_inclusao"] or "-",
            r["nome_solicitante"] or "-",
            r["especialidade"] or "-",
            cbo_badge,
            r["procedimento"] or "-",
            r["tipo_atendimento"] or "-",
            f'<span class="font-monospace fw-semibold">{r["protocolo"]}</span>' if r["protocolo"] else "-",
            f'<span class="fw-semibold text-primary">{r["nome_paciente"]}</span>' if r["nome_paciente"] else "-",
            f'<span class="font-monospace small text-muted">{r["cns_paciente"]}</span>' if r["cns_paciente"] else "-",
            r["prioridade"] or "-",
            cid_badge,
            badge
        ])

    return {"data": data}


def obter_nominal_fr_json(estab_filtro=None, espec_filtro=None, status_cid_filtro=None):
    """
    Retorna todos os registros da Fila do Regulador Nominal em formato JSON/dict
    otimizado para DataTables com renderização rápida no navegador e suporte ao Excel Filter.
    """
    conn = get_db()
    filtros = []
    params = []
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
            data_entrada_fila, estabelecimento_solicitante, especialidade, cbo_codigo, procedimento,
            prioridade, numero_solicitacao, nome_paciente, codigo_cid, cid_status, cid_esperado,
            situacao_fila_regulador
        FROM fila_regulador_nominal
        {where_clause}
        ORDER BY data_entrada_fila DESC
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = []
    for r in rows:
        status_cid = r["cid_status"] or "N/A"
        if status_cid == "CORRETO":
            badge = '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="bi bi-check-circle me-1"></i>Correto</span>'
        elif status_cid == "INCORRETO":
            badge = f'<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1" title="Esperado: {r["cid_esperado"]}"><i class="bi bi-x-circle me-1"></i>Incorreto</span>'
        else:
            badge = '<span class="badge bg-secondary-subtle text-secondary border px-2 py-1">N/A</span>'

        prio = r["prioridade"] or "-"
        if "alta" in prio.lower():
            prio_badge = f'<span class="badge bg-danger text-white">{prio}</span>'
        elif "méd" in prio.lower() or "med" in prio.lower():
            prio_badge = f'<span class="badge bg-warning text-dark">{prio}</span>'
        else:
            prio_badge = f'<span class="badge bg-info text-dark">{prio}</span>'

        cbo_badge = f'<span class="badge bg-light text-dark border font-monospace">{r["cbo_codigo"]}</span>' if r["cbo_codigo"] else '<span class="text-muted">-</span>'
        cid_badge = f'<span class="badge bg-light text-primary border font-monospace fw-bold">{r["codigo_cid"]}</span>' if r["codigo_cid"] else '-'

        data.append([
            r["data_entrada_fila"] or "-",
            r["estabelecimento_solicitante"] or "-",
            r["especialidade"] or "-",
            cbo_badge,
            r["procedimento"] or "-",
            prio_badge,
            f'<span class="font-monospace fw-semibold">{r["numero_solicitacao"]}</span>' if r["numero_solicitacao"] else "-",
            f'<span class="fw-semibold text-primary">{r["nome_paciente"]}</span>' if r["nome_paciente"] else "-",
            cid_badge,
            badge,
            f'<span class="badge bg-light text-dark border small">{r["situacao_fila_regulador"]}</span>' if r["situacao_fila_regulador"] else "-"
        ])

    return {"data": data}


def executar_extracao_bi_fr(usuario, senha, relatorio_opcao="FR_TODOS", callback_status=None, cancel_event=None):
    """
    Executa o robô Playwright para extrair os relatórios FR-03 e/ou FR-04 diretamente do portal SIGA Saúde / BI.
    Aplica os filtros da STS Penha e substitui automaticamente os registros da Fila do Regulador no SQLite.
    """
    from services.utils import bot_setup_page, download_bi
    import time

    def log(msg, pct=None):
        if callback_status:
            callback_status(msg, pct)
        print(f"[BI Regulação] {msg}")

    log("Iniciando navegador seguro para acesso ao BI Prodam...", 5)
    p = None
    browser = None
    page = None
    caminhos_baixados = {}

    try:
        if cancel_event and cancel_event.is_set():
            return None, "Operação cancelada pelo usuário."

        p, browser, page = bot_setup_page(usuario, senha, headless=True, default_timeout=60000)

        # 1. Navegar até o BI Prodam
        log("Acessando portal corporativo do SIGA Saúde / BI...", 15)
        page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")
        page.wait_for_load_state("networkidle", timeout=60000)

        if cancel_event and cancel_event.is_set():
            return None, "Operação cancelada pelo usuário."

        relatorios_para_extrair = []
        if relatorio_opcao in ["FR_TODOS", "FR_03"]:
            relatorios_para_extrair.append("FR_03")
        if relatorio_opcao in ["FR_TODOS", "FR_04"]:
            relatorios_para_extrair.append("FR_04")

        for idx, cod_rel in enumerate(relatorios_para_extrair):
            if cancel_event and cancel_event.is_set():
                return None, "Operação cancelada pelo usuário."

            base_pct = 20 + int(idx * 35)
            nome_amigavel = "FR-03 (Lista Nominal com Motivo)" if cod_rel == "FR_03" else "FR-04 (Devolvidos e Reinseridos)"
            log(f"Navegando para o relatório {nome_amigavel}...", base_pct)

            # Voltar para a página inicial se não estiver nela
            if not page.url.endswith("Inicial.aspx"):
                page.goto("https://biprodam.saude.prefeitura.sp.gov.br/sites/siga/Paginas/Inicial.aspx")
                page.wait_for_load_state("networkidle", timeout=60000)

            # Localizar e clicar na categoria Regulação
            categoria_encontrada = False
            for cat_nome in ["Regulação", "Regulacao", "Fila Regulação", "Fila Regulacao", "Fila de Regulação"]:
                try:
                    elem = page.get_by_text(cat_nome).first
                    if elem.is_visible(timeout=2000):
                        elem.click()
                        categoria_encontrada = True
                        break
                except Exception:
                    continue

            if not categoria_encontrada:
                try:
                    page.locator("a:has-text('Regula')").first.click(timeout=3000)
                except Exception:
                    pass

            page.wait_for_timeout(1500)

            # Clicar no relatório correspondente
            prefixo_busca = "FR-03" if cod_rel == "FR_03" else "FR-04"
            log(f"Abrindo relatório {prefixo_busca}...", base_pct + 5)
            page.get_by_text(prefixo_busca, exact=False).first.click(timeout=15000)
            page.wait_for_load_state("networkidle", timeout=60000)

            if cancel_event and cancel_event.is_set():
                return None, "Operação cancelada pelo usuário."

            log(f"Configurando parâmetros da STS Penha para {prefixo_busca}...", base_pct + 10)

            # Preenchimento tolerante dos parâmetros do SSRS
            # Nível 2
            try:
                elem_n2 = page.locator("[title*='Nível 2'], [title*='Nivel 2']").first
                if elem_n2.is_visible(timeout=3000):
                    elem_n2.click()
                    page.wait_for_timeout(500)
                    page.get_by_text("COORD", exact=False).first.click(timeout=10000)
                    try:
                        page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=3000)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[SSRS] Nível 2: {e}")

            page.wait_for_timeout(1000)

            # Nível 3
            try:
                elem_n3 = page.locator("[title*='Nível 3'], [title*='Nivel 3']").first
                if elem_n3.is_visible(timeout=3000):
                    elem_n3.click()
                    page.wait_for_timeout(500)
                    page.get_by_text("PENHA", exact=False).first.click(timeout=10000)
                    try:
                        page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=3000)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[SSRS] Nível 3: {e}")

            page.wait_for_timeout(1000)

            # Parâmetros adicionais se presentes: Estabelecimento, Especialidade, Procedimento -> All
            for param_nome in ["Estabelecimento", "Especialidade", "Procedimento", "Regulador"]:
                try:
                    elem_p = page.locator(f"[title*='{param_nome}']").first
                    if elem_p.is_visible(timeout=2000):
                        elem_p.click()
                        page.wait_for_timeout(400)
                        page.get_by_text("All", exact=True).first.click(timeout=5000)
                        try:
                            page.locator("#m_sqlRsWebPart_ctl00_ctl19_ButtonCell").click(position={"x": 10, "y": 10}, timeout=3000)
                        except Exception:
                            pass
                except Exception:
                    pass

            if cancel_event and cancel_event.is_set():
                return None, "Operação cancelada pelo usuário."

            log(f"Aplicando filtros e gerando exportação CSV de {prefixo_busca}...", base_pct + 18)
            caminho_csv = download_bi(page, click_timeout=60000, timeout_geral=1500)
            caminhos_baixados[cod_rel] = caminho_csv
            log(f"Relatório {prefixo_busca} exportado com sucesso: {os.path.basename(caminho_csv)}", base_pct + 25)

        # Ingestão e substituição dos arquivos no SQLite
        log("Processando relatórios e substituindo registros antigos no banco de dados...", 90)
        caminho_fr03 = caminhos_baixados.get("FR_03")
        caminho_fr04 = caminhos_baixados.get("FR_04")

        resumo = processar_arquivos_fila(
            caminho_siga=None,
            caminho_fr03=caminho_fr03,
            caminho_fr04=caminho_fr04,
            nome_siga="Preservado",
            nome_fr03=os.path.basename(caminho_fr03) if caminho_fr03 else "Nenhum",
            nome_fr04=os.path.basename(caminho_fr04) if caminho_fr04 else "Nenhum"
        )

        log(f"Processamento concluído com sucesso! Total na Fila do Regulador: {resumo['total_fr']} registros.", 100)
        return resumo, None

    except Exception as e:
        import traceback
        traceback.print_exc()
        msg_erro = str(e)
        if any(t in msg_erro for t in ["Executable doesn't exist", "playwright install", "Chromium"]):
            msg_erro = "Navegador de automação (Chromium) não configurado. Execute instalar.bat."
        log(f"Falha na extração do BI: {msg_erro}", None)
        return None, msg_erro

    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass

