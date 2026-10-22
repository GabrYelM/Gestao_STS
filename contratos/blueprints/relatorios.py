"""
Relatórios em Excel para conferência de cadastro.

Dois relatórios:
  - Indicadores: todos os indicadores cadastrados, com seus vínculos de
    CBO e de Procedimento (uma aba por tipo de conteúdo), para conferir se
    cada indicador tem os vínculos corretos batendo com a Matriz de
    Avaliação de Produção / Anexos da Portaria.
  - Metas: todas as metas cadastradas (por TA/estabelecimento/indicador/CBO)
    mais um resumo de cobertura (quantos estabelecimentos têm meta lançada
    para cada indicador, dentro de um TA) para achar lacunas de cadastro.

Ambos aceitam filtro opcional (portaria_id / ta_id); sem filtro, exportam
tudo o que está cadastrado no banco.
"""

import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request

from ..db import get_db

bp = Blueprint("relatorios", __name__, url_prefix="/contratos/relatorios")


def _autofit(ws, largura_max=60):
    for col in ws.columns:
        largura = max((len(str(c.value)) if c.value is not None else 0) for c in col) + 2
        ws.column_dimensions[col[0].column_letter].width = min(largura, largura_max)


def _cabecalho(ws, titulos):
    from openpyxl.styles import Font, PatternFill

    ws.append(titulos)
    for cel in ws[1]:
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="2B2A27")
    ws.freeze_panes = "A2"


@bp.route("/")
def index():
    db = get_db()
    portarias = db.execute("SELECT * FROM portarias ORDER BY id DESC").fetchall()
    tas = db.execute("SELECT * FROM termos_aditivos ORDER BY id DESC").fetchall()
    return render_template("contratos/relatorios.html", portarias=portarias, tas=tas)


# ---------------------------------------------------------------------------
# Relatório de indicadores + vínculos (CBO e Procedimento)
# ---------------------------------------------------------------------------

@bp.route("/indicadores.xlsx")
def indicadores_xlsx():
    from openpyxl import Workbook

    db = get_db()
    portaria_id = request.args.get("portaria_id") or None

    filtro_ind = ""
    params_base = []
    if portaria_id:
        filtro_ind = "WHERE i.portaria_id = ?"
        params_base = [portaria_id]

    indicadores = db.execute(
        f"""SELECT i.*, p.numero AS portaria_numero,
                   p.periodo_inicio AS portaria_inicio, p.periodo_fim AS portaria_fim
            FROM indicadores i
            JOIN portarias p ON p.id = i.portaria_id
            {filtro_ind}
            ORDER BY p.numero, i.codigo""",
        params_base,
    ).fetchall()

    vinculos_cbo = db.execute(
        f"""SELECT p.numero AS portaria_numero, i.codigo AS indicador_codigo,
                   i.nome AS indicador_nome, i.tipo AS indicador_tipo,
                   ic.cbo_codigo, c.nome_categoria AS cbo_nome, ic.curinga,
                   sg.nome AS subgrupo_nome
            FROM indicador_cbo ic
            JOIN indicadores i ON i.id = ic.indicador_id
            JOIN portarias p ON p.id = i.portaria_id
            LEFT JOIN cbo c ON c.codigo = ic.cbo_codigo
            LEFT JOIN indicador_subgrupo sg ON sg.id = ic.subgrupo_id
            {filtro_ind}
            ORDER BY p.numero, i.codigo, sg.nome, ic.cbo_codigo""",
        params_base,
    ).fetchall()

    vinculos_proc = db.execute(
        f"""SELECT p.numero AS portaria_numero, i.codigo AS indicador_codigo,
                   i.nome AS indicador_nome, i.tipo AS indicador_tipo,
                   ip.procedimento_codigo, proc.nome AS procedimento_nome,
                   ip.tipo_vinculo,
                   ip.categoria_estabelecimento, ip.categoria_estabelecimento_neg,
                   e1.nome AS estabelecimento_nome, e2.nome AS estabelecimento_neg_nome,
                   sg.nome AS subgrupo_nome
            FROM indicador_procedimento ip
            JOIN indicadores i ON i.id = ip.indicador_id
            JOIN portarias p ON p.id = i.portaria_id
            LEFT JOIN procedimentos proc ON proc.codigo = ip.procedimento_codigo
            LEFT JOIN estabelecimentos e1 ON e1.id = ip.estabelecimento_id
            LEFT JOIN estabelecimentos e2 ON e2.id = ip.estabelecimento_id_neg
            LEFT JOIN indicador_subgrupo sg ON sg.id = ip.subgrupo_id
            {filtro_ind}
            ORDER BY p.numero, i.codigo, sg.nome, ip.procedimento_codigo""",
        params_base,
    ).fetchall()

    excecoes = db.execute(
        f"""SELECT p.numero AS portaria_numero, i.codigo AS indicador_codigo, i.nome AS indicador_nome,
                   'CBO excluído' AS tipo_excecao, c.codigo AS valor_codigo, c.nome_categoria AS valor_nome
            FROM indicador_cbo_excecao ex
            JOIN indicadores i ON i.id = ex.indicador_id
            JOIN portarias p ON p.id = i.portaria_id
            LEFT JOIN cbo c ON c.codigo = ex.cbo_codigo
            {filtro_ind}
            UNION ALL
            SELECT p.numero, i.codigo, i.nome,
                   'Estabelecimento excluído', CAST(es.id AS TEXT), es.nome
            FROM indicador_estabelecimento_excecao ex
            JOIN indicadores i ON i.id = ex.indicador_id
            JOIN portarias p ON p.id = i.portaria_id
            LEFT JOIN estabelecimentos es ON es.id = ex.estabelecimento_id
            {filtro_ind}
            ORDER BY 1, 2, 4""",
        params_base + params_base,
    ).fetchall()

    # contagem de vínculos por indicador, para a aba-resumo sinalizar
    # rapidamente indicadores sem nenhum vínculo cadastrado (provável
    # esquecimento de cadastro)
    contagem_cbo = {}
    for v in vinculos_cbo:
        chave = (v["portaria_numero"], v["indicador_codigo"])
        contagem_cbo[chave] = contagem_cbo.get(chave, 0) + 1
    contagem_proc = {}
    for v in vinculos_proc:
        chave = (v["portaria_numero"], v["indicador_codigo"])
        contagem_proc[chave] = contagem_proc.get(chave, 0) + 1

    wb = Workbook()

    ws_resumo = wb.active
    ws_resumo.title = "Indicadores"
    _cabecalho(ws_resumo, [
        "Portaria", "Vigência", "Código", "Nome do indicador", "Tipo",
        "Complexidade", "Serviço", "Fonte de dados", "Qtd vínculos CBO", "Qtd vínculos Procedimento",
        "Alerta",
    ])
    for i in indicadores:
        chave = (i["portaria_numero"], i["codigo"])
        qtd_cbo = contagem_cbo.get(chave, 0)
        qtd_proc = contagem_proc.get(chave, 0)
        alerta = ""
        if qtd_cbo == 0 and qtd_proc == 0:
            alerta = "SEM NENHUM VÍNCULO"
        elif qtd_proc == 0:
            alerta = "sem vínculo de procedimento"
        ws_resumo.append([
            i["portaria_numero"],
            f"{i['portaria_inicio']} a {i['portaria_fim']}",
            i["codigo"], i["nome"], i["tipo"],
            i["complexidade"], i["servico"], i["fonte_dados"] or "-",
            qtd_cbo, qtd_proc, alerta,
        ])
    _autofit(ws_resumo)

    ws_cbo = wb.create_sheet("Vinculos CBO")
    _cabecalho(ws_cbo, [
        "Portaria", "Indicador", "Nome do indicador", "Tipo",
        "Subgrupo", "CBO", "Nome do CBO", "Aceita qualquer CBO (curinga)",
    ])
    for v in vinculos_cbo:
        ws_cbo.append([
            v["portaria_numero"], v["indicador_codigo"], v["indicador_nome"], v["indicador_tipo"],
            v["subgrupo_nome"] or "-",
            v["cbo_codigo"] or "-", v["cbo_nome"] or "-",
            "SIM" if v["curinga"] else "não",
        ])
    _autofit(ws_cbo)

    ws_proc = wb.create_sheet("Vinculos Procedimento")
    _cabecalho(ws_proc, [
        "Portaria", "Indicador", "Nome do indicador", "Tipo", "Subgrupo",
        "Procedimento", "Nome do procedimento", "Tipo vínculo",
        "Categoria estabelecimento (+)", "Categoria estabelecimento (-)",
        "Estabelecimento específico (+)", "Estabelecimento específico (-)",
    ])
    for v in vinculos_proc:
        ws_proc.append([
            v["portaria_numero"], v["indicador_codigo"], v["indicador_nome"], v["indicador_tipo"],
            v["subgrupo_nome"] or "-",
            v["procedimento_codigo"], v["procedimento_nome"], v["tipo_vinculo"],
            v["categoria_estabelecimento"] or "-", v["categoria_estabelecimento_neg"] or "-",
            v["estabelecimento_nome"] or "-", v["estabelecimento_neg_nome"] or "-",
        ])
    _autofit(ws_proc)

    ws_excecoes = wb.create_sheet("Excecoes")
    _cabecalho(ws_excecoes, [
        "Portaria", "Indicador", "Nome do indicador", "Tipo de exceção", "Código", "Nome",
    ])
    for e in excecoes:
        ws_excecoes.append([
            e["portaria_numero"], e["indicador_codigo"], e["indicador_nome"],
            e["tipo_excecao"], e["valor_codigo"] or "-", e["valor_nome"] or "-",
        ])
    _autofit(ws_excecoes)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    sufixo = f"_portaria{portaria_id}" if portaria_id else "_todas"
    nome_arquivo = f"relatorio_indicadores{sufixo}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------------------------------------------------------------------------
# Relatório de metas + resumo de cobertura
# ---------------------------------------------------------------------------

@bp.route("/metas.xlsx")
def metas_xlsx():
    from openpyxl import Workbook

    db = get_db()
    ta_id = request.args.get("ta_id") or None

    filtro = ""
    params = []
    if ta_id:
        filtro = "WHERE m.ta_id = ?"
        params = [ta_id]

    metas = db.execute(
        f"""SELECT ta.numero AS ta_numero, ta.periodo_inicio AS ta_inicio, ta.periodo_fim AS ta_fim,
                   e.cod_cnes, e.cod_cmes, e.nome AS estabelecimento_nome,
                   pt.numero AS portaria_numero,
                   i.codigo AS indicador_codigo, i.nome AS indicador_nome, i.tipo AS indicador_tipo,
                   m.cbo_codigo, c.nome_categoria AS cbo_nome, m.valor_meta,
                   sg.nome AS subgrupo_nome
            FROM metas m
            JOIN termos_aditivos ta ON ta.id = m.ta_id
            LEFT JOIN indicador_subgrupo sg ON sg.id = m.subgrupo_id
            JOIN estabelecimentos e ON e.id = m.estabelecimento_id
            JOIN indicadores i ON i.id = m.indicador_id
            JOIN portarias pt ON pt.id = i.portaria_id
            LEFT JOIN cbo c ON c.codigo = m.cbo_codigo
            {filtro}
            ORDER BY ta.numero, e.nome, i.codigo""",
        params,
    ).fetchall()

    # resumo de cobertura: quantos estabelecimentos têm meta lançada para
    # cada indicador, dentro do(s) TA(s) filtrado(s) - ajuda a achar
    # indicadores esquecidos (0 metas) ou parcialmente cadastrados
    total_estab = db.execute("SELECT COUNT(*) AS n FROM estabelecimentos WHERE ativo=1").fetchone()["n"]

    resumo_cobertura = db.execute(
        f"""SELECT ta.numero AS ta_numero, pt.numero AS portaria_numero,
                   i.codigo AS indicador_codigo, i.nome AS indicador_nome,
                   COUNT(DISTINCT m.estabelecimento_id) AS qtd_estabelecimentos,
                   COUNT(m.id) AS qtd_linhas_meta,
                   SUM(m.valor_meta) AS soma_metas
            FROM metas m
            JOIN termos_aditivos ta ON ta.id = m.ta_id
            JOIN indicadores i ON i.id = m.indicador_id
            JOIN portarias pt ON pt.id = i.portaria_id
            {filtro}
            GROUP BY ta.numero, i.id
            ORDER BY ta.numero, i.codigo""",
        params,
    ).fetchall()

    wb = Workbook()

    ws_metas = wb.active
    ws_metas.title = "Metas"
    _cabecalho(ws_metas, [
        "TA", "Vigência do TA", "CNES", "CMES", "Estabelecimento",
        "Portaria", "Indicador", "Nome do indicador", "Subgrupo", "Tipo",
        "CBO", "Nome do CBO", "Valor da meta",
    ])
    for m in metas:
        ws_metas.append([
            m["ta_numero"], f"{m['ta_inicio']} a {m['ta_fim']}",
            m["cod_cnes"] or "-", m["cod_cmes"] or "-", m["estabelecimento_nome"],
            m["portaria_numero"], m["indicador_codigo"], m["indicador_nome"], m["subgrupo_nome"] or "-", m["indicador_tipo"],
            m["cbo_codigo"] or "Curinga / Geral", m["cbo_nome"] or "-", m["valor_meta"],
        ])
    _autofit(ws_metas)

    ws_cobertura = wb.create_sheet("Resumo cobertura")
    _cabecalho(ws_cobertura, [
        "TA", "Portaria", "Indicador", "Nome do indicador",
        "Estabelecimentos com meta", f"Total estabelecimentos ativos ({total_estab})",
        "Linhas de meta (com quebra por CBO)", "Soma das metas", "Alerta",
    ])
    for r in resumo_cobertura:
        alerta = ""
        if total_estab and r["qtd_estabelecimentos"] < total_estab:
            alerta = f"faltam {total_estab - r['qtd_estabelecimentos']} estabelecimento(s)"
        ws_cobertura.append([
            r["ta_numero"], r["portaria_numero"], r["indicador_codigo"], r["indicador_nome"],
            r["qtd_estabelecimentos"], total_estab, r["qtd_linhas_meta"], r["soma_metas"], alerta,
        ])
    _autofit(ws_cobertura)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    sufixo = f"_ta{ta_id}" if ta_id else "_todos"
    nome_arquivo = f"relatorio_metas{sufixo}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------------------------------------------------------------------------
# Relatório de Auditoria Contratual (Apurado STS vs Declarado Websaass)
# ---------------------------------------------------------------------------

@bp.route("/auditoria_websass.xlsx")
def auditoria_websass_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from .painel import _resultados_com_status, _carregar_mapa_websaass, _resolver_vinculo_websaass

    db = get_db()
    linhas = _resultados_com_status(db)
    mapa_ws = _carregar_mapa_websaass(db)

    wb = Workbook()
    ws_auditoria = wb.active
    ws_auditoria.title = "Auditoria Detalhada"

    titulos = [
        "Unidade / Estabelecimento", "CNES", "Código Indicador", "Nome do Indicador",
        "Subgrupo", "Tipo", "Complexidade", "Serviço", "CBO", "Nome CBO",
        "Período", "Apurado (STS)", "Declarado (Websaass)",
        "Cód. WebSaass", "Indicador WebSaass",
        "Divergência", "Meta Contratual", "% Meta Atingida", "Status Meta", "Status Auditoria Websaass",
        "Observações",
    ]
    _cabecalho(ws_auditoria, titulos)

    col_idx_status = titulos.index("Status Auditoria Websaass") + 1
    col_idx_div = titulos.index("Divergência") + 1

    fill_ok = PatternFill("solid", fgColor="E2F0D9")      # Verde claro
    font_ok = Font(color="276A3C", bold=True)
    fill_warn = PatternFill("solid", fgColor="FFF2CC")    # Amarelo claro
    font_warn = Font(color="8A6100", bold=True)
    fill_perigo = PatternFill("solid", fgColor="FCE4D6")  # Vermelho claro
    font_perigo = Font(color="C00000", bold=True)
    fill_cinza = PatternFill("solid", fgColor="F2F2F2")   # Cinza
    font_cinza = Font(color="595959")

    unidades_map = {}

    for row_idx, r in enumerate(linhas, start=2):
        ap = r.get("valor_apurado") or 0
        dec = r.get("valor_declarado") or 0
        div = r.get("divergencia", 0)
        meta = r.get("valor_meta")
        pct = f"{r.get('percentual_meta')}%" if r.get("percentual_meta") is not None else "-"
        rot_aud = r.get("auditoria_rotulo") or ""
        unidade_nome = r.get("estabelecimento_nome") or ""

        ws_cods, ws_prods = _resolver_vinculo_websaass(
            mapa_ws, r["indicador_id"], r.get("subgrupo_id"), r.get("cbo_codigo")
        )

        # Estatísticas por unidade
        if unidade_nome not in unidades_map:
            unidades_map[unidade_nome] = {
                "cnes": r.get("grupo_cnes") or "",
                "total_itens": 0,
                "conformes": 0,
                "divergentes": 0,
                "total_apurado": 0,
                "total_declarado": 0,
            }
        u_stat = unidades_map[unidade_nome]
        u_stat["total_itens"] += 1
        if rot_aud == "Conforme (OK)":
            u_stat["conformes"] += 1
        elif rot_aud != "Sem produção":
            u_stat["divergentes"] += 1
        u_stat["total_apurado"] += ap
        u_stat["total_declarado"] += dec

        ws_auditoria.append([
            unidade_nome,
            r.get("grupo_cnes") or "",
            r.get("indicador_codigo") or "",
            r.get("indicador_nome") or "",
            r.get("subgrupo_nome") or "",
            r.get("indicador_tipo") or "",
            r.get("complexidade") or "",
            r.get("servico") or "",
            r.get("cbo_codigo") or "",
            r.get("cbo_nome") or "Curinga / Geral",
            r.get("periodo") or "",
            ap,
            dec,
            ws_cods,
            ws_prods,
            div,
            meta if meta is not None else "-",
            pct,
            r.get("status_rotulo") or "",
            rot_aud,
            r.get("observacao") or "",
        ])

        cell_status = ws_auditoria.cell(row=row_idx, column=col_idx_status)
        cell_div = ws_auditoria.cell(row=row_idx, column=col_idx_div)

        if rot_aud == "Conforme (OK)":
            cell_status.fill = fill_ok
            cell_status.font = font_ok
            cell_div.font = font_ok
        elif "Declarado maior" in rot_aud or "Não apurado" in rot_aud:
            cell_status.fill = fill_perigo
            cell_status.font = font_perigo
            cell_div.font = font_perigo
        elif "Apurado maior" in rot_aud or "Não declarado" in rot_aud:
            cell_status.fill = fill_warn
            cell_status.font = font_warn
            cell_div.font = font_warn
        else:
            cell_status.fill = fill_cinza
            cell_status.font = font_cinza

    _autofit(ws_auditoria)

    # Aba de Resumo por Unidade
    ws_resumo = wb.create_sheet("Resumo por Unidade")
    titulos_resumo = [
        "Unidade de Saúde", "CNES", "Total Indicadores", "Itens Conformes",
        "Itens Divergentes", "% Conformidade", "Total Apurado (STS)",
        "Total Declarado (Websaass)", "Divergência Total",
    ]
    _cabecalho(ws_resumo, titulos_resumo)

    for r_idx, (unidade, st) in enumerate(sorted(unidades_map.items()), start=2):
        tot_it = st["total_itens"]
        conf = st["conformes"]
        pct_conf = f"{(conf / tot_it * 100):.1f}%" if tot_it > 0 else "-"
        div_total = st["total_apurado"] - st["total_declarado"]

        ws_resumo.append([
            unidade,
            st["cnes"],
            tot_it,
            conf,
            st["divergentes"],
            pct_conf,
            st["total_apurado"],
            st["total_declarado"],
            div_total,
        ])
        c_pct = ws_resumo.cell(row=r_idx, column=6)
        if tot_it > 0:
            val_pct = (conf / tot_it) * 100
            if val_pct == 100:
                c_pct.fill = fill_ok
                c_pct.font = font_ok
            elif val_pct >= 80:
                c_pct.fill = fill_warn
                c_pct.font = font_warn
            else:
                c_pct.fill = fill_perigo
                c_pct.font = font_perigo

    _autofit(ws_resumo)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nome_arquivo = f"auditoria_websaass_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------------------------------------------------------------------------
# Espelho do WebSaass com Produção Apurada (STS)
# ---------------------------------------------------------------------------

@bp.route("/espelho_websaass.xlsx")
def espelho_websaass_xlsx():
    """
    Exporta a visão do WebSaass: traz cada linha oficial do WebSaass
    (staging_webssas: Contrato, Unidade, Período, Serviço, Cód. Produção,
    Produção, Meta Prevista, Declarado), acrescentando uma coluna com o
    que o STS apurou/encontrou para cada item, além da divergência, status
    e do indicador STS correspondente.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from ..funcoes import _normalizar_periodo, _periodo_para_webssas, _resolver_estabelecimento_websaass, consolidacao

    db = get_db()
    periodo_filtro = request.args.get("periodo") or None

    # 1. Carregar mapeamento de estabelecimentos e consolidação CNES
    estabs_map = {e["id"]: e["nome"] for e in db.execute("SELECT id, nome FROM estabelecimentos").fetchall()}
    grupos = consolidacao.analisar(db)

    # 2. Carregar de-para de indicadores (indexado por cod_producao e servico normalizado)
    from ..funcoes import _normalizar_texto_chave
    dp_ind = {}
    for dp in db.execute("""
        SELECT lower(trim(dp.cod_producao)) as cp,
               dp.servico,
               dp.indicador_id, dp.subgrupo_id, dp.cbo_codigo, dp.codigo_indicador,
               i.nome as indicador_nome
        FROM de_para_websaass_indicador dp
        LEFT JOIN indicadores i ON i.id = dp.indicador_id
        WHERE dp.cod_producao IS NOT NULL
    """).fetchall():
        cp = dp["cp"]
        serv_norm = _normalizar_texto_chave(dp["servico"])
        dp_dict = dict(dp)
        if serv_norm:
            dp_ind.setdefault((cp, serv_norm), []).append(dp_dict)
        else:
            dp_ind.setdefault((cp, ""), []).append(dp_dict)

    # 3. Carregar fatos apurados (STS)
    filtro_fatos = "WHERE tipo_registro = 'apurado'"
    params_fatos = []
    if periodo_filtro:
        p_norm = _normalizar_periodo(periodo_filtro)
        filtro_fatos += " AND periodo = ?"
        params_fatos.append(p_norm)

    mapa_fatos = {}
    for f in db.execute(f"""
        SELECT estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo, periodo, sum(quantidade) as total
        FROM fato_apuracao
        {filtro_fatos}
        GROUP BY estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo, periodo
    """, params_fatos).fetchall():
        eid = f["estabelecimento_id"]
        iid = f["indicador_id"]
        sub = f["subgrupo_id"]
        cbo = f["cbo_codigo"]
        per = f["periodo"]
        qty = f["total"] or 0
        mapa_fatos[(eid, iid, sub, cbo, per)] = qty

    # 4. Consultar linhas de staging_webssas
    query_ws = "SELECT * FROM staging_webssas"
    params_ws = []
    if periodo_filtro:
        p_norm = _normalizar_periodo(periodo_filtro)
        p_ws = _periodo_para_webssas(p_norm)
        query_ws += " WHERE periodo = ? OR periodo = ? OR periodo = ?"
        params_ws = [periodo_filtro, p_norm, p_ws]
    query_ws += " ORDER BY unidade, cod_producao, id"

    linhas_ws = db.execute(query_ws, params_ws).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Espelho WebSaass"

    titulos = [
        "Contrato",
        "Unidade WebSaass",
        "Estabelecimento STS",
        "Período",
        "Serviço WebSaass",
        "Produção WebSaass",
        "WebSaass",
        "STS",
        "Diferença",
        "Indicador STS Vinculado",
        "CBO / Regra STS",
    ]

    _cabecalho(ws, titulos)

    fill_ok = PatternFill("solid", fgColor="E2F0D9")
    font_ok = Font(color="276A3C", bold=True)
    fill_warn = PatternFill("solid", fgColor="FFF2CC")
    font_warn = Font(color="8A6100", bold=True)
    fill_perigo = PatternFill("solid", fgColor="FCE4D6")
    font_perigo = Font(color="C00000", bold=True)
    font_cinza = Font(color="595959")

    col_idx_div = titulos.index("Diferença") + 1

    for row_idx, r in enumerate(linhas_ws, start=2):
        unidade_ws = (r["unidade"] or "").strip()
        estab_id = _resolver_estabelecimento_websaass(db, unidade_ws)
        if not estab_id and not unidade_ws and r["cod_producao"]:
            estab_id = _resolver_estabelecimento_websaass(db, r["cod_producao"])
        estab_nome = estabs_map.get(estab_id, "") if estab_id else ""

        cp = (r["cod_producao"] or "").strip().lower()
        serv_norm = _normalizar_texto_chave(r["servico"])

        regras = dp_ind.get((cp, serv_norm))
        if not regras and serv_norm:
            for (k_cp, k_serv), r_list in dp_ind.items():
                if k_cp == cp and k_serv and (k_serv in serv_norm or serv_norm in k_serv):
                    regras = r_list
                    break
        if not regras:
            regras = dp_ind.get((cp, ""), [])

        per_linha = _normalizar_periodo(r["periodo"])

        # Consolidação por CNES / membros de estabelecimento
        info_grp = grupos.get(estab_id)
        eids_busca = info_grp["membros"] if (info_grp and info_grp.get("agrupado")) else [estab_id]

        apurado_sts = 0
        inds_set = set()
        cbos_set = set()
        chaves_somadas = set()
        tem_vinculo = bool(regras)

        if estab_id and regras:
            for rg in regras:
                iid = rg["indicador_id"]
                sub = rg["subgrupo_id"]
                cbo = rg["cbo_codigo"]
                if rg["codigo_indicador"]:
                    inds_set.add(rg["codigo_indicador"])
                if cbo:
                    cbos_set.add(cbo)
                for m_eid in eids_busca:
                    if cbo:
                        k = (m_eid, iid, sub, cbo, per_linha)
                        if k not in chaves_somadas:
                            chaves_somadas.add(k)
                            apurado_sts += mapa_fatos.get(k, 0)
                    else:
                        for (k_eid, k_iid, k_sub, k_cbo, k_per), k_qty in mapa_fatos.items():
                            if k_eid == m_eid and k_iid == iid and (sub is None or k_sub == sub) and k_per == per_linha:
                                k = (k_eid, k_iid, k_sub, k_cbo, k_per)
                                if k not in chaves_somadas:
                                    chaves_somadas.add(k)
                                    apurado_sts += k_qty

        dec_ws = r["qtde_realizada"] or 0
        dif = apurado_sts - dec_ws

        ws.append([
            r["cod_contrato"] or "",
            unidade_ws,
            estab_nome,
            r["periodo"] or "",
            r["servico"] or "",
            r["producao"] or "",
            dec_ws,
            apurado_sts,
            dif,
            ", ".join(sorted(inds_set)) if inds_set else ("Sem vínculo" if not tem_vinculo else "-"),
            ", ".join(sorted(cbos_set)) if cbos_set else "Geral",
        ])

        c_div = ws.cell(row=row_idx, column=col_idx_div)

        if not tem_vinculo or (apurado_sts == 0 and dec_ws == 0):
            c_div.font = font_cinza
        elif dif == 0:
            c_div.fill = fill_ok
            c_div.font = font_ok
        elif dif < 0:
            c_div.fill = fill_perigo
            c_div.font = font_perigo
        else:
            c_div.fill = fill_warn
            c_div.font = font_warn

    _autofit(ws)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    sufixo_per = f"_{periodo_filtro}" if periodo_filtro else ""
    nome_arquivo = f"espelho_websaass{sufixo_per}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


