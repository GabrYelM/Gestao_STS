import io

from flask import Blueprint, Response, jsonify, render_template, request

from ..db import get_db
from ..funcoes import consolidacao, diagnostico_metas, pendencias

bp = Blueprint("painel", __name__, url_prefix="/contratos")


def _resultados_filtrados(db):
    """Linhas do painel. Em modo de consolidação 'CNES' (Administração >
    Portaria/TA, ou seletor do próprio painel), os cadastros que compartilham
    o mesmo CNES viram uma linha só - ver app/etl/consolidacao.py. Em 'CMES'
    (padrão) a view é usada como está."""
    linhas = [
        dict(r) for r in db.execute(
            "SELECT * FROM resultados_indicador ORDER BY estabelecimento_nome, indicador_codigo, subgrupo_nome"
        ).fetchall()
    ]
    linhas = consolidacao.consolidar_resultados(
        linhas, consolidacao.analisar(db), consolidacao.indicadores_cnes(db)
    )
    linhas = consolidacao.completar_metas_do_grupo(db, linhas)
    for linha in linhas:
        linha.setdefault("estabelecimento_ids", [linha["estabelecimento_id"]])
    linhas.sort(key=lambda r: (
        r["estabelecimento_nome"] or "", r["indicador_codigo"] or "", r.get("subgrupo_nome") or "",
        r["cbo_codigo"] or "", r["periodo"] or "",
    ))
    return linhas


def status_meta(percentual):
    """
    Classifica o percentual de atingimento da meta em uma das faixas do
    painel. Regras (definidas junto com o time gestor do contrato):
      - sem meta cadastrada para cruzar com o apurado -> "Sem meta" (cinza)
      - acima de 100%                                  -> "Acima de 100%" (amarelo)
      - entre 90% e 100% (inclusive)                    -> "Entre 90-100%" (azul/neutro)
      - abaixo de 90%                                    -> "Abaixo de 90%" (vermelho/alerta)
    Retorna (rotulo, classe_css_do_badge).
    """
    if percentual is None:
        return ("Sem meta", "badge-cinza")
    if percentual > 100:
        return ("Acima de 100%", "badge-amarelo")
    if percentual >= 90:
        return ("Entre 90-100%", "badge-azul")
    return ("Abaixo de 90%", "badge-vermelho")


def status_auditoria(apurado, declarado, meta):
    """
    Classifica a conformidade da auditoria entre Apurado (STS) e Declarado (Websaass).
    """
    ap = apurado or 0
    dec = declarado or 0
    dif = ap - dec

    if ap == 0 and dec == 0:
        return ("Sem produção", "badge-cinza", 0)
    if ap == dec:
        return ("Conforme (OK)", "badge-verde", 0)
    if dec > 0 and ap == 0:
        return (f"Não apurado ({dif:+d})", "badge-perigo", dif)
    if ap > 0 and dec == 0:
        return (f"Não declarado ({dif:+d})", "badge-amarelo", dif)
    if dif > 0:
        return (f"Apurado maior ({dif:+d})", "badge-amarelo", dif)
    return (f"Declarado maior ({dif:+d})", "badge-perigo", dif)


def _resultados_com_status(db):
    linhas = []
    for r in _resultados_filtrados(db):
        linha = dict(r)
        rotulo, classe = status_meta(linha.get("percentual_meta"))
        linha["status_rotulo"] = rotulo
        linha["status_classe"] = classe

        ap = linha.get("valor_apurado") or 0
        dec = linha.get("valor_declarado") or 0
        aud_rotulo, aud_classe, divergencia = status_auditoria(ap, dec, linha.get("valor_meta"))
        linha["divergencia"] = divergencia
        linha["auditoria_rotulo"] = aud_rotulo
        linha["auditoria_classe"] = aud_classe

        linhas.append(linha)
    return linhas


def _contadores_alerta(db):
    """
    Contagens para os cards de destaque do topo do painel.
    """
    sem_cbo = db.execute(
        """SELECT COUNT(*) AS n FROM indicadores i
           WHERE NOT EXISTS (SELECT 1 FROM indicador_cbo ic WHERE ic.indicador_id = i.id)"""
    ).fetchone()["n"]

    sem_procedimento = db.execute(
        """SELECT COUNT(*) AS n FROM indicadores i
           WHERE NOT EXISTS (SELECT 1 FROM indicador_procedimento ip WHERE ip.indicador_id = i.id)"""
    ).fetchone()["n"]

    sem_estabelecimento = db.execute(
        """SELECT COUNT(*) AS n FROM indicadores i
           WHERE NOT EXISTS (
               SELECT 1 FROM indicador_procedimento ip
               WHERE ip.indicador_id = i.id
                 AND (ip.categoria_estabelecimento IS NOT NULL OR ip.estabelecimento_id IS NOT NULL)
           )"""
    ).fetchone()["n"]

    sem_meta = db.execute(
        """SELECT COUNT(*) AS n FROM indicadores i
           WHERE NOT EXISTS (SELECT 1 FROM metas mt WHERE mt.indicador_id = i.id)"""
    ).fetchone()["n"]

    linhas_f = _resultados_com_status(db)
    abaixo_da_meta = len({
        r["indicador_id"] for r in linhas_f
        if r["percentual_meta"] is not None and r["percentual_meta"] < 90
    })

    metas_atingidas = sum(1 for r in linhas_f if r.get("percentual_meta") is not None and r["percentual_meta"] >= 100)
    metas_andamento = sum(1 for r in linhas_f if r.get("percentual_meta") is not None and 90 <= r["percentual_meta"] < 100)
    metas_abaixo = sum(1 for r in linhas_f if r.get("percentual_meta") is not None and r["percentual_meta"] < 90)
    sem_meta_linhas = sum(1 for r in linhas_f if r.get("percentual_meta") is None)

    total_apurado_geral = sum(r.get("valor_apurado") or 0 for r in linhas_f)
    total_metas_geral = sum(r.get("valor_meta") or 0 for r in linhas_f if r.get("valor_meta") is not None)
    total_unidades = len({r["estabelecimento_id"] for r in linhas_f if r.get("estabelecimento_id")})
    percentual_global = round((total_apurado_geral / total_metas_geral * 100), 1) if total_metas_geral else 0

    auditoria_conformes = sum(
        1 for r in linhas_f
        if r["auditoria_rotulo"] == "Conforme (OK)"
    )
    auditoria_divergentes = sum(
        1 for r in linhas_f
        if r["auditoria_rotulo"] not in ("Conforme (OK)", "Sem produção")
    )

    metas_sem_painel = len(diagnostico_metas.diagnosticar(db))

    return {
        "metas_atingidas": metas_atingidas,
        "metas_andamento": metas_andamento,
        "metas_abaixo": metas_abaixo,
        "sem_meta_linhas": sem_meta_linhas,
        "total_apurado_geral": total_apurado_geral,
        "total_metas_geral": total_metas_geral,
        "total_unidades": total_unidades,
        "percentual_global": percentual_global,
        "metas_sem_painel": metas_sem_painel,
        "sem_cbo": sem_cbo,
        "sem_estabelecimento": sem_estabelecimento,
        "sem_procedimento": sem_procedimento,
        "sem_meta": sem_meta,
        "abaixo_da_meta": abaixo_da_meta,
        "auditoria_conformes": auditoria_conformes,
        "auditoria_divergentes": auditoria_divergentes,
    }


@bp.route("/painel/alerta_detalhe", methods=["GET"])
def alerta_detalhe():
    """
    Detalhe por trás de cada card de alerta do topo do painel - a mesma
    lógica de _contadores_alerta, mas retornando as linhas em vez de só a
    contagem, para o card poder abrir um modal com a lista ao ser clicado.
    """
    tipo = request.args.get("tipo", "")
    db = get_db()

    if tipo in ("metas_atingidas", "metas_andamento", "metas_abaixo", "abaixo_da_meta", "sem_meta_linhas"):
        linhas_f = _resultados_com_status(db)
        if tipo == "metas_atingidas":
            filtradas = [r for r in linhas_f if r.get("percentual_meta") is not None and r["percentual_meta"] >= 100]
            filtradas.sort(key=lambda r: r.get("percentual_meta") or 0, reverse=True)
        elif tipo == "metas_andamento":
            filtradas = [r for r in linhas_f if r.get("percentual_meta") is not None and 90 <= r["percentual_meta"] < 100]
            filtradas.sort(key=lambda r: r.get("percentual_meta") or 0, reverse=True)
        elif tipo in ("metas_abaixo", "abaixo_da_meta"):
            filtradas = [r for r in linhas_f if r.get("percentual_meta") is not None and r["percentual_meta"] < 90]
            filtradas.sort(key=lambda r: r.get("percentual_meta") or 0)
        else:  # sem_meta_linhas
            filtradas = [r for r in linhas_f if r.get("percentual_meta") is None]

        return jsonify({
            "tipo": tipo,
            "colunas": ["Indicador", "Estabelecimento", "CBO", "Período", "Apurado STS", "Meta", "% Atingido", "Status"],
            "itens": [
                {
                    "indicador_id": r["indicador_id"],
                    "celulas": [
                        f"{r['indicador_codigo']} - {r['indicador_nome']}"
                        + (f" ({r['subgrupo_nome']})" if r.get("subgrupo_nome") else ""),
                        r["estabelecimento_nome"],
                        (f"{r['cbo_codigo']} - {r['cbo_nome']}" if r.get("cbo_codigo") else (r.get("cbo_nome") or "Curinga / Geral")),
                        r["periodo"],
                        f"{r.get('valor_apurado', 0):,}".replace(",", "."),
                        f"{r.get('valor_meta', 0):,}".replace(",", ".") if r.get("valor_meta") is not None else "-",
                        f"{r['percentual_meta']}%" if r.get("percentual_meta") is not None else "-",
                        r.get("status_rotulo") or "",
                    ],
                }
                for r in filtradas
            ],
        })

    if tipo in ("auditoria_conformes", "auditoria_divergentes"):
        linhas_f = _resultados_com_status(db)
        if tipo == "auditoria_conformes":
            linhas = [r for r in linhas_f if r.get("auditoria_rotulo") == "Conforme (OK)"]
        else:
            linhas = [r for r in linhas_f if r.get("auditoria_rotulo") not in ("Conforme (OK)", "Sem produção")]

        return jsonify({
            "tipo": tipo,
            "colunas": ["Indicador", "Estabelecimento", "CBO", "Período", "Apurado", "Declarado", "Divergência", "Status Auditoria"],
            "itens": [
                {
                    "indicador_id": r["indicador_id"],
                    "celulas": [
                        f"{r['indicador_codigo']} - {r['indicador_nome']}"
                        + (f" ({r['subgrupo_nome']})" if r.get("subgrupo_nome") else ""),
                        r["estabelecimento_nome"],
                        (f"{r['cbo_codigo']} - {r['cbo_nome']}" if r.get("cbo_codigo") else (r.get("cbo_nome") or "Curinga / Geral")),
                        r["periodo"],
                        str(r.get("valor_apurado") or 0),
                        str(r.get("valor_declarado") or 0),
                        f"{r.get('divergencia', 0):+d}",
                        r.get("auditoria_rotulo") or "",
                    ],
                }
                for r in linhas
            ],
        })


    condicoes = {
        "sem_cbo": "NOT EXISTS (SELECT 1 FROM indicador_cbo ic WHERE ic.indicador_id = i.id)",
        "sem_procedimento": "NOT EXISTS (SELECT 1 FROM indicador_procedimento ip WHERE ip.indicador_id = i.id)",
        "sem_estabelecimento": """NOT EXISTS (
            SELECT 1 FROM indicador_procedimento ip
            WHERE ip.indicador_id = i.id
              AND (ip.categoria_estabelecimento IS NOT NULL OR ip.estabelecimento_id IS NOT NULL)
        )""",
        "sem_meta": "NOT EXISTS (SELECT 1 FROM metas mt WHERE mt.indicador_id = i.id)",
    }
    if tipo not in condicoes:
        return jsonify({"erro": "tipo inválido"}), 400

    linhas = db.execute(
        f"""SELECT i.id, i.codigo, i.nome, i.tipo AS tipo_indicador, p.numero AS portaria_numero
            FROM indicadores i JOIN portarias p ON p.id = i.portaria_id
            WHERE {condicoes[tipo]}
            ORDER BY p.numero, i.codigo"""
    ).fetchall()
    return jsonify({
        "tipo": tipo,
        "colunas": ["Indicador", "Tipo", "Portaria"],
        "itens": [
            {
                "indicador_id": r["id"],
                "celulas": [f"{r['codigo']} - {r['nome']}", r["tipo_indicador"], r["portaria_numero"]],
            }
            for r in linhas
        ],
    })


@bp.route("/")
def index():
    db = get_db()
    resultados = _resultados_com_status(db)
    alertas = _contadores_alerta(db)
    return render_template(
        "contratos/painel.html", resultados=resultados, alertas=alertas,
        qtd_indicadores_cnes=len(consolidacao.indicadores_cnes(db)),
        pendencias=pendencias.pendencias_at02(db),
        sem_fatos=db.execute("SELECT 1 FROM fato_apuracao LIMIT 1").fetchone() is None,
    )


def _ids_da_linha(args):
    """Ids de estabelecimento de uma linha do painel: 'estabelecimento_ids'
    (lista separada por vírgula - linha consolidada por CNES) ou, para
    compatibilidade, o 'estabelecimento_id' único."""
    bruto = args.get("estabelecimento_ids") or args.get("estabelecimento_id") or ""
    return [int(x) for x in str(bruto).split(",") if x.strip().isdigit()]


def _subgrupo_da_linha(valor):
    return int(valor) if valor not in (None, "", "None") else None


def _obter_info_linha(db, indicador_id, estabelecimento_ids):
    """Retorna codigo do indicador, nome, e listas de CNES e CMES dos estabelecimentos."""
    ind = db.execute("SELECT codigo, nome FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
    ind_cod = (ind["codigo"] if ind else "").upper().strip()
    ind_nome = ind["nome"] if ind else ""

    cnes_list = []
    cmes_list = []
    if estabelecimento_ids:
        marcadores = ",".join("?" * len(estabelecimento_ids))
        estabs = db.execute(
            f"SELECT cod_cnes, cod_cmes FROM estabelecimentos WHERE id IN ({marcadores})",
            estabelecimento_ids,
        ).fetchall()
        for e in estabs:
            if e["cod_cnes"]:
                c = e["cod_cnes"].strip()
                cnes_list.append(c)
                cnes_list.append(c.lstrip("0"))
            if e["cod_cmes"]:
                c = e["cod_cmes"].strip()
                cmes_list.append(c)
                cmes_list.append(c.lstrip("0"))
    cnes_list = list(set(cnes_list))
    cmes_list = list(set(cmes_list))
    return ind_cod, ind_nome, cnes_list, cmes_list


def _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id=None):
    """Códigos de procedimento (com nome) que compõem esta linha exata do
    painel - usado para restringir a busca em staging_at02 tanto no nível
    1 (profissionais) quanto no nível 2 (procedimentos de um profissional).
    Sem cbo_codigo (linha 'Curinga / Geral') não filtra por CBO."""
    if not estabelecimento_ids:
        return []
    marcadores = ",".join("?" * len(estabelecimento_ids))
    sql = f"""SELECT p.codigo, p.nome
           FROM fato_apuracao f JOIN procedimentos p ON p.codigo = f.procedimento_codigo
           WHERE f.indicador_id = ? AND f.estabelecimento_id IN ({marcadores}) AND f.periodo = ?
             AND f.tipo_registro = 'apurado' AND f.subgrupo_id IS ?"""
    params = [indicador_id, *estabelecimento_ids, periodo, subgrupo_id]
    if cbo_codigo:
        sql += " AND f.cbo_codigo = ?"
        params.append(cbo_codigo)
    sql += " GROUP BY p.codigo"
    res = db.execute(sql, params).fetchall()
    if not res:
        if subgrupo_id is not None:
            res = db.execute(
                """SELECT p.codigo, p.nome FROM indicador_procedimento ip
                   JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
                   WHERE ip.indicador_id = ? AND ip.subgrupo_id = ?""",
                (indicador_id, subgrupo_id)
            ).fetchall()
        else:
            res = db.execute(
                """SELECT p.codigo, p.nome FROM indicador_procedimento ip
                   JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
                   WHERE ip.indicador_id = ? AND ip.subgrupo_id IS NULL""",
                (indicador_id,)
            ).fetchall()
    return res


def _cmes_e_cbos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id):
    """CMES dos cadastros da linha e, numa linha 'Curinga / Geral', os CBOs que
    de fato entraram no apurado."""
    marcadores = ",".join("?" * len(estabelecimento_ids))
    cmes = [
        r["cod_cmes"] for r in db.execute(
            f"SELECT cod_cmes FROM estabelecimentos WHERE id IN ({marcadores})", estabelecimento_ids
        ).fetchall() if r["cod_cmes"]
    ]
    cbos = None
    if not cbo_codigo:
        ind_cbos = db.execute(
            """SELECT cbo_codigo, curinga FROM indicador_cbo
               WHERE indicador_id = ? AND subgrupo_id IS ?""",
            (indicador_id, subgrupo_id),
        ).fetchall()
        tem_cbos_especificos = ind_cbos and not any(c["curinga"] == 1 for c in ind_cbos)
        if tem_cbos_especificos:
            return cmes, []

        fatos = db.execute(
            f"""SELECT DISTINCT cbo_codigo FROM fato_apuracao
                WHERE indicador_id = ? AND estabelecimento_id IN ({marcadores}) AND periodo = ?
                  AND tipo_registro = 'apurado' AND subgrupo_id IS ?""",
            [indicador_id, *estabelecimento_ids, periodo, subgrupo_id],
        ).fetchall()
        valores = [f["cbo_codigo"] for f in fatos]
        if valores and None not in valores:
            cbos = valores
    return cmes, cbos


def _profissionais_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id=None):
    """
    Nível 1 do drill-down: profissionais (com o CBO de cada um) e o total
    apurado por cada um, para esta linha exata do painel. Suporta todas as fontes
    oficiais (Visitas Domiciliares, DTIC eMulti REL134, DTIC AD eSUS REL130,
    SSRS AT-57, AT-61, AT-48, AT-49, AT-11, AT-40, AT-39, AT-08 e AT-02).
    """
    ind_cod, ind_nome, cnes_list, cmes_list = _obter_info_linha(db, indicador_id, estabelecimento_ids)

    # 1. Visita Domiciliar (P06 / P6)
    if ind_cod in ("P06", "P6"):
        if not cnes_list:
            return []
        p = str(periodo or "")
        ano = p[:4] if len(p) >= 4 else ""
        mes = p[4:6] if len(p) >= 6 else ""
        mes_sem_zero = mes.lstrip("0")
        marc_cnes = ",".join("?" * len(cnes_list))
        params = [p, p, ano, mes, mes_sem_zero, *cnes_list]
        sql = f"""SELECT s.nome_profissional, s.cod_cbo AS cbo_codigo, s.nome_cbo AS cbo_nome,
                         SUM(s.total_visitas) AS apurado
                  FROM staging_visita_domiciliar s
                  WHERE (s.ano || s.mes = ? OR s.ano || printf('%02d', CAST(s.mes AS INT)) = ?
                         OR (s.ano = ? AND (s.mes = ? OR s.mes = ?)))
                    AND s.cod_cnes IN ({marc_cnes})
                    AND s.nome_profissional IS NOT NULL"""
        if cbo_codigo:
            sql += " AND (s.cod_cbo = ? OR s.cod_cbo LIKE ?)"
            params.extend([cbo_codigo, f"%{cbo_codigo}%"])
        sql += " GROUP BY s.nome_profissional, s.cod_cbo ORDER BY apurado DESC"
        return db.execute(sql, params).fetchall()

    # 2. Atividades Coletivas eMulti (P12 / P22)
    if ind_cod in ("P12", "P22"):
        if not cnes_list:
            return []
        marc_cnes = ",".join("?" * len(cnes_list))
        p = str(periodo or "")
        params = [p, f"%{p}%", *cnes_list]
        sql = f"""SELECT s.nome_profissional, s.cbo_prof AS cbo_codigo, s.cbo AS cbo_nome,
                         COUNT(*) AS apurado
                  FROM staging_dtic_rel134 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional IS NOT NULL"""
        if cbo_codigo:
            sql += " AND (s.cbo_prof = ? OR s.cbo_prof LIKE ?)"
            params.extend([cbo_codigo, f"%{cbo_codigo}%"])
        sql += " GROUP BY s.nome_profissional, s.cbo_prof ORDER BY apurado DESC"
        return db.execute(sql, params).fetchall()

    # 3. Atendimento Domiciliar eSUS (P30 / P33)
    if ind_cod in ("P30", "P33"):
        if not cnes_list:
            return []
        marc_cnes = ",".join("?" * len(cnes_list))
        p = str(periodo or "")
        equipe_filtro = "%EMAD%" if ind_cod == "P30" else "%EMAP%"
        params = [p, f"%{p}%", equipe_filtro, *cnes_list]
        sql = f"""SELECT s.nome_profissional, s.cod_cbo AS cbo_codigo, s.cbo AS cbo_nome,
                         COUNT(*) AS apurado
                  FROM staging_dtic_rel130 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND s.nome_equipe LIKE ?
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional IS NOT NULL"""
        if cbo_codigo:
            sql += " AND (s.cod_cbo = ? OR s.cod_cbo LIKE ?)"
            params.extend([cbo_codigo, f"%{cbo_codigo}%"])
        sql += " GROUP BY s.nome_profissional, s.cod_cbo ORDER BY apurado DESC"
        return db.execute(sql, params).fetchall()

    # 4. PICS (P09, P10, P19, P20) ou Grupos (P11, P21) - SSRS
    if ind_cod in ("P09", "P10", "P19", "P20", "P11", "P21"):
        fonte = "AT57" if ind_cod in ("P09", "P10", "P19", "P20") else "AT61"
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        row = db.execute(
            f"""SELECT SUM(quantidade) AS tot FROM staging_bi_siga
                WHERE fonte_at = ? AND (ano_mes = ? OR ano_mes LIKE ?) AND cod_cnes IN ({marc_cnes})""",
            [fonte, str(periodo or ""), f"%{periodo}%", *cnes_list],
        ).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        desc = "Práticas Integrativas (PICS)" if fonte == "AT57" else "Grupos e Atendimentos"
        return [{"nome_profissional": f"Consolidado SIGA ({desc})", "cbo_codigo": cbo_codigo, "cbo_nome": desc, "apurado": tot}]

    # 5. Outros SSRS (P25 [PAI], P29 [CAPS], P36 [CER], P38 [CEO], P41 [APD], P27 [URSI])
    if ind_cod in ("P25", "P29", "P36", "P38", "P41", "P27"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        row = db.execute(
            f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
               WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'""",
            [indicador_id, *estabelecimento_ids, str(periodo or "")],
        ).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        return [{"nome_profissional": f"Consolidado SIGA ({ind_nome})", "cbo_codigo": cbo_codigo, "cbo_nome": ind_nome, "apurado": tot}]

    # 6. AT-02 padrão
    procedimentos = _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not procedimentos:
        return []

    cmes, cbos = _cmes_e_cbos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not cmes or cbos == []:
        return []

    proc_lista = [p["codigo"] for p in procedimentos]
    sql = f"""SELECT s.nome_profissional, s.cod_cbo_sus AS cbo_codigo, c.nome_categoria AS cbo_nome,
                     SUM(s.quantidade) AS apurado
              FROM staging_at02 s LEFT JOIN cbo c ON c.codigo = s.cod_cbo_sus
              WHERE s.ano_mes = ? AND s.cod_cmes IN ({",".join("?" * len(cmes))})
                AND s.cod_procedimento IN ({",".join("?" * len(proc_lista))})
                AND s.nome_profissional IS NOT NULL"""
    params = [periodo, *cmes, *proc_lista]
    if cbo_codigo:
        sql += " AND s.cod_cbo_sus = ?"
        params.append(cbo_codigo)
    elif cbos:
        sql += f" AND s.cod_cbo_sus IN ({','.join('?' * len(cbos))})"
        params.extend(cbos)
    sql += " GROUP BY s.nome_profissional, s.cod_cbo_sus ORDER BY apurado DESC"
    return db.execute(sql, params).fetchall()


def _procedimentos_do_profissional(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, profissional,
                                   subgrupo_id=None, cbo_profissional=None):
    """Nível 2 do drill-down: procedimentos realizados por UM profissional
    específico (ou detalhamento de procedimentos do indicador), dentro da mesma linha do painel."""
    ind_cod, ind_nome, cnes_list, cmes_list = _obter_info_linha(db, indicador_id, estabelecimento_ids)

    # 1. Visita Domiciliar (P06 / P6)
    if ind_cod in ("P06", "P6"):
        p = str(periodo or "")
        ano = p[:4] if len(p) >= 4 else ""
        mes = p[4:6] if len(p) >= 6 else ""
        mes_sem_zero = mes.lstrip("0")
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        row = db.execute(
            f"""SELECT SUM(s.total_visitas) AS apurado
               FROM staging_visita_domiciliar s
               WHERE (s.ano || s.mes = ? OR s.ano || printf('%02d', CAST(s.mes AS INT)) = ?
                      OR (s.ano = ? AND (s.mes = ? OR s.mes = ?)))
                 AND s.cod_cnes IN ({marc_cnes})
                 AND s.nome_profissional = ?""",
            [p, p, ano, mes, mes_sem_zero, *cnes_list, profissional],
        ).fetchone()
        tot = row["apurado"] if row and row["apurado"] is not None else 0
        return [{"codigo": "0101030010", "nome": "Visita Domiciliar por Profissional de Nível Superior", "apurado": tot}]

    # 2. Atividades Coletivas eMulti (P12 / P22)
    if ind_cod in ("P12", "P22"):
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        p = str(periodo or "")
        sql = f"""SELECT COALESCE(s.cod_proced_sigtap, '0101010010') AS codigo,
                         COALESCE(s.procedimento_sigtap, 'Atividade Coletiva eMulti') AS nome,
                         COUNT(*) AS apurado
                  FROM staging_dtic_rel134 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional = ?
                  GROUP BY s.cod_proced_sigtap, s.procedimento_sigtap
                  ORDER BY apurado DESC"""
        return db.execute(sql, [p, f"%{p}%", *cnes_list, profissional]).fetchall()

    # 3. Atendimento Domiciliar eSUS (P30 / P33)
    if ind_cod in ("P30", "P33"):
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        p = str(periodo or "")
        equipe_filtro = "%EMAD%" if ind_cod == "P30" else "%EMAP%"
        sql = f"""SELECT COALESCE(s.cod_procedimento, '-') AS codigo,
                         COALESCE(s.procedimento, 'Atendimento Domiciliar') AS nome,
                         COUNT(*) AS apurado
                  FROM staging_dtic_rel130 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND s.nome_equipe LIKE ?
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional = ?
                  GROUP BY s.cod_procedimento, s.procedimento
                  ORDER BY apurado DESC"""
        return db.execute(sql, [p, f"%{p}%", equipe_filtro, *cnes_list, profissional]).fetchall()

    # 4. PICS (P09, P10, P19, P20)
    if ind_cod in ("P09", "P10", "P19", "P20"):
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        sql = f"""SELECT s.procedimento_codigo AS codigo, s.procedimento_nome AS nome, SUM(s.quantidade) AS apurado
                  FROM staging_bi_siga s
                  WHERE s.fonte_at = 'AT57' AND (s.ano_mes = ? OR s.ano_mes LIKE ?) AND s.cod_cnes IN ({marc_cnes})
                  GROUP BY s.procedimento_codigo, s.procedimento_nome
                  ORDER BY apurado DESC"""
        return db.execute(sql, [str(periodo or ""), f"%{periodo}%", *cnes_list]).fetchall()

    # 5. Grupos (P11, P21)
    if ind_cod in ("P11", "P21"):
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        sql = f"""SELECT '' AS codigo, s.procedimento_nome AS nome, SUM(s.quantidade) AS apurado
                  FROM staging_bi_siga s
                  WHERE s.fonte_at = 'AT61' AND (s.ano_mes = ? OR s.ano_mes LIKE ?) AND s.cod_cnes IN ({marc_cnes})
                  GROUP BY s.procedimento_nome
                  ORDER BY apurado DESC"""
        return db.execute(sql, [str(periodo or ""), f"%{periodo}%", *cnes_list]).fetchall()

    # 6. Outros SSRS (P25, P29, P36, P38, P41, P27)
    if ind_cod in ("P25", "P29", "P36", "P38", "P41", "P27"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        row = db.execute(
            f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
               WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'""",
            [indicador_id, *estabelecimento_ids, str(periodo or "")],
        ).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        return [{"codigo": ind_cod, "nome": ind_nome, "apurado": tot}]

    # 7. AT-02 padrão
    procedimentos = _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not procedimentos:
        return []

    cmes, cbos = _cmes_e_cbos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not cmes or cbos == []:
        return []

    proc_lista = [p["codigo"] for p in procedimentos]
    sql = f"""SELECT s.cod_procedimento AS codigo, p.nome, SUM(s.quantidade) AS apurado
              FROM staging_at02 s JOIN procedimentos p ON p.codigo = s.cod_procedimento
              WHERE s.ano_mes = ? AND s.cod_cmes IN ({",".join("?" * len(cmes))}) AND s.nome_profissional = ?
                AND s.cod_procedimento IN ({",".join("?" * len(proc_lista))})"""
    params = [periodo, *cmes, profissional, *proc_lista]
    if cbo_codigo:
        sql += " AND s.cod_cbo_sus = ?"
        params.append(cbo_codigo)
    elif cbo_profissional:
        sql += " AND s.cod_cbo_sus = ?"
        params.append(cbo_profissional)
    elif cbos:
        sql += f" AND s.cod_cbo_sus IN ({','.join('?' * len(cbos))})"
        params.extend(cbos)
    sql += " GROUP BY s.cod_procedimento, p.nome ORDER BY apurado DESC"
    return db.execute(sql, params).fetchall()



@bp.route("/linha_detalhe")
def linha_detalhe():
    """Nível 1 do drill-down inline: profissionais de uma linha específica
    do painel, para expansão via JS - ver painel.html."""
    db = get_db()
    profissionais = _profissionais_da_linha(
        db, request.args.get("indicador_id"), _ids_da_linha(request.args),
        request.args.get("cbo_codigo") or None, request.args.get("periodo"),
        _subgrupo_da_linha(request.args.get("subgrupo_id")),
    )
    return jsonify({"profissionais": [dict(p) for p in profissionais]})


@bp.route("/profissional_detalhe")
def profissional_detalhe():
    """Nível 2 do drill-down inline: procedimentos de um profissional
    específico dentro de uma linha do painel."""
    db = get_db()
    procedimentos = _procedimentos_do_profissional(
        db, request.args.get("indicador_id"), _ids_da_linha(request.args),
        request.args.get("cbo_codigo") or None, request.args.get("periodo"),
        request.args.get("profissional"),
        _subgrupo_da_linha(request.args.get("subgrupo_id")),
        request.args.get("cbo_profissional") or None,
    )
    itens = []
    for p in procedimentos:
        d = dict(p)
        cod = str(d.get("codigo") or "").strip()
        nome = str(d.get("nome") or "").upper()
        d["municipal"] = bool(
            cod.startswith(("0301019", "0101019", "0307019", "030905"))
            or "MAE PAULISTANA" in nome
            or "MUNICIPAL" in nome
            or "SALA DO IDOSO" in nome
        )
        itens.append(d)
    return jsonify({"procedimentos": itens})


@bp.route("/exportar_excel")
def exportar_excel():
    """
    Exporta todo o conteúdo atual do painel para .xlsx (a exportação não
    aplica o filtro por coluna da tela, que é só uma busca visual - exporta
    sempre tudo o que está cadastrado/apurado).
    formato=resumido: só a tabela do painel, uma linha por indicador x
        estabelecimento x CBO (igual ao que está na tela).
    formato=expandido: além da aba de resumo, inclui uma aba única com uma
        linha para cada combinação profissional x procedimento de cada
        linha do painel (o mesmo que aparece ao expandir os dois níveis na
        tela, só que para todas as linhas de uma vez).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    db = get_db()
    formato = request.args.get("formato", "resumido")

    resultados = _resultados_filtrados(db)

    wb = Workbook()
    resumo_ws = wb.active
    resumo_ws.title = "Resumo"
    cabecalho_resumo = [
        "Indicador", "Nome do indicador", "Subgrupo", "Tipo", "Complexidade", "Serviço",
        "Estabelecimento", "CBO", "Período", "Apurado", "Declarado", "Meta", "% Meta", "Status",
    ]
    resumo_ws.append(cabecalho_resumo)
    for cel in resumo_ws[1]:
        cel.font = Font(bold=True)

    for r in resultados:
        rotulo_status, _ = status_meta(r["percentual_meta"])
        resumo_ws.append([
            r["indicador_codigo"], r["indicador_nome"], r.get("subgrupo_nome") or "", r["indicador_tipo"],
            r["complexidade"], r["servico"], r["estabelecimento_nome"],
            (f"{r['cbo_codigo']} - {r['cbo_nome']}" if r["cbo_codigo"] else "Curinga / Geral"),
            r["periodo"], r["valor_apurado"], r["valor_declarado"],
            r["valor_meta"], r["percentual_meta"], rotulo_status,
        ])
    for col in resumo_ws.columns:
        largura = max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2
        resumo_ws.column_dimensions[col[0].column_letter].width = min(largura, 45)

    if formato == "expandido":
        detalhe_ws = wb.create_sheet("Detalhe - Profissional-Proced")
        detalhe_ws.append([
            "Indicador", "Subgrupo", "Estabelecimento", "CBO da linha", "Período",
            "Profissional", "CBO do profissional", "Procedimento", "Nome do procedimento", "Apurado",
        ])
        for cel in detalhe_ws[1]:
            cel.font = Font(bold=True)

        for r in resultados:
            rotulo_indicador = f"{r['indicador_codigo']} - {r['indicador_nome']}"
            rotulo_cbo = f"{r['cbo_codigo']} - {r['cbo_nome']}" if r["cbo_codigo"] else "Curinga / Geral"
            profissionais = _profissionais_da_linha(
                db, r["indicador_id"], r["estabelecimento_ids"], r["cbo_codigo"], r["periodo"],
                r.get("subgrupo_id"),
            )
            for prof in profissionais:
                procedimentos = _procedimentos_do_profissional(
                    db, r["indicador_id"], r["estabelecimento_ids"], r["cbo_codigo"],
                    r["periodo"], prof["nome_profissional"], r.get("subgrupo_id"), prof["cbo_codigo"],
                )
                rotulo_cbo_prof = (
                    f"{prof['cbo_codigo']} - {prof['cbo_nome']}" if prof["cbo_codigo"] and prof["cbo_nome"]
                    else (prof["cbo_codigo"] or "")
                )
                for p in procedimentos:
                    detalhe_ws.append([
                        rotulo_indicador, r.get("subgrupo_nome") or "", r["estabelecimento_nome"], rotulo_cbo,
                        r["periodo"], prof["nome_profissional"], rotulo_cbo_prof,
                        p["codigo"], p["nome"], p["apurado"],
                    ])

        for col in detalhe_ws.columns:
            largura = max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2
            detalhe_ws.column_dimensions[col[0].column_letter].width = min(largura, 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    from datetime import datetime
    nome_arquivo = f"painel_{formato}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )
