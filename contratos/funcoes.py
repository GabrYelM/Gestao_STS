"""
Módulo Unificado de Funções de Negócio, Cálculo e Regras Contratuais.

Unifica:
1. Motor de Cálculo e Apuração da Produção (fato_apuracao):
   - AT-02, WebSaass, Visitas Domiciliares (eSUS), BI SIGA, DTIC REL130/134
   - Resolução de estabelecimentos (CMES / CNES / De-Para), CBOs e procedimentos
   - Recálculo global ou por fonte, logs de auditoria e auto-cadastro de pendentes
2. Consolidação Territorial (CMES vs CNES):
   - Agrupamento de unidades, resolução de cadastros principais e tratamento de metas
3. Diagnóstico de Metas:
   - Identificação de divergências de vigência de TA, subgrupo, CBO ou ausência de produção
4. Gestão de Pendências Cadastrais:
   - Identificação de unidades e profissionais não cadastrados no staging
5. Carga Base em Lote:
   - Importação e validação de indicadores, vínculos e metas a partir de planilhas/JSON
"""

import csv
import io
import json
import re
import sys
import unicodedata
from collections import Counter

from .etl import carregar_catalogo_procedimentos, normalizar_cod_procedimento

# ==============================================================================
# 1. NORMALIZAÇÃO DE PERÍODOS E RESOLUÇÃO DE ENTIDADES
# ==============================================================================

MESES_NUM_PARA_SIGLA = {
    "01": "JAN", "02": "FEV", "03": "MAR", "04": "ABR", "05": "MAI", "06": "JUN",
    "07": "JUL", "08": "AGO", "09": "SET", "10": "OUT", "11": "NOV", "12": "DEZ",
}
MESES_SIGLA_PARA_NUM = {v: k for k, v in MESES_NUM_PARA_SIGLA.items()}
MESES_EXTENSO_PARA_NUM = {
    "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÇO": "03", "ABRIL": "04",
    "MAIO": "05", "JUNHO": "06", "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09",
    "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12",
}


def _normalizar_periodo(periodo):
    """
    Normaliza qualquer formato de competência para 'AAAAMM' (ex.: '202608').
    Aceita '202608', '2026-08', '2026/08', '08/2026', 'AGO 2026', 'AGO/2026', 'Agosto 2026'.
    """
    if not periodo:
        return ""
    p = str(periodo).strip().upper().replace("-", "").replace("/", "").replace(" ", "")
    if len(p) == 6 and p.isdigit():
        return p
    if len(p) == 6 and p[:2].isdigit() and p[2:].isdigit():
        if int(p[:2]) <= 12 and int(p[2:]) >= 2000:
            return f"{p[2:]}{p[:2]}"
    for sigla, num in MESES_SIGLA_PARA_NUM.items():
        if sigla in p:
            ano = "".join(ch for ch in p if ch.isdigit())
            if len(ano) == 4:
                return f"{ano}{num}"
    for ext, num in MESES_EXTENSO_PARA_NUM.items():
        if ext in p:
            ano = "".join(ch for ch in p if ch.isdigit())
            if len(ano) == 4:
                return f"{ano}{num}"
    return p


def _periodo_para_webssas(periodo):
    """Converte '202608' para 'AGO 2026' (padrão de staging_webssas.periodo)."""
    p = _normalizar_periodo(periodo)
    if len(p) == 6 and p.isdigit():
        ano = p[:4]
        mes = p[4:6]
        sigla = MESES_NUM_PARA_SIGLA.get(mes, mes)
        return f"{sigla} {ano}"
    return periodo


def _resolver_estabelecimento(db, cod_cmes, cod_cnes=None, com_origem=False):
    """
    Casa a linha do arquivo com um estabelecimento cadastrado, na ordem:
      1. CMES exato;
      2. CMES ignorando zeros à esquerda ('0123' x '123');
      3. CNES, quando o CMES da linha NÃO está cadastrado: só se o CNES aponta para UM cadastro,
         ou, havendo vários, para o cadastro principal do CNES (onde CMES == CNES).
    """
    cmes = (cod_cmes or "").strip()
    cnes = (cod_cnes or "").strip()
    achado, origem = None, None
    if cmes:
        row = db.execute("SELECT id FROM estabelecimentos WHERE cod_cmes = ?", (cmes,)).fetchone()
        if row:
            achado, origem = row["id"], "cmes"
        elif cmes.lstrip("0"):
            row = db.execute(
                "SELECT id FROM estabelecimentos WHERE ltrim(cod_cmes, '0') = ?", (cmes.lstrip("0"),)
            ).fetchone()
            if row:
                achado, origem = row["id"], "cmes_zeros"
    if achado is None and cnes.lstrip("0"):
        rows = db.execute(
            "SELECT id, cod_cmes FROM estabelecimentos WHERE ltrim(cod_cnes, '0') = ? ORDER BY id", (cnes.lstrip("0"),)
        ).fetchall()
        if len(rows) == 1:
            achado, origem = rows[0]["id"], "cnes"
        elif len(rows) > 1:
            principais = [r for r in rows if (r["cod_cmes"] or "").strip().lstrip("0") == cnes.lstrip("0")]
            if len(principais) == 1:
                achado, origem = principais[0]["id"], "cnes"
    return (achado, origem) if com_origem else achado


def _resolver_estabelecimento_por_nome(db, nome_estabelecimento):
    """Localiza o estabelecimento pelo nome na Penha, desconsiderando variações de maiúsculas/acentos."""
    if not nome_estabelecimento:
        return None
    nome = str(nome_estabelecimento).strip().lower()
    row = db.execute("SELECT id FROM estabelecimentos WHERE lower(nome) = ?", (nome,)).fetchone()
    if row:
        return row["id"]
    row = db.execute("SELECT estabelecimento_id FROM de_para_websaass_unidade WHERE lower(trim(nome_websass)) = ?", (nome,)).fetchone()
    if row:
        return row["estabelecimento_id"]
    row = db.execute("SELECT id FROM estabelecimentos WHERE lower(nome) LIKE ?", (f"%{nome}%",)).fetchone()
    if row:
        return row["id"]
    return None


def _resolver_estabelecimento_por_cnes(db, cod_cnes, indicador_id=None):
    """
    Resolve estabelecimento por CNES com desempate por cadastro principal e serviço.
    """
    if not cod_cnes:
        return None, "nao_encontrado"
    cnes = str(cod_cnes).strip().lstrip("0")
    if not cnes:
        return None, "nao_encontrado"

    if indicador_id is not None:
        alternativo = db.execute(
            """SELECT estabelecimento_id FROM indicador_estabelecimento_cnes_alternativo
               WHERE indicador_id=? AND ltrim(cnes_alternativo, '0')=?""",
            (indicador_id, cnes),
        ).fetchone()
        if alternativo:
            return alternativo["estabelecimento_id"], "ok"

    linhas = db.execute(
        "SELECT id, cod_cmes FROM estabelecimentos WHERE ltrim(cod_cnes, '0') = ? ORDER BY id", (cnes,)
    ).fetchall()
    if len(linhas) == 0:
        return None, "nao_encontrado"
    if len(linhas) == 1:
        return linhas[0]["id"], "ok"

    principais = [r for r in linhas if (r["cod_cmes"] or "").strip().lstrip("0") == cnes]
    if len(principais) == 1:
        return principais[0]["id"], "ok"

    if indicador_id is not None:
        servico_row = db.execute("SELECT servico FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
        if servico_row and servico_row["servico"]:
            servico = servico_row["servico"].strip().lower()
            compativeis = db.execute(
                """SELECT e.id FROM estabelecimentos e
                   JOIN estabelecimento_tipo_servico ets ON ets.estabelecimento_id = e.id
                   WHERE ltrim(e.cod_cnes, '0') = ? AND lower(ets.tipo_servico) = ?""",
                (cnes, servico),
            ).fetchall()
            if len(compativeis) == 1:
                return compativeis[0]["id"], "ok"

    return linhas[0]["id"], "ok"


MAPEAMENTO_EMULTI_PADRAO = [
    ("maringa", 52),       # Ubs Jardim Maringa - Vila Talarico
    ("villalobo", 55),     # Ubs Dr. Antonio Pires Ferreira Villalobo
    ("guilhermina", 66),   # Ubs Vila Guilhermina - Dr Americo Raspa Neto
    ("nobrega", 5),        # Ama/Ubs Integrada Padre Manoel Da Nobrega
    ("vila silvia", 6),    # Ama/Ubs Integrada Vila Silvia
    ("silvia", 6),         # Ama/Ubs Integrada Vila Silvia
    ("trindade", 57),      # Ubs Eng Trindade
    ("ae carvalho", 53),   # Ubs Ae Carvalho
    ("carvalho", 53),      # Ubs Ae Carvalho
    ("chacara", 4),        # Ama/Ubs Integrada Chacara Cruzeiro Do Sul
    ("esperanca", 63),     # Ubs Vila Esperanca-Cassio Bittencourt Filho
    ("sao francisco", 58), # Ubs Jardim Sao Francisco I
    ("arthur alvim", 60),  # Ubs Parque Arthur Alvim
    ("anchieta", 61),      # Ubs Pe Jose De Anchieta
    ("aricanduva", 62),    # Ubs Vila Aricanduva
    ("goulart", 56),       # Ubs Eng Goulart- Dr Jose Pires
    ("granada", 65),       # Ubs Vila Granada-Alfredo F Paulino Filho
    ("matilde", 67),       # Ubs Vila Matilde - Dr Rubens Do Val
    ("cangaiba", 21),      # Ama/Ubs Integrada Cangaiba - Dr. Carlos Gentile De Mello
    ("patriarca", 54),     # Ubs Cidade Patriarca - Dr Hermenegildo Morbin Junior
    ("emilio", 64),        # Ubs Vila Esperanca-Emilio Santiago De Oliveira
    ("sao nicolau", 59),   # Ubs Jardim Sao Nicolau
]


def resolver_unidade_at57(db, nome_estabelecimento, cod_cnes=None, indicador_id=None):
    """
    Resolve o estabelecimento de destino para linhas do relatório AT-57.
    Aplica:
      1. Vínculo manual explícito da tabela indicador_unidade_origem (se indicador_id informado).
      2. Regra de eMulti/eMAB: o último nome (após '/') define a unidade de referência.
      3. Caso geral: resolução por CNES ou nome direto da unidade.
    """
    nome = (nome_estabelecimento or "").strip()
    if not nome:
        return None, None

    # 1. Checa indicador_unidade_origem para o indicador específico
    if indicador_id:
        row = db.execute(
            """SELECT uo.estabelecimento_id, e.nome
               FROM indicador_unidade_origem uo
               JOIN estabelecimentos e ON e.id = uo.estabelecimento_id
               WHERE uo.indicador_id = ? AND lower(trim(uo.nome_origem)) = lower(trim(?))""",
            (indicador_id, nome),
        ).fetchone()
        if row:
            return row["estabelecimento_id"], row["nome"]

    # 2. Regra de eMulti/eMAB pelo último nome
    nome_low = nome.lower()
    if "emulti" in nome_low or "emab" in nome_low:
        partes = nome.split("/")
        ultimo = partes[-1].strip()
        for pref in ["inativo - emab ", "inativo -  emab ", "inativo - emulti ", "emulti ", "emab "]:
            if ultimo.lower().startswith(pref):
                ultimo = ultimo[len(pref):].strip()
                break
        u_low = ultimo.lower()
        for termo, estab_id in MAPEAMENTO_EMULTI_PADRAO:
            if termo in u_low:
                e = db.execute("SELECT id, nome FROM estabelecimentos WHERE id = ?", (estab_id,)).fetchone()
                if e:
                    return e["id"], e["nome"]

    # 3. Não é eMulti: busca por CNES
    if cod_cnes:
        cnes_str = str(cod_cnes).strip().lstrip("0")
        cnes_matches = db.execute(
            "SELECT id, nome FROM estabelecimentos WHERE ltrim(cod_cnes, '0') = ?", (cnes_str,)
        ).fetchall()
        for e in cnes_matches:
            if nome_low in e["nome"].lower() or e["nome"].lower() in nome_low:
                return e["id"], e["nome"]
        if len(cnes_matches) == 1:
            return cnes_matches[0]["id"], cnes_matches[0]["nome"]

    # 4. Busca por nome direto
    row = db.execute("SELECT id, nome FROM estabelecimentos WHERE lower(nome) = ?", (nome_low,)).fetchone()
    if row:
        return row["id"], row["nome"]
    row = db.execute("SELECT id, nome FROM estabelecimentos WHERE lower(nome) LIKE ?", (f"%{nome_low}%",)).fetchone()
    if row:
        return row["id"], row["nome"]

    return None, None


def autovincular_emulti_indicador(db, indicador_id):
    """
    Popula indicador_unidade_origem para um indicador aplicando a regra do último
    nome em todas as equipes eMulti/eMAB encontradas no staging do AT-57.
    Vincula prioritariamente as equipes que atendem unidades com meta cadastrada
    para este indicador (ou todas caso o indicador ainda não tenha metas).
    """
    estabs_meta = {
        r["estabelecimento_id"] for r in db.execute(
            "SELECT DISTINCT estabelecimento_id FROM metas WHERE indicador_id = ?", (indicador_id,)
        ).fetchall()
    }

    linhas = db.execute(
        """SELECT DISTINCT nome_estabelecimento, cod_cnes
           FROM staging_bi_siga
           WHERE fonte_at = 'AT57'
             AND (lower(nome_estabelecimento) LIKE '%emulti%' OR lower(nome_estabelecimento) LIKE '%emab%')"""
    ).fetchall()

    criados = 0
    for r in linhas:
        nome_origem = r["nome_estabelecimento"]
        estab_id, _ = resolver_unidade_at57(db, nome_origem, r["cod_cnes"], indicador_id=None)
        if estab_id:
            # Se o indicador tem metas, vincula apenas as equipes pertinentes a ele
            if estabs_meta and estab_id not in estabs_meta:
                continue
            db.execute(
                """INSERT INTO indicador_unidade_origem (indicador_id, nome_origem, estabelecimento_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(indicador_id, nome_origem)
                   DO UPDATE SET estabelecimento_id = excluded.estabelecimento_id""",
                (indicador_id, nome_origem, estab_id),
            )
            criados += 1
    db.commit()
    return criados


def _categoria_contrato(db, estabelecimento_id):
    if not estabelecimento_id:
        return None
    row = db.execute("SELECT categoria_contrato FROM estabelecimentos WHERE id = ?", (estabelecimento_id,)).fetchone()
    return row["categoria_contrato"] if row else None


def _resolver_cbo(db, cod_cbo_sus, nome_cbo1):
    if cod_cbo_sus:
        row = db.execute("SELECT codigo FROM cbo WHERE codigo = ?", (cod_cbo_sus,)).fetchone()
        if row:
            return row["codigo"]
    if not nome_cbo1:
        return None
    import unicodedata
    def _norm(s):
        return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn").strip()

    cbo_norm = _norm(nome_cbo1)
    mapa_especial = {
        "assistente social": "251605",
        "farmaceutico": "223405",
        "fisioterapeuta": "223605",
        "fisioterapeuta geral": "223605",
        "fonoaudiologo": "223810",
        "medico ginecologista e obstetra": "225250",
        "medico ginecologista": "225250",
        "medico psiquiatra": "225133",
        "nutricionista": "223710",
        "profissional de educacao fisica na saude": "224140",
        "psicologo clinico": "251510",
        "psicologo": "251510",
        "terapeuta ocupacional": "223905",
    }
    if cbo_norm in mapa_especial:
        return mapa_especial[cbo_norm]

    row = db.execute("SELECT codigo FROM cbo WHERE lower(nome_categoria) = lower(?)", (nome_cbo1,)).fetchone()
    if row:
        return row["codigo"]

    row_like = db.execute("SELECT codigo FROM cbo WHERE lower(nome_categoria) LIKE lower(?) LIMIT 1", (f"{cbo_norm}%",)).fetchone()
    return row_like["codigo"] if row_like else None


def _garantir_procedimento(db, codigo, nome):
    if not codigo:
        return None
    db.execute("INSERT OR IGNORE INTO procedimentos (codigo, nome) VALUES (?, ?)", (codigo, nome or codigo))
    return codigo


def _carregar_mapa_depara_procedimentos(db):
    """Traduções automáticas de SIGA para SIGTAP desativadas: apuração usa códigos exatos vinculados."""
    return {}, {}


def _obter_codigos_equivalentes(procedimento_codigo, mapa_depara=None):
    if not procedimento_codigo:
        return []
    return [str(procedimento_codigo).strip()]


def _candidatos_indicador_subgrupo(db, procedimento_codigo, estabelecimento_id, categoria_estabelecimento=None, fonte_id=None, mapa_depara=None):
    if not procedimento_codigo:
        return []
    cod = str(procedimento_codigo).strip()

    incluidos = db.execute(
        """SELECT ip.indicador_id, ip.subgrupo_id, ip.categoria_estabelecimento, ip.categoria_estabelecimento_neg
           FROM indicador_procedimento ip
           JOIN indicadores i ON i.id = ip.indicador_id
           WHERE ip.procedimento_codigo = ? AND ip.tipo_vinculo = 'inclusao'
             AND (ip.estabelecimento_id IS NULL OR ip.estabelecimento_id = ?)
             AND (? IS NULL OR i.fonte_id IS NULL OR i.fonte_id = ?)""",
        (cod, estabelecimento_id, fonte_id, fonte_id),
    ).fetchall()

    cat_estab = (categoria_estabelecimento or "").strip().lower()
    resultado = []
    vistos = set()
    for row in incluidos:
        indicador_id, subgrupo_id = row["indicador_id"], row["subgrupo_id"]

        cat_pos = (row["categoria_estabelecimento"] or "").strip().lower()
        if cat_pos and cat_pos != cat_estab:
            continue
        cat_neg = (row["categoria_estabelecimento_neg"] or "").strip().lower()
        if cat_neg and cat_neg == cat_estab:
            continue

        chave = (indicador_id, subgrupo_id)
        if chave in vistos:
            continue
        vistos.add(chave)

        excluido = db.execute(
            """SELECT 1 FROM indicador_procedimento
               WHERE indicador_id = ? AND procedimento_codigo = ? AND tipo_vinculo = 'exclusao'
                 AND (estabelecimento_id IS NULL OR estabelecimento_id = ?)
                 AND (subgrupo_id IS NULL OR subgrupo_id = ?)
               LIMIT 1""",
            (indicador_id, cod, estabelecimento_id, subgrupo_id),
        ).fetchone()
        if not excluido:
            resultado.append((indicador_id, subgrupo_id))
    return resultado


def _cbo_permitido(db, indicador_id, cbo_codigo):
    vinculos = db.execute(
        "SELECT cbo_codigo, curinga FROM indicador_cbo WHERE indicador_id = ? AND subgrupo_id IS NULL",
        (indicador_id,),
    ).fetchall()
    if not vinculos:
        permitido = True
    else:
        permitido = any(v["curinga"] or v["cbo_codigo"] == cbo_codigo for v in vinculos)
    if not permitido:
        return False

    excluido = db.execute(
        "SELECT 1 FROM indicador_cbo_excecao WHERE indicador_id = ? AND cbo_codigo = ?",
        (indicador_id, cbo_codigo),
    ).fetchone()
    return excluido is None


def _cbo_permitido_subgrupo(db, indicador_id, subgrupo_id, cbo_codigo):
    if subgrupo_id is not None:
        vinculos_subgrupo = db.execute(
            "SELECT cbo_codigo, curinga FROM indicador_cbo WHERE subgrupo_id = ?",
            (subgrupo_id,),
        ).fetchall()
        if vinculos_subgrupo:
            return any(v["curinga"] or v["cbo_codigo"] == cbo_codigo for v in vinculos_subgrupo)
        # Se outros subgrupos deste indicador possuem CBOs específicos (como no P42 onde cada subgrupo representa uma especialidade),
        # um subgrupo sem vínculo próprio NÃO deve aceitar CBOs de outras especialidades ou regra geral indistintamente
        tem_outros_cbos = db.execute(
            """SELECT 1 FROM indicador_cbo ic
               JOIN indicador_subgrupo sg ON sg.id = ic.subgrupo_id
               WHERE sg.indicador_id = ? LIMIT 1""",
            (indicador_id,),
        ).fetchone()
        if tem_outros_cbos:
            return False
    return _cbo_permitido(db, indicador_id, cbo_codigo)


def _estabelecimento_permitido(db, indicador_id, estabelecimento_id):
    excluido = db.execute(
        "SELECT 1 FROM indicador_estabelecimento_excecao WHERE indicador_id = ? AND estabelecimento_id = ?",
        (indicador_id, estabelecimento_id),
    ).fetchone()
    return excluido is None


SERVICOS_COMPATIVEIS = {
    "UBS_ESF": {"UBS_ESF", "UBS_MISTA"},
    "UBS_TRAD": {"UBS_TRAD", "UBS_MISTA"},
    "EMULTI_ESF": {"EMULTI_ESF", "EMULTI_MISTA"},
    "EMULTI_TRAD": {"EMULTI_TRAD", "EMULTI_MISTA"},
}


def _servico_compativel(db, indicador_id, estabelecimento_id):
    row = db.execute("SELECT servico FROM indicadores WHERE id=?", (indicador_id,)).fetchone()
    if not row or not row["servico"]:
        return True
    servico = row["servico"].strip().upper()
    compativeis = SERVICOS_COMPATIVEIS.get(servico, {servico})
    estab_servicos = {
        r["tipo_servico"].strip().upper()
        for r in db.execute(
            "SELECT tipo_servico FROM estabelecimento_tipo_servico WHERE estabelecimento_id=?",
            (estabelecimento_id,),
        ).fetchall()
        if r["tipo_servico"]
    }
    return bool(compativeis & estab_servicos)


# ==============================================================================
# 2. MOTOR DE CÁLCULO E APURAÇÃO (fato_apuracao)
# ==============================================================================

def _garantir_linhas_subgrupos(db, periodo_norm):
    """
    Garante que especialidades vinculadas a subgrupos (ex: P43 Infantil: Neuro e Pneumo)
    tenham linha no painel (fato_apuracao com apurado=0) para os estabelecimentos
    que possuem apuração ou metas desse indicador, mesmo quando não houve produção no mês.
    """
    estabs_ind = db.execute(
        """SELECT DISTINCT f.estabelecimento_id, f.indicador_id
           FROM fato_apuracao f
           WHERE f.periodo = ? AND f.indicador_id IS NOT NULL
           UNION
           SELECT DISTINCT m.estabelecimento_id, m.indicador_id
           FROM metas m
           WHERE m.indicador_id IS NOT NULL""",
        (periodo_norm,),
    ).fetchall()

    for row in estabs_ind:
        eid = row["estabelecimento_id"]
        iid = row["indicador_id"]
        sub_cbos = db.execute(
            """SELECT ic.subgrupo_id, ic.cbo_codigo
               FROM indicador_cbo ic
               WHERE ic.indicador_id = ? AND ic.subgrupo_id IS NOT NULL""",
            (iid,),
        ).fetchall()
        for sc in sub_cbos:
            existe = db.execute(
                """SELECT 1 FROM fato_apuracao
                   WHERE periodo = ? AND estabelecimento_id = ? AND indicador_id = ?
                     AND subgrupo_id = ? AND cbo_codigo = ?
                   LIMIT 1""",
                (periodo_norm, eid, iid, sc["subgrupo_id"], sc["cbo_codigo"]),
            ).fetchone()
            if not existe:
                ind_row = db.execute("SELECT fonte_id FROM indicadores WHERE id = ?", (iid,)).fetchone()
                fid = ind_row["fonte_id"] if ind_row and ind_row["fonte_id"] else 1
                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, profissional_id,
                           cbo_codigo, procedimento_codigo, indicador_id, periodo,
                           quantidade, tipo_registro, subgrupo_id
                       ) VALUES (?, 1, ?, NULL, ?, NULL, ?, ?, 0, 'apurado', ?)""",
                    (fid, eid, sc["cbo_codigo"], iid, periodo_norm, sc["subgrupo_id"]),
                )


def calcular_at02(db, periodo, importacao_id=None):
    """Gera fato_apuracao (tipo_registro='apurado') a partir de staging_at02."""
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='AT02'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    query = "SELECT * FROM staging_at02 WHERE ano_mes = ?"
    params = [periodo_norm]
    if importacao_id:
        query += " AND importacao_id = ?"
        params.append(importacao_id)

    linhas = db.execute(query, params).fetchall()
    mapa_nomes_subgrupo = {r["id"]: r["nome"] for r in db.execute("SELECT id, nome FROM indicador_subgrupo").fetchall()}

    total = 0
    vinculadas = 0
    sem_estabelecimento = 0
    sem_indicador = 0
    sem_indicador_procedimento_nao_vinculado = 0
    sem_indicador_cbo_nao_autorizado = 0
    sem_indicador_servico_incompativel = 0
    sem_indicador_estabelecimento_excluido = 0
    cmes_nao_encontrados = Counter()
    procedimentos_sem_vinculo = Counter()
    cbo_nao_cadastrados = Counter()
    cbo_removeu_indicador = Counter()
    servico_removeu_indicador = Counter()
    estabelecimento_excecao_removeu_indicador = Counter()

    cmes_pendentes_nomes = {}
    cmes_pendentes_cnes = {}
    cbo_pendentes_codigos = {}
    linhas_casadas_por_cnes = 0
    mapa_depara = _carregar_mapa_depara_procedimentos(db)

    for linha in linhas:
        total += 1
        estabelecimento_id, origem_estab = _resolver_estabelecimento(
            db, linha["cod_cmes"], linha["cod_cnes"], com_origem=True
        )
        if origem_estab == "cnes":
            linhas_casadas_por_cnes += 1
        if estabelecimento_id is None:
            sem_estabelecimento += 1
            cmes_nao_encontrados[linha["cod_cmes"]] += 1
            if linha["cod_cmes"] and linha["cod_cmes"] not in cmes_pendentes_nomes:
                cmes_pendentes_nomes[linha["cod_cmes"]] = linha["nome_estabelecimento"]
                cmes_pendentes_cnes[linha["cod_cmes"]] = linha["cod_cnes"]
            continue

        cbo_codigo = _resolver_cbo(db, linha["cod_cbo_sus"], linha["nome_cbo1"])
        if cbo_codigo is None and linha["nome_cbo1"]:
            cbo_nao_cadastrados[linha["nome_cbo1"]] += 1
            if linha["nome_cbo1"] not in cbo_pendentes_codigos:
                cbo_pendentes_codigos[linha["nome_cbo1"]] = linha["cod_cbo_sus"]

        procedimento_codigo = _garantir_procedimento(
            db, linha["cod_procedimento"], linha["nome_procedimento"]
        )
        if procedimento_codigo is None:
            continue

        candidatos = _candidatos_indicador_subgrupo(
            db, procedimento_codigo, estabelecimento_id,
            categoria_estabelecimento=_categoria_contrato(db, estabelecimento_id),
            fonte_id=fonte_id,
            mapa_depara=mapa_depara,
        )

        aprovados = []
        razoes_bloqueio = set()
        for indicador_id, subgrupo_id in candidatos:
            if not _cbo_permitido_subgrupo(db, indicador_id, subgrupo_id, cbo_codigo):
                razoes_bloqueio.add("cbo")
                continue
            if not _estabelecimento_permitido(db, indicador_id, estabelecimento_id):
                razoes_bloqueio.add("estabelecimento_excecao")
                continue
            if not _servico_compativel(db, indicador_id, estabelecimento_id):
                razoes_bloqueio.add("servico")
                continue
            if (indicador_id, subgrupo_id) not in aprovados:
                aprovados.append((indicador_id, subgrupo_id))

        indicadores = []
        for indicador_id in dict.fromkeys(ind for ind, _ in aprovados):
            subgrupos_aprovados = [sg for ind, sg in aprovados if ind == indicador_id and sg is not None]
            if indicador_id == 35 and subgrupos_aprovados:
                esp = (linha["nome_especialidade2"] or "").lower()
                sg_filtrado = []
                for sg_id in subgrupos_aprovados:
                    sg_nome = mapa_nomes_subgrupo.get(sg_id, "").lower()
                    if "auditiva" in sg_nome and "auditiva" in esp:
                        sg_filtrado.append(sg_id)
                    elif ("fisica" in sg_nome or "fsica" in sg_nome) and ("fisica" in esp or "fsica" in esp):
                        sg_filtrado.append(sg_id)
                    elif "intelectual" in sg_nome and "intelectual" in esp:
                        sg_filtrado.append(sg_id)
                    elif "visual" in sg_nome and "visual" in esp:
                        sg_filtrado.append(sg_id)
                subgrupos_aprovados = sg_filtrado
                if not subgrupos_aprovados:
                    continue

            if subgrupos_aprovados:
                indicadores.extend((indicador_id, sg) for sg in subgrupos_aprovados)
            else:
                indicadores.append((indicador_id, None))

        if not indicadores:
            sem_indicador += 1
            if not candidatos:
                sem_indicador_procedimento_nao_vinculado += 1
                procedimentos_sem_vinculo[f"{procedimento_codigo} ({linha['nome_procedimento'] or ''})"] += 1
            elif "cbo" in razoes_bloqueio:
                sem_indicador_cbo_nao_autorizado += 1
                cbo_removeu_indicador[f"{linha['nome_cbo1'] or '(sem CBO)'} ({procedimento_codigo})"] += 1
            elif "estabelecimento_excecao" in razoes_bloqueio:
                sem_indicador_estabelecimento_excluido += 1
                estabelecimento_excecao_removeu_indicador[f"{linha['nome_estabelecimento'] or linha['cod_cmes']} ({procedimento_codigo})"] += 1
            else:
                sem_indicador_servico_incompativel += 1
                servico_removeu_indicador[f"{linha['nome_estabelecimento'] or linha['cod_cmes']} ({procedimento_codigo})"] += 1
            continue

        for indicador_id, subgrupo_id in indicadores:
            sg_id_registro = subgrupo_id
            # Regra P43: Neuro (225112) e Pneumo (225127) quando CMES != CNES é lançado como Infantil
            if indicador_id == 43 and cbo_codigo in ("225112", "225127"):
                cod_cmes_reg = str(linha["cod_cmes"] or "").strip()
                cod_cnes_reg = str(linha["cod_cnes"] or "").strip()
                if cod_cmes_reg and cod_cnes_reg and cod_cmes_reg != cod_cnes_reg:
                    sg_row = db.execute(
                        "SELECT id FROM indicador_subgrupo WHERE indicador_id = 43 AND lower(nome) = 'infantil'"
                    ).fetchone()
                    if sg_row:
                        sg_id_registro = sg_row["id"]
                else:
                    sg_id_registro = None

            db.execute(
                """INSERT INTO fato_apuracao (
                       fonte_id, importacao_id, estabelecimento_id, profissional_id,
                       cbo_codigo, procedimento_codigo, indicador_id, periodo,
                       quantidade, tipo_registro, subgrupo_id
                   ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, 'apurado', ?)""",
                (
                    fonte_id,
                    linha["importacao_id"],
                    estabelecimento_id,
                    cbo_codigo,
                    procedimento_codigo,
                    indicador_id,
                    periodo_norm,
                    linha["quantidade"] or 0,
                    sg_id_registro,
                ),
            )
            vinculadas += 1

    _garantir_linhas_subgrupos(db, periodo_norm)
    db.commit()
    return {
        "total_linhas": total,
        "linhas_vinculadas": vinculadas,
        "sem_estabelecimento": sem_estabelecimento,
        "sem_indicador": sem_indicador,
        "sem_indicador_procedimento_nao_vinculado": sem_indicador_procedimento_nao_vinculado,
        "sem_indicador_cbo_nao_autorizado": sem_indicador_cbo_nao_autorizado,
        "sem_indicador_servico_incompativel": sem_indicador_servico_incompativel,
        "sem_indicador_estabelecimento_excluido": sem_indicador_estabelecimento_excluido,
        "cmes_nao_encontrados": cmes_nao_encontrados.most_common(),
        "procedimentos_sem_indicador": procedimentos_sem_vinculo.most_common(),
        "cbo_nao_cadastrados": cbo_nao_cadastrados.most_common(),
        "cbo_removeu_indicador": cbo_removeu_indicador.most_common(),
        "servico_removeu_indicador": servico_removeu_indicador.most_common(),
        "estabelecimento_excecao_removeu_indicador": estabelecimento_excecao_removeu_indicador.most_common(),
        "cmes_pendentes_nomes": cmes_pendentes_nomes,
        "cmes_pendentes_cnes": cmes_pendentes_cnes,
        "cbo_pendentes_codigos": cbo_pendentes_codigos,
        "linhas_casadas_por_cnes": linhas_casadas_por_cnes,
    }


def calcular_webssas(db, periodo, importacao_id=None):
    """
    Gera fato_apuracao (tipo_registro='declarado') a partir de staging_webssas.
    Resolve unidades via de_para_websaass_unidade e indicadores via de_para_websaass_indicador.
    Sincroniza as metas contratadas com a tabela metas (TA ativo).
    """
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='WEBSSAS'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)
    periodo_ws = _periodo_para_webssas(periodo_norm)

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    ta_row = db.execute(
        """SELECT id FROM termos_aditivos
           WHERE periodo_inicio <= date(substr(?,1,4) || '-' || substr(?,5,2) || '-01', '+1 month', '-1 day')
             AND periodo_fim   >= date(substr(?,1,4) || '-' || substr(?,5,2) || '-01')
           ORDER BY periodo_inicio DESC, id DESC LIMIT 1""",
        (periodo_norm, periodo_norm, periodo_norm, periodo_norm),
    ).fetchone()
    ta_id = ta_row["id"] if ta_row else 1

    query = "SELECT * FROM staging_webssas WHERE (periodo = ? OR periodo = ?)"
    params = [periodo_norm, periodo_ws]
    if importacao_id:
        query += " AND importacao_id = ?"
        params.append(importacao_id)

    linhas = db.execute(query, params).fetchall()

    total = 0
    vinculadas = 0
    sem_estabelecimento = 0
    sem_indicador = 0
    metas_sincronizadas = 0
    unidades_nao_encontradas = Counter()
    producoes_nao_encontradas = Counter()

    for linha in linhas:
        total += 1
        nome_unidade = (linha["unidade"] or "").strip()
        if not nome_unidade:
            continue

        estab = db.execute(
            "SELECT estabelecimento_id FROM de_para_websaass_unidade WHERE lower(trim(nome_websass)) = lower(?)",
            (nome_unidade,),
        ).fetchone()
        if not estab:
            estab_id = _resolver_estabelecimento_por_nome(db, nome_unidade)
        else:
            estab_id = estab["estabelecimento_id"]

        if not estab_id:
            sem_estabelecimento += 1
            unidades_nao_encontradas[nome_unidade] += 1
            continue

        cp = (linha["cod_producao"] or "").strip()
        serv = (linha["servico"] or "").strip()
        prod = (linha["producao"] or "").strip()

        ind_info = db.execute(
            """SELECT indicador_id, codigo_indicador, cbo_codigo, subgrupo_id
               FROM de_para_websaass_indicador
               WHERE lower(trim(cod_producao)) = lower(?) AND (servico IS NULL OR lower(trim(servico)) = lower(?))
               LIMIT 1""",
            (cp, serv),
        ).fetchone()
        if not ind_info and cp:
            ind_info = db.execute(
                """SELECT indicador_id, codigo_indicador, cbo_codigo, subgrupo_id
                   FROM de_para_websaass_indicador
                   WHERE lower(trim(cod_producao)) = lower(?)
                   LIMIT 1""",
                (cp,),
            ).fetchone()
        if not ind_info and prod:
            ind_info = db.execute(
                """SELECT indicador_id, codigo_indicador, cbo_codigo, subgrupo_id
                   FROM de_para_websaass_indicador
                   WHERE lower(trim(producao)) = lower(?)
                   LIMIT 1""",
                (prod,),
            ).fetchone()

        if not ind_info or not ind_info["indicador_id"]:
            sem_indicador += 1
            producoes_nao_encontradas[f"{cp} - {prod}"] += 1
            continue

        indicador_id = ind_info["indicador_id"]
        cbo_codigo = str(ind_info["cbo_codigo"]).split(".")[0].strip() if ind_info["cbo_codigo"] else None
        subgrupo_id = ind_info["subgrupo_id"] if ind_info and "subgrupo_id" in ind_info.keys() else None

        if not cbo_codigo:
            cbos_ind = db.execute(
                "SELECT cbo_codigo FROM indicador_cbo WHERE indicador_id = ? AND subgrupo_id IS NULL AND curinga = 0",
                (indicador_id,),
            ).fetchall()
            if len(cbos_ind) == 1:
                cbo_codigo = cbos_ind[0]["cbo_codigo"]

        qtde_realizada = int(linha["qtde_realizada"] or 0)
        qtde_prevista = linha["qtde_prevista"]

        db.execute(
            """INSERT INTO fato_apuracao (
                   fonte_id, importacao_id, estabelecimento_id, profissional_id,
                   cbo_codigo, procedimento_codigo, indicador_id, periodo,
                   quantidade, tipo_registro, subgrupo_id
               ) VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?, 'declarado', ?)""",
            (
                fonte_id,
                linha["importacao_id"],
                estab_id,
                cbo_codigo,
                indicador_id,
                periodo_norm,
                qtde_realizada,
                subgrupo_id,
            ),
        )
        vinculadas += 1

        if qtde_prevista is not None and qtde_prevista > 0 and ta_id:
            meta_existente = db.execute(
                """SELECT id, valor_meta FROM metas
                   WHERE ta_id = ? AND estabelecimento_id = ? AND indicador_id = ?
                     AND ((cbo_codigo IS NULL AND ? IS NULL) OR cbo_codigo = ?)
                     AND ((subgrupo_id IS NULL AND ? IS NULL) OR subgrupo_id = ?)
                     AND rt IS NULL AND tipo_equipe IS NULL AND pmmb IS NULL""",
                (ta_id, estab_id, indicador_id, cbo_codigo, cbo_codigo, subgrupo_id, subgrupo_id),
            ).fetchone()
            if meta_existente:
                if meta_existente["valor_meta"] != float(qtde_prevista):
                    db.execute("UPDATE metas SET valor_meta = ? WHERE id = ?", (float(qtde_prevista), meta_existente["id"]))
                    metas_sincronizadas += 1
            else:
                db.execute(
                    """INSERT INTO metas (ta_id, estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo, valor_meta)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (ta_id, estab_id, indicador_id, subgrupo_id, cbo_codigo, float(qtde_prevista)),
                )
                metas_sincronizadas += 1

    db.commit()
    return {
        "total_linhas": total,
        "linhas_vinculadas": vinculadas,
        "sem_estabelecimento": sem_estabelecimento,
        "sem_indicador": sem_indicador,
        "metas_sincronizadas": metas_sincronizadas,
        "unidades_nao_encontradas": unidades_nao_encontradas.most_common(),
        "producoes_nao_encontradas": producoes_nao_encontradas.most_common(),
    }


def calcular_visita_domiciliar(db, periodo, importacao_id=None):
    """Gera fato_apuracao (tipo_registro='apurado') para o indicador P06/P6 a partir de staging_visita_domiciliar."""
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='VISITA_DOMICILIAR'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)
    ano_ref = periodo_norm[:4]
    mes_ref = int(periodo_norm[4:6]) if len(periodo_norm) >= 6 and periodo_norm[4:6].isdigit() else 1

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    indicador = (
        db.execute("SELECT id FROM indicadores WHERE codigo IN ('P06', 'P6') LIMIT 1").fetchone()
        or db.execute("SELECT id FROM indicadores WHERE fonte_id = ? ORDER BY id LIMIT 1", (fonte_id,)).fetchone()
    )

    query = "SELECT * FROM staging_visita_domiciliar WHERE ano = ? AND (CAST(mes AS INT) = ? OR mes = ?)"
    params = [ano_ref, mes_ref, f"{mes_ref:02d}"]
    if importacao_id:
        query += " AND importacao_id = ?"
        params.append(importacao_id)
    linhas = db.execute(query, params).fetchall()

    total = 0
    vinculadas = 0
    sem_estabelecimento = 0
    cnes_nao_encontrados = Counter()

    if not indicador:
        return {
            "total_linhas": len(linhas), "linhas_vinculadas": 0,
            "sem_estabelecimento": 0, "sem_indicador": len(linhas),
            "erro": "Indicador 'P06' não encontrado.",
        }

    cbo_acs = "515105"
    for linha in linhas:
        total += 1
        estabelecimento_id, _ = _resolver_estabelecimento_por_cnes(db, linha["cod_cnes"], indicador["id"])
        if not estabelecimento_id:
            sem_estabelecimento += 1
            cnes_nao_encontrados[f"{linha['cod_cnes']} ({linha['nome_estabelecimento'] or ''})"] += 1
            continue

        cbo = str(linha["cod_cbo"]).split(".")[0].strip() if linha["cod_cbo"] else cbo_acs
        qtd = int(linha["total_visitas"] or 0)
        if qtd <= 0:
            continue

        db.execute(
            """INSERT INTO fato_apuracao (
                   fonte_id, importacao_id, estabelecimento_id, profissional_id,
                   cbo_codigo, procedimento_codigo, indicador_id, periodo,
                   quantidade, tipo_registro
               ) VALUES (?, ?, ?, NULL, ?, '0101030029', ?, ?, ?, 'apurado')""",
            (
                fonte_id, linha["importacao_id"], estabelecimento_id,
                cbo, indicador["id"], periodo_norm, qtd,
            ),
        )
        vinculadas += 1

    db.commit()
    return {
        "total_linhas": total,
        "linhas_vinculadas": vinculadas,
        "sem_estabelecimento": sem_estabelecimento,
        "sem_indicador": 0,
        "cnes_nao_encontrados": cnes_nao_encontrados.most_common(),
    }


def calcular_bi_siga(db, periodo, fonte_at=None, importacao_id=None):
    """Gera fato_apuracao para fontes SSRS: AT-48, AT-49, AT-11, AT-39, AT-40, AT-57, AT-61, AT-08."""
    periodo_norm = _normalizar_periodo(periodo)
    ano = periodo_norm[:4]
    fontes_a_calcular = [fonte_at] if fonte_at else ["AT48", "AT49", "AT11", "AT39", "AT40", "AT57", "AT61", "AT08"]
    resumos = {}

    for fat in fontes_a_calcular:
        fonte_row = db.execute("SELECT id FROM fontes_dados WHERE nome = ?", (fat,)).fetchone()
        if not fonte_row:
            continue
        fonte_id = fonte_row["id"]
        db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

        total = 0
        vinculadas = 0

        if fat == "AT48":
            ind = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P25', 'P025') LIMIT 1").fetchone()
            if ind:
                query = "SELECT * FROM staging_bi_siga WHERE fonte_at = 'AT48' AND (ano_mes = ? OR ano_mes LIKE ?)"
                params = [periodo_norm, f"%{periodo_norm}%"]
                if importacao_id:
                    query += " AND importacao_id = ?"
                    params.append(importacao_id)
                linhas = db.execute(query, params).fetchall()
                for r in linhas:
                    total += 1
                    qty = int(r["quantidade_pacientes"] or r["quantidade"] or 0)
                    estab_id, _ = _resolver_estabelecimento_por_cnes(db, r["cod_cnes"], ind["id"])
                    if not estab_id:
                        estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                    if estab_id and qty > 0:
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                            (fonte_id, r["importacao_id"], estab_id, ind["id"], periodo_norm, qty),
                        )
                        vinculadas += 1

                # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (ind["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind["id"], eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, ind["id"], periodo_norm),
                        )

        elif fat == "AT49":
            ind = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P29', 'P029') LIMIT 1").fetchone()
            if ind:
                query = "SELECT * FROM staging_bi_siga WHERE fonte_at = 'AT49' AND (ano_mes = ? OR ano_mes LIKE ?)"
                params = [periodo_norm, f"%{periodo_norm}%"]
                if importacao_id:
                    query += " AND importacao_id = ?"
                    params.append(importacao_id)
                linhas = db.execute(query, params).fetchall()
                for r in linhas:
                    total += 1
                    qty = int(r["quantidade_pacientes"] or 0)
                    estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                    if estab_id and qty > 0:
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                            (fonte_id, r["importacao_id"], estab_id, ind["id"], periodo_norm, qty),
                        )
                        vinculadas += 1

                # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (ind["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind["id"], eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, ind["id"], periodo_norm),
                        )

        elif fat == "AT11":
            ind_p36 = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P36', 'P036') LIMIT 1").fetchone()
            ind_p37 = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P37', 'P037') LIMIT 1").fetchone()

            query = "SELECT * FROM staging_bi_siga WHERE fonte_at = 'AT11' AND (ano_mes = ? OR ano_mes LIKE ?)"
            params = [periodo_norm, f"%{periodo_norm}%"]
            if importacao_id:
                query += " AND importacao_id = ?"
                params.append(importacao_id)
            linhas = db.execute(query, params).fetchall()
            for r in linhas:
                total += 1
                qty_pac = float(r["quantidade_pacientes"] or 0)
                qty_proc = float(r["quantidade"] or 0)
                estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                if not estab_id and r["cod_cnes"]:
                    estab_id, _ = _resolver_estabelecimento_por_cnes(db, r["cod_cnes"])

                if not estab_id:
                    continue

                # P36: contagem de pacientes
                if ind_p36 and qty_pac > 0:
                    db.execute(
                        """INSERT INTO fato_apuracao (
                               fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                           ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                        (fonte_id, r["importacao_id"], estab_id, ind_p36["id"], periodo_norm, int(qty_pac)),
                    )
                    vinculadas += 1

                # P37: quantidade de procedimentos dividida pela quantia de pacientes
                if ind_p37 and qty_pac > 0:
                    media_proc_usu = round(qty_proc / qty_pac, 2)
                    db.execute(
                        """INSERT INTO fato_apuracao (
                               fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                           ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                        (fonte_id, r["importacao_id"], estab_id, ind_p37["id"], periodo_norm, media_proc_usu),
                    )
                    vinculadas += 1

            # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
            for ind_item in (ind_p36, ind_p37):
                if not ind_item:
                    continue
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (ind_item["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind_item["id"], eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, ind_item["id"], periodo_norm),
                        )

        elif fat == "AT39":
            ind = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P41', 'P041') LIMIT 1").fetchone()
            if ind:
                query = "SELECT * FROM staging_bi_siga WHERE fonte_at = 'AT39' AND (ano_mes = ? OR ano_mes LIKE ?)"
                params = [periodo_norm, f"%{periodo_norm}%"]
                if importacao_id:
                    query += " AND importacao_id = ?"
                    params.append(importacao_id)
                linhas = db.execute(query, params).fetchall()
                for r in linhas:
                    total += 1
                    qty = int(r["quantidade_pacientes"] or 0)
                    estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                    if estab_id and qty > 0:
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                            (fonte_id, r["importacao_id"], estab_id, ind["id"], periodo_norm, qty),
                        )
                        vinculadas += 1

                # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (ind["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind["id"], eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, ind["id"], periodo_norm),
                        )


        elif fat == "AT40":
            # Garante que os CBOs com metas do P38 estejam vinculados na tabela indicador_cbo
            cbos_p38 = ["223605", "223810", "251510", "223905", "239425", "251605", "223505"]
            ind = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P38', 'P038') LIMIT 1").fetchone()
            if ind:
                for c in cbos_p38:
                    db.execute("INSERT OR IGNORE INTO indicador_cbo (indicador_id, cbo_codigo, curinga) VALUES (?, ?, 0)", (ind["id"], c))

                query = "SELECT * FROM staging_bi_siga WHERE fonte_at = 'AT40' AND (ano_mes = ? OR ano_mes LIKE ?)"
                params = [periodo_norm, f"%{periodo_norm}%"]
                if importacao_id:
                    query += " AND importacao_id = ?"
                    params.append(importacao_id)
                linhas = db.execute(query, params).fetchall()

                def _resolver_cbo_at40(nome_cbo):
                    if not nome_cbo:
                        return False, None
                    import unicodedata
                    def _norm_s(s):
                        return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn").strip()
                    norm = _norm_s(nome_cbo)
                    if "fisioterapeuta" in norm:
                        return True, "223605"
                    if "fonoaudiologo" in norm:
                        return True, "223810"
                    if "psicologo" in norm:
                        return True, "251510"
                    if "psicopedagogo" in norm:
                        return True, "239425"
                    if "terapeuta ocupacional" in norm:
                        return True, "223905"
                    if "assistente social" in norm:
                        return True, "251605"
                    if "enfermeiro" in norm:
                        return True, "223505"
                    if norm.startswith("medico") or "medico" in norm:
                        return True, None
                    return False, None

                for r in linhas:
                    total += 1
                    qty = int(r["quantidade"] or 0)
                    estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                    if not estab_id and r["cod_cnes"]:
                        estab_id, _ = _resolver_estabelecimento_por_cnes(db, r["cod_cnes"])

                    valido, cbo_cod = _resolver_cbo_at40(r["cbo_nome"])
                    if estab_id and valido and qty > 0:
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, ?, ?, ?, ?, 'apurado')""",
                            (fonte_id, r["importacao_id"], estab_id, cbo_cod, ind["id"], periodo_norm, qty),
                        )
                        vinculadas += 1

                # Garante linha com quantidade=0 para estabelecimentos e CBOs com meta no período sem produção
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id, m.cbo_codigo FROM metas m WHERE m.indicador_id = ?", (ind["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    cbo_m = mr["cbo_codigo"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? 
                             AND ((cbo_codigo IS NULL AND ? IS NULL) OR cbo_codigo = ?)
                             AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind["id"], eid, cbo_m, cbo_m, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, ?, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, cbo_m, ind["id"], periodo_norm),
                        )

        elif fat == "AT57":
            ind_p09 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P09'").fetchone()
            ind_p10 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P10'").fetchone()
            ind_p19 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P19'").fetchone()
            ind_p20 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P20'").fetchone()

            metas_p09 = {r["estabelecimento_id"] for r in db.execute("SELECT DISTINCT estabelecimento_id FROM metas WHERE indicador_id = ?", (ind_p09["id"],)).fetchall()} if ind_p09 else set()
            metas_p10 = {r["estabelecimento_id"] for r in db.execute("SELECT DISTINCT estabelecimento_id FROM metas WHERE indicador_id = ?", (ind_p10["id"],)).fetchall()} if ind_p10 else set()
            metas_p19 = {r["estabelecimento_id"] for r in db.execute("SELECT DISTINCT estabelecimento_id FROM metas WHERE indicador_id = ?", (ind_p19["id"],)).fetchall()} if ind_p19 else set()
            metas_p20 = {r["estabelecimento_id"] for r in db.execute("SELECT DISTINCT estabelecimento_id FROM metas WHERE indicador_id = ?", (ind_p20["id"],)).fetchall()} if ind_p20 else set()

            linhas = db.execute(
                """SELECT cod_cnes, nome_estabelecimento, grupo, procedimento_codigo, procedimento_nome,
                          sum(quantidade) as total, max(importacao_id) as imp_id
                   FROM staging_bi_siga
                   WHERE fonte_at = 'AT57' AND (ano_mes = ? OR ano_mes LIKE ?)
                   GROUP BY cod_cnes, nome_estabelecimento, grupo, procedimento_codigo, procedimento_nome""",
                (periodo_norm, f"%{periodo_norm}%"),
            ).fetchall()
            for r in linhas:
                total += 1
                qty = int(r["total"] or 0)
                if qty <= 0:
                    continue

                # Apenas unidades UBS, AMA/UBS e eMulti podem ser contadas; CAPS, CECCO, CER, CNR e outros não entram
                nome_origem_low = (r["nome_estabelecimento"] or "").lower()
                termos_nao_ubs = ("caps", "cecco", "cer", "cnr", "hospital dia", "teleassistencia")
                if any(t in nome_origem_low for t in termos_nao_ubs):
                    continue

                grupo = (r["grupo"] or "").upper()
                is_coletivo = "COLETIV" in grupo

                # 1. Verifica se há vínculo explícito em indicador_unidade_origem
                estab_id = None
                ind_escolhido = None
                candidatos = (ind_p10, ind_p20) if is_coletivo else (ind_p09, ind_p19)
                for ind_candidato in candidatos:
                    if not ind_candidato:
                        continue
                    v_row = db.execute(
                        """SELECT uo.estabelecimento_id FROM indicador_unidade_origem uo
                           WHERE uo.indicador_id = ? AND lower(trim(uo.nome_origem)) = lower(trim(?))""",
                        (ind_candidato["id"], r["nome_estabelecimento"]),
                    ).fetchone()
                    if v_row:
                        estab_id = v_row["estabelecimento_id"]
                        ind_escolhido = ind_candidato
                        break

                # 2. Se não houver vínculo manual, aplica regra do último nome (eMulti) ou CNES/Nome
                if not estab_id:
                    estab_id, _ = resolver_unidade_at57(db, r["nome_estabelecimento"], r["cod_cnes"])

                if not estab_id:
                    continue

                estab_row = db.execute("SELECT nome FROM estabelecimentos WHERE id = ?", (estab_id,)).fetchone()
                estab_nome = (estab_row["nome"] if estab_row else "").upper()
                if any(t in estab_nome.lower() for t in termos_nao_ubs):
                    continue

                servicos = [s[0].upper() for s in db.execute(
                    "SELECT tipo_servico FROM estabelecimento_tipo_servico WHERE estabelecimento_id = ?", (estab_id,)
                ).fetchall()]
                is_ubs = "UBS" in estab_nome or any("UBS" in s or "ESF" in s or "TRAD" in s for s in servicos)

                # Se a unidade de destino não for UBS/AMA-UBS, descarta
                if not is_ubs:
                    continue

                # 3. Define o indicador correto por tipo de serviço:
                # P09 e P10: apenas unidades da Estratégia de Saúde da Família (ESF)
                # P19 e P20: apenas unidades Tradicionais (TRAD)
                if not ind_escolhido:
                    is_esf = any("ESF" in s for s in servicos)
                    if is_esf:
                        ind_escolhido = ind_p10 if is_coletivo else ind_p09
                    else:
                        ind_escolhido = ind_p20 if is_coletivo else ind_p19

                if not ind_escolhido:
                    continue

                proc_cod = (r["procedimento_codigo"] or "").rstrip("A").strip()
                if proc_cod:
                    _garantir_procedimento(db, proc_cod, r["procedimento_nome"])

                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, cbo_codigo, procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
                       ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, 'apurado')""",
                    (fonte_id, r["imp_id"], estab_id, proc_cod or None, ind_escolhido["id"], periodo_norm, qty),
                )
                vinculadas += 1

            # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
            for ind_item in (ind_p09, ind_p10, ind_p19, ind_p20):
                if not ind_item:
                    continue
                iid = ind_item["id"]
                estabs_meta = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (iid,)
                ).fetchall()
                for em in estabs_meta:
                    eid = em["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (iid, eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, iid, periodo_norm),
                        )

        elif fat == "AT61":
            ind_p11 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P11'").fetchone()
            ind_p21 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P21'").fetchone()

            # Limpa apuração anterior deste período para P11 e P21
            if ind_p11 and ind_p21:
                db.execute(
                    "DELETE FROM fato_apuracao WHERE periodo = ? AND indicador_id IN (?, ?) AND tipo_registro = 'apurado'",
                    (periodo_norm, ind_p11["id"], ind_p21["id"]),
                )
            elif ind_p11:
                db.execute(
                    "DELETE FROM fato_apuracao WHERE periodo = ? AND indicador_id = ? AND tipo_registro = 'apurado'",
                    (periodo_norm, ind_p11["id"]),
                )
            elif ind_p21:
                db.execute(
                    "DELETE FROM fato_apuracao WHERE periodo = ? AND indicador_id = ? AND tipo_registro = 'apurado'",
                    (periodo_norm, ind_p21["id"]),
                )

            linhas = db.execute(
                """SELECT cod_cnes, nome_estabelecimento, cbo_nome, procedimento_codigo, procedimento_nome,
                          sum(quantidade) as total, max(importacao_id) as imp_id
                   FROM staging_bi_siga
                   WHERE fonte_at = 'AT61' AND (ano_mes = ? OR ano_mes LIKE ?)
                   GROUP BY cod_cnes, nome_estabelecimento, cbo_nome, procedimento_codigo, procedimento_nome""",
                (periodo_norm, f"%{periodo_norm}%"),
            ).fetchall()

            termos_nao_ubs = ("caps", "cecco", "cer", "cnr", "hospital dia", "teleassistencia")
            for r in linhas:
                total += 1
                qty = int(r["total"] or 0)
                if qty <= 0:
                    continue

                nome_origem_low = (r["nome_estabelecimento"] or "").lower()
                if any(t in nome_origem_low for t in termos_nao_ubs):
                    continue

                # 1. Verifica vínculo em indicador_unidade_origem
                estab_id = None
                ind_escolhido = None
                for ind_cand in (ind_p11, ind_p21):
                    if not ind_cand:
                        continue
                    v_row = db.execute(
                        """SELECT uo.estabelecimento_id FROM indicador_unidade_origem uo
                           WHERE uo.indicador_id = ? AND lower(trim(uo.nome_origem)) = lower(trim(?))""",
                        (ind_cand["id"], r["nome_estabelecimento"]),
                    ).fetchone()
                    if v_row:
                        estab_id = v_row["estabelecimento_id"]
                        ind_escolhido = ind_cand
                        break

                # 2. Resolução da unidade base pelo CNES da equipe eMulti
                if not estab_id:
                    cnes_clean = str(r["cod_cnes"] or "").strip().lstrip("0")
                    estab_base = db.execute(
                        """SELECT id, nome FROM estabelecimentos
                           WHERE ltrim(cod_cnes, '0') = ?
                             AND (upper(nome) LIKE 'UBS%' OR upper(nome) LIKE 'AMA/UBS%')
                           ORDER BY id LIMIT 1""",
                        (cnes_clean,),
                    ).fetchone()
                    if estab_base:
                        estab_id = estab_base["id"]
                    else:
                        estab_id, _ = _resolver_estabelecimento_por_cnes(db, r["cod_cnes"])

                if not estab_id:
                    continue

                estab_row = db.execute("SELECT nome FROM estabelecimentos WHERE id = ?", (estab_id,)).fetchone()
                estab_nome = (estab_row["nome"] if estab_row else "").upper()
                if any(t in estab_nome.lower() for t in termos_nao_ubs):
                    continue

                servicos = [s[0].upper() for s in db.execute(
                    "SELECT tipo_servico FROM estabelecimento_tipo_servico WHERE estabelecimento_id = ?", (estab_id,)
                ).fetchall()]
                is_ubs = "UBS" in estab_nome or any("UBS" in s or "ESF" in s or "TRAD" in s for s in servicos)
                if not is_ubs:
                    continue

                if not ind_escolhido:
                    is_esf = any("ESF" in s for s in servicos)
                    ind_escolhido = ind_p11 if is_esf else ind_p21

                if not ind_escolhido:
                    continue

                cbo_cod = _resolver_cbo(db, None, r["cbo_nome"])
                proc_cod = (r["procedimento_codigo"] or "").rstrip("A").strip()
                if proc_cod:
                    _garantir_procedimento(db, proc_cod, r["procedimento_nome"])

                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, cbo_codigo, procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'apurado')""",
                    (fonte_id, r["imp_id"], estab_id, cbo_cod, proc_cod or None, ind_escolhido["id"], periodo_norm, qty),
                )
                vinculadas += 1

            # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
            for ind_item in (ind_p11, ind_p21):
                if not ind_item:
                    continue
                iid = ind_item["id"]
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id, m.cbo_codigo FROM metas m WHERE m.indicador_id = ?", (iid,)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    cbo_m = mr["cbo_codigo"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND ((cbo_codigo IS NULL AND ? IS NULL) OR cbo_codigo = ?)
                             AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (iid, eid, cbo_m, cbo_m, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, cbo_m, iid, periodo_norm),
                        )

        elif fat == "AT08":
            ind = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P27', 'P027') LIMIT 1").fetchone()
            if ind:
                query = """SELECT nome_estabelecimento, sum(quantidade) as total, max(importacao_id) as imp_id
                           FROM staging_bi_siga
                           WHERE fonte_at = 'AT08' 
                             AND (ano_mes = ? OR ano_mes LIKE ?)
                             AND lower(procedimento_nome) LIKE '%acolhimento%noturno%'"""
                params = [periodo_norm, f"%{periodo_norm}%"]
                if importacao_id:
                    query += " AND importacao_id = ?"
                    params.append(importacao_id)
                query += " GROUP BY nome_estabelecimento"
                linhas = db.execute(query, params).fetchall()
                for r in linhas:
                    total += 1
                    qty = int(r["total"] or 0)
                    estab_id = _resolver_estabelecimento_por_nome(db, r["nome_estabelecimento"])
                    if estab_id and qty > 0:
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                            (fonte_id, r["imp_id"], estab_id, ind["id"], periodo_norm, qty),
                        )
                        vinculadas += 1

                # Garante linha com quantidade=0 para estabelecimentos com meta no período sem produção
                metas_rows = db.execute(
                    "SELECT DISTINCT m.estabelecimento_id FROM metas m WHERE m.indicador_id = ?", (ind["id"],)
                ).fetchall()
                for mr in metas_rows:
                    eid = mr["estabelecimento_id"]
                    existe = db.execute(
                        """SELECT 1 FROM fato_apuracao 
                           WHERE indicador_id = ? AND estabelecimento_id = ? AND periodo = ? AND tipo_registro = 'apurado'
                           LIMIT 1""",
                        (ind["id"], eid, periodo_norm),
                    ).fetchone()
                    if not existe:
                        max_imp = db.execute(
                            "SELECT max(id) as imp_id FROM importacoes WHERE fonte_id = ?", (fonte_id,)
                        ).fetchone()
                        imp_id = max_imp["imp_id"] if max_imp and max_imp["imp_id"] else 1
                        db.execute(
                            """INSERT INTO fato_apuracao (
                                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                               ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                            (fonte_id, imp_id, eid, ind["id"], periodo_norm),
                        )

        resumos[fat] = {"total_linhas": total, "linhas_vinculadas": vinculadas}

    db.commit()
    return resumos.get(fonte_at, {"total_linhas": 0, "linhas_vinculadas": 0}) if fonte_at else resumos


def calcular_dtic_rel134(db, periodo, importacao_id=None):
    """
    Gera fato_apuracao para P12 (ESF) e P22 (TRAD) Atividades Coletivas eMulti
    a partir do staging_dtic_rel134.
    Aplica os 5 filtros:
      1. Supervisão Sudeste - Penha (supervisao LIKE '%penha%')
      2. emulti = 'SIM'
      3. data_atividade dentro do mês sendo consolidado (ano/mes correspondentes)
      4. num_participantes > 1
      5. tipo_atividade desconsiderando reuniões (NOT LIKE '%reuni%')
    Aplica a tabela de redirecionamento de unidades (de_para_unidades_rel134),
    onde a produção de unidade participante vai para a unidade base da eMulti.
    Agrupa por (estabelecimento_destino, cbo) gerando registros com cbo_codigo.
    Garante os CBOs de eMulti em indicador_cbo e preenche metas zeradas.
    """
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='DTIC_REL134'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)
    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    emulti_cbos = (
        "251605", "223405", "223445", "223605", "223710",
        "223810", "223905", "224140", "225133", "225250", "251510"
    )

    ind_p12 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P12' LIMIT 1").fetchone()
    ind_p22 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P22' LIMIT 1").fetchone()

    # Garantir que P12 e P22 tenham os CBOs em indicador_cbo para que a view resultados_indicador agrupe por CBO
    for ind_row in (ind_p12, ind_p22):
        if ind_row:
            iid = ind_row["id"]
            for cbo in emulti_cbos:
                db.execute(
                    """INSERT INTO indicador_cbo (indicador_id, cbo_codigo, curinga)
                       SELECT ?, ?, 0
                       WHERE NOT EXISTS (
                           SELECT 1 FROM indicador_cbo WHERE indicador_id = ? AND cbo_codigo = ?
                       )""",
                    (iid, cbo, iid, cbo),
                )

    # Carregar redirecionamentos específicos do REL 134
    redirecionamentos = {}
    for row in db.execute("SELECT unidade_origem_id, unidade_destino_id FROM de_para_unidades_rel134").fetchall():
        redirecionamentos[row["unidade_origem_id"]] = row["unidade_destino_id"]

    ano_ref = periodo_norm[:4]
    mes_ref = periodo_norm[4:6]
    mes_sem_zero = str(int(mes_ref))

    # Staging query com os 5 filtros utilizando estritamente as colunas ano e mes para o período
    query = """
        SELECT cnes, nome_unidade, cbo_prof, num_participantes, ano, mes, importacao_id
        FROM staging_dtic_rel134
        WHERE LOWER(COALESCE(supervisao, '')) LIKE '%penha%'
          AND UPPER(TRIM(COALESCE(emulti, ''))) = 'SIM'
          AND CAST(COALESCE(num_participantes, '0') AS INTEGER) > 1
          AND LOWER(COALESCE(tipo_atividade, '')) NOT LIKE '%reuni%'
          AND ano = ? AND (mes = ? OR mes = ?)
    """
    params = [ano_ref, mes_ref, mes_sem_zero]
    if importacao_id:
        query += " AND importacao_id = ?"
        params.append(importacao_id)

    linhas = db.execute(query, params).fetchall()

    # Agrupar produção por (unidade_destino_id, cbo_codigo)
    producao_agrupada = {}
    total_linhas_filtradas = len(linhas)

    for r in linhas:

        origem_id, _ = _resolver_estabelecimento_por_cnes(db, r["cnes"])
        if not origem_id:
            origem_id = _resolver_estabelecimento_por_nome(db, r["nome_unidade"])
        if not origem_id:
            continue

        cbo_cod = str(r["cbo_prof"] or "").split(".")[0].strip()
        if not cbo_cod:
            continue

        # Para Farmacêutico (2234) e Assistente Social (2516), a relação com a unidade base NÃO deve ser considerada
        if cbo_cod.startswith("2234"):
            destino_id = origem_id
            cbo_cod = "223405"
        elif cbo_cod.startswith("2516"):
            destino_id = origem_id
            cbo_cod = "251605"
        else:
            destino_id = redirecionamentos.get(origem_id, origem_id)

        chave = (destino_id, cbo_cod)
        if chave not in producao_agrupada:
            producao_agrupada[chave] = {"qtd": 0, "imp_id": r["importacao_id"]}
        producao_agrupada[chave]["qtd"] += 1
        if r["importacao_id"]:
            producao_agrupada[chave]["imp_id"] = r["importacao_id"]

    # Gravar na fato_apuracao
    vinculadas = 0
    max_imp_geral = importacao_id
    for (destino_id, cbo_cod), dados in producao_agrupada.items():
        qty = dados["qtd"]
        imp_id = dados["imp_id"] or importacao_id or 1
        if not max_imp_geral and dados["imp_id"]:
            max_imp_geral = dados["imp_id"]

        # Determinar se vai para P12 ou P22
        tem_meta_12 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 12", (destino_id,)).fetchone()
        tem_meta_22 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 22", (destino_id,)).fetchone()
        if tem_meta_12 and not tem_meta_22:
            indicador_id = ind_p12["id"] if ind_p12 else 12
        elif tem_meta_22 and not tem_meta_12:
            indicador_id = ind_p22["id"] if ind_p22 else 22
        else:
            if db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 12 AND cbo_codigo = ?", (destino_id, cbo_cod)).fetchone():
                indicador_id = ind_p12["id"] if ind_p12 else 12
            elif db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 22 AND cbo_codigo = ?", (destino_id, cbo_cod)).fetchone():
                indicador_id = ind_p22["id"] if ind_p22 else 22
            else:
                servicos = [s[0].upper() for s in db.execute(
                    "SELECT tipo_servico FROM estabelecimento_tipo_servico WHERE estabelecimento_id = ?", (destino_id,)
                ).fetchall()]
                indicador_id = ind_p12["id"] if "ESF" in servicos else (ind_p22["id"] if ind_p22 else (ind_p12["id"] if ind_p12 else 12))

        db.execute(
            """INSERT INTO fato_apuracao (
                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                   periodo, quantidade, tipo_registro
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 'apurado')""",
            (fonte_id, imp_id, destino_id, cbo_cod, indicador_id, periodo_norm, qty),
        )
        vinculadas += qty

    # Inserir linhas com apurado=0 para metas cadastradas de P12/P22 sem produção no mês
    metas_emulti = db.execute(
        """SELECT DISTINCT m.estabelecimento_id, m.indicador_id, m.cbo_codigo
           FROM metas m
           WHERE m.indicador_id IN (12, 22) AND m.cbo_codigo IS NOT NULL"""
    ).fetchall()
    for m in metas_emulti:
        existe = db.execute(
            """SELECT 1 FROM fato_apuracao
               WHERE periodo = ? AND estabelecimento_id = ? AND indicador_id = ? AND cbo_codigo = ?
               LIMIT 1""",
            (periodo_norm, m["estabelecimento_id"], m["indicador_id"], m["cbo_codigo"]),
        ).fetchone()
        if not existe:
            db.execute(
                """INSERT INTO fato_apuracao (
                       fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                       periodo, quantidade, tipo_registro
                   ) VALUES (?, ?, ?, ?, ?, ?, 0, 'apurado')""",
                (fonte_id, max_imp_geral or 1, m["estabelecimento_id"], m["cbo_codigo"], m["indicador_id"], periodo_norm),
            )

    db.commit()
    return {"total_linhas": total_linhas_filtradas, "linhas_vinculadas": vinculadas}


def calcular_dtic_rel130(db, periodo, importacao_id=None):
    """Gera fato_apuracao para P30 (EMAD) e P33 (EMAP) Atendimento Domiciliar eSUS."""
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='DTIC_REL130'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)
    ano_ref = periodo_norm[:4] if len(periodo_norm) >= 4 else ""
    mes_ref = periodo_norm[4:6] if len(periodo_norm) >= 6 else ""

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    ind_p30 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P30' LIMIT 1").fetchone()
    ind_p33 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P33' LIMIT 1").fetchone()

    # Garantir que P30 e P33 tenham os CBOs vinculados em indicador_cbo para separação por CBO na view e no painel
    p30_cbos = ("223505", "223605", "225125", "322230")
    p33_cbos = ("223605", "223710", "223810", "251510", "251605")

    if ind_p30:
        for cbo in p30_cbos:
            db.execute(
                """INSERT INTO indicador_cbo (indicador_id, cbo_codigo, curinga)
                   SELECT ?, ?, 0
                   WHERE NOT EXISTS (
                       SELECT 1 FROM indicador_cbo WHERE indicador_id = ? AND cbo_codigo = ?
                   )""",
                (ind_p30["id"], cbo, ind_p30["id"], cbo),
            )

    if ind_p33:
        for cbo in p33_cbos:
            db.execute(
                """INSERT INTO indicador_cbo (indicador_id, cbo_codigo, curinga)
                   SELECT ?, ?, 0
                   WHERE NOT EXISTS (
                       SELECT 1 FROM indicador_cbo WHERE indicador_id = ? AND cbo_codigo = ?
                   )""",
                (ind_p33["id"], cbo, ind_p33["id"], cbo),
            )

    query = """SELECT cnes, unidade, nome_equipe, cod_cbo,
                      COUNT(DISTINCT codigo_atendimento) AS total,
                      MAX(importacao_id) AS imp_id
               FROM staging_dtic_rel130
               WHERE (periodo_referencia = ? OR periodo_referencia LIKE ?)
                 AND (supervisao LIKE '%PENHA%' OR supervisao LIKE '%penha%')
                 AND substr(data_cadastro, 7, 4) = ?
                 AND substr(data_cadastro, 4, 2) = ?
               GROUP BY cnes, unidade, nome_equipe, cod_cbo"""
    params = [periodo_norm, f"%{periodo_norm}%", ano_ref, mes_ref]
    linhas = db.execute(query, params).fetchall()

    total = 0
    vinculadas = 0
    max_imp_id = importacao_id

    for r in linhas:
        total += 1
        qty = int(r["total"] or 0)
        equipe = (r["nome_equipe"] or "").upper()
        if "EMAP" in equipe:
            indicador_id = ind_p33["id"] if ind_p33 else None
        elif "EMAD" in equipe:
            indicador_id = ind_p30["id"] if ind_p30 else None
        else:
            continue

        if not indicador_id:
            continue

        estab_id, _ = _resolver_estabelecimento_por_cnes(db, r["cnes"], indicador_id)
        if not estab_id:
            estab_id = _resolver_estabelecimento_por_nome(db, r["unidade"])
        if not estab_id:
            continue

        cbo_cod = (r["cod_cbo"] or "").strip() or None
        if not max_imp_id and r["imp_id"]:
            max_imp_id = r["imp_id"]

        if qty > 0:
            db.execute(
                """INSERT INTO fato_apuracao (
                       fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id, periodo, quantidade, tipo_registro
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'apurado')""",
                (fonte_id, r["imp_id"] or max_imp_id or 1, estab_id, cbo_cod, indicador_id, periodo_norm, qty),
            )
            vinculadas += qty

    # Inserir linhas com apurado=0 para metas cadastradas de P30/P33 sem produção no mês
    ind_ids = [i["id"] for i in (ind_p30, ind_p33) if i]
    if ind_ids:
        marc_inds = ",".join("?" * len(ind_ids))
        metas = db.execute(
            f"""SELECT DISTINCT m.estabelecimento_id, m.cbo_codigo, m.indicador_id
               FROM metas m
               WHERE m.indicador_id IN ({marc_inds}) AND m.cbo_codigo IS NOT NULL""",
            ind_ids,
        ).fetchall()
        for m in metas:
            existe = db.execute(
                """SELECT 1 FROM fato_apuracao
                   WHERE periodo = ? AND estabelecimento_id = ? AND indicador_id = ? AND cbo_codigo = ?
                   LIMIT 1""",
                (periodo_norm, m["estabelecimento_id"], m["indicador_id"], m["cbo_codigo"]),
            ).fetchone()
            if not existe:
                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                           periodo, quantidade, tipo_registro
                       ) VALUES (?, ?, ?, ?, ?, ?, 0, 'apurado')""",
                    (fonte_id, max_imp_id or 1, m["estabelecimento_id"], m["cbo_codigo"], m["indicador_id"], periodo_norm),
                )

    db.commit()
    return {"total_linhas": total, "linhas_vinculadas": vinculadas}


def calcular_sisad(db, periodo, importacao_id=None):
    """
    Gera fato_apuracao para os indicadores da fonte SISAD:
      - P31: Número de Pacientes Ativos da EMAD (por unidade EMAD: ativos até o fim do mês + óbitos do mês)
      - P32: Desospitalização por Procedência (por unidade EMAD: procedência HOSPITAL no mês)
      - P34: Número de Pacientes Ativos da EMAP (UBS Jardim Maringá: soma dos ativos de todas as EMADs)
    """
    import calendar
    from collections import defaultdict
    from datetime import datetime

    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='SISAD'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)
    ano = int(periodo_norm[:4])
    mes = int(periodo_norm[4:6])
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dt_limite = datetime(ano, mes, ultimo_dia, 23, 59, 59)

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    ind_p31 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P31' LIMIT 1").fetchone()
    ind_p32 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P32' LIMIT 1").fetchone()
    ind_p34 = db.execute("SELECT id FROM indicadores WHERE codigo = 'P34' LIMIT 1").fetchone()

    # Mapeamento oficial de unidades SISAD para estabelecimentos
    mapa_unidades = {
        "EMAD GRANADA": 65,  # UBS Vila Granada-Alfredo F Paulino Filho
        "EMAD UBS CANGAÍBA": 21,  # Ama/Ubs Integrada Cangaiba - Dr. Carlos Gentile De Mello
        "EMAD UBS CANGAIBA": 21,
        "EMAD UBS INTEGRAL TALARICO/MARINGA": 52,  # Ubs Jardim Maringa - Vila Talarico
        "EMAD UBS SÃO NICOLAU": 59,  # Ubs Jardim Sao Nicolau
        "EMAD UBS SAO NICOLAU": 59,
    }

    # Estabelecimento da EMAP (UBS Jardim Maringá)
    estab_emap_id = 52

    linhas = db.execute(
        """SELECT importacao_id, unidade, tipo_acompanhamento, situacao,
                  data_admissao, procedencia, data_obito
           FROM staging_sisad
           WHERE periodo_referencia = ? OR periodo_referencia LIKE ?""",
        (periodo_norm, f"%{periodo_norm}%"),
    ).fetchall()

    def parse_dt(d):
        if not d:
            return None
        if isinstance(d, datetime):
            return d
        d_str = str(d).strip()
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d_str[:10], fmt)
            except Exception:
                pass
        return None

    ativos_esq = defaultdict(int)
    obitos_dir = defaultdict(int)
    desosp_verm = defaultdict(int)
    max_imp_id = importacao_id

    for r in linhas:
        if not max_imp_id and r["importacao_id"]:
            max_imp_id = r["importacao_id"]

        u_raw = (r["unidade"] or "").strip().upper()
        if not u_raw:
            continue

        tipo = (r["tipo_acompanhamento"] or r["situacao"] or "").strip().upper()
        proc = (r["procedencia"] or "").strip().upper()
        dt_adm = parse_dt(r["data_admissao"])
        dt_ob = parse_dt(r["data_obito"])

        # 1. Tabela Azul Esquerda: Tipo == ATIVO e Data de Admissao <= fim do mes
        if tipo == "ATIVO" and dt_adm and dt_adm <= dt_limite:
            ativos_esq[u_raw] += 1

        # 2. Tabela Azul Direita: Tipo == INATIVO e Data de Obito no mes/ano da competencia
        if tipo == "INATIVO" and dt_ob and dt_ob.year == ano and dt_ob.month == mes:
            obitos_dir[u_raw] += 1

        # 3. Tabela Vermelha: Tipo == ATIVO e Procedencia == HOSPITAL e Data de Admissao no mes/ano da competencia
        if tipo == "ATIVO" and proc == "HOSPITAL" and dt_adm and dt_adm.year == ano and dt_adm.month == mes:
            desosp_verm[u_raw] += 1

    vinculadas = 0
    total_ativos_emad_soma = 0

    # Gravar P31 (Ativos EMAD: soma tabela azul esq + azul dir) e P32 (Deshospitalização)
    todas_emad_nomes = set(list(ativos_esq.keys()) + list(obitos_dir.keys()) + list(desosp_verm.keys()))

    for u_nome in todas_emad_nomes:
        estab_id = mapa_unidades.get(u_nome)
        if not estab_id:
            estab_id = _resolver_estabelecimento_por_nome(db, u_nome)
        if not estab_id:
            continue

        qtd_ativos = ativos_esq[u_nome] + obitos_dir[u_nome]
        total_ativos_emad_soma += qtd_ativos

        if ind_p31 and qtd_ativos > 0:
            db.execute(
                """INSERT INTO fato_apuracao (
                       fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                       periodo, quantidade, tipo_registro
                   ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                (fonte_id, max_imp_id or 1, estab_id, ind_p31["id"], periodo_norm, qtd_ativos),
            )
            vinculadas += qtd_ativos

        qtd_desosp = desosp_verm[u_nome]
        if ind_p32 and qtd_desosp > 0:
            db.execute(
                """INSERT INTO fato_apuracao (
                       fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                       periodo, quantidade, tipo_registro
                   ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
                (fonte_id, max_imp_id or 1, estab_id, ind_p32["id"], periodo_norm, qtd_desosp),
            )
            vinculadas += qtd_desosp

    # Gravar P34 (EMAP Ativos = soma de todas as EMADs na UBS Jardim Maringá)
    if ind_p34 and total_ativos_emad_soma > 0:
        db.execute(
            """INSERT INTO fato_apuracao (
                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                   periodo, quantidade, tipo_registro
               ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'apurado')""",
            (fonte_id, max_imp_id or 1, estab_emap_id, ind_p34["id"], periodo_norm, total_ativos_emad_soma),
        )
        vinculadas += total_ativos_emad_soma

    # Inserir linhas com apurado=0 para metas cadastradas de P31/P32/P34 sem produção no mês
    ind_ids = [i["id"] for i in (ind_p31, ind_p32, ind_p34) if i]
    if ind_ids:
        marc_inds = ",".join("?" * len(ind_ids))
        metas = db.execute(
            f"""SELECT DISTINCT m.estabelecimento_id, m.indicador_id
               FROM metas m
               WHERE m.indicador_id IN ({marc_inds})""",
            ind_ids,
        ).fetchall()
        for m in metas:
            existe = db.execute(
                """SELECT 1 FROM fato_apuracao
                   WHERE periodo = ? AND estabelecimento_id = ? AND indicador_id = ? AND cbo_codigo IS NULL
                   LIMIT 1""",
                (periodo_norm, m["estabelecimento_id"], m["indicador_id"]),
            ).fetchone()
            if not existe:
                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, cbo_codigo, indicador_id,
                           periodo, quantidade, tipo_registro
                       ) VALUES (?, ?, ?, NULL, ?, ?, 0, 'apurado')""",
                    (fonte_id, max_imp_id or 1, m["estabelecimento_id"], m["indicador_id"], periodo_norm),
                )

    db.commit()
    return {"total_linhas": len(linhas), "linhas_vinculadas": vinculadas}


def calcular_dtic_rel164(db, periodo, importacao_id=None):
    """
    Gera fato_apuracao para os indicadores do Hospital Dia (REL 164 / 136):
      - P45: Cirurgias de Pequeno Porte (AIH) -> DEFINICAO contendo 'PEQUENO PORTE'
      - P46: Cirurgias de Médio Porte (AIH) -> DEFINICAO contendo 'MEDIO PORTE' ou 'MÉDIO PORTE'
      - P47: Pequenas Cirurgias (BPA) -> DEFINICAO contendo 'PEQUENAS CIRURGIAS'
    Regras:
      1. Filtrado para STS-Penha -> Estabelecimento: Hospital Dia Penha Hatiro Shimomoto (id 44 / CNES 2751933).
      2. Classificação direta pela coluna DEFINICAO da staging_dtic_rel164 (sem cruzar com tabela de códigos).
      3. Caso não haja produção apurada no mês para P45, P46 ou P47, grava registro com quantidade = 0.
    """
    fonte_id = db.execute("SELECT id FROM fontes_dados WHERE nome='DTIC_REL164'").fetchone()["id"]
    periodo_norm = _normalizar_periodo(periodo)

    db.execute("DELETE FROM fato_apuracao WHERE periodo = ? AND fonte_id = ?", (periodo_norm, fonte_id))

    ind_p45 = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P45', 'P045') LIMIT 1").fetchone()
    ind_p46 = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P46', 'P046') LIMIT 1").fetchone()
    ind_p47 = db.execute("SELECT id FROM indicadores WHERE codigo IN ('P47', 'P047') LIMIT 1").fetchone()

    # Estabelecimento Hospital Dia Penha (id 44 / CNES 2751933)
    estab_row = db.execute(
        """SELECT id FROM estabelecimentos 
           WHERE upper(nome) LIKE '%HOSPITAL DIA%PENHA%' AND cod_cmes = '2751933'
           LIMIT 1"""
    ).fetchone()
    if not estab_row:
        estab_row = db.execute(
            """SELECT id FROM estabelecimentos 
               WHERE upper(nome) LIKE '%HOSPITAL DIA%PENHA%'
               ORDER BY (id = 44) DESC LIMIT 1"""
        ).fetchone()
    estab_id = estab_row["id"] if estab_row else 44

    # Buscar dados do staging filtrando onde a coluna definicao está preenchida
    query = """
        SELECT cod_procedimento, procedimento, definicao,
               SUM(COALESCE(total, 1)) AS total_qtd,
               MAX(importacao_id) AS imp_id
        FROM staging_dtic_rel164
        WHERE (periodo_referencia = ? OR periodo_referencia LIKE ?)
          AND definicao IS NOT NULL AND TRIM(definicao) != ''
    """
    params = [periodo_norm, f"%{periodo_norm}%"]
    if importacao_id:
        query += " AND importacao_id = ?"
        params.append(importacao_id)
    query += " GROUP BY cod_procedimento, procedimento, definicao"

    linhas = db.execute(query, params).fetchall()

    total_linhas = len(linhas)
    vinculadas = 0
    max_imp_id = importacao_id

    # Rastrear quais indicadores receberam produção
    indicadores_com_producao = set()

    for r in linhas:
        def_upper = (r["definicao"] or "").upper().strip()
        target_ind = None

        if "PEQUENAS CIRURGIAS" in def_upper:
            target_ind = ind_p47["id"] if ind_p47 else None
        elif "MEDIO PORTE" in def_upper or "MÉDIO PORTE" in def_upper:
            target_ind = ind_p46["id"] if ind_p46 else None
        elif "PEQUENO PORTE" in def_upper:
            target_ind = ind_p45["id"] if ind_p45 else None

        if not target_ind:
            continue

        qtd = int(r["total_qtd"] or 0)
        if qtd <= 0:
            continue

        cod_raw = (r["cod_procedimento"] or "").strip()
        nome_proc = (r["procedimento"] or "").strip() or f"Procedimento {cod_raw}"

        # Garantir cadastro do procedimento em procedimentos
        if cod_raw:
            db.execute(
                """INSERT INTO procedimentos (codigo, nome)
                   VALUES (?, ?)
                   ON CONFLICT(codigo) DO NOTHING""",
                (cod_raw, nome_proc),
            )
            # Garantir vínculo do procedimento no indicador
            db.execute(
                """INSERT INTO indicador_procedimento (indicador_id, procedimento_codigo, tipo_vinculo)
                   SELECT ?, ?, 'inclusao'
                   WHERE NOT EXISTS (
                       SELECT 1 FROM indicador_procedimento
                       WHERE indicador_id = ? AND procedimento_codigo = ?
                   )""",
                (target_ind, cod_raw, target_ind, cod_raw),
            )

        if not max_imp_id and r["imp_id"]:
            max_imp_id = r["imp_id"]

        db.execute(
            """INSERT INTO fato_apuracao (
                   fonte_id, importacao_id, estabelecimento_id, cbo_codigo,
                   procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
               ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, 'apurado')""",
            (fonte_id, r["imp_id"] or max_imp_id or 1, estab_id, cod_raw or None, target_ind, periodo_norm, qtd),
        )
        vinculadas += qtd
        indicadores_com_producao.add(target_ind)

    # Inserir quantidade=0 para os indicadores P45, P46, P47 que não tiveram produção no mês
    for ind in (ind_p45, ind_p46, ind_p47):
        if not ind:
            continue
        if ind["id"] not in indicadores_com_producao:
            existe = db.execute(
                """SELECT 1 FROM fato_apuracao
                   WHERE periodo = ? AND estabelecimento_id = ? AND indicador_id = ?
                   LIMIT 1""",
                (periodo_norm, estab_id, ind["id"]),
            ).fetchone()
            if not existe:
                db.execute(
                    """INSERT INTO fato_apuracao (
                           fonte_id, importacao_id, estabelecimento_id, cbo_codigo,
                           procedimento_codigo, indicador_id, periodo, quantidade, tipo_registro
                       ) VALUES (?, ?, ?, NULL, NULL, ?, ?, 0, 'apurado')""",
                    (fonte_id, max_imp_id or 1, estab_id, ind["id"], periodo_norm),
                )

    db.commit()
    return {"total_linhas": total_linhas, "linhas_vinculadas": vinculadas}


def recalcular_periodo(db, periodo, fonte_nome):
    """Reprocessa o staging de um período para uma fonte específica ou para TODAS."""
    periodo_norm = _normalizar_periodo(periodo)
    fn = (fonte_nome or "").strip().upper()

    if fn in ("TODAS", "TUDO", "TODOS"):
        resumos = {}
        resumos["AT02"] = calcular_at02(db, periodo_norm)
        resumos["WEBSSAS"] = calcular_webssas(db, periodo_norm)
        resumos["VISITA_DOMICILIAR"] = calcular_visita_domiciliar(db, periodo_norm)
        resumos["BI_SIGA"] = calcular_bi_siga(db, periodo_norm)
        resumos["DTIC_REL134"] = calcular_dtic_rel134(db, periodo_norm)
        resumos["DTIC_REL130"] = calcular_dtic_rel130(db, periodo_norm)
        resumos["SISAD"] = calcular_sisad(db, periodo_norm)
        resumos["DTIC_REL164"] = calcular_dtic_rel164(db, periodo_norm)
        return resumos

    if fn == "AT02":
        return calcular_at02(db, periodo_norm)
    elif fn in ("WEBSSAS", "WEBSAAS"):
        return calcular_webssas(db, periodo_norm)
    elif fn == "VISITA_DOMICILIAR":
        return calcular_visita_domiciliar(db, periodo_norm)
    elif fn in ("AT08", "AT11", "AT39", "AT40", "AT48", "AT49", "AT57", "AT61", "BI_SIGA"):
        fat = None if fn == "BI_SIGA" else fn
        return calcular_bi_siga(db, periodo_norm, fonte_at=fat)
    elif fn == "DTIC_REL134":
        return calcular_dtic_rel134(db, periodo_norm)
    elif fn == "DTIC_REL130":
        return calcular_dtic_rel130(db, periodo_norm)
    elif fn == "SISAD":
        return calcular_sisad(db, periodo_norm)
    elif fn in ("DTIC_REL164", "REL164", "REL_164", "REL136", "REL_136", "HOSPITAL_DIA"):
        return calcular_dtic_rel164(db, periodo_norm)
    else:
        raise ValueError(f"Não há rotina de cálculo para a fonte: {fonte_nome}")


def sincronizar_apuracao_dinamica(db, periodo=None):
    """
    Sincroniza automaticamente a apuração (fato_apuracao) a partir do staging.
    É chamada dinamicamente sempre que cadastros de indicadores, procedimentos,
    CBOs ou estabelecimentos são modificados, eliminando a necessidade de qualquer
    ação manual de recálculo por parte do usuário.
    """
    if periodo:
        periodos = [_normalizar_periodo(periodo)]
    else:
        rows = db.execute(
            """SELECT DISTINCT periodo_referencia AS p FROM importacoes WHERE periodo_referencia IS NOT NULL
               UNION
               SELECT DISTINCT ano_mes AS p FROM staging_at02 WHERE ano_mes IS NOT NULL
               UNION
               SELECT DISTINCT periodo AS p FROM fato_apuracao WHERE periodo IS NOT NULL"""
        ).fetchall()
        periodos = [r["p"] for r in rows if r["p"]]

    for p in periodos:
        try:
            recalcular_periodo(db, p, "TODAS")
        except Exception:
            try:
                calcular_at02(db, p)
            except Exception:
                pass
        try:
            _garantir_linhas_subgrupos(db, p)
            db.commit()
        except Exception:
            pass


def registrar_log(db, fonte, periodo, resumo):
    """Persiste o diagnóstico COMPLETO de uma importação/recálculo em logs_calculo."""
    detalhes = {
        k: v for k, v in resumo.items()
        if k not in ("total_linhas", "linhas_vinculadas", "sem_estabelecimento", "sem_indicador")
    }
    db.execute(
        """INSERT INTO logs_calculo (fonte, periodo, total_linhas, vinculadas,
               sem_estabelecimento, sem_indicador, detalhes_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            fonte,
            periodo,
            resumo.get("total_linhas"),
            resumo.get("linhas_vinculadas"),
            resumo.get("sem_estabelecimento"),
            resumo.get("sem_indicador"),
            json.dumps(detalhes, ensure_ascii=False),
        ),
    )
    db.commit()


def auto_cadastrar_pendentes(db, periodo):
    """Cadastra automaticamente os estabelecimentos e CBOs pendentes identificados no AT-02."""
    resumo = calcular_at02(db, periodo)

    estabelecimentos_criados = 0
    for cod_cmes, nome in resumo["cmes_pendentes_nomes"].items():
        if not cod_cmes:
            continue
        db.execute(
            "INSERT OR IGNORE INTO estabelecimentos (cod_cmes, cod_cnes, nome) VALUES (?, ?, ?)",
            (cod_cmes, (resumo.get("cmes_pendentes_cnes") or {}).get(cod_cmes), nome or f"Estabelecimento {cod_cmes}"),
        )
        estabelecimentos_criados += 1

    cbos_criados = 0
    cbos_sem_codigo = []
    for nome_cbo, cod_cbo in resumo["cbo_pendentes_codigos"].items():
        if cod_cbo:
            db.execute("INSERT OR IGNORE INTO cbo (codigo, nome_categoria) VALUES (?, ?)", (cod_cbo, nome_cbo))
            cbos_criados += 1
        else:
            cbos_sem_codigo.append(nome_cbo)

    db.commit()
    return estabelecimentos_criados, cbos_criados, cbos_sem_codigo


# ==============================================================================
# 3. CONSOLIDAÇÃO TERRITORIAL (CMES vs CNES)
# ==============================================================================

CHAVE_MODO_CONSOLIDACAO = "consolidacao_primaria"
MODOS_CONSOLIDACAO = ("CMES", "CNES")
CHAVE_MODO = CHAVE_MODO_CONSOLIDACAO
MODOS = MODOS_CONSOLIDACAO


def obter_modo(db):
    try:
        row = db.execute("SELECT valor FROM configuracoes WHERE chave = ?", (CHAVE_MODO_CONSOLIDACAO,)).fetchone()
    except Exception:
        return "CMES"
    valor = (row["valor"] if row else "CMES") or "CMES"
    return valor.upper() if valor.upper() in MODOS_CONSOLIDACAO else "CMES"


def definir_modo(db, modo):
    modo = (modo or "").upper()
    if modo not in MODOS_CONSOLIDACAO:
        raise ValueError(f"Modo de consolidação inválido: {modo!r} (use CMES ou CNES).")
    db.execute(
        """INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES (?, ?, datetime('now'))
           ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em""",
        (CHAVE_MODO_CONSOLIDACAO, modo),
    )
    db.commit()


def _cnes(valor):
    return (valor or "").strip()


def analisar(db):
    """Analisa o cadastro como se fosse consolidado por CNES."""
    linhas = db.execute(
        "SELECT id, nome, cod_cnes, cod_cmes, categoria_contrato, exige_cmes FROM estabelecimentos ORDER BY id"
    ).fetchall()

    por_cnes = {}
    for e in linhas:
        cnes = _cnes(e["cod_cnes"])
        if cnes and not e["exige_cmes"]:
            por_cnes.setdefault(cnes, []).append(e)

    resultado = {}

    def individual(e, motivo):
        resultado[e["id"]] = {
            "chave": f"CMES:{e['id']}", "agrupado": False,
            "representante_id": e["id"], "representante_nome": e["nome"],
            "cnes": _cnes(e["cod_cnes"]) or None,
            "membros": [e["id"]], "cmes_membros": [e["cod_cmes"]], "motivo": motivo,
        }

    for e in linhas:
        if e["exige_cmes"]:
            individual(e, "CMES (exceção manual)")
        elif not _cnes(e["cod_cnes"]):
            individual(e, "CMES (sem CNES cadastrado)")

    for cnes, membros in por_cnes.items():
        if len(membros) == 1:
            individual(membros[0], "CMES (único cadastro neste CNES)")
            continue
        categorias = sorted({(m["categoria_contrato"] or "").strip().upper() for m in membros} - {""})
        if len(categorias) > 1:
            for m in membros:
                individual(m, "CMES (CNES ambíguo: contratos distintos - " + ", ".join(categorias) + ")")
            continue
        representante = sorted(membros, key=lambda m: (0 if _cnes(m["cod_cmes"]) == cnes else 1, m["id"]))[0]
        ids = [m["id"] for m in membros]
        for m in membros:
            resultado[m["id"]] = {
                "chave": f"CNES:{cnes}", "agrupado": True,
                "representante_id": representante["id"], "representante_nome": representante["nome"],
                "cnes": cnes, "membros": ids, "cmes_membros": [x["cod_cmes"] for x in membros],
                "motivo": f"CNES {cnes} ({len(ids)} cadastros)",
            }
    return resultado


def aplicar_a_todos(db, modo):
    definir_modo(db, modo)
    cur = db.execute("UPDATE indicadores SET consolida_cnes = ?", (1 if modo.upper() == "CNES" else 0,))
    db.commit()
    return cur.rowcount


def resumir_consolidacao(analise):
    grupos = {i["chave"]: i for i in analise.values() if i["agrupado"]}
    return {
        "grupos": len(grupos),
        "cmes_agrupados": sum(len(g["membros"]) for g in grupos.values()),
        "excecoes_manuais": sum(1 for i in analise.values() if i["motivo"] == "CMES (exceção manual)"),
        "cnes_ambiguos": len({i["cnes"] for i in analise.values() if "ambíguo" in i["motivo"]}),
    }


def indicadores_cnes(db):
    try:
        return {r["id"] for r in db.execute("SELECT id FROM indicadores WHERE consolida_cnes = 1").fetchall()}
    except Exception:
        return set()


def info_para(analise, flags, indicador_id, estabelecimento_id):
    if indicador_id not in flags:
        return None
    info = analise.get(estabelecimento_id)
    return info if info and info["agrupado"] else None


def grupos_ativos(db, modo=None):
    modo = modo or obter_modo(db)
    analise = analisar(db)
    if modo == "CNES":
        return analise
    return {
        est_id: {
            "chave": f"CMES:{est_id}", "agrupado": False,
            "representante_id": est_id, "representante_nome": info["representante_nome"] if info["representante_id"] == est_id else None,
            "cnes": info["cnes"], "membros": [est_id], "cmes_membros": [], "motivo": "CMES",
        }
        for est_id, info in analise.items()
    }


def consolidar_resultados(linhas, grupos, indicadores_cnes=None):
    acumulado = {}
    for r in linhas:
        info = grupos.get(r["estabelecimento_id"])
        if indicadores_cnes is not None and r["indicador_id"] not in indicadores_cnes:
            info = None
        if not info or not info["agrupado"]:
            chave_grupo = f"CMES:{r['estabelecimento_id']}"
        else:
            chave_grupo = info["chave"]
        chave = (r["indicador_id"], r.get("subgrupo_id"), chave_grupo, r["periodo"], r["cbo_codigo"])
        item = acumulado.get(chave)
        if item is None:
            item = dict(r)
            item["estabelecimento_ids"] = [r["estabelecimento_id"]]
            if info and info["agrupado"]:
                item["estabelecimento_id"] = info["representante_id"]
                item["estabelecimento_nome"] = info["representante_nome"]
                item["grupo_cnes"] = info["cnes"]
                item["qtd_cmes"] = len(info["membros"])
                item["membros_grupo"] = list(info["membros"])
            else:
                item["grupo_cnes"] = None
                item["qtd_cmes"] = 1
            acumulado[chave] = item
            continue
        item["estabelecimento_ids"].append(r["estabelecimento_id"])
        item["valor_apurado"] = (item["valor_apurado"] or 0) + (r["valor_apurado"] or 0)
        item["valor_declarado"] = (item["valor_declarado"] or 0) + (r["valor_declarado"] or 0)
        if r["valor_meta"] is not None:
            item["valor_meta"] = (item["valor_meta"] or 0) + r["valor_meta"]

    resultado = list(acumulado.values())
    for item in resultado:
        meta = item["valor_meta"]
        item["percentual_meta"] = (
            round(100.0 * (item["valor_apurado"] or 0) / meta, 2) if meta not in (None, 0) else None
        )
    return resultado


_SQL_META_MEMBRO = """
    SELECT mm.valor_meta
    FROM metas mm
    JOIN termos_aditivos ta ON ta.id = mm.ta_id
    WHERE mm.indicador_id = ? AND mm.estabelecimento_id = ? AND mm.subgrupo_id IS ?
      AND ((mm.cbo_codigo IS NULL AND ? IS NULL) OR mm.cbo_codigo = ?)
      AND mm.rt IS NULL AND mm.tipo_equipe IS NULL AND mm.pmmb IS NULL
      AND ta.periodo_inicio <= date(substr(?,1,4) || '-' || substr(?,5,2) || '-01')
      AND ta.periodo_fim   >= date(substr(?,1,4) || '-' || substr(?,5,2) || '-01')
    ORDER BY ta.periodo_inicio DESC, ta.id DESC
    LIMIT 1
"""


def completar_metas_do_grupo(db, linhas):
    for r in linhas:
        membros = r.get("membros_grupo")
        if not membros:
            continue
        ausentes = [m for m in membros if m not in r["estabelecimento_ids"]]
        if not ausentes:
            continue
        adicional = 0.0
        achou = False
        for est_id in ausentes:
            linha = db.execute(
                _SQL_META_MEMBRO,
                (r["indicador_id"], est_id, r.get("subgrupo_id"), r["cbo_codigo"], r["cbo_codigo"],
                 r["periodo"], r["periodo"], r["periodo"], r["periodo"]),
            ).fetchone()
            if linha and linha["valor_meta"] is not None:
                adicional += linha["valor_meta"]
                achou = True
        if achou:
            r["valor_meta"] = (r["valor_meta"] or 0) + adicional
            r["percentual_meta"] = (
                round(100.0 * (r["valor_apurado"] or 0) / r["valor_meta"], 2) if r["valor_meta"] else None
            )
    return linhas


# ==============================================================================
# 4. DIAGNÓSTICO DE METAS ÓRFÃS
# ==============================================================================

def _rotulo_cbo(cbo):
    return cbo if cbo else "Curinga / Geral"


def diagnosticar(db, limite=None):
    """Retorna a lista de metas cadastradas que não aparecem no Painel."""
    metas = db.execute(
        """SELECT m.id, m.ta_id, m.estabelecimento_id, m.indicador_id, m.subgrupo_id, m.cbo_codigo,
                  m.rt, m.tipo_equipe, m.pmmb, m.valor_meta,
                  ta.numero AS ta_numero, ta.periodo_inicio, ta.periodo_fim,
                  i.codigo AS indicador_codigo, i.nome AS indicador_nome,
                  e.nome AS estabelecimento_nome, sg.nome AS subgrupo_nome
           FROM metas m
           JOIN termos_aditivos ta ON ta.id = m.ta_id
           JOIN indicadores i ON i.id = m.indicador_id
           JOIN estabelecimentos e ON e.id = m.estabelecimento_id
           LEFT JOIN indicador_subgrupo sg ON sg.id = m.subgrupo_id
           WHERE m.valor_meta IS NOT NULL
           ORDER BY i.codigo, e.nome"""
    ).fetchall()
    if not metas:
        return []

    linhas = {}
    for r in db.execute(
        "SELECT indicador_id, estabelecimento_id, subgrupo_id, cbo_codigo, periodo, valor_meta FROM resultados_indicador"
    ).fetchall():
        linhas.setdefault((r["indicador_id"], r["estabelecimento_id"]), []).append(r)

    def comp_para_data(periodo):
        p = (periodo or "").replace("-", "").replace("/", "")
        return f"{p[:4]}-{p[4:6]}"

    def vigente(meta, periodo):
        mes = comp_para_data(periodo)
        return meta["periodo_inicio"][:7] <= mes <= meta["periodo_fim"][:7]

    tem_subgrupos = {
        r[0] for r in db.execute("SELECT DISTINCT indicador_id FROM indicador_subgrupo").fetchall()
    }
    nomes_subgrupo = {r["id"]: r["nome"] for r in db.execute("SELECT id, nome FROM indicador_subgrupo").fetchall()}

    problemas = []
    for m in metas:
        do_par = linhas.get((m["indicador_id"], m["estabelecimento_id"]), [])
        base = {
            "meta_id": m["id"], "ta_numero": m["ta_numero"], "indicador": f"{m['indicador_codigo']} - {m['indicador_nome']}",
            "estabelecimento": m["estabelecimento_nome"], "subgrupo": m["subgrupo_nome"] or "",
            "cbo": _rotulo_cbo(m["cbo_codigo"]), "valor_meta": m["valor_meta"],
            "segmento": " / ".join(x for x in (m["rt"], m["tipo_equipe"], m["pmmb"]) if x),
            "ta_id": m["ta_id"], "indicador_id": m["indicador_id"], "estabelecimento_id": m["estabelecimento_id"],
        }

        if not do_par:
            problemas.append({**base, "codigo": "sem_producao",
                "motivo": "Sem produção apurada deste indicador neste estabelecimento em nenhuma competência calculada.",
                "acao": "Confira Serviço do indicador x estabelecimento, procedimentos e CBOs, e execute Recalcular."})
            continue

        periodos = sorted({r["periodo"] for r in do_par})
        vigentes = [r for r in do_par if vigente(m, r["periodo"])]
        if not vigentes:
            problemas.append({**base, "codigo": "fora_vigencia",
                "motivo": f"Meta fora do período de vigência do TA {m['ta_numero']} ({m['periodo_inicio']} a {m['periodo_fim']}): produção existe só em {', '.join(periodos)}.",
                "acao": "Ajuste datas do TA ou cadastre meta no TA vigente."})
            continue

        mesmo_sg = [r for r in vigentes if r["subgrupo_id"] == m["subgrupo_id"]]
        if not mesmo_sg:
            achados = sorted({nomes_subgrupo.get(r["subgrupo_id"], "sem subgrupo") if r["subgrupo_id"] is not None else "sem subgrupo" for r in vigentes})
            problemas.append({**base, "codigo": "subgrupo",
                "motivo": f"Divergência de Subgrupo: meta é '{m['subgrupo_nome'] or 'sem subgrupo'}', produção está em: {', '.join(achados)}.",
                "acao": "Confira a linha da grade (Estabelecimento | Subgrupo)."})
            continue

        mesmo_cbo = [r for r in mesmo_sg if r["cbo_codigo"] == m["cbo_codigo"]]
        if not mesmo_cbo:
            cbos = sorted({_rotulo_cbo(r["cbo_codigo"]) for r in mesmo_sg})
            problemas.append({**base, "codigo": "cbo",
                "motivo": f"Divergência de CBO: meta é '{_rotulo_cbo(m['cbo_codigo'])}', linhas do Painel são: {', '.join(cbos)}.",
                "acao": "Ajuste a regra de CBO ou regrave a meta na linha correta."})
            continue

        candidatas = db.execute(
            """SELECT mm.id, mm.ta_id, ta.numero, ta.periodo_inicio, ta.periodo_fim,
                      (mm.rt IS NOT NULL OR mm.tipo_equipe IS NOT NULL OR mm.pmmb IS NOT NULL) AS segmentada
               FROM metas mm JOIN termos_aditivos ta ON ta.id = mm.ta_id
               WHERE mm.indicador_id = ? AND mm.estabelecimento_id = ? AND mm.subgrupo_id IS ? AND mm.cbo_codigo IS ?
                 AND mm.valor_meta IS NOT NULL""",
            (m["indicador_id"], m["estabelecimento_id"], m["subgrupo_id"], m["cbo_codigo"]),
        ).fetchall()
        eh_segmentada = bool(m["rt"] or m["tipo_equipe"] or m["pmmb"])

        def vencedora(periodo):
            mes = comp_para_data(periodo)
            for segmentada in (False, True):
                cobrem = sorted(
                    (c for c in candidatas if bool(c["segmentada"]) == segmentada and c["periodo_inicio"][:7] <= mes <= c["periodo_fim"][:7]),
                    key=lambda c: (c["periodo_inicio"], c["id"] if not segmentada else c["ta_id"]), reverse=True,
                )
                if cobrem:
                    return cobrem[0], segmentada
            return None, None

        usada, outra = False, None
        for r in mesmo_cbo:
            venc, seg_venc = vencedora(r["periodo"])
            if venc is None:
                continue
            if (not eh_segmentada and venc["id"] == m["id"]) or (eh_segmentada and seg_venc and venc["ta_id"] == m["ta_id"]):
                usada = True
                break
            outra = outra or (venc, seg_venc)
        if usada:
            continue
        if outra:
            venc, seg_venc = outra
            motivo = (f"Meta substituída pelo TA {venc['numero']}." if venc["ta_id"] != m["ta_id"] else
                      "Meta segmentada não usada: existe meta GERAL prioritária.")
            problemas.append({**base, "codigo": "substituida", "motivo": motivo, "acao": "Revise vigências ou TAs."})
        else:
            problemas.append({**base, "codigo": "substituida", "motivo": "Linha existe, mas não recebeu a meta.", "acao": "Revise TAs."})

    return problemas[:limite] if limite else problemas


def resumir_diagnostico_metas(problemas):
    resumo = {}
    for p in problemas:
        resumo[p["codigo"]] = resumo.get(p["codigo"], 0) + 1
    return resumo


# ==============================================================================
# 5. GESTÃO DE PENDÊNCIAS
# ==============================================================================

def pendencias_at02(db):
    try:
        tem_staging = db.execute("SELECT 1 FROM staging_at02 LIMIT 1").fetchone()
    except Exception:
        tem_staging = None
    vazio = {"estabelecimentos": [], "cbos": [], "periodos": [], "sem_servico": 0}
    if not tem_staging:
        return vazio

    candidatos = db.execute(
        """SELECT s.cod_cmes, s.cod_cnes, MAX(s.nome_estabelecimento) AS nome
           FROM staging_at02 s
           WHERE s.cod_cmes IS NOT NULL AND TRIM(s.cod_cmes) != ''
             AND NOT EXISTS (SELECT 1 FROM estabelecimentos e WHERE e.cod_cmes = s.cod_cmes)
           GROUP BY s.cod_cmes, s.cod_cnes"""
    ).fetchall()
    estabelecimentos, vistos = [], set()
    for c in candidatos:
        if c["cod_cmes"] in vistos:
            continue
        if _resolver_estabelecimento(db, c["cod_cmes"], c["cod_cnes"]) is None:
            vistos.add(c["cod_cmes"])
            estabelecimentos.append({"cod_cmes": c["cod_cmes"], "cod_cnes": c["cod_cnes"], "nome": c["nome"]})

    cbos = [
        {"codigo": r["cod_cbo_sus"], "nome": r["nome"]}
        for r in db.execute(
            """SELECT s.cod_cbo_sus, MAX(s.nome_cbo1) AS nome
               FROM staging_at02 s
               WHERE s.cod_cbo_sus IS NOT NULL AND TRIM(s.cod_cbo_sus) != ''
                 AND NOT EXISTS (SELECT 1 FROM cbo c WHERE c.codigo = s.cod_cbo_sus)
               GROUP BY s.cod_cbo_sus"""
        ).fetchall()
    ]
    periodos = [r[0] for r in db.execute("SELECT DISTINCT ano_mes FROM staging_at02 ORDER BY ano_mes").fetchall()]
    sem_servico = db.execute(
        """SELECT COUNT(*) FROM estabelecimentos e
           WHERE e.cod_cmes IN (SELECT DISTINCT cod_cmes FROM staging_at02)
             AND NOT EXISTS (SELECT 1 FROM estabelecimento_tipo_servico t WHERE t.estabelecimento_id = e.id)"""
    ).fetchone()[0]
    return {"estabelecimentos": estabelecimentos, "cbos": cbos, "periodos": periodos, "sem_servico": sem_servico}


def cadastrar_pendentes(db, pend):
    estabs = cbos = 0
    for e in pend["estabelecimentos"]:
        cur = db.execute(
            "INSERT OR IGNORE INTO estabelecimentos (cod_cmes, cod_cnes, nome) VALUES (?, ?, ?)",
            (e["cod_cmes"], e["cod_cnes"] or None, e["nome"] or f"Estabelecimento {e['cod_cmes']}"),
        )
        estabs += cur.rowcount
    for c in pend["cbos"]:
        cur = db.execute(
            "INSERT OR IGNORE INTO cbo (codigo, nome_categoria) VALUES (?, ?)", (c["codigo"], c["nome"] or c["codigo"])
        )
        cbos += cur.rowcount
    db.commit()
    return estabs, cbos


# ==============================================================================
# 6. CARGA BASE EM LOTE (INDICADORES + METAS)
# ==============================================================================

TIPOS_INDICADOR = {"PRODUCAO": "PRODUCAO", "QUALIDADE": "QUALIDADE", "MONITORAMENTO": "MONITORAMENTO"}
CABECALHO_METAS = ["codigo_indicador", "subgrupo", "cod_cmes_ou_cnes", "codigo_cbo", "valor_meta"]

MODELO_INDICADORES_CSV = (
    "codigo;nome;tipo;complexidade;servico;fonte_dados;consolida_cnes;subgrupo;procedimentos;cbos\n"
    "P1;Consultas médicas na atenção primária;PRODUCAO;ATENCAO_BASICA;UBS;AT02;0;;0301010064|0301010072;225125|225142\n"
    "P42;Procedimentos odontológicos por especialidade;PRODUCAO;;CEO;AT02;0;;;*\n"
    "P42;Procedimentos odontológicos por especialidade;PRODUCAO;;CEO;AT02;0;Endodontia;0307020010|0307020029;223212\n"
)
MODELO_METAS_CSV = (
    "codigo_indicador;subgrupo;cod_cmes_ou_cnes;codigo_cbo;valor_meta\n"
    "P1;;2027070;225125;120\n"
    "P1;;2027070;225142;80,5\n"
    "P42;Endodontia;2788861;;35\n"
)


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn")


def _chave(texto):
    return re.sub(r"[^a-z0-9_]+", "_", _sem_acento(texto).strip().lower()).strip("_")


def _decodificar(conteudo):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("utf-8", errors="replace")


def ler_csv(conteudo):
    texto = _decodificar(conteudo)
    primeira = texto.splitlines()[0] if texto.strip() else ""
    delimitador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    linhas = [l for l in leitor if any((c or "").strip() for c in l)]
    if not linhas:
        return [], []
    colunas = [_chave(c) for c in linhas[0]]
    registros = []
    for numero, l in enumerate(linhas[1:], start=2):
        d = {colunas[i]: (l[i].strip() if i < len(l) else "") for i in range(len(colunas))}
        d["_linha"] = numero
        registros.append(d)
    return colunas, registros


def _lista(valor):
    if isinstance(valor, (list, tuple)):
        itens = [str(v) for v in valor]
    else:
        itens = re.split(r"[|,;\s]+", str(valor or ""))
    return [i.strip() for i in itens if i and i.strip()]


def _booleano(valor):
    return str(valor or "").strip().lower() in {"1", "sim", "s", "true", "verdadeiro", "x", "yes"}


def registros_de_indicadores(nome_arquivo, conteudo):
    if (nome_arquivo or "").lower().endswith(".json"):
        bruto = json.loads(_decodificar(conteudo))
        itens = bruto.get("indicadores", []) if isinstance(bruto, dict) else bruto
        saida = []
        for n, it in enumerate(itens, start=1):
            escopos = {None: {"procs": _lista(it.get("procedimentos")), "cbos": _lista(it.get("cbos"))}}
            for sg in it.get("subgrupos", []) or []:
                escopos[str(sg.get("nome") or "").strip() or None] = {
                    "procs": _lista(sg.get("procedimentos")), "cbos": _lista(sg.get("cbos"))}
            saida.append({
                "codigo": str(it.get("codigo") or "").strip(), "nome": str(it.get("nome") or "").strip(),
                "tipo": it.get("tipo"), "complexidade": it.get("complexidade"), "servico": it.get("servico"),
                "fonte": it.get("fonte_dados") or it.get("fonte"), "consolida_cnes": it.get("consolida_cnes"),
                "escopos": escopos, "linhas": [n],
            })
        return saida

    colunas, linhas = ler_csv(conteudo)
    faltando = [c for c in ("codigo", "nome") if c not in colunas]
    if faltando:
        raise ValueError("Cabeçalho inválido: faltam as colunas obrigatórias " + ", ".join(faltando)
                         + f". Colunas encontradas: {', '.join(colunas) or '(nenhuma)'}.")
    por_codigo = {}
    for l in linhas:
        codigo = l.get("codigo", "").strip()
        if not codigo:
            continue
        ind = por_codigo.setdefault(codigo, {
            "codigo": codigo, "nome": "", "tipo": "", "complexidade": "", "servico": "", "fonte": "",
            "consolida_cnes": "", "escopos": {}, "linhas": [],
        })
        for campo, coluna in (("nome", "nome"), ("tipo", "tipo"), ("complexidade", "complexidade"), ("servico", "servico"),
                              ("consolida_cnes", "consolida_cnes")):
            if l.get(coluna) and not ind[campo]:
                ind[campo] = l[coluna]
        fonte = l.get("fonte_dados") or l.get("fonte") or ""
        if fonte and not ind["fonte"]:
            ind["fonte"] = fonte
        escopo = ind["escopos"].setdefault((l.get("subgrupo") or "").strip() or None, {"procs": [], "cbos": []})
        escopo["procs"] += _lista(l.get("procedimentos"))
        escopo["cbos"] += _lista(l.get("cbos"))
        ind["linhas"].append(l["_linha"])
    return list(por_codigo.values())


def importar_indicadores(db, indicadores, portaria_id, substituir=False):
    r = {"criados": 0, "atualizados": 0, "vinculos_proc": 0, "vinculos_cbo": 0, "proc_criados": 0,
         "subgrupos_criados": 0, "avisos": [], "erros": []}
    fontes = {}
    for f in db.execute("SELECT id, nome, descricao FROM fontes_dados").fetchall():
        fontes[_chave(f["nome"])] = f
        if f["descricao"]:
            fontes.setdefault(_chave(f["descricao"]), f)
    try:
        for ind in indicadores:
            rot = f"{ind['codigo'] or '?'} (linha {', '.join(map(str, ind['linhas']))})"
            if not ind["codigo"] or not ind["nome"]:
                r["erros"].append(f"{rot}: código e nome são obrigatórios - indicador ignorado.")
                continue
            tipo = TIPOS_INDICADOR.get(_sem_acento(ind["tipo"] or "PRODUCAO").strip().upper())
            if tipo is None:
                r["erros"].append(f"{rot}: tipo '{ind['tipo']}' inválido (use PRODUCAO, QUALIDADE ou MONITORAMENTO) - indicador ignorado.")
                continue
            fonte_row = None
            if ind["fonte"]:
                fonte_row = fontes.get(_chave(ind["fonte"]))
                if fonte_row is None:
                    r["avisos"].append(f"{rot}: fonte de dados '{ind['fonte']}' não existe em fontes_dados - ficou sem fonte.")
            consolida = 1 if _booleano(ind["consolida_cnes"]) else 0

            existente = db.execute(
                "SELECT id FROM indicadores WHERE portaria_id = ? AND codigo = ?", (portaria_id, ind["codigo"])
            ).fetchone()
            if existente:
                indicador_id = existente["id"]
                db.execute(
                    """UPDATE indicadores SET nome = ?, tipo = ?, complexidade = ?, servico = ?,
                                              fonte_id = ?, consolida_cnes = ?
                       WHERE id = ?""",
                    (ind["nome"], tipo, ind["complexidade"] or None, ind["servico"] or None,
                     fonte_row["id"] if fonte_row else None, consolida, indicador_id),
                )
                r["atualizados"] += 1
            else:
                cur = db.execute(
                    """INSERT INTO indicadores (portaria_id, codigo, nome, tipo, complexidade, servico,
                                                fonte_id, consolida_cnes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (portaria_id, ind["codigo"], ind["nome"], tipo, ind["complexidade"] or None, ind["servico"] or None,
                     fonte_row["id"] if fonte_row else None, consolida),
                )
                indicador_id = cur.lastrowid
                r["criados"] += 1

            for nome_sg, esc in ind["escopos"].items():
                sg_id = None
                if nome_sg:
                    row_sg = db.execute(
                        "SELECT id FROM indicador_subgrupo WHERE indicador_id = ? AND lower(trim(nome)) = lower(?)",
                        (indicador_id, nome_sg),
                    ).fetchone()
                    if row_sg:
                        sg_id = row_sg["id"]
                    else:
                        prox_ordem = (db.execute(
                            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM indicador_subgrupo WHERE indicador_id = ?",
                            (indicador_id,),
                        ).fetchone()[0])
                        cur_sg = db.execute(
                            "INSERT INTO indicador_subgrupo (indicador_id, nome, ordem) VALUES (?, ?, ?)",
                            (indicador_id, nome_sg, prox_ordem),
                        )
                        sg_id = cur_sg.lastrowid
                        r["subgrupos_criados"] += 1

                if substituir:
                    db.execute(
                        "DELETE FROM indicador_procedimento WHERE indicador_id = ? AND subgrupo_id IS ? AND tipo_vinculo = 'inclusao'",
                        (indicador_id, sg_id),
                    )
                    db.execute("DELETE FROM indicador_cbo WHERE indicador_id = ? AND subgrupo_id IS ?", (indicador_id, sg_id))

                for proc in esc["procs"]:
                    cod_proc = normalizar_cod_procedimento(proc)
                    if not cod_proc:
                        continue
                    db.execute(
                        "INSERT OR IGNORE INTO procedimentos (codigo, nome) VALUES (?, ?)", (cod_proc, cod_proc)
                    )
                    cur_p = db.execute(
                        """INSERT OR IGNORE INTO indicador_procedimento (indicador_id, subgrupo_id, procedimento_codigo, tipo_vinculo)
                           VALUES (?, ?, ?, 'inclusao')""",
                        (indicador_id, sg_id, cod_proc),
                    )
                    if cur_p.rowcount:
                        r["vinculos_proc"] += 1

                for cbo in esc["cbos"]:
                    cbo_s = str(cbo).strip()
                    if not cbo_s:
                        continue
                    if cbo_s in {"*", "CURINGA", "TODOS"}:
                        cur_c = db.execute(
                            "INSERT OR IGNORE INTO indicador_cbo (indicador_id, subgrupo_id, curinga) VALUES (?, ?, 1)",
                            (indicador_id, sg_id),
                        )
                        if cur_c.rowcount:
                            r["vinculos_cbo"] += 1
                        continue
                    db.execute("INSERT OR IGNORE INTO cbo (codigo, nome_categoria) VALUES (?, ?)", (cbo_s, cbo_s))
                    cur_c = db.execute(
                        """INSERT OR IGNORE INTO indicador_cbo (indicador_id, subgrupo_id, cbo_codigo, curinga)
                           VALUES (?, ?, ?, 0)""",
                        (indicador_id, sg_id, cbo_s),
                    )
                    if cur_c.rowcount:
                        r["vinculos_cbo"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return r


def registros_de_metas(conteudo):
    colunas, linhas = ler_csv(conteudo)
    faltando = [c for c in ("codigo_indicador", "cod_cmes_ou_cnes") if c not in colunas]
    if faltando:
        raise ValueError("Cabeçalho inválido: faltam as colunas obrigatórias " + ", ".join(faltando)
                         + f". Colunas encontradas: {', '.join(colunas) or '(nenhuma)'}.")
    registros = []
    for l in linhas:
        v = l.get("valor_meta", "").strip()
        if not v:
            continue
        try:
            valor = float(v.replace(",", "."))
        except ValueError:
            continue
        cbo = l.get("codigo_cbo", "").strip()
        if cbo in {"*", "GERAL", "CURINGA"}:
            cbo = ""
        registros.append({
            "codigo_indicador": l.get("codigo_indicador", "").strip(),
            "subgrupo": l.get("subgrupo", "").strip() or None,
            "cod_cmes_ou_cnes": l.get("cod_cmes_ou_cnes", "").strip(),
            "codigo_cbo": cbo or None,
            "valor_meta": valor,
            "linha": l["_linha"],
        })
    return registros


def importar_metas(db, metas, ta_id, substituir=False):
    r = {"criadas": 0, "atualizadas": 0, "avisos": [], "erros": []}
    ta = db.execute("SELECT id, portaria_origem_id FROM termos_aditivos WHERE id = ?", (ta_id,)).fetchone()
    if not ta:
        raise ValueError(f"Termo Aditivo id={ta_id} não existe.")
    portaria_id = ta["portaria_origem_id"]

    indicadores = {
        row["codigo"]: row for row in db.execute(
            "SELECT id, codigo, nome, consolida_cnes FROM indicadores WHERE portaria_id = ?", (portaria_id,)
        ).fetchall()
    }
    subgrupos = {}
    for sg in db.execute("SELECT id, indicador_id, lower(trim(nome)) AS chave FROM indicador_subgrupo").fetchall():
        subgrupos[(sg["indicador_id"], sg["chave"])] = sg["id"]

    try:
        if substituir:
            db.execute("DELETE FROM metas WHERE ta_id = ?", (ta_id,))
        for m in metas:
            rot = f"linha {m['linha']}"
            ind = indicadores.get(m["codigo_indicador"])
            if not ind:
                r["erros"].append(f"{rot}: indicador '{m['codigo_indicador']}' não existe nesta portaria.")
                continue

            sg_id = None
            if m["subgrupo"]:
                sg_id = subgrupos.get((ind["id"], m["subgrupo"].lower().strip()))
                if sg_id is None:
                    r["erros"].append(f"{rot}: subgrupo '{m['subgrupo']}' não existe no indicador {ind['codigo']}.")
                    continue

            estab_id = _resolver_estabelecimento(db, m["cod_cmes_ou_cnes"], m["cod_cmes_ou_cnes"])
            if not estab_id:
                r["erros"].append(f"{rot}: estabelecimento com CMES/CNES '{m['cod_cmes_ou_cnes']}' não foi encontrado.")
                continue

            if m["codigo_cbo"]:
                db.execute(
                    "INSERT OR IGNORE INTO cbo (codigo, nome_categoria) VALUES (?, ?)",
                    (m["codigo_cbo"], m["codigo_cbo"]),
                )

            existente = db.execute(
                """SELECT id, valor_meta FROM metas
                   WHERE ta_id = ? AND estabelecimento_id = ? AND indicador_id = ?
                     AND subgrupo_id IS ? AND ((cbo_codigo IS NULL AND ? IS NULL) OR cbo_codigo = ?)
                     AND rt IS NULL AND tipo_equipe IS NULL AND pmmb IS NULL""",
                (ta_id, estab_id, ind["id"], sg_id, m["codigo_cbo"], m["codigo_cbo"]),
            ).fetchone()
            if existente:
                db.execute("UPDATE metas SET valor_meta = ? WHERE id = ?", (m["valor_meta"], existente["id"]))
                r["atualizadas"] += 1
            else:
                db.execute(
                    """INSERT INTO metas (ta_id, estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo, valor_meta)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (ta_id, estab_id, ind["id"], sg_id, m["codigo_cbo"], m["valor_meta"]),
                )
                r["criadas"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return r


# ==============================================================================
# ALIASES DE RETROCOMPATIBILIDADE
# ==============================================================================
resumir = resumir_consolidacao

_modulo_atual = sys.modules[__name__]
calculo = _modulo_atual
consolidacao = _modulo_atual
class _DiagnosticoMetasProxy:
    diagnosticar = staticmethod(diagnosticar)
    resumir = staticmethod(resumir_diagnostico_metas)

diagnostico_metas = _DiagnosticoMetasProxy()
pendencias = _modulo_atual
carga_base = _modulo_atual
