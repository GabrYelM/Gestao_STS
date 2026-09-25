"""
Aplica automaticamente, a cada início da aplicação, qualquer alteração de
schema que ainda não tenha sido feita no banco em uso - equivalente a rodar
manualmente migrate_v7/v8/v9/v10, mas sem depender de lembrar de rodar cada
script depois de atualizar o código.

Cada passo verifica se já foi aplicado antes de mexer (mesma lógica dos
scripts migrate_v*.py, que continuam existindo e podem ser rodados à mão se
preferir - rodar os dois não tem problema, esta função simplesmente não vai
encontrar nada pendente na segunda vez).

Chamada de dentro de app/__init__.py::create_app(), então roda toda vez que
o servidor sobe (`python run.py`), antes de qualquer rota atender uma
requisição.
"""


def _tabela_existe(conn, nome):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)
    ).fetchone() is not None


def _coluna_existe(conn, tabela, coluna):
    return any(row[1] == coluna for row in conn.execute(f"PRAGMA table_info({tabela})").fetchall())


def _indice_existe(conn, nome):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (nome,)
    ).fetchone() is not None


def _view_existe(conn, nome):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?", (nome,)
    ).fetchone() is not None


# ===========================================================================
# v14 - Subgrupo em metas e em fato_apuracao + view do painel por subgrupo +
#       índices de desempenho dos cadastros
# v15 - Consolidação por CNES: tabela de configuração e exceção manual "só CMES"
# (ver README.md seções 6.31 a 6.35 e INSTALACAO_E_OPERACAO.md seção 1.3)
#
# Ficam em funções próprias (em vez de dentro de aplicar_migracoes_pendentes)
# para que os scripts migrate_v14_*.py / migrate_v15_*.py possam chamar
# exatamente o mesmo código - sem duas cópias do SQL para manter em sincronia.
# ===========================================================================

# View do painel. Diferenças em relação à versão anterior (v11):
#   - agrupa também por SUBGRUPO (subgrupo_id/subgrupo_nome);
#   - a meta só casa com a linha do MESMO subgrupo (subgrupo_id IS ...);
#   - "CBO agrupado": quando o indicador (ou o subgrupo) aceita qualquer CBO
#     - curinga OU nenhum CBO vinculado, que no cálculo significa o mesmo -,
#     a produção de todos os CBOs cai numa única linha "Curinga / Geral"
#     (cbo_codigo NULL), que é justamente a linha que a meta GERAL da grade
#     de metas casa. O CBO individual de cada profissional continua
#     disponível no drill-down do painel (que lê fato_apuracao/staging).
VIEW_RESULTADOS_INDICADOR = """
CREATE VIEW resultados_indicador AS /* v16 */
WITH base AS (
    SELECT
        f.*,
        -- competência normalizada (AAAAMM), aceitando também AAAA-MM
        replace(replace(f.periodo, '-', ''), '/', '') AS comp,
        CASE
            WHEN f.subgrupo_id IS NOT NULL
                 AND EXISTS (SELECT 1 FROM indicador_cbo ic WHERE ic.subgrupo_id = f.subgrupo_id)
                THEN CASE
                    WHEN EXISTS (SELECT 1 FROM indicador_cbo ic
                                 WHERE ic.subgrupo_id = f.subgrupo_id AND ic.curinga = 1)
                        THEN NULL
                    ELSE f.cbo_codigo
                END
            WHEN NOT EXISTS (SELECT 1 FROM indicador_cbo ic
                             WHERE ic.indicador_id = f.indicador_id AND ic.subgrupo_id IS NULL)
                THEN NULL
            WHEN EXISTS (SELECT 1 FROM indicador_cbo ic
                         WHERE ic.indicador_id = f.indicador_id AND ic.subgrupo_id IS NULL
                           AND ic.curinga = 1)
                THEN NULL
            ELSE f.cbo_codigo
        END AS cbo_agrupado
    FROM fato_apuracao f
    WHERE f.indicador_id IS NOT NULL
),
agr AS (
    SELECT
        b.indicador_id,
        b.subgrupo_id,
        b.estabelecimento_id,
        b.periodo,
        b.comp,
        b.cbo_agrupado,
        SUM(CASE WHEN b.tipo_registro = 'apurado'   THEN b.quantidade ELSE 0 END) AS valor_apurado,
        SUM(CASE WHEN b.tipo_registro = 'declarado' THEN b.quantidade ELSE 0 END) AS valor_declarado,
        -- Meta GERAL (sem segmento) do TA mais recente que COBRE a competência. "Cobre" = o intervalo
        -- do TA se sobrepõe ao mês da competência (um TA que começa no dia 15 já vale para aquele mês).
        (SELECT mm.valor_meta
           FROM metas mm
           JOIN termos_aditivos ta ON ta.id = mm.ta_id
          WHERE mm.indicador_id = b.indicador_id
            AND mm.estabelecimento_id = b.estabelecimento_id
            AND mm.subgrupo_id IS b.subgrupo_id
            AND ((mm.cbo_codigo IS NULL AND b.cbo_agrupado IS NULL) OR mm.cbo_codigo = b.cbo_agrupado)
            AND mm.rt IS NULL AND mm.tipo_equipe IS NULL AND mm.pmmb IS NULL
            AND ta.periodo_inicio <= date(substr(b.comp,1,4) || '-' || substr(b.comp,5,2) || '-01', '+1 month', '-1 day')
            AND ta.periodo_fim   >= date(substr(b.comp,1,4) || '-' || substr(b.comp,5,2) || '-01')
          ORDER BY ta.periodo_inicio DESC, ta.id DESC
          LIMIT 1) AS meta_geral,
        -- Só quando NÃO há meta geral: metas segmentadas por RT/equipe/PMMB (a produção não sabe a que
        -- segmento pertence) entram SOMADAS, no TA mais recente que cobre a competência.
        (SELECT SUM(mm.valor_meta)
           FROM metas mm
          WHERE mm.ta_id = (
                SELECT mm2.ta_id
                  FROM metas mm2
                  JOIN termos_aditivos ta ON ta.id = mm2.ta_id
                 WHERE mm2.indicador_id = b.indicador_id
                   AND mm2.estabelecimento_id = b.estabelecimento_id
                   AND mm2.subgrupo_id IS b.subgrupo_id
                   AND ((mm2.cbo_codigo IS NULL AND b.cbo_agrupado IS NULL) OR mm2.cbo_codigo = b.cbo_agrupado)
                   AND (mm2.rt IS NOT NULL OR mm2.tipo_equipe IS NOT NULL OR mm2.pmmb IS NOT NULL)
                   AND ta.periodo_inicio <= date(substr(b.comp,1,4) || '-' || substr(b.comp,5,2) || '-01', '+1 month', '-1 day')
                   AND ta.periodo_fim   >= date(substr(b.comp,1,4) || '-' || substr(b.comp,5,2) || '-01')
                 ORDER BY ta.periodo_inicio DESC, ta.id DESC
                 LIMIT 1)
            AND mm.indicador_id = b.indicador_id
            AND mm.estabelecimento_id = b.estabelecimento_id
            AND mm.subgrupo_id IS b.subgrupo_id
            AND ((mm.cbo_codigo IS NULL AND b.cbo_agrupado IS NULL) OR mm.cbo_codigo = b.cbo_agrupado)
            AND (mm.rt IS NOT NULL OR mm.tipo_equipe IS NOT NULL OR mm.pmmb IS NOT NULL)
        ) AS meta_segmentada
    FROM base b
    GROUP BY b.indicador_id, b.subgrupo_id, b.estabelecimento_id, b.periodo, b.cbo_agrupado
)
SELECT
    a.indicador_id,
    i.codigo             AS indicador_codigo,
    i.nome                AS indicador_nome,
    i.tipo                AS indicador_tipo,
    i.complexidade,
    i.servico,
    i.fonte_dados,
    a.subgrupo_id,
    sg.nome               AS subgrupo_nome,
    a.estabelecimento_id,
    e.nome                AS estabelecimento_nome,
    a.periodo,
    a.cbo_agrupado        AS cbo_codigo,
    c.nome_categoria      AS cbo_nome,
    a.valor_apurado,
    a.valor_declarado,
    COALESCE(a.meta_geral, a.meta_segmentada) AS valor_meta,
    CASE
        WHEN COALESCE(a.meta_geral, a.meta_segmentada) IS NOT NULL
             AND COALESCE(a.meta_geral, a.meta_segmentada) != 0
        THEN round(100.0 * a.valor_apurado / COALESCE(a.meta_geral, a.meta_segmentada), 2)
        ELSE NULL
    END AS percentual_meta
FROM agr a
JOIN indicadores i       ON i.id = a.indicador_id
JOIN estabelecimentos e  ON e.id = a.estabelecimento_id
LEFT JOIN indicador_subgrupo sg ON sg.id = a.subgrupo_id
LEFT JOIN cbo c          ON c.codigo = a.cbo_agrupado
"""


def _migrar_v14(conn):
    """Subgrupo em metas/fato_apuracao, view nova e índices de desempenho. Idempotente."""
    aplicou = False

    if not _coluna_existe(conn, "fato_apuracao", "subgrupo_id"):
        conn.execute(
            "ALTER TABLE fato_apuracao ADD COLUMN subgrupo_id "
            "INTEGER REFERENCES indicador_subgrupo(id) ON DELETE SET NULL"
        )
        aplicou = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fato_subgrupo ON fato_apuracao(subgrupo_id)")

    if not _coluna_existe(conn, "metas", "subgrupo_id"):
        conn.execute(
            "ALTER TABLE metas ADD COLUMN subgrupo_id "
            "INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE"
        )
        conn.execute("DROP INDEX IF EXISTS idx_metas_unico")
        conn.execute(
            """CREATE UNIQUE INDEX idx_metas_unico ON metas (
                   ta_id, estabelecimento_id, indicador_id,
                   COALESCE(subgrupo_id, -1),
                   COALESCE(cbo_codigo, '__GERAL__'),
                   COALESCE(rt, '__QUALQUER__'),
                   COALESCE(tipo_equipe, '__QUALQUER__'),
                   COALESCE(pmmb, '__QUALQUER__')
               )"""
        )
        aplicou = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metas_subgrupo ON metas(subgrupo_id)")

    # A view é recriada sempre que ainda não for a versão v14 (ou se não
    # existir) - o SQL guardado no próprio banco denuncia a versão.
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='resultados_indicador'"
    ).fetchone()
    if row is None or "cbo_agrupado" not in (row[0] or ""):
        conn.execute("DROP VIEW IF EXISTS resultados_indicador")
        conn.execute(VIEW_RESULTADOS_INDICADOR)
        aplicou = True

    # Índices de desempenho dos cadastros (ordenação por nome e busca por CNES)
    for nome_indice, tabela, coluna in (
        ("idx_profissionais_nome", "profissionais", "nome"),
        ("idx_procedimentos_nome", "procedimentos", "nome"),
        ("idx_cbo_nome_categoria", "cbo", "nome_categoria"),
        ("idx_estabelecimentos_nome", "estabelecimentos", "nome"),
        ("idx_estabelecimentos_cnes", "estabelecimentos", "cod_cnes"),
    ):
        if not _indice_existe(conn, nome_indice):
            conn.execute(f"CREATE INDEX {nome_indice} ON {tabela}({coluna})")
            aplicou = True

    return aplicou


def _migrar_v15(conn):
    """Consolidação por CNES: configuracoes + estabelecimentos.exige_cmes. Idempotente."""
    aplicou = False

    if not _tabela_existe(conn, "configuracoes"):
        conn.execute(
            """CREATE TABLE configuracoes (
                   chave          TEXT PRIMARY KEY,
                   valor          TEXT NOT NULL,
                   atualizado_em  TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )
        aplicou = True
    conn.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('consolidacao_primaria', 'CMES')"
    )

    if not _coluna_existe(conn, "estabelecimentos", "exige_cmes"):
        conn.execute("ALTER TABLE estabelecimentos ADD COLUMN exige_cmes INTEGER NOT NULL DEFAULT 0")
        aplicou = True

    return aplicou


def _migrar_v16(conn):
    """View do painel v16: a meta passa a valer quando o TA SE SOBREPÕE ao mês da competência (antes
    o TA precisava começar até o dia 1º do mês - um TA iniciado no dia 15 nunca casava naquele mês), a
    competência aceita AAAA-MM e metas segmentadas (RT/equipe/PMMB) entram somadas quando não há meta
    geral. Não altera dados - só recria a view. Idempotente (o marcador /* v16 */ fica no SQL guardado)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='resultados_indicador'"
    ).fetchone()
    if row is not None and "/* v16 */" in (row[0] or ""):
        return False
    conn.execute("DROP VIEW IF EXISTS resultados_indicador")
    conn.execute(VIEW_RESULTADOS_INDICADOR)
    return True


def _fonte_por_texto(texto, fontes):
    """Tenta descobrir a fonte oficial (fontes_dados.nome) a partir do texto livre antigo do indicador
    (ex.: 'SIGA (AT-02)', 'Webssas', 'SISAD'). Só devolve algo se o texto apontar para UMA fonte; ambíguo ou
    desconhecido = None (o indicador continua aceitando qualquer fonte, como antes)."""
    import re
    t = (texto or "").lower()
    if not t.strip():
        return None
    achadas = set()
    for m in re.finditer(r"at[-_ ]?0?(\d{1,2})\b", t):
        nome = f"AT{int(m.group(1)):02d}"
        if nome in fontes:
            achadas.add(nome)
    for chave, nome in (("webs", "WEBSSAS"), ("rel_142", "VISITA_DOMICILIAR"), ("visita", "VISITA_DOMICILIAR"),
                        ("sisad", "SISAD"), ("rel_134", "DTIC_REL134"), ("rel_130", "DTIC_REL130")):
        if chave in t and nome in fontes:
            achadas.add(nome)
    return next(iter(achadas)) if len(achadas) == 1 else None


def _migrar_v17(conn):
    """v17: indicadores.fonte_id (Fonte de dados = vínculo com fontes_dados; o cálculo só considera o indicador
    na fonte escolhida) e indicadores.consolida_cnes (consolidação por CNES individual por indicador).
    Preenche fonte_id a partir do texto antigo quando o texto aponta para uma única fonte e consolida_cnes
    a partir da configuração global antiga. Idempotente."""
    aplicou = False
    if not _coluna_existe(conn, "indicadores", "fonte_id"):
        conn.execute("ALTER TABLE indicadores ADD COLUMN fonte_id INTEGER REFERENCES fontes_dados(id)")
        fontes = {r[1]: r[0] for r in conn.execute("SELECT id, nome FROM fontes_dados").fetchall()}
        for ind_id, texto in conn.execute("SELECT id, fonte_dados FROM indicadores WHERE fonte_dados IS NOT NULL").fetchall():
            nome = _fonte_por_texto(texto, fontes)
            if nome:
                conn.execute("UPDATE indicadores SET fonte_id = ? WHERE id = ?", (fontes[nome], ind_id))
        aplicou = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_indicadores_fonte ON indicadores(fonte_id)")

    if not _coluna_existe(conn, "indicadores", "consolida_cnes"):
        conn.execute("ALTER TABLE indicadores ADD COLUMN consolida_cnes INTEGER NOT NULL DEFAULT 0")
        if _tabela_existe(conn, "configuracoes"):
            row = conn.execute("SELECT valor FROM configuracoes WHERE chave = 'consolidacao_primaria'").fetchone()
            if row and (row[0] or "").upper() == "CNES":
                conn.execute("UPDATE indicadores SET consolida_cnes = 1")
        aplicou = True
    return aplicou


def aplicar_migracoes_pendentes(conn):
    aplicou_algo = False

    # ============================== v7 ==============================
    if not _tabela_existe(conn, "indicador_subgrupo"):
        conn.execute(
            """CREATE TABLE indicador_subgrupo (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                indicador_id   INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
                nome           TEXT NOT NULL,
                ordem          INTEGER NOT NULL DEFAULT 0,
                criado_em      TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        conn.execute("CREATE INDEX idx_indicador_subgrupo_indicador ON indicador_subgrupo(indicador_id)")
        aplicou_algo = True

    if not _tabela_existe(conn, "indicador_cbo_excecao"):
        conn.execute(
            """CREATE TABLE indicador_cbo_excecao (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                indicador_id   INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
                cbo_codigo     TEXT NOT NULL REFERENCES cbo(codigo),
                criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (indicador_id, cbo_codigo)
            )"""
        )
        conn.execute("CREATE INDEX idx_indicador_cbo_excecao_indicador ON indicador_cbo_excecao(indicador_id)")
        aplicou_algo = True

    if not _tabela_existe(conn, "indicador_estabelecimento_excecao"):
        conn.execute(
            """CREATE TABLE indicador_estabelecimento_excecao (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
                estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
                criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (indicador_id, estabelecimento_id)
            )"""
        )
        conn.execute(
            "CREATE INDEX idx_indicador_estab_excecao_indicador ON indicador_estabelecimento_excecao(indicador_id)"
        )
        aplicou_algo = True

    if not _coluna_existe(conn, "indicador_cbo", "subgrupo_id"):
        conn.execute(
            "ALTER TABLE indicador_cbo ADD COLUMN subgrupo_id "
            "INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE"
        )
        conn.execute("DROP INDEX IF EXISTS idx_indicador_cbo_unico")
        conn.execute(
            """CREATE UNIQUE INDEX idx_indicador_cbo_unico
               ON indicador_cbo (indicador_id, COALESCE(subgrupo_id, -1), COALESCE(cbo_codigo, '__CURINGA__'))"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ind_cbo_subgrupo ON indicador_cbo(subgrupo_id)")
        aplicou_algo = True

    if not _coluna_existe(conn, "indicador_procedimento", "subgrupo_id"):
        conn.execute(
            "ALTER TABLE indicador_procedimento ADD COLUMN subgrupo_id "
            "INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE"
        )
        conn.execute("DROP INDEX IF EXISTS idx_indicador_procedimento_unico")
        conn.execute(
            """CREATE UNIQUE INDEX idx_indicador_procedimento_unico
               ON indicador_procedimento (indicador_id, procedimento_codigo,
                                           COALESCE(estabelecimento_id, -1), COALESCE(subgrupo_id, -1))"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ind_proc_subgrupo ON indicador_procedimento(subgrupo_id)")
        aplicou_algo = True

    # ============================== v8 ==============================
    if not _coluna_existe(conn, "indicadores", "fonte_dados"):
        conn.execute("ALTER TABLE indicadores ADD COLUMN fonte_dados TEXT")
        aplicou_algo = True

    view_precisa_recriar = not _tabela_existe(conn, "staging_visita_domiciliar")
    if not _tabela_existe(conn, "staging_visita_domiciliar"):
        conn.execute(
            """CREATE TABLE staging_visita_domiciliar (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                importacao_id           INTEGER NOT NULL REFERENCES importacoes(id),
                tipo_visita             TEXT,
                supervisao              TEXT,
                cod_cnes                TEXT,
                nome_estabelecimento    TEXT,
                cns_profissional        TEXT,
                nome_profissional       TEXT,
                cod_cbo                 TEXT,
                nome_cbo                TEXT,
                cod_equipe              TEXT,
                ano                     TEXT,
                mes                     TEXT,
                total_visitas           INTEGER
            )"""
        )
        conn.execute(
            "CREATE INDEX idx_staging_visita_domiciliar_importacao ON staging_visita_domiciliar(importacao_id)"
        )
        aplicou_algo = True

    conn.execute(
        "INSERT OR IGNORE INTO fontes_dados (nome, granularidade, formato_arquivo) "
        "VALUES ('VISITA_DOMICILIAR', 'indicador', 'csv')"
    )

    if view_precisa_recriar or not _view_existe(conn, "resultados_indicador"):
        aplicou_algo = True  # view é (re)criada mais abaixo, na seção v11, já na versão atual

    # ============================== v9 ==============================
    if not _coluna_existe(conn, "profissionais", "cns"):
        conn.execute("ALTER TABLE profissionais ADD COLUMN cns TEXT")
        aplicou_algo = True
    if not _coluna_existe(conn, "profissionais", "rt"):
        conn.execute("ALTER TABLE profissionais ADD COLUMN rt INTEGER NOT NULL DEFAULT 0")
        aplicou_algo = True
    if not _coluna_existe(conn, "profissionais", "tipo_equipe"):
        conn.execute("ALTER TABLE profissionais ADD COLUMN tipo_equipe TEXT")
        aplicou_algo = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_profissionais_cns ON profissionais(cns)")

    # ============================== v10 ==============================
    if not _coluna_existe(conn, "indicadores", "usa_profissionais"):
        conn.execute("ALTER TABLE indicadores ADD COLUMN usa_profissionais INTEGER NOT NULL DEFAULT 0")
        aplicou_algo = True

    if not _tabela_existe(conn, "indicador_profissional"):
        conn.execute(
            """CREATE TABLE indicador_profissional (
                   id               INTEGER PRIMARY KEY AUTOINCREMENT,
                   indicador_id     INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
                   profissional_id  INTEGER NOT NULL REFERENCES profissionais(id) ON DELETE CASCADE,
                   criado_em        TEXT NOT NULL DEFAULT (datetime('now')),
                   UNIQUE (indicador_id, profissional_id)
               )"""
        )
        conn.execute("CREATE INDEX idx_ind_prof_indicador ON indicador_profissional(indicador_id)")
        conn.execute("CREATE INDEX idx_ind_prof_profissional ON indicador_profissional(profissional_id)")
        aplicou_algo = True

    if not _tabela_existe(conn, "indicador_estabelecimento_cnes_alternativo"):
        conn.execute(
            """CREATE TABLE indicador_estabelecimento_cnes_alternativo (
                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                   indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
                   estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
                   cnes_alternativo    TEXT NOT NULL,
                   criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
                   UNIQUE (indicador_id, estabelecimento_id)
               )"""
        )
        conn.execute(
            "CREATE INDEX idx_ind_estab_cnes_alt_indicador "
            "ON indicador_estabelecimento_cnes_alternativo(indicador_id)"
        )
        conn.execute(
            "CREATE INDEX idx_ind_estab_cnes_alt_cnes "
            "ON indicador_estabelecimento_cnes_alternativo(cnes_alternativo)"
        )
        aplicou_algo = True

    # ============================== v11 ==============================
    if not _coluna_existe(conn, "profissionais", "pmmb"):
        conn.execute("ALTER TABLE profissionais ADD COLUMN pmmb INTEGER NOT NULL DEFAULT 0")
        aplicou_algo = True

    for coluna in ("segmenta_metas_rt", "segmenta_metas_tipo_equipe", "segmenta_metas_pmmb"):
        if not _coluna_existe(conn, "indicadores", coluna):
            conn.execute(f"ALTER TABLE indicadores ADD COLUMN {coluna} INTEGER NOT NULL DEFAULT 0")
            aplicou_algo = True

    metas_v11_pendente = not _indice_existe(conn, "idx_metas_unico")
    if metas_v11_pendente:
        conn.execute("ALTER TABLE metas RENAME TO metas_old_v10")
        # os índices antigos ficam presos ao nome antigo da tabela mas mantêm
        # o mesmo NOME - precisam sair do caminho antes de recriar com esses
        # mesmos nomes na tabela nova, ou o CREATE INDEX abaixo falha
        for nome_indice in ("idx_metas_ta", "idx_metas_estabelecimento", "idx_metas_indicador", "idx_metas_cbo"):
            conn.execute(f"DROP INDEX IF EXISTS {nome_indice}")
        conn.execute(
            """CREATE TABLE metas (
                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                   ta_id               INTEGER NOT NULL REFERENCES termos_aditivos(id),
                   estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
                   indicador_id        INTEGER NOT NULL REFERENCES indicadores(id),
                   cbo_codigo          TEXT REFERENCES cbo(codigo),
                   rt                  TEXT CHECK (rt IN ('SIM', 'NAO')),
                   tipo_equipe         TEXT,
                   pmmb                TEXT CHECK (pmmb IN ('SIM', 'NAO')),
                   valor_meta          REAL
               )"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX idx_metas_unico ON metas (
                   ta_id, estabelecimento_id, indicador_id,
                   COALESCE(cbo_codigo, '__GERAL__'),
                   COALESCE(rt, '__QUALQUER__'),
                   COALESCE(tipo_equipe, '__QUALQUER__'),
                   COALESCE(pmmb, '__QUALQUER__')
               )"""
        )
        conn.execute("CREATE INDEX idx_metas_ta ON metas(ta_id)")
        conn.execute("CREATE INDEX idx_metas_estabelecimento ON metas(estabelecimento_id)")
        conn.execute("CREATE INDEX idx_metas_indicador ON metas(indicador_id)")
        conn.execute("CREATE INDEX idx_metas_cbo ON metas(cbo_codigo)")
        conn.execute(
            """INSERT INTO metas (id, ta_id, estabelecimento_id, indicador_id, cbo_codigo, valor_meta)
               SELECT id, ta_id, estabelecimento_id, indicador_id, cbo_codigo, valor_meta FROM metas_old_v10"""
        )
        conn.execute("DROP TABLE metas_old_v10")
        aplicou_algo = True

    if view_precisa_recriar or metas_v11_pendente or not _view_existe(conn, "resultados_indicador"):
        conn.execute("DROP VIEW IF EXISTS resultados_indicador")
        conn.execute(
            """CREATE VIEW resultados_indicador AS
            SELECT
                f.indicador_id,
                i.codigo             AS indicador_codigo,
                i.nome                AS indicador_nome,
                i.tipo                AS indicador_tipo,
                i.complexidade,
                i.servico,
                i.fonte_dados,
                f.estabelecimento_id,
                e.nome                AS estabelecimento_nome,
                f.periodo,
                f.cbo_codigo,
                c.nome_categoria      AS cbo_nome,
                SUM(CASE WHEN f.tipo_registro = 'apurado'   THEN f.quantidade ELSE 0 END) AS valor_apurado,
                SUM(CASE WHEN f.tipo_registro = 'declarado' THEN f.quantidade ELSE 0 END) AS valor_declarado,
                m.valor_meta,
                CASE
                    WHEN m.valor_meta IS NOT NULL AND m.valor_meta != 0
                    THEN round(
                        100.0 * SUM(CASE WHEN f.tipo_registro = 'apurado' THEN f.quantidade ELSE 0 END)
                        / m.valor_meta, 2
                    )
                    ELSE NULL
                END AS percentual_meta
            FROM fato_apuracao f
            JOIN indicadores i       ON i.id = f.indicador_id
            JOIN estabelecimentos e  ON e.id = f.estabelecimento_id
            LEFT JOIN cbo c          ON c.codigo = f.cbo_codigo
            LEFT JOIN metas m
                ON m.id = (
                    SELECT mm.id
                    FROM metas mm
                    JOIN termos_aditivos ta ON ta.id = mm.ta_id
                    WHERE mm.indicador_id = f.indicador_id
                      AND mm.estabelecimento_id = f.estabelecimento_id
                      AND ((mm.cbo_codigo IS NULL AND f.cbo_codigo IS NULL) OR mm.cbo_codigo = f.cbo_codigo)
                      AND mm.rt IS NULL AND mm.tipo_equipe IS NULL AND mm.pmmb IS NULL
                      AND ta.periodo_inicio <= date(substr(f.periodo,1,4) || '-' || substr(f.periodo,5,2) || '-01')
                      AND ta.periodo_fim   >= date(substr(f.periodo,1,4) || '-' || substr(f.periodo,5,2) || '-01')
                    ORDER BY ta.periodo_inicio DESC, ta.id DESC
                    LIMIT 1
                )
            WHERE f.indicador_id IS NOT NULL
            GROUP BY f.indicador_id, f.estabelecimento_id, f.periodo, f.cbo_codigo"""
        )
        aplicou_algo = True

    # ============================== v12 ==============================
    if not _tabela_existe(conn, "categorias_estabelecimento"):
        conn.execute(
            """CREATE TABLE categorias_estabelecimento (
                   id      INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome    TEXT NOT NULL UNIQUE
               )"""
        )
        aplicou_algo = True

    # ============================== v13 ==============================
    # Staging das 10 fontes novas (8 BI SIGA + DTIC REL_134/REL_130 + SISAD)
    # - ver app/etl/bi_siga.py e app/etl/outras_fontes.py.
    if not _tabela_existe(conn, "staging_bi_siga"):
        conn.execute(
            """CREATE TABLE staging_bi_siga (
                   id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                   importacao_id            INTEGER NOT NULL REFERENCES importacoes(id),
                   fonte_at                 TEXT NOT NULL,
                   ano_mes                  TEXT,
                   ano                      TEXT,
                   mes                      TEXT,
                   cod_cnes                 TEXT,
                   nome_estabelecimento     TEXT,
                   nivel2                   TEXT,
                   nivel3                   TEXT,
                   nivel4                   TEXT,
                   cbo_nome                 TEXT,
                   especialidade            TEXT,
                   procedimento_codigo      TEXT,
                   procedimento_nome        TEXT,
                   grupo                    TEXT,
                   quantidade               REAL,
                   quantidade_pacientes     REAL,
                   quantidade_vaga_ofertada REAL
               )"""
        )
        conn.execute("CREATE INDEX idx_staging_bi_siga_importacao ON staging_bi_siga(importacao_id)")
        conn.execute("CREATE INDEX idx_staging_bi_siga_fonte_periodo ON staging_bi_siga(fonte_at, ano_mes)")
        aplicou_algo = True

    if not _tabela_existe(conn, "staging_dtic_rel134"):
        conn.execute(
            """CREATE TABLE staging_dtic_rel134 (
                   id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                   importacao_id        INTEGER NOT NULL REFERENCES importacoes(id),
                   periodo_referencia   TEXT,
                   coordenadoria        TEXT,
                   supervisao           TEXT,
                   oss                  TEXT,
                   tipo_atividade       TEXT,
                   cnes                 TEXT,
                   nome_unidade         TEXT,
                   cns_prof             TEXT,
                   nome_profissional    TEXT,
                   cbo_prof             TEXT,
                   cbo                  TEXT,
                   data_atividade       TEXT,
                   ano                  TEXT,
                   mes                  TEXT,
                   num_participantes    TEXT,
                   cod_proced_sigtap    TEXT,
                   procedimento_sigtap  TEXT
               )"""
        )
        conn.execute("CREATE INDEX idx_staging_dtic_rel134_importacao ON staging_dtic_rel134(importacao_id)")
        conn.execute("CREATE INDEX idx_staging_dtic_rel134_periodo ON staging_dtic_rel134(periodo_referencia)")
        aplicou_algo = True

    if not _tabela_existe(conn, "staging_dtic_rel130"):
        conn.execute(
            """CREATE TABLE staging_dtic_rel130 (
                   id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                   importacao_id        INTEGER NOT NULL REFERENCES importacoes(id),
                   periodo_referencia   TEXT,
                   coordenadoria        TEXT,
                   supervisao           TEXT,
                   oss                  TEXT,
                   cnes                 TEXT,
                   unidade              TEXT,
                   codigo_atendimento   TEXT,
                   cns_profissional     TEXT,
                   nome_profissional    TEXT,
                   cod_cbo              TEXT,
                   cbo                  TEXT,
                   nome_equipe          TEXT,
                   data_cadastro        TEXT,
                   cod_procedimento     TEXT,
                   procedimento         TEXT
               )"""
        )
        conn.execute("CREATE INDEX idx_staging_dtic_rel130_importacao ON staging_dtic_rel130(importacao_id)")
        conn.execute("CREATE INDEX idx_staging_dtic_rel130_periodo ON staging_dtic_rel130(periodo_referencia)")
        aplicou_algo = True

    if not _tabela_existe(conn, "staging_sisad"):
        conn.execute(
            """CREATE TABLE staging_sisad (
                   id                                 INTEGER PRIMARY KEY AUTOINCREMENT,
                   importacao_id                      INTEGER NOT NULL REFERENCES importacoes(id),
                   periodo_referencia                 TEXT,
                   id_sisad                            TEXT,
                   coordenadoria                       TEXT,
                   supervisao                          TEXT,
                   unidade                              TEXT,
                   ubs_referencia                       TEXT,
                   cns                                  TEXT,
                   nome                                 TEXT,
                   situacao                             TEXT,
                   classificacao_cuidados_paliativos    TEXT,
                   data_criacao                         TEXT,
                   data_admissao                        TEXT,
                   data_alta                            TEXT,
                   motivo_alta                          TEXT,
                   data_obito                           TEXT
               )"""
        )
        conn.execute("CREATE INDEX idx_staging_sisad_importacao ON staging_sisad(importacao_id)")
        conn.execute("CREATE INDEX idx_staging_sisad_periodo ON staging_sisad(periodo_referencia)")
        aplicou_algo = True

    # ============================== v14 / v15 / v18 ==============================
    if _migrar_v14(conn):
        aplicou_algo = True
    if _migrar_v15(conn):
        aplicou_algo = True
    if _migrar_v16(conn):
        aplicou_algo = True
    if _migrar_v17(conn):
        aplicou_algo = True
    if _migrar_v18(conn):
        aplicou_algo = True

    conn.commit()
    return aplicou_algo


def _migrar_v18(conn):
    aplicou = False
    if not _tabela_existe(conn, "de_para_websaass_indicador"):
        conn.execute("""
            CREATE TABLE de_para_websaass_indicador (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                cod_producao      TEXT NOT NULL,
                producao          TEXT,
                servico           TEXT,
                codigo_indicador  TEXT,
                cbo_codigo        TEXT,
                indicador_id      INTEGER REFERENCES indicadores(id)
            )
        """)
        conn.execute("CREATE INDEX idx_depara_ws_cod ON de_para_websaass_indicador(cod_producao)")
        conn.execute("CREATE INDEX idx_depara_ws_ind ON de_para_websaass_indicador(indicador_id)")
        aplicou = True

    if not _tabela_existe(conn, "de_para_websaass_unidade"):
        conn.execute("""
            CREATE TABLE de_para_websaass_unidade (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_websass        TEXT NOT NULL UNIQUE,
                estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id)
            )
        """)
        conn.execute("CREATE INDEX idx_depara_ws_estab ON de_para_websaass_unidade(estabelecimento_id)")
        aplicou = True

    if _tabela_existe(conn, "de_para_websaass_indicador") and not _coluna_existe(conn, "de_para_websaass_indicador", "subgrupo_id"):
        conn.execute("ALTER TABLE de_para_websaass_indicador ADD COLUMN subgrupo_id INTEGER REFERENCES indicador_subgrupo(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_depara_ws_sg ON de_para_websaass_indicador(subgrupo_id)")
        aplicou = True

    if _tabela_existe(conn, "categorias_estabelecimento"):
        conn.execute("INSERT OR IGNORE INTO categorias_estabelecimento (nome) VALUES ('INTEGRADA')")

    return aplicou

