import io
import re
import unicodedata

from flask import Blueprint, Response, jsonify, render_template, request

from ..db import get_db
from ..funcoes import (
    consolidacao, diagnostico_metas, pendencias, obter_cbos_transferencia_rel134,
    obter_cbos_buscar_at02, MAPEAMENTO_EMULTI_PADRAO, _resolver_cbo, resolver_unidade_at57,
    obter_equipes_emulti_unidade,
    calcular_webssas, _normalizar_periodo, _periodo_para_webssas, _normalizar_nome_prof
)

bp = Blueprint("painel", __name__, url_prefix="/contratos")


def _chave_ordem_indicador(r):
    cod = str(r.get("indicador_codigo") or "").strip()
    m = re.search(r"\d+", cod)
    num = int(m.group(0)) if m else 9999
    return (
        num,
        cod,
        r.get("subgrupo_nome") or "",
        r.get("estabelecimento_nome") or "",
        r.get("cbo_codigo") or "",
        r.get("periodo") or "",
    )


def _resultados_filtrados(db):
    """Linhas do painel. Em modo de consolidação 'CNES' (Administração >
    Portaria/TA, ou seletor do próprio painel), os cadastros que compartilham
    o mesmo CNES viram uma linha só - ver app/etl/consolidacao.py. Em 'CMES'
    (padrão) a view é usada como está."""
    has_fatos = db.execute("SELECT 1 FROM fato_apuracao LIMIT 1").fetchone()
    if not has_fatos:
        has_staging = db.execute("SELECT 1 FROM staging_at02 LIMIT 1").fetchone()
        if has_staging:
            from ..funcoes import sincronizar_apuracao_dinamica
            sincronizar_apuracao_dinamica(db)

    linhas = [
        dict(r) for r in db.execute(
            "SELECT * FROM resultados_indicador"
        ).fetchall()
    ]
    linhas = consolidacao.consolidar_resultados(
        linhas, consolidacao.analisar(db), consolidacao.indicadores_cnes(db)
    )
    linhas = consolidacao.completar_metas_do_grupo(db, linhas)
    for linha in linhas:
        linha.setdefault("estabelecimento_ids", [linha["estabelecimento_id"]])
    linhas.sort(key=_chave_ordem_indicador)
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

    if isinstance(dif, float) and not dif.is_integer():
        dif_str = f"{dif:+.2f}"
    else:
        dif_str = f"{int(dif):+d}"

    if ap == 0 and dec == 0:
        return ("Sem produção", "badge-cinza", 0)
    if ap == dec:
        return ("Conforme (OK)", "badge-verde", 0)
    if dec > 0 and ap == 0:
        return (f"Não apurado ({dif_str})", "badge-vermelho", dif)
    if ap > 0 and dec == 0:
        return (f"Não declarado ({dif_str})", "badge-amarelo", dif)
    if dif > 0:
        return (f"Apurado maior ({dif_str})", "badge-amarelo", dif)
    return (f"Declarado maior ({dif_str})", "badge-vermelho", dif)


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
                        f"{int(round(r.get('divergencia') or 0)):+d}",
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
                   WHERE ip.indicador_id = ? AND ip.subgrupo_id = ?
                     AND ip.tipo_vinculo = 'inclusao'
                     AND ip.procedimento_codigo NOT IN (
                         SELECT procedimento_codigo FROM indicador_procedimento
                         WHERE indicador_id = ? AND tipo_vinculo = 'exclusao'
                           AND (subgrupo_id IS NULL OR subgrupo_id = ?)
                     )""",
                (indicador_id, subgrupo_id, indicador_id, subgrupo_id)
            ).fetchall()
            if not res:
                res = db.execute(
                    """SELECT p.codigo, p.nome FROM indicador_procedimento ip
                       JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
                       WHERE ip.indicador_id = ?
                         AND ip.tipo_vinculo = 'inclusao'
                         AND ip.procedimento_codigo NOT IN (
                             SELECT procedimento_codigo FROM indicador_procedimento
                             WHERE indicador_id = ? AND tipo_vinculo = 'exclusao'
                               AND (subgrupo_id IS NULL OR subgrupo_id = ?)
                         )""",
                    (indicador_id, indicador_id, subgrupo_id)
                ).fetchall()
        else:
            res = db.execute(
                """SELECT p.codigo, p.nome FROM indicador_procedimento ip
                   JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
                   WHERE ip.indicador_id = ? AND ip.subgrupo_id IS NULL
                     AND ip.tipo_vinculo = 'inclusao'
                     AND ip.procedimento_codigo NOT IN (
                         SELECT procedimento_codigo FROM indicador_procedimento
                         WHERE indicador_id = ? AND tipo_vinculo = 'exclusao'
                           AND subgrupo_id IS NULL
                     )""",
                (indicador_id, indicador_id)
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


def _obter_matcher_pmmb(db):
    pmmb_profs = db.execute("SELECT id, nome, estabelecimento_id FROM profissionais WHERE pmmb = 1 AND ativo = 1").fetchall()
    from ..funcoes import _normalizar_nome_prof
    pmmb_profs_norm = []
    for p in pmmb_profs:
        n = _normalizar_nome_prof(p["nome"])
        pmmb_profs_norm.append({"id": p["id"], "nome": p["nome"], "norm": n, "words": set(n.split()), "est_id": p["estabelecimento_id"]})

    def _eh_prof_pmmb(nome):
        if not nome:
            return False
        stg_n = _normalizar_nome_prof(nome)
        stg_w = set(stg_n.split())
        for p in pmmb_profs_norm:
            if p["norm"] == stg_n:
                return True
            inter = p["words"].intersection(stg_w)
            if (p["words"].issubset(stg_w) or stg_w.issubset(p["words"])) and len(inter) >= 3:
                return True
        return False

    return _eh_prof_pmmb, bool(pmmb_profs_norm)


def _obter_matcher_rt(db):
    rt_profs = db.execute("SELECT id, nome, estabelecimento_id FROM profissionais WHERE rt = 1 AND ativo = 1").fetchall()
    from ..funcoes import _normalizar_nome_prof
    rt_profs_norm = []
    for p in rt_profs:
        n = _normalizar_nome_prof(p["nome"])
        rt_profs_norm.append({"id": p["id"], "nome": p["nome"], "norm": n, "words": set(n.split()), "est_id": p["estabelecimento_id"]})

    def _eh_prof_rt(nome):
        if not nome:
            return False
        stg_n = _normalizar_nome_prof(nome)
        stg_w = set(stg_n.split())
        for p in rt_profs_norm:
            if p["norm"] == stg_n:
                return True
            inter = p["words"].intersection(stg_w)
            if (p["words"].issubset(stg_w) or stg_w.issubset(p["words"])) and len(inter) >= 3:
                return True
        return False

    return _eh_prof_rt, bool(rt_profs_norm)


def _ordenar_profissionais_alfabeticamente(lista):
    """Ordena uma lista de profissionais em ordem alfabética crescente (A-Z)
    desconsiderando acentos e maiúsculas/minúsculas."""
    if not lista:
        return []

    def _chave(p):
        nome = ""
        if isinstance(p, dict):
            nome = p.get("nome_profissional") or p.get("nome") or ""
        else:
            try:
                nome = p["nome_profissional"]
            except Exception:
                nome = ""
        nome_norm = unicodedata.normalize("NFKD", str(nome or "")).encode("ASCII", "ignore").decode("ASCII")
        return nome_norm.strip().upper()

    return sorted(lista, key=_chave)


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
        sql += " GROUP BY s.nome_profissional, s.cod_cbo ORDER BY s.nome_profissional ASC"
        return _ordenar_profissionais_alfabeticamente(db.execute(sql, params).fetchall())

    # 2. Atividades Coletivas eMulti (P12 / P22)
    if ind_cod in ("P12", "P22"):
        p = str(periodo or "")
        ano_ref = p[:4] if len(p) >= 4 else ""
        mes_ref = p[4:6] if len(p) >= 6 else ""
        mes_sem_zero = str(int(mes_ref)) if mes_ref.isdigit() else mes_ref

        # Verifica se o CBO desta linha deve utilizar redirecionamento para a Unidade Base
        cbos_transferem = obter_cbos_transferencia_rel134(db)
        cbo_alvo = str(cbo_codigo or "").strip()
        transfere_base = bool(cbo_alvo and (cbo_alvo in cbos_transferem or any(cbo_alvo.startswith(c) for c in cbos_transferem)))

        # Identificar CNESs da própria unidade de apuração
        cnes_base = set()
        if estabelecimento_ids:
            marc_base = ",".join("?" * len(estabelecimento_ids))
            rows_cb = db.execute(
                f"SELECT DISTINCT cod_cnes FROM estabelecimentos WHERE id IN ({marc_base}) AND cod_cnes IS NOT NULL",
                estabelecimento_ids,
            ).fetchall()
            cnes_base = {r["cod_cnes"].strip() for r in rows_cb if r["cod_cnes"]}

        # Obter estabelecimentos da linha e estabelecimentos que redirecionam para ela
        estabs_busca = []
        for eid in (estabelecimento_ids or []):
            dest_row = db.execute("SELECT destinacao_mista FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
            dest_m = (dest_row["destinacao_mista"] or "TRAD").upper() if dest_row else "TRAD"
            if ind_cod == "P12":
                tem_meta_p22 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 22 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                if tem_meta_p22 and dest_m == "TRAD":
                    continue
            elif ind_cod == "P22":
                tem_meta_p12 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 12 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                if tem_meta_p12 and dest_m == "ESF":
                    continue
            estabs_busca.append(eid)

        if estabelecimento_ids and transfere_base:
            marc_dest = ",".join("?" * len(estabelecimento_ids))
            rows_red = db.execute(
                f"SELECT unidade_origem_id FROM de_para_unidades_rel134 WHERE unidade_destino_id IN ({marc_dest})",
                estabelecimento_ids,
            ).fetchall()
            for r_red in rows_red:
                if r_red["unidade_origem_id"] not in estabs_busca:
                    estabs_busca.append(r_red["unidade_origem_id"])

        cnes_busca = []
        if estabs_busca:
            marc_est = ",".join("?" * len(estabs_busca))
            rows_c = db.execute(
                f"SELECT DISTINCT cod_cnes FROM estabelecimentos WHERE id IN ({marc_est}) AND cod_cnes IS NOT NULL",
                estabs_busca,
            ).fetchall()
            cnes_busca = [r["cod_cnes"].strip() for r in rows_c if r["cod_cnes"]]

        if not cnes_busca:
            return []

        marc_cnes = ",".join("?" * len(cnes_busca))
        sql = f"""SELECT s.nome_profissional, s.cbo_prof AS cbo_codigo, COALESCE(c.nome_categoria, s.cbo) AS cbo_nome,
                         COUNT(*) AS apurado,
                         GROUP_CONCAT(DISTINCT s.cnes) AS cnes_exec,
                         GROUP_CONCAT(DISTINCT s.nome_unidade) AS unidades_exec
                  FROM staging_dtic_rel134 s
                  LEFT JOIN cbo c ON c.codigo = s.cbo_prof
                  WHERE LOWER(COALESCE(s.supervisao, '')) LIKE '%penha%'
                    AND UPPER(TRIM(COALESCE(s.emulti, ''))) = 'SIM'
                    AND CAST(COALESCE(s.num_participantes, '0') AS INTEGER) > 1
                    AND LOWER(COALESCE(s.tipo_atividade, '')) NOT LIKE '%reuni%'
                    AND s.ano = ? AND (s.mes = ? OR s.mes = ?)
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional IS NOT NULL"""
        params = [ano_ref, mes_ref, mes_sem_zero, *cnes_busca]
        if cbo_codigo:
            if cbo_codigo.startswith("2234"):
                sql += " AND s.cbo_prof LIKE '2234%'"
            elif cbo_codigo.startswith("2516"):
                sql += " AND s.cbo_prof LIKE '2516%'"
            else:
                sql += " AND (s.cbo_prof = ? OR s.cbo_prof LIKE ?)"
                params.extend([cbo_codigo, f"{cbo_codigo}%"])
        sql += " GROUP BY s.nome_profissional ORDER BY s.nome_profissional ASC"
        rows = db.execute(sql, params).fetchall()
        resultado = []
        for r in rows:
            cnes_exec_list = [c.strip() for c in (r["cnes_exec"] or "").split(",") if c.strip()]
            unidades_exec = (r["unidades_exec"] or "").strip()
            apenas_base = bool(cnes_exec_list and all(c in cnes_base for c in cnes_exec_list))
            apenas_outros = bool(cnes_exec_list and all(c not in cnes_base for c in cnes_exec_list))

            if apenas_base:
                origem_rotulo = "Própria Unidade Base"
                is_transferido = False
            elif apenas_outros:
                origem_rotulo = f"Transferido de: {unidades_exec}"
                is_transferido = True
            else:
                origem_rotulo = f"Base + Transferido ({unidades_exec})"
                is_transferido = True

            resultado.append({
                "nome_profissional": r["nome_profissional"],
                "cbo_codigo": r["cbo_codigo"],
                "cbo_nome": r["cbo_nome"],
                "apurado": r["apurado"],
                "origem_rotulo": origem_rotulo,
                "is_transferido": is_transferido,
            })
        return _ordenar_profissionais_alfabeticamente(resultado)

    # 3. Atendimento Domiciliar eSUS (P30 / P33)
    if ind_cod in ("P30", "P33"):
        if not cnes_list:
            return []
        marc_cnes = ",".join("?" * len(cnes_list))
        p = str(periodo or "")
        ano_ref = p[:4] if len(p) >= 4 else ""
        mes_ref = p[4:6] if len(p) >= 6 else ""
        equipe_filtro = "%EMAD%" if ind_cod == "P30" else "%EMAP%"
        params = [p, f"%{p}%", equipe_filtro, *cnes_list]
        sql = f"""SELECT s.nome_profissional, s.cod_cbo AS cbo_codigo, s.cbo AS cbo_nome,
                         COUNT(DISTINCT s.codigo_atendimento) AS apurado
                  FROM staging_dtic_rel130 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND (s.supervisao LIKE '%PENHA%' OR s.supervisao LIKE '%penha%')
                    AND s.nome_equipe LIKE ?
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional IS NOT NULL"""
        if ano_ref and mes_ref:
            sql += " AND substr(s.data_cadastro, 7, 4) = ? AND substr(s.data_cadastro, 4, 2) = ?"
            params.extend([ano_ref, mes_ref])
        if cbo_codigo:
            sql += " AND (s.cod_cbo = ? OR s.cod_cbo LIKE ?)"
            params.extend([cbo_codigo, f"%{cbo_codigo}%"])
        sql += " GROUP BY s.nome_profissional, s.cod_cbo ORDER BY s.nome_profissional ASC"
        return _ordenar_profissionais_alfabeticamente(db.execute(sql, params).fetchall())

    # 4. PICS (P09, P10, P19, P20) - SSRS / AT-57
    if ind_cod in ("P09", "P10", "P19", "P20"):
        estabs_set = set(estabelecimento_ids) if estabelecimento_ids else set()
        grupo_alvo = "PROCEDIMENTOS COLETIVOS" if ind_cod in ("P10", "P20") else "PROCEDIMENTOS INDIVIDUAIS"

        linhas_at57 = db.execute(
            """SELECT cod_cnes, nome_estabelecimento, grupo, sum(quantidade) as total
               FROM staging_bi_siga
               WHERE fonte_at = 'AT57' AND (ano_mes = ? OR ano_mes LIKE ?)
               GROUP BY cod_cnes, nome_estabelecimento, grupo""",
            (str(periodo or ""), f"%{str(periodo or '')}%"),
        ).fetchall()

        termos_nao_ubs = ("caps", "cecco", "cer", "cnr", "hospital dia", "teleassistencia")
        equipes_pics = {}
        for r in linhas_at57:
            if (r["grupo"] or "").upper() != grupo_alvo:
                continue
            qty = int(r["total"] or 0)
            if qty <= 0:
                continue
            nome_est = (r["nome_estabelecimento"] or "").strip()
            if any(t in nome_est.lower() for t in termos_nao_ubs):
                continue

            # Checar vínculo manual explícito ou resolver por regra do último nome / CNES
            estab_id = None
            v_row = db.execute(
                """SELECT uo.estabelecimento_id FROM indicador_unidade_origem uo
                   WHERE uo.indicador_id = ? AND lower(trim(uo.nome_origem)) = lower(trim(?))""",
                (indicador_id, nome_est),
            ).fetchone()
            if v_row:
                estab_id = v_row["estabelecimento_id"]
            if not estab_id:
                estab_id, _ = resolver_unidade_at57(db, nome_est, r["cod_cnes"])

            if not estab_id or (estabs_set and estab_id not in estabs_set):
                continue

            # CNES da sede da equipe volante
            cnes_sede = str(r["cod_cnes"] or "").strip().lstrip("0")
            estab_dest = db.execute("SELECT id, nome, cod_cnes FROM estabelecimentos WHERE id = ?", (estab_id,)).fetchone()
            cnes_dest = str(estab_dest["cod_cnes"] or "").strip().lstrip("0") if estab_dest else ""

            if cnes_sede and cnes_dest and cnes_sede != cnes_dest:
                estab_sede = db.execute("SELECT nome FROM estabelecimentos WHERE ltrim(cod_cnes, '0') = ? LIMIT 1", (cnes_sede,)).fetchone()
                nome_sede = estab_sede["nome"] if estab_sede else "Sede Administrativa"
                origem_rotulo = f"Transferido de: {nome_sede}"
                is_transferido = True
            else:
                origem_rotulo = "Própria Unidade Base"
                is_transferido = False

            chave = (nome_est, origem_rotulo, is_transferido)
            equipes_pics[chave] = equipes_pics.get(chave, 0) + qty

        if equipes_pics:
            desc = "PICS Coletivas" if ind_cod in ("P10", "P20") else "PICS Individuais"
            return _ordenar_profissionais_alfabeticamente([
                {
                    "nome_profissional": k[0],
                    "cbo_codigo": cbo_codigo,
                    "cbo_nome": desc,
                    "apurado": v,
                    "origem_rotulo": k[1],
                    "is_transferido": k[2],
                }
                for k, v in equipes_pics.items()
            ])

        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        row = db.execute(
            f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
                WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'""",
            [indicador_id, *estabelecimento_ids, str(periodo or "")],
        ).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        desc = "Práticas Integrativas (PICS Individuais)" if ind_cod in ("P09", "P19") else "Práticas Integrativas (PICS Coletivas)"
        return [{"nome_profissional": f"Consolidado SIGA ({desc})", "cbo_codigo": cbo_codigo, "cbo_nome": desc, "apurado": tot, "origem_rotulo": "Consolidado SIGA", "is_transferido": False}]

    if ind_cod in ("P11", "P21"):
        cbos_at02_config = obter_cbos_buscar_at02(db)

        # Se for CBO configurado para busca no AT-02, busca os profissionais reais que atenderam no AT-02
        if str(cbo_codigo) in cbos_at02_config:
            cbo_nome_real = None
            if cbo_codigo:
                c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
                if c_row and c_row["nome_categoria"]:
                    cbo_nome_real = c_row["nome_categoria"]

            procs_ind = set([r[0] for r in db.execute("SELECT procedimento_codigo FROM indicador_procedimento WHERE indicador_id = ?", (indicador_id,)).fetchall()])
            procs_ind.add("0301010030")
            marc_procs = ",".join("?" * len(procs_ind))

            # Monta filtro de estabelecimentos considerando CNES próprio e eMulti de referência
            clausula_unidades = []
            params_estabs = []
            for eid in (estabelecimento_ids or []):
                dest_row = db.execute("SELECT destinacao_mista FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
                dest_m = (dest_row["destinacao_mista"] or "TRAD").upper() if dest_row else "TRAD"
                if ind_cod == "P11":
                    tem_meta_p21 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 21 AND cbo_codigo = ?", (eid, cbo_codigo)).fetchone()
                    if tem_meta_p21 and dest_m == "TRAD":
                        continue
                elif ind_cod == "P21":
                    tem_meta_p11 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 11 AND cbo_codigo = ?", (eid, cbo_codigo)).fetchone()
                    if tem_meta_p11 and dest_m == "ESF":
                        continue

                e_row = db.execute("SELECT cod_cnes FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
                cnes_l = str(e_row["cod_cnes"] or "").strip().lstrip("0") if e_row else ""
                cnes_lista = [cnes_l] if cnes_l else []
                for r_alt in db.execute(
                    "SELECT cnes_alternativo FROM indicador_estabelecimento_cnes_alternativo WHERE indicador_id = ? AND estabelecimento_id = ?",
                    (indicador_id, eid)
                ).fetchall():
                    ca = str(r_alt["cnes_alternativo"] or "").strip().lstrip("0")
                    if ca and ca not in cnes_lista:
                        cnes_lista.append(ca)

                if cnes_lista:
                    m_cnes = ",".join("?" * len(cnes_lista))
                    clausula_unidades.append(f"(ltrim(s.cod_cnes, '0') IN ({m_cnes}) AND lower(s.nome_estabelecimento) NOT LIKE '%emab%' AND lower(s.nome_estabelecimento) NOT LIKE '%emulti%')")
                    params_estabs.extend(cnes_lista)

                eqs = obter_equipes_emulti_unidade(db, eid, indicador_id=indicador_id)
                if eqs:
                    m_eq = ",".join("?" * len(eqs))
                    clausula_unidades.append(f"s.nome_estabelecimento IN ({m_eq})")
                    params_estabs.extend(eqs)

            filtro_unidades = " OR ".join(clausula_unidades) if clausula_unidades else "1=0"

            sql_profs = f"""
                SELECT s.nome_profissional, s.nome_estabelecimento, sum(s.quantidade) as total
                FROM staging_at02 s
                WHERE s.ano_mes = ? AND s.cod_cbo_sus = ?
                  AND s.cod_procedimento IN ({marc_procs})
                  AND lower(s.nome_estabelecimento) NOT LIKE '%caps%'
                  AND lower(s.nome_estabelecimento) NOT LIKE '%cnr%'
                  AND lower(s.nome_estabelecimento) NOT LIKE '%cecco%'
                  AND ({filtro_unidades})
                GROUP BY s.nome_profissional, s.nome_estabelecimento
                ORDER BY total DESC
            """
            params_query = [str(periodo or ""), str(cbo_codigo), *procs_ind, *params_estabs]
            profs_at02 = db.execute(sql_profs, params_query).fetchall()

            if profs_at02:
                resultado = []
                for r in profs_at02:
                    nome_est = (r["nome_estabelecimento"] or "").strip()
                    is_emulti = "emab" in nome_est.lower() or "emulti" in nome_est.lower()
                    rotulo = f"eMulti: {nome_est}" if is_emulti else f"UBS: {nome_est}"
                    resultado.append({
                        "nome_profissional": r["nome_profissional"],
                        "cbo_codigo": cbo_codigo,
                        "cbo_nome": cbo_nome_real or "Profissional",
                        "apurado": int(r["total"] or 0),
                        "origem_rotulo": rotulo,
                        "nome_estabelecimento": nome_est,
                        "is_transferido": False,
                    })
                return _ordenar_profissionais_alfabeticamente(resultado)
            return []

        # Obter nome oficial do CBO
        cbo_nome_real = None
        if cbo_codigo:
            c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
            if c_row and c_row["nome_categoria"]:
                cbo_nome_real = c_row["nome_categoria"]
        if not cbo_nome_real:
            cbo_nome_real = "Atividades Individuais eMulti"

        # Se não for CBO do AT-02, busca as equipes do AT-61
        cbos_transferem = obter_cbos_transferencia_rel134(db)
        estabs_set = set(estabelecimento_ids) if estabelecimento_ids else set()

        linhas_stg = db.execute(
            """SELECT cod_cnes, nome_estabelecimento, cbo_nome, sum(quantidade) as total
               FROM staging_bi_siga
               WHERE fonte_at = 'AT61' AND (ano_mes = ? OR ano_mes LIKE ?)
               GROUP BY cod_cnes, nome_estabelecimento, cbo_nome""",
            (str(periodo or ""), f"%{periodo}%"),
        ).fetchall()

        termos_nao_ubs = ("caps", "cecco", "cer", "cnr", "hospital dia", "teleassistencia")
        equipes_apuradas = {}
        for r in linhas_stg:
            c_cod = _resolver_cbo(db, None, r["cbo_nome"])
            if cbo_codigo and str(c_cod) != str(cbo_codigo):
                continue

            qty = int(r["total"] or 0)
            if qty <= 0:
                continue

            nome_origem = (r["nome_estabelecimento"] or "").strip()
            if any(t in nome_origem.lower() for t in termos_nao_ubs):
                continue

            deve_transferir = bool(
                c_cod and (c_cod in cbos_transferem or any(str(c_cod).startswith(c) for c in cbos_transferem))
            )

            # Unidade Base pelo CNES
            cnes_clean = str(r["cod_cnes"] or "").strip().lstrip("0")
            estab_base = db.execute(
                """SELECT id, nome FROM estabelecimentos
                   WHERE ltrim(cod_cnes, '0') = ? AND (upper(nome) LIKE 'UBS%' OR upper(nome) LIKE 'AMA/UBS%')
                   ORDER BY id LIMIT 1""",
                (cnes_clean,),
            ).fetchone()
            unidade_base_id = estab_base["id"] if estab_base else None

            # Unidade de Realização
            unidade_realizou_id = None
            if "/" in nome_origem:
                partes = nome_origem.split("/")
                ultimo = partes[-1].strip().lower()
                for pref in ["inativo - emab ", "inativo -  emab ", "inativo - emulti ", "emulti ", "emab "]:
                    if ultimo.startswith(pref):
                        ultimo = ultimo[len(pref):].strip()
                        break
                for termo, eid in MAPEAMENTO_EMULTI_PADRAO:
                    if termo in ultimo:
                        unidade_realizou_id = eid
                        break
            if not unidade_realizou_id:
                unidade_realizou_id = unidade_base_id

            # Unidade final
            estab_final = unidade_base_id if deve_transferir and unidade_base_id else (unidade_realizou_id or unidade_base_id)
            if not estab_final or (estabs_set and estab_final not in estabs_set):
                continue

            # Rótulo de Origem
            if deve_transferir and unidade_realizou_id and unidade_base_id and unidade_realizou_id != unidade_base_id:
                estab_part = db.execute("SELECT nome FROM estabelecimentos WHERE id = ?", (unidade_realizou_id,)).fetchone()
                nome_part = estab_part["nome"] if estab_part else "Unidade Parceira"
                origem_rotulo = f"Transferido de: {nome_part}"
                is_transferido = True
            elif not deve_transferir and unidade_realizou_id and unidade_base_id and unidade_realizou_id != unidade_base_id:
                origem_rotulo = f"Origem Local: {nome_origem}"
                is_transferido = False
            else:
                origem_rotulo = f"eMulti de Referência: {nome_origem}"
                is_transferido = False

            chave_eq = (nome_origem, origem_rotulo, is_transferido)
            equipes_apuradas[chave_eq] = equipes_apuradas.get(chave_eq, 0) + qty

        if equipes_apuradas:
            return _ordenar_profissionais_alfabeticamente([
                {
                    "nome_profissional": k[0],
                    "cbo_codigo": cbo_codigo,
                    "cbo_nome": cbo_nome_real,
                    "apurado": v,
                    "origem_rotulo": k[1],
                    "is_transferido": k[2],
                }
                for k, v in equipes_apuradas.items()
            ])

        # Obter apurado específico deste CBO na linha via fato_apuracao
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        params_fato = [indicador_id, *estabelecimento_ids, str(periodo or "")]
        sql_fato = f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
                       WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'"""
        if cbo_codigo:
            sql_fato += " AND cbo_codigo = ?"
            params_fato.append(cbo_codigo)
        row = db.execute(sql_fato, params_fato).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0

        return [{"nome_profissional": "Consolidado SIGA (eMulti)", "cbo_codigo": cbo_codigo, "cbo_nome": cbo_nome_real, "apurado": tot, "origem_rotulo": "Consolidado SIGA", "is_transferido": False}]

    # 5. Hospital Dia (P45, P46, P47 - REL 164)
    if ind_cod in ("P45", "P46", "P47"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        row = db.execute(
            f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
                WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'""",
            [indicador_id, *estabelecimento_ids, str(periodo or "")],
        ).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        return [{
            "nome_profissional": "Consolidado Hospital Dia (REL 164)",
            "cbo_codigo": cbo_codigo,
            "cbo_nome": "Cirurgias Hospital Dia",
            "apurado": tot,
        }]

    # 6. Outros consolidados (P25 [PAI], P29 [CAPS], P36 [CER], P37 [CER Proced/Usu], P38 [CER CBO], P41 [APD], P27 [URSI], P31 [SISAD EMAD Ativos], P32 [SISAD Desospitalizacao], P34 [SISAD EMAP Ativos])
    if ind_cod in ("P25", "P29", "P36", "P37", "P38", "P41", "P27", "P31", "P32", "P34"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        params_fato = [indicador_id, *estabelecimento_ids, str(periodo or "")]
        sql_fato = f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
                       WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'"""
        if cbo_codigo:
            sql_fato += " AND cbo_codigo = ?"
            params_fato.append(cbo_codigo)

        row = db.execute(sql_fato, params_fato).fetchone()
        tot = row["tot"] if row and row["tot"] is not None else 0
        if isinstance(tot, float) and tot.is_integer():
            tot = int(tot)
        elif isinstance(tot, float):
            tot = round(tot, 2)
        elif tot is not None:
            tot = int(tot)

        nome_prof_desc = ind_nome
        if cbo_codigo:
            c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
            if c_row and c_row["nome_categoria"]:
                nome_prof_desc = f"{ind_nome} - {c_row['nome_categoria']}"

        rotulo_origem = "SISAD" if ind_cod in ("P31", "P32", "P34") else "SIGA"
        return [{"nome_profissional": f"Consolidado {rotulo_origem} ({nome_prof_desc})", "cbo_codigo": cbo_codigo, "cbo_nome": nome_prof_desc, "apurado": tot}]

    # 6. AT-02 padrão
    procedimentos = _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not procedimentos:
        return []

    eh_linha_pmmb = bool(cbo_codigo and str(cbo_codigo).endswith("_PMMB"))
    base_cbo = str(cbo_codigo).replace("_PMMB", "") if cbo_codigo else None
    _eh_prof_pmmb, tem_pmmb_cadastrado = _obter_matcher_pmmb(db)

    eh_linha_rt = bool(cbo_codigo and str(cbo_codigo).endswith("_RT"))
    if eh_linha_rt:
        base_cbo = str(cbo_codigo).replace("_RT", "")
    _eh_prof_rt, tem_rt_cadastrado = _obter_matcher_rt(db)

    cmes, cbos = _cmes_e_cbos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not cmes or cbos == []:
        return []

    regras_prof = {}
    for rp in db.execute(
        """SELECT procedimento_codigo, nome_profissional
           FROM indicador_procedimento
           WHERE indicador_id = ? AND (subgrupo_id IS ? OR subgrupo_id IS NULL)
             AND tipo_vinculo = 'inclusao' AND nome_profissional IS NOT NULL AND TRIM(nome_profissional) != ''""",
        (indicador_id, subgrupo_id),
    ).fetchall():
        regras_prof[rp["procedimento_codigo"]] = _normalizar_nome_prof(rp["nome_profissional"])

    proc_lista = [p["codigo"] for p in procedimentos]
    sql = f"""SELECT s.nome_profissional, s.cod_cbo_sus AS cbo_codigo, c.nome_categoria AS cbo_nome,
                     s.cod_procedimento, SUM(s.quantidade) AS apurado
              FROM staging_at02 s LEFT JOIN cbo c ON c.codigo = s.cod_cbo_sus
              WHERE s.ano_mes = ? AND s.cod_cmes IN ({",".join("?" * len(cmes))})
                AND s.cod_procedimento IN ({",".join("?" * len(proc_lista))})
                AND s.nome_profissional IS NOT NULL"""
    params = [periodo, *cmes, *proc_lista]
    if eh_linha_pmmb:
        sql += " AND s.cod_cbo_sus IN (?, '225142', '225170')"
        params.append(base_cbo)
    elif eh_linha_rt:
        sql += " AND s.cod_cbo_sus IN (?, '223293', '223208', '223240')"
        params.append(base_cbo)
    elif cbo_codigo:
        sql += " AND s.cod_cbo_sus = ?"
        params.append(cbo_codigo)
    elif cbos:
        sql += f" AND s.cod_cbo_sus IN ({','.join('?' * len(cbos))})"
        params.extend(cbos)
    if str(indicador_id) == "43" and (cbo_codigo in ("225112", "225127") or (cbos and any(c in ("225112", "225127") for c in cbos))):
        if subgrupo_id is not None:
            sql += " AND s.cod_cmes != s.cod_cnes"
        else:
            sql += " AND (s.cod_cmes = s.cod_cnes OR s.cod_cmes IS NULL OR s.cod_cnes IS NULL)"
    if str(indicador_id) == "35" and subgrupo_id is not None:
        sg_row = db.execute("SELECT nome FROM indicador_subgrupo WHERE id = ?", (subgrupo_id,)).fetchone()
        if sg_row:
            sg_n = (sg_row["nome"] or "").lower()
            if "auditiva" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%auditiva%'"
            elif "fisica" in sg_n or "fsica" in sg_n:
                sql += " AND (lower(s.nome_especialidade2) LIKE '%fisica%' OR lower(s.nome_especialidade2) LIKE '%fsica%')"
            elif "intelectual" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%intelectual%'"
            elif "visual" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%visual%'"
    sql += " GROUP BY s.nome_profissional, s.cod_cbo_sus, s.cod_procedimento ORDER BY s.nome_profissional ASC"
    rows = db.execute(sql, params).fetchall()

    prof_agrupado = {}
    for r in rows:
        d = dict(r)
        proc_r = d.get("cod_procedimento")
        if proc_r in regras_prof:
            if _normalizar_nome_prof(d["nome_profissional"]) != regras_prof[proc_r]:
                continue
        chave_p = (d["nome_profissional"], d["cbo_codigo"], d["cbo_nome"])
        prof_agrupado[chave_p] = prof_agrupado.get(chave_p, 0) + int(d["apurado"] or 0)

    resultado = []
    for (nome_p, cbo_c, cbo_n), apurado_tot in prof_agrupado.items():
        d = {
            "nome_profissional": nome_p,
            "cbo_codigo": cbo_c,
            "cbo_nome": cbo_n,
            "apurado": apurado_tot,
        }
        is_pmmb = _eh_prof_pmmb(d["nome_profissional"])
        is_rt = _eh_prof_rt(d["nome_profissional"])
        if eh_linha_pmmb:
            if not is_pmmb:
                continue
            d["cbo_codigo"] = cbo_codigo
            d["cbo_nome"] = "Médico Generalista PMMB"
            resultado.append(d)
        elif eh_linha_rt:
            if not is_rt:
                continue
            d["cbo_codigo"] = cbo_codigo
            c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
            d["cbo_nome"] = c_row["nome_categoria"] if c_row and c_row["nome_categoria"] else f"{base_cbo} RT"
            resultado.append(d)
        else:
            if tem_pmmb_cadastrado and is_pmmb and (str(indicador_id) in ("1", "2", "13") or base_cbo in ("225142", "225170")):
                continue
            if tem_rt_cadastrado and is_rt and (str(indicador_id) in ("7", "8", "17", "18", "42") or base_cbo in ("223293", "223208", "223240")):
                continue
            resultado.append(d)
    return _ordenar_profissionais_alfabeticamente(resultado)


def _procedimentos_do_profissional(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, profissional,
                                   subgrupo_id=None, cbo_profissional=None, estabelecimento_origem=None):
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
        return [{"codigo": "0101030029", "nome": "Visita Domiciliar Periódica (ACS)", "apurado": tot, "considerado": True}]

    # 2. Atividades Coletivas eMulti (P12 / P22)
    if ind_cod in ("P12", "P22"):
        p = str(periodo or "")
        ano_ref = p[:4] if len(p) >= 4 else ""
        mes_ref = p[4:6] if len(p) >= 6 else ""
        mes_sem_zero = str(int(mes_ref)) if mes_ref.isdigit() else mes_ref

        cbo_alvo = str(cbo_codigo or cbo_profissional or "").strip()
        cbos_transferem = obter_cbos_transferencia_rel134(db)
        transfere_base = bool(cbo_alvo and (cbo_alvo in cbos_transferem or any(cbo_alvo.startswith(c) for c in cbos_transferem)))

        estabs_busca = []
        for eid in (estabelecimento_ids or []):
            dest_row = db.execute("SELECT destinacao_mista FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
            dest_m = (dest_row["destinacao_mista"] or "TRAD").upper() if dest_row else "TRAD"
            if ind_cod == "P12":
                tem_meta_p22 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 22 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                if tem_meta_p22 and dest_m == "TRAD":
                    continue
            elif ind_cod == "P22":
                tem_meta_p12 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 12 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                if tem_meta_p12 and dest_m == "ESF":
                    continue
            estabs_busca.append(eid)

        if estabelecimento_ids and transfere_base:
            marc_dest = ",".join("?" * len(estabelecimento_ids))
            rows_red = db.execute(
                f"SELECT unidade_origem_id FROM de_para_unidades_rel134 WHERE unidade_destino_id IN ({marc_dest})",
                estabelecimento_ids,
            ).fetchall()
            for r_red in rows_red:
                if r_red["unidade_origem_id"] not in estabs_busca:
                    estabs_busca.append(r_red["unidade_origem_id"])

        cnes_busca = []
        if estabs_busca:
            marc_est = ",".join("?" * len(estabs_busca))
            rows_c = db.execute(
                f"SELECT DISTINCT cod_cnes FROM estabelecimentos WHERE id IN ({marc_est}) AND cod_cnes IS NOT NULL",
                estabs_busca,
            ).fetchall()
            cnes_busca = [r["cod_cnes"].strip() for r in rows_c if r["cod_cnes"]]

        if not cnes_busca:
            return []

        # Identificar CNESs da própria base
        cnes_base = set()
        if estabelecimento_ids:
            marc_base = ",".join("?" * len(estabelecimento_ids))
            rows_cb = db.execute(
                f"SELECT DISTINCT cod_cnes FROM estabelecimentos WHERE id IN ({marc_base}) AND cod_cnes IS NOT NULL",
                estabelecimento_ids,
            ).fetchall()
            cnes_base = {r["cod_cnes"].strip() for r in rows_cb if r["cod_cnes"]}

        marc_cnes = ",".join("?" * len(cnes_busca))
        sql = f"""SELECT s.nome_unidade, s.cnes,
                         COALESCE(s.tipo_atividade, 'Atividade Coletiva') AS tipo_atividade,
                         COUNT(*) AS apurado,
                         SUM(CAST(COALESCE(s.num_participantes, '0') AS INTEGER)) AS num_participantes
                  FROM staging_dtic_rel134 s
                  WHERE LOWER(COALESCE(s.supervisao, '')) LIKE '%penha%'
                    AND UPPER(TRIM(COALESCE(s.emulti, ''))) = 'SIM'
                    AND CAST(COALESCE(s.num_participantes, '0') AS INTEGER) > 1
                    AND LOWER(COALESCE(s.tipo_atividade, '')) NOT LIKE '%reuni%'
                    AND s.ano = ? AND (s.mes = ? OR s.mes = ?)
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional = ?"""
        params = [ano_ref, mes_ref, mes_sem_zero, *cnes_busca, profissional]
        cbo_alvo = cbo_codigo or cbo_profissional
        if cbo_alvo:
            if str(cbo_alvo).startswith("2234"):
                sql += " AND s.cbo_prof LIKE '2234%'"
            elif str(cbo_alvo).startswith("2516"):
                sql += " AND s.cbo_prof LIKE '2516%'"
            else:
                sql += " AND (s.cbo_prof = ? OR s.cbo_prof LIKE ?)"
                params.extend([cbo_alvo, f"{cbo_alvo}%"])
        sql += " GROUP BY s.nome_unidade, s.cnes, s.tipo_atividade ORDER BY apurado DESC, s.nome_unidade"
        rows = db.execute(sql, params).fetchall()
        return [
            {
                "nome_unidade": r["nome_unidade"],
                "tipo_atividade": r["tipo_atividade"],
                "num_participantes": r["num_participantes"],
                "apurado": r["apurado"],
                "is_atividade_rel134": True,
                "is_transferido": bool(r["cnes"] and r["cnes"].strip() not in cnes_base),
                "considerado": True,
            }
            for r in rows
        ]

    # 3. Atendimento Domiciliar eSUS (P30 / P33)
    if ind_cod in ("P30", "P33"):
        marc_cnes = ",".join("?" * len(cnes_list)) if cnes_list else "''"
        p = str(periodo or "")
        ano_ref = p[:4] if len(p) >= 4 else ""
        mes_ref = p[4:6] if len(p) >= 6 else ""
        equipe_filtro = "%EMAD%" if ind_cod == "P30" else "%EMAP%"
        params = [p, f"%{p}%", equipe_filtro, *cnes_list, profissional]
        sql = f"""SELECT COALESCE(NULLIF(s.cod_procedimento, ''), '-') AS codigo,
                         COALESCE(NULLIF(s.procedimento, ''), 'Atendimento Domiciliar') AS nome,
                         COUNT(DISTINCT s.codigo_atendimento) AS apurado
                  FROM staging_dtic_rel130 s
                  WHERE (s.periodo_referencia = ? OR s.periodo_referencia LIKE ?)
                    AND (s.supervisao LIKE '%PENHA%' OR s.supervisao LIKE '%penha%')
                    AND s.nome_equipe LIKE ?
                    AND s.cnes IN ({marc_cnes})
                    AND s.nome_profissional = ?"""
        if ano_ref and mes_ref:
            sql += " AND substr(s.data_cadastro, 7, 4) = ? AND substr(s.data_cadastro, 4, 2) = ?"
            params.extend([ano_ref, mes_ref])
        cbo_alvo = cbo_codigo or cbo_profissional
        if cbo_alvo:
            sql += " AND (s.cod_cbo = ? OR s.cod_cbo LIKE ?)"
            params.extend([cbo_alvo, f"%{cbo_alvo}%"])
        sql += """ GROUP BY s.cod_procedimento, s.procedimento
                   ORDER BY apurado DESC"""
        rows = db.execute(sql, params).fetchall()
        return [{**dict(r), "considerado": True} for r in rows]

    # 4. PICS (P09, P10, P19, P20)
    if ind_cod in ("P09", "P10", "P19", "P20"):
        grupo_alvo = "PROCEDIMENTOS COLETIVOS" if ind_cod in ("P10", "P20") else "PROCEDIMENTOS INDIVIDUAIS"
        if profissional and not profissional.startswith("Consolidado SIGA"):
            rows_stg = db.execute(
                """SELECT COALESCE(NULLIF(procedimento_codigo, ''), '-') AS codigo,
                          COALESCE(NULLIF(procedimento_nome, ''), 'Procedimento PICS') AS nome,
                          SUM(quantidade) AS apurado
                   FROM staging_bi_siga
                   WHERE fonte_at = 'AT57' AND (ano_mes = ? OR ano_mes LIKE ?)
                     AND UPPER(grupo) = ?
                     AND nome_estabelecimento = ?
                   GROUP BY procedimento_codigo, procedimento_nome
                   ORDER BY apurado DESC""",
                (str(periodo or ""), f"%{str(periodo or '')}%", grupo_alvo, profissional),
            ).fetchall()
            if rows_stg:
                return [{**dict(r), "considerado": True} for r in rows_stg]

        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        sql = f"""SELECT f.procedimento_codigo AS codigo,
                         COALESCE(p.nome, 'Procedimento ' || f.procedimento_codigo) AS nome,
                         SUM(f.quantidade) AS apurado
                  FROM fato_apuracao f
                  LEFT JOIN procedimentos p ON p.codigo = f.procedimento_codigo
                  WHERE f.indicador_id = ? AND f.estabelecimento_id IN ({marc_estabs}) AND f.periodo = ?
                    AND f.tipo_registro = 'apurado' AND f.quantidade > 0
                  GROUP BY f.procedimento_codigo, p.nome
                  ORDER BY apurado DESC"""
        rows = db.execute(sql, [indicador_id, *estabelecimento_ids, str(periodo or "")]).fetchall()
        return [{**dict(r), "considerado": True} for r in rows]

    # 5. Atividades Individuais eMulti (P11, P21 - AT-61 / AT-02)
    if ind_cod in ("P11", "P21"):
        cbo_alvo = cbo_codigo or cbo_profissional
        cbos_at02_config = obter_cbos_buscar_at02(db)

        # Se for CBO configurado para busca no AT-02, detalha procedimentos a partir do AT-02
        if str(cbo_alvo) in cbos_at02_config:
            procs_ind = set([r[0] for r in db.execute("SELECT procedimento_codigo FROM indicador_procedimento WHERE indicador_id = ?", (indicador_id,)).fetchall()])
            procs_ind.add("0301010030")

            # Monta filtro de unidades/equipes
            params_estabs = []
            if estabelecimento_origem:
                filtro_estabs = "s.nome_estabelecimento = ?"
                params_estabs.append(estabelecimento_origem)
            else:
                clausula_unidades = []
                for eid in (estabelecimento_ids or []):
                    dest_row = db.execute("SELECT destinacao_mista FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
                    dest_m = (dest_row["destinacao_mista"] or "TRAD").upper() if dest_row else "TRAD"
                    if ind_cod == "P11":
                        tem_meta_p21 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 21 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                        if tem_meta_p21 and dest_m == "TRAD":
                            continue
                    elif ind_cod == "P21":
                        tem_meta_p11 = db.execute("SELECT 1 FROM metas WHERE estabelecimento_id = ? AND indicador_id = 11 AND cbo_codigo = ?", (eid, cbo_alvo)).fetchone()
                        if tem_meta_p11 and dest_m == "ESF":
                            continue

                    e_row = db.execute("SELECT cod_cnes FROM estabelecimentos WHERE id = ?", (eid,)).fetchone()
                    cnes_l = str(e_row["cod_cnes"] or "").strip().lstrip("0") if e_row else ""
                    cnes_lista = [cnes_l] if cnes_l else []
                    for r_alt in db.execute(
                        "SELECT cnes_alternativo FROM indicador_estabelecimento_cnes_alternativo WHERE indicador_id = ? AND estabelecimento_id = ?",
                        (indicador_id, eid)
                    ).fetchall():
                        ca = str(r_alt["cnes_alternativo"] or "").strip().lstrip("0")
                        if ca and ca not in cnes_lista:
                            cnes_lista.append(ca)

                    if cnes_lista:
                        m_cnes = ",".join("?" * len(cnes_lista))
                        clausula_unidades.append(f"(ltrim(s.cod_cnes, '0') IN ({m_cnes}) AND lower(s.nome_estabelecimento) NOT LIKE '%emab%' AND lower(s.nome_estabelecimento) NOT LIKE '%emulti%')")
                        params_estabs.extend(cnes_lista)

                    eqs = obter_equipes_emulti_unidade(db, eid, indicador_id=indicador_id)
                    if eqs:
                        m_eq = ",".join("?" * len(eqs))
                        clausula_unidades.append(f"s.nome_estabelecimento IN ({m_eq})")
                        params_estabs.extend(eqs)

                filtro_estabs = " OR ".join(clausula_unidades) if clausula_unidades else "1=0"

            sql_at02 = f"""
                SELECT s.cod_procedimento AS codigo, s.nome_procedimento AS nome, sum(s.quantidade) AS apurado
                FROM staging_at02 s
                WHERE s.ano_mes = ? AND s.cod_cbo_sus = ?
                  AND lower(s.nome_estabelecimento) NOT LIKE '%caps%'
                  AND lower(s.nome_estabelecimento) NOT LIKE '%cnr%'
                  AND lower(s.nome_estabelecimento) NOT LIKE '%cecco%'
                  AND ({filtro_estabs})
            """
            params_at02 = [str(periodo or ""), str(cbo_alvo), *params_estabs]
            if profissional and not profissional.startswith("Consolidado SIGA"):
                sql_at02 += " AND s.nome_profissional = ?"
                params_at02.append(profissional)
            sql_at02 += """
                GROUP BY s.cod_procedimento, s.nome_procedimento
                ORDER BY apurado DESC
            """
            rows_at02 = db.execute(sql_at02, params_at02).fetchall()
            if rows_at02:
                itens = []
                for r in rows_at02:
                    d = dict(r)
                    d["considerado"] = d["codigo"] in procs_ind
                    itens.append(d)
                itens.sort(key=lambda x: (not x["considerado"], -x["apurado"]))
                return itens
            return []
        from collections import defaultdict

        cbos_transferem = obter_cbos_transferencia_rel134(db)
        estabs_set = set(estabelecimento_ids) if estabelecimento_ids else set()

        linhas_stg = db.execute(
            """SELECT cod_cnes, nome_estabelecimento, cbo_nome, procedimento_nome, sum(quantidade) as total
               FROM staging_bi_siga
               WHERE fonte_at = 'AT61' AND (ano_mes = ? OR ano_mes LIKE ?)
               GROUP BY cod_cnes, nome_estabelecimento, cbo_nome, procedimento_nome""",
            (str(periodo or ""), f"%{periodo}%"),
        ).fetchall()

        res_proc = defaultdict(int)
        for r in linhas_stg:
            c_cod = _resolver_cbo(db, None, r["cbo_nome"])
            if cbo_alvo and str(c_cod) != str(cbo_alvo):
                continue
            if profissional and not profissional.startswith("Consolidado SIGA") and r["nome_estabelecimento"] != profissional:
                continue

            deve_transferir = bool(c_cod and (c_cod in cbos_transferem or any(str(c_cod).startswith(c) for c in cbos_transferem)))
            cnes_clean = str(r["cod_cnes"] or "").strip().lstrip("0")
            estab_base = db.execute(
                """SELECT id FROM estabelecimentos
                   WHERE ltrim(cod_cnes, '0') = ? AND (upper(nome) LIKE 'UBS%' OR upper(nome) LIKE 'AMA/UBS%') LIMIT 1""",
                (cnes_clean,),
            ).fetchone()
            unidade_base_id = estab_base["id"] if estab_base else None

            unidade_realizou_id = None
            nome_origem = r["nome_estabelecimento"] or ""
            if "/" in nome_origem:
                partes = nome_origem.split("/")
                ultimo = partes[-1].strip().lower()
                for pref in ["inativo - emab ", "inativo -  emab ", "inativo - emulti ", "emulti ", "emab "]:
                    if ultimo.startswith(pref):
                        ultimo = ultimo[len(pref):].strip()
                        break
                for termo, eid in MAPEAMENTO_EMULTI_PADRAO:
                    if termo in ultimo:
                        unidade_realizou_id = eid
                        break
            if not unidade_realizou_id:
                unidade_realizou_id = unidade_base_id

            estab_final = unidade_base_id if deve_transferir and unidade_base_id else (unidade_realizou_id or unidade_base_id)
            if estabs_set and estab_final in estabs_set:
                proc_n = r["procedimento_nome"] or "Atendimento Individual eMulti"
                res_proc[proc_n] += int(r["total"] or 0)
            elif not estabs_set:
                proc_n = r["procedimento_nome"] or "Atendimento Individual eMulti"
                res_proc[proc_n] += int(r["total"] or 0)

        return sorted([{"codigo": "", "nome": k, "apurado": v, "considerado": True} for k, v in res_proc.items()], key=lambda x: x["apurado"], reverse=True)

    # 6. SISAD (P31 [EMAD Ativos], P32 [Deshospitalizacao], P34 [EMAP Ativos])
    if ind_cod in ("P31", "P32", "P34"):
        import calendar
        from collections import defaultdict
        from datetime import datetime

        p = str(periodo or "")
        ano = int(p[:4]) if len(p) >= 4 and p[:4].isdigit() else 2026
        mes = int(p[4:6]) if len(p) >= 6 and p[4:6].isdigit() else 1
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        dt_limite = datetime(ano, mes, ultimo_dia, 23, 59, 59)

        mapa_estab_para_sisad = {
            21: ["EMAD UBS CANGAÍBA", "EMAD UBS CANGAIBA"],
            52: ["EMAD UBS INTEGRAL TALARICO/MARINGA"],
            59: ["EMAD UBS SÃO NICOLAU", "EMAD UBS SAO NICOLAU"],
            65: ["EMAD GRANADA"],
        }

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

        itens = []
        if ind_cod == "P31":
            unidades_alvo = []
            for eid in (estabelecimento_ids or []):
                unidades_alvo.extend(mapa_estab_para_sisad.get(eid, []))

            marc_u = ",".join("?" * len(unidades_alvo)) if unidades_alvo else "''"
            sql_sisad = f"""SELECT tipo_acompanhamento, situacao, data_admissao, data_obito
                            FROM staging_sisad
                            WHERE (periodo_referencia = ? OR periodo_referencia LIKE ?)
                              AND UPPER(unidade) IN ({marc_u})"""
            rows = db.execute(sql_sisad, [p, f"%{p}%", *unidades_alvo]).fetchall()
            qtd_ativos = 0
            qtd_obitos = 0
            for r in rows:
                tipo = (r["tipo_acompanhamento"] or r["situacao"] or "").strip().upper()
                dt_adm = parse_dt(r["data_admissao"])
                dt_ob = parse_dt(r["data_obito"])
                if tipo == "ATIVO" and dt_adm and dt_adm <= dt_limite:
                    qtd_ativos += 1
                if tipo == "INATIVO" and dt_ob and dt_ob.year == ano and dt_ob.month == mes:
                    qtd_obitos += 1
            itens.append({"codigo": "ATIVOS", "nome": "Pacientes Ativos (Admissão até o fim do mês)", "apurado": qtd_ativos, "considerado": True})
            itens.append({"codigo": "ÓBITOS", "nome": "Pacientes em Óbito no Mês (Inativos)", "apurado": qtd_obitos, "considerado": True})
            itens.append({"codigo": "TOTAL", "nome": "Total Pacientes Ativos da EMAD (Soma)", "apurado": qtd_ativos + qtd_obitos, "considerado": True})
            return itens

        elif ind_cod == "P32":
            unidades_alvo = []
            for eid in (estabelecimento_ids or []):
                unidades_alvo.extend(mapa_estab_para_sisad.get(eid, []))

            marc_u = ",".join("?" * len(unidades_alvo)) if unidades_alvo else "''"
            sql_sisad = f"""SELECT tipo_acompanhamento, situacao, data_admissao, procedencia
                            FROM staging_sisad
                            WHERE (periodo_referencia = ? OR periodo_referencia LIKE ?)
                              AND UPPER(unidade) IN ({marc_u})"""
            rows = db.execute(sql_sisad, [p, f"%{p}%", *unidades_alvo]).fetchall()
            qtd_desosp = 0
            for r in rows:
                tipo = (r["tipo_acompanhamento"] or r["situacao"] or "").strip().upper()
                proc = (r["procedencia"] or "").strip().upper()
                dt_adm = parse_dt(r["data_admissao"])
                if tipo == "ATIVO" and proc == "HOSPITAL" and dt_adm and dt_adm.year == ano and dt_adm.month == mes:
                    qtd_desosp += 1
            itens.append({"codigo": "HOSPITAL", "nome": "Desospitalização - Procedência Hospitalar (Admissão no Mês)", "apurado": qtd_desosp, "considerado": True})
            return itens

        elif ind_cod == "P34":
            sql_sisad = """SELECT unidade, tipo_acompanhamento, situacao, data_admissao, data_obito
                           FROM staging_sisad
                           WHERE (periodo_referencia = ? OR periodo_referencia LIKE ?)"""
            rows = db.execute(sql_sisad, [p, f"%{p}%"]).fetchall()
            emad_totais = defaultdict(int)
            for r in rows:
                u = (r["unidade"] or "").strip().upper()
                tipo = (r["tipo_acompanhamento"] or r["situacao"] or "").strip().upper()
                dt_adm = parse_dt(r["data_admissao"])
                dt_ob = parse_dt(r["data_obito"])
                if tipo == "ATIVO" and dt_adm and dt_adm <= dt_limite:
                    emad_totais[u] += 1
                if tipo == "INATIVO" and dt_ob and dt_ob.year == ano and dt_ob.month == mes:
                    emad_totais[u] += 1
            for u in sorted(emad_totais.keys()):
                itens.append({"codigo": "EMAD", "nome": f"{u} (Ativos + Óbitos)", "apurado": emad_totais[u], "considerado": True})
            itens.append({"codigo": "TOTAL", "nome": "Total Pacientes Ativos da EMAP (Região)", "apurado": sum(emad_totais.values()), "considerado": True})
            return itens

    # 7. Hospital Dia (P45, P46, P47 - Cirurgias)
    if ind_cod in ("P45", "P46", "P47"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        rows = db.execute(
            f"""SELECT f.procedimento_codigo AS codigo,
                       COALESCE(pp.nome, p.nome, 'Procedimento ' || f.procedimento_codigo) AS nome,
                       SUM(f.quantidade) AS apurado,
                       1 AS considerado
                FROM fato_apuracao f
                LEFT JOIN procedimento_portes pp ON pp.codigo = f.procedimento_codigo
                LEFT JOIN procedimentos p ON p.codigo = f.procedimento_codigo
                WHERE f.indicador_id = ? AND f.estabelecimento_id IN ({marc_estabs})
                  AND f.periodo = ? AND f.tipo_registro = 'apurado' AND f.procedimento_codigo IS NOT NULL
                GROUP BY f.procedimento_codigo
                ORDER BY apurado DESC""",
            [indicador_id, *estabelecimento_ids, str(periodo or "")],
        ).fetchall()
        return [dict(r) for r in rows]

    # 8. Outros consolidados (P25, P29, P36, P38, P41, P27)
    if ind_cod in ("P25", "P29", "P36", "P38", "P41", "P27"):
        marc_estabs = ",".join("?" * len(estabelecimento_ids)) if estabelecimento_ids else "''"
        sql_fato = f"""SELECT SUM(quantidade) AS tot FROM fato_apuracao
                       WHERE indicador_id = ? AND estabelecimento_id IN ({marc_estabs}) AND periodo = ? AND tipo_registro = 'apurado'"""
        params_fato = [indicador_id, *estabelecimento_ids, str(periodo or "")]
        if cbo_codigo:
            sql_fato += " AND cbo_codigo = ?"
            params_fato.append(cbo_codigo)
        row = db.execute(sql_fato, params_fato).fetchone()
        tot = int(row["tot"]) if row and row["tot"] is not None else 0
        return [{"codigo": ind_cod, "nome": ind_nome, "apurado": tot, "considerado": True}]

    # 7. AT-02 padrão
    procedimentos = _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not procedimentos:
        return []

    cmes, cbos = _cmes_e_cbos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
    if not cmes or cbos == []:
        return []

    proc_lista = [p["codigo"] for p in procedimentos]
    sql = f"""SELECT s.cod_procedimento AS codigo,
                     COALESCE(NULLIF(s.nome_procedimento, ''), p.nome) AS nome,
                     SUM(s.quantidade) AS apurado
              FROM staging_at02 s JOIN procedimentos p ON p.codigo = s.cod_procedimento
              WHERE s.ano_mes = ? AND s.cod_cmes IN ({",".join("?" * len(cmes))}) AND s.nome_profissional = ?
                AND s.cod_procedimento IN ({",".join("?" * len(proc_lista))})"""
    params = [periodo, *cmes, profissional, *proc_lista]
    cbo_alvo = cbo_codigo or cbo_profissional
    if cbo_alvo:
        if str(cbo_alvo).endswith("_PMMB"):
            base_cbo = str(cbo_alvo).replace("_PMMB", "")
            sql += " AND s.cod_cbo_sus IN (?, '225142', '225170')"
            params.append(base_cbo)
        elif str(cbo_alvo).endswith("_RT"):
            base_cbo = str(cbo_alvo).replace("_RT", "")
            sql += " AND s.cod_cbo_sus IN (?, '223293', '223208', '223240')"
            params.append(base_cbo)
        else:
            sql += " AND s.cod_cbo_sus = ?"
            params.append(cbo_alvo)
    elif cbos:
        sql += f" AND s.cod_cbo_sus IN ({','.join('?' * len(cbos))})"
        params.extend(cbos)
    if str(indicador_id) == "43" and (cbo_alvo in ("225112", "225127") or (cbos and any(c in ("225112", "225127") for c in cbos))):
        if subgrupo_id is not None:
            sql += " AND s.cod_cmes != s.cod_cnes"
        else:
            sql += " AND (s.cod_cmes = s.cod_cnes OR s.cod_cmes IS NULL OR s.cod_cnes IS NULL)"
    if str(indicador_id) == "35" and subgrupo_id is not None:
        sg_row = db.execute("SELECT nome FROM indicador_subgrupo WHERE id = ?", (subgrupo_id,)).fetchone()
        if sg_row:
            sg_n = (sg_row["nome"] or "").lower()
            if "auditiva" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%auditiva%'"
            elif "fisica" in sg_n or "fsica" in sg_n:
                sql += " AND (lower(s.nome_especialidade2) LIKE '%fisica%' OR lower(s.nome_especialidade2) LIKE '%fsica%')"
            elif "intelectual" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%intelectual%'"
            elif "visual" in sg_n:
                sql += " AND lower(s.nome_especialidade2) LIKE '%visual%'"
    sql += " GROUP BY s.cod_procedimento, p.nome ORDER BY apurado DESC"
    considerados_rows = db.execute(sql, params).fetchall()

    resultado = []
    for r in considerados_rows:
        item = dict(r)
        item["considerado"] = True
        resultado.append(item)

    # Procedimentos restantes do profissional na mesma competência e unidade
    sql_todos = f"""
        SELECT s.cod_procedimento AS codigo,
               COALESCE(p.nome, s.nome_procedimento, s.cod_procedimento) AS nome,
               s.nome_especialidade2,
               SUM(s.quantidade) AS total_qtd
        FROM staging_at02 s
        LEFT JOIN procedimentos p ON p.codigo = s.cod_procedimento
        WHERE s.ano_mes = ? AND s.cod_cmes IN ({",".join("?" * len(cmes))}) AND s.nome_profissional = ?
    """
    params_todos = [periodo, *cmes, profissional]
    if cbo_alvo:
        if str(cbo_alvo).endswith("_PMMB"):
            base_cbo = str(cbo_alvo).replace("_PMMB", "")
            sql_todos += " AND s.cod_cbo_sus IN (?, '225142', '225170')"
            params_todos.append(base_cbo)
        elif str(cbo_alvo).endswith("_RT"):
            base_cbo = str(cbo_alvo).replace("_RT", "")
            sql_todos += " AND s.cod_cbo_sus IN (?, '223293', '223208', '223240')"
            params_todos.append(base_cbo)
        else:
            sql_todos += " AND s.cod_cbo_sus = ?"
            params_todos.append(cbo_alvo)
    sql_todos += " GROUP BY s.cod_procedimento, p.nome, s.nome_especialidade2 ORDER BY total_qtd DESC"
    todos_rows = db.execute(sql_todos, params_todos).fetchall()

    restantes_map = {}
    for row in todos_rows:
        cod = row["codigo"]
        nome = row["nome"]
        tot = row["total_qtd"] or 0
        esp = (row["nome_especialidade2"] or "").lower()

        if str(indicador_id) == "35" and subgrupo_id is not None:
            sg_row = db.execute("SELECT nome FROM indicador_subgrupo WHERE id = ?", (subgrupo_id,)).fetchone()
            sg_n = (sg_row["nome"] or "").lower() if sg_row else ""
            pertence_a_este_subgrupo = False
            if "auditiva" in sg_n and "auditiva" in esp:
                pertence_a_este_subgrupo = True
            elif ("fisica" in sg_n or "fsica" in sg_n) and ("fisica" in esp or "fsica" in esp):
                pertence_a_este_subgrupo = True
            elif "intelectual" in sg_n and "intelectual" in esp:
                pertence_a_este_subgrupo = True
            elif "visual" in sg_n and "visual" in esp:
                pertence_a_este_subgrupo = True

            if pertence_a_este_subgrupo and cod in proc_lista:
                continue
            else:
                nome_exibir = nome
                if cod == "0301079005" and row["nome_especialidade2"]:
                    nome_exibir = f"{nome} ({row['nome_especialidade2']})"
                chave = (cod, nome_exibir)
                restantes_map[chave] = restantes_map.get(chave, 0) + tot
        else:
            if cod in proc_lista:
                continue
            chave = (cod, nome)
            restantes_map[chave] = restantes_map.get(chave, 0) + tot

    for (cod, nome), qtd in sorted(restantes_map.items(), key=lambda x: x[1], reverse=True):
        resultado.append({
            "codigo": cod,
            "nome": nome,
            "apurado": qtd,
            "considerado": False,
        })

    return resultado


def _procedimentos_at02_do_cbo(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id=None):
    """
    Retorna os procedimentos registrados no SIGA AT-02 para o CBO e unidade(s)
    desta linha na competência, que NÃO estão sendo contabilizados no indicador.
    Tabela meramente visual e informativa para auditoria e identificação de lançamentos incorretos.
    """
    if not estabelecimento_ids:
        return [], [], False, "", "", 0

    ind_cod, ind_nome, cnes_list, cmes_list = _obter_info_linha(db, indicador_id, estabelecimento_ids)
    unidades = list(set(cnes_list + cmes_list))
    if not unidades:
        return [], [], False, "", "", 0

    cbo_codigo = (cbo_codigo or "").strip()
    eh_linha_pmmb = bool(cbo_codigo and cbo_codigo.endswith("_PMMB"))
    eh_linha_rt = bool(cbo_codigo and cbo_codigo.endswith("_RT"))
    base_cbo = cbo_codigo.replace("_PMMB", "").replace("_RT", "") if (eh_linha_pmmb or eh_linha_rt) else cbo_codigo
    cbos_alvo = []
    cbo_nome = ""

    if cbo_codigo:
        if eh_linha_pmmb:
            cbos_alvo = [base_cbo, "225142", "225170"]
            cbo_nome = "Médico Generalista PMMB"
        elif eh_linha_rt:
            cbos_alvo = [base_cbo, "223293", "223208", "223240"]
            c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
            cbo_nome = c_row["nome_categoria"] if c_row and c_row["nome_categoria"] else f"{base_cbo} RT"
        else:
            cbos_alvo = [cbo_codigo]
            c_row = db.execute("SELECT nome_categoria FROM cbo WHERE codigo = ?", (cbo_codigo,)).fetchone()
            if c_row and c_row["nome_categoria"]:
                cbo_nome = c_row["nome_categoria"]
    else:
        # Se não há CBO explícito na linha, verificar se o indicador tem CBOs específicos cadastrados
        ind_cbos = db.execute(
            "SELECT cbo_codigo FROM indicador_cbo WHERE indicador_id = ? AND curinga != 1",
            (indicador_id,)
        ).fetchall()
        cbos_alvo = [c["cbo_codigo"].strip() for c in ind_cbos if c["cbo_codigo"]]
        if cbos_alvo:
            cbo_nome = f"{len(cbos_alvo)} CBOs vinculados"

    if not cbos_alvo:
        return [], [], False, "", "", 0

    # Descobrir fonte do indicador para saber se ele é baseado no AT-02
    ind_info = db.execute(
        """SELECT i.fonte_dados, f.nome as fonte_nome 
           FROM indicadores i 
           LEFT JOIN fontes_dados f ON f.id = i.fonte_id 
           WHERE i.id = ?""",
        (indicador_id,)
    ).fetchone()
    fonte_nome = (ind_info["fonte_nome"] or "").upper() if ind_info else ""
    fonte_dados = (ind_info["fonte_dados"] or "").upper() if ind_info else ""
    eh_fonte_at02 = ("AT02" in fonte_nome) or ("AT-02" in fonte_dados) or ("AT02" in fonte_dados)
    if not eh_fonte_at02:
        return [], [], False, "", "", 0

    codigos_considerados = []
    if eh_fonte_at02:
        procs_linha = _procedimentos_da_linha(db, indicador_id, estabelecimento_ids, cbo_codigo, periodo, subgrupo_id)
        codigos_considerados = [p["codigo"] for p in procs_linha if p and p["codigo"]]

    # Query em staging_at02
    marc_unid = ",".join("?" * len(unidades))
    marc_cbos = ",".join("?" * len(cbos_alvo))

    sql = f"""
        SELECT s.cod_procedimento AS codigo,
               COALESCE(NULLIF(s.nome_procedimento, ''), p.nome, s.cod_procedimento) AS nome,
               s.nome_profissional AS profissional,
               s.cod_cbo_sus AS cbo_codigo,
               COALESCE(c.nome_categoria, s.nome_cbo1, s.cod_cbo_sus) AS cbo_nome,
               SUM(s.quantidade) AS quantidade
        FROM staging_at02 s
        LEFT JOIN procedimentos p ON p.codigo = s.cod_procedimento
        LEFT JOIN cbo c ON c.codigo = s.cod_cbo_sus
        WHERE s.ano_mes = ?
          AND (s.cod_cmes IN ({marc_unid}) OR s.cod_cnes IN ({marc_unid}))
          AND s.cod_cbo_sus IN ({marc_cbos})
    """
    params = [str(periodo or ""), *unidades, *unidades, *cbos_alvo]

    if codigos_considerados:
        marc_cons = ",".join("?" * len(codigos_considerados))
        sql += f" AND s.cod_procedimento NOT IN ({marc_cons})"
        params.extend(codigos_considerados)

    sql += """
        GROUP BY s.cod_procedimento, s.nome_procedimento, p.nome, s.nome_profissional, s.cod_cbo_sus, c.nome_categoria, s.nome_cbo1
        ORDER BY quantidade DESC, s.cod_procedimento, s.nome_profissional
    """

    rows = db.execute(sql, params).fetchall()

    # Agrupa por procedimento para exibição hierárquica (Procedimento -> Profissionais)
    from collections import OrderedDict
    grupos = OrderedDict()
    _eh_prof_pmmb, tem_pmmb_cadastrado = _obter_matcher_pmmb(db)
    _eh_prof_rt, tem_rt_cadastrado = _obter_matcher_rt(db)
    for r in rows:
        prof = r["profissional"]
        is_pmmb = _eh_prof_pmmb(prof)
        is_rt = _eh_prof_rt(prof)
        if eh_linha_pmmb:
            if not is_pmmb:
                continue
        elif eh_linha_rt:
            if not is_rt:
                continue
        else:
            if tem_pmmb_cadastrado and is_pmmb and (ind_cod in ("P01", "P02", "P13") or base_cbo in ("225142", "225170")):
                continue
            if tem_rt_cadastrado and is_rt and (ind_cod in ("P07", "P08", "P17", "P18", "P42") or base_cbo in ("223293", "223208", "223240")):
                continue
        cod = str(r["codigo"] or "").strip()
        nome = str(r["nome"] or "").strip()
        nome_upper = nome.upper()
        is_municipal = bool(
            cod.startswith(("0301019", "0101019", "0307019", "030905"))
            or "MAE PAULISTANA" in nome_upper
            or "MUNICIPAL" in nome_upper
            or "SALA DO IDOSO" in nome_upper
        )
        if cod not in grupos:
            grupos[cod] = {
                "codigo": cod,
                "nome": nome,
                "municipal": is_municipal,
                "quantidade_total": 0,
                "profissionais": [],
            }
        qtd = int(r["quantidade"] or 0)
        grupos[cod]["quantidade_total"] += qtd
        grupos[cod]["profissionais"].append({
            "profissional": r["profissional"] or "Não identificado",
            "quantidade": qtd,
        })

    # Ordena os procedimentos pelo total realizado decrescente
    procs_agrupados = sorted(grupos.values(), key=lambda x: x["quantidade_total"], reverse=True)
    # Ordena profissionais dentro de cada procedimento por quantidade decrescente
    for p in procs_agrupados:
        p["profissionais"].sort(key=lambda x: x["quantidade"], reverse=True)

    total_qtd = sum(p["quantidade_total"] for p in procs_agrupados)
    return procs_agrupados, cbos_alvo, True, cbo_codigo, cbo_nome, total_qtd


@bp.route("/linha_detalhe")
def linha_detalhe():
    """Nível 1 do drill-down inline: profissionais de uma linha específica
    do painel e procedimentos do CBO no AT-02 para conferência visual."""
    db = get_db()
    indicador_id = request.args.get("indicador_id")
    est_ids = _ids_da_linha(request.args)
    cbo_codigo = request.args.get("cbo_codigo") or None
    periodo = request.args.get("periodo")
    subgrupo_id = _subgrupo_da_linha(request.args.get("subgrupo_id"))

    profissionais = _profissionais_da_linha(
        db, indicador_id, est_ids,
        cbo_codigo, periodo, subgrupo_id,
    )
    profissionais_ordenados = _ordenar_profissionais_alfabeticamente([dict(p) for p in profissionais])

    regra_prof_row = db.execute(
        """SELECT ip.id, ip.procedimento_codigo, ip.nome_profissional, p.nome as procedimento_nome
           FROM indicador_procedimento ip
           LEFT JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
           WHERE ip.indicador_id = ? AND (ip.subgrupo_id IS ? OR ip.subgrupo_id IS NULL)
             AND ip.tipo_vinculo = 'inclusao' AND ip.nome_profissional IS NOT NULL AND TRIM(nome_profissional) != ''
           LIMIT 1""",
        (indicador_id, subgrupo_id),
    ).fetchone()

    procs_at02, cbos_alvo, tem_cbo, cbo_cod_rotulo, cbo_nome_rotulo, total_at02 = _procedimentos_at02_do_cbo(
        db, indicador_id, est_ids, cbo_codigo, periodo, subgrupo_id,
    )

    return jsonify({
        "profissionais": profissionais_ordenados,
        "procedimentos_cbo_at02": procs_at02,
        "tem_cbo": tem_cbo,
        "cbo_codigo": cbo_cod_rotulo or (", ".join(cbos_alvo) if cbos_alvo else ""),
        "cbo_nome": cbo_nome_rotulo,
        "total_at02": total_at02,
        "regra_profissional": dict(regra_prof_row) if regra_prof_row else None,
        "subgrupo_id": subgrupo_id,
    })


@bp.route("/profissional_detalhe")
def profissional_detalhe():
    """Nível 2 do drill-down inline: procedimentos ou atividades de um profissional
    específico dentro de uma linha do painel."""
    db = get_db()
    indicador_id = request.args.get("indicador_id")
    est_ids = _ids_da_linha(request.args)
    cbo_codigo = request.args.get("cbo_codigo") or None
    periodo = request.args.get("periodo")
    profissional = request.args.get("profissional")
    subgrupo_id = _subgrupo_da_linha(request.args.get("subgrupo_id"))
    cbo_profissional = request.args.get("cbo_profissional") or None
    estabelecimento_origem = request.args.get("estabelecimento_origem") or None

    procedimentos = _procedimentos_do_profissional(
        db, indicador_id, est_ids,
        cbo_codigo, periodo,
        profissional,
        subgrupo_id,
        cbo_profissional,
        estabelecimento_origem=estabelecimento_origem,
    )

    ind_cod, _, _, _ = _obter_info_linha(db, indicador_id, est_ids)
    if ind_cod in ("P12", "P22"):
        return jsonify({
            "is_atividade_rel134": True,
            "tipo_detalhe": "atividades",
            "atividades": [dict(p) for p in procedimentos],
            "procedimentos": [dict(p) for p in procedimentos],
        })

    if ind_cod in ("P30", "P33"):
        return jsonify({
            "is_ad_rel130": True,
            "tipo_detalhe": "atend_domiciliar",
            "procedimentos": [dict(p) for p in procedimentos],
        })

    if ind_cod in ("P31", "P32", "P34"):
        return jsonify({
            "is_sisad": True,
            "tipo_detalhe": "sisad",
            "procedimentos": [dict(p) for p in procedimentos],
        })

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
        d["considerado"] = p.get("considerado", True)
        itens.append(d)
    return jsonify({"procedimentos": itens})


def _obter_dados_linha_resumo(db, indicador_id, estabelecimento_ids, subgrupo_id, cbo_codigo, periodo):
    """Retorna os dados consolidados e recalculados de uma linha específica do painel."""
    linhas_f = _resultados_com_status(db)
    est_list = []
    if estabelecimento_ids:
        if isinstance(estabelecimento_ids, str):
            est_list = [int(x) for x in estabelecimento_ids.split(",") if x.isdigit()]
        elif isinstance(estabelecimento_ids, (list, tuple)):
            est_list = [int(x) for x in estabelecimento_ids if str(x).isdigit()]

    for r in linhas_f:
        if (str(r.get("indicador_id")) == str(indicador_id) and
            str(r.get("subgrupo_id") or "") == str(subgrupo_id or "") and
            str(r.get("cbo_codigo") or "") == str(cbo_codigo or "") and
            str(r.get("periodo") or "") == str(periodo or "")):
            if est_list:
                r_estabs = r.get("estabelecimento_ids") or [r.get("estabelecimento_id")]
                if not any(e in r_estabs for e in est_list):
                    continue
            return {
                "valor_apurado": r.get("valor_apurado") or 0,
                "valor_declarado": r.get("valor_declarado"),
                "divergencia": r.get("divergencia"),
                "valor_meta": r.get("valor_meta"),
                "percentual_meta": r.get("percentual_meta"),
                "status_rotulo": r.get("status_rotulo"),
                "status_classe": r.get("status_classe"),
                "auditoria_rotulo": r.get("auditoria_rotulo"),
                "auditoria_classe": r.get("auditoria_classe"),
            }
    return None


@bp.route("/desvincular_procedimento", methods=["POST"])
def desvincular_procedimento():
    """Remove o vínculo de um procedimento com o indicador (adiciona regra de exclusão)."""
    data = request.get_json() or {}
    indicador_id = data.get("indicador_id")
    subgrupo_id = data.get("subgrupo_id")
    if subgrupo_id in ("", "None", "null", "undefined"):
        subgrupo_id = None
    elif subgrupo_id is not None:
        try:
            subgrupo_id = int(subgrupo_id)
        except (ValueError, TypeError):
            pass

    cod_procedimento = str(data.get("cod_procedimento") or "").strip()
    periodo = data.get("periodo")

    if not indicador_id or not cod_procedimento:
        return jsonify({"ok": False, "mensagem": "Indicador ou procedimento não informado."}), 400

    db = get_db()

    # 1. Remove qualquer vínculo direto de inclusão para esse indicador/subgrupo
    db.execute(
        """DELETE FROM indicador_procedimento
           WHERE indicador_id = ? AND procedimento_codigo = ?
             AND ((subgrupo_id IS NULL AND ? IS NULL) OR subgrupo_id = ?)
             AND tipo_vinculo = 'inclusao'""",
        (indicador_id, cod_procedimento, subgrupo_id, subgrupo_id),
    )

    # 2. Insere regra explícita de exclusão para blindar contra inclusões gerais ou De-Para
    exclusao_existente = db.execute(
        """SELECT id FROM indicador_procedimento
           WHERE indicador_id = ? AND procedimento_codigo = ?
             AND ((subgrupo_id IS NULL AND ? IS NULL) OR subgrupo_id = ?)
             AND tipo_vinculo = 'exclusao'""",
        (indicador_id, cod_procedimento, subgrupo_id, subgrupo_id),
    ).fetchone()

    if not exclusao_existente:
        db.execute(
            """INSERT INTO indicador_procedimento (indicador_id, subgrupo_id, procedimento_codigo, tipo_vinculo)
               VALUES (?, ?, ?, 'exclusao')""",
            (indicador_id, subgrupo_id, cod_procedimento),
        )

    db.commit()

    # 3. Recalcula a apuração dinâmica
    from ..funcoes import sincronizar_apuracao_dinamica
    sincronizar_apuracao_dinamica(db, periodo=periodo)

    linha_atualizada = _obter_dados_linha_resumo(
        db, indicador_id, data.get("estabelecimento_ids"), subgrupo_id, data.get("cbo_codigo"), periodo
    )

    return jsonify({
        "ok": True,
        "mensagem": f"Procedimento {cod_procedimento} desvinculado com sucesso!",
        "linha": linha_atualizada
    })


@bp.route("/vincular_procedimento", methods=["POST"])
def vincular_procedimento():
    """Vincula / reativa um procedimento a um indicador ou subgrupo diretamente pelo painel."""
    data = request.get_json() or {}
    indicador_id = data.get("indicador_id")
    subgrupo_id = data.get("subgrupo_id")
    if subgrupo_id in ("", "None", "null", "undefined"):
        subgrupo_id = None
    elif subgrupo_id is not None:
        try:
            subgrupo_id = int(subgrupo_id)
        except (ValueError, TypeError):
            pass

    cod_procedimento = str(data.get("cod_procedimento") or "").strip()
    periodo = data.get("periodo")

    if not indicador_id or not cod_procedimento:
        return jsonify({"ok": False, "mensagem": "Indicador ou procedimento não informado."}), 400

    db = get_db()

    # 1. Remove qualquer regra de exclusão anterior
    db.execute(
        """DELETE FROM indicador_procedimento
           WHERE indicador_id = ? AND procedimento_codigo = ?
             AND ((subgrupo_id IS NULL AND ? IS NULL) OR subgrupo_id = ?)
             AND tipo_vinculo = 'exclusao'""",
        (indicador_id, cod_procedimento, subgrupo_id, subgrupo_id),
    )

    # 2. Insere regra de inclusão se não existir
    inclusao_existente = db.execute(
        """SELECT id FROM indicador_procedimento
           WHERE indicador_id = ? AND procedimento_codigo = ?
             AND ((subgrupo_id IS NULL AND ? IS NULL) OR subgrupo_id = ?)
             AND tipo_vinculo = 'inclusao'""",
        (indicador_id, cod_procedimento, subgrupo_id, subgrupo_id),
    ).fetchone()

    if not inclusao_existente:
        db.execute(
            """INSERT INTO indicador_procedimento (indicador_id, subgrupo_id, procedimento_codigo, tipo_vinculo)
               VALUES (?, ?, ?, 'inclusao')""",
            (indicador_id, subgrupo_id, cod_procedimento),
        )

    db.commit()

    # 3. Recalcula a apuração dinâmica
    from ..funcoes import sincronizar_apuracao_dinamica
    sincronizar_apuracao_dinamica(db, periodo=periodo)

    linha_atualizada = _obter_dados_linha_resumo(
        db, indicador_id, data.get("estabelecimento_ids"), subgrupo_id, data.get("cbo_codigo"), periodo
    )

    return jsonify({
        "ok": True,
        "mensagem": f"Procedimento {cod_procedimento} vinculado com sucesso!",
        "linha": linha_atualizada
    })


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
                    estabelecimento_origem=prof.get("nome_estabelecimento"),
                )
                rotulo_cbo_prof = (
                    f"{prof['cbo_codigo']} - {prof['cbo_nome']}" if prof["cbo_codigo"] and prof["cbo_nome"]
                    else (prof["cbo_codigo"] or "")
                )
                for p in procedimentos:
                    if not p.get("considerado", True):
                        continue
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


# ----------------------------------------------------------------------------
# GERENCIAMENTO DE VÍNCULOS COM O WEBSAASS (DE/PARA DE PRODUÇÃO)
# ----------------------------------------------------------------------------

@bp.route("/websaass/info_vinculos", methods=["GET"])
def websaass_info_vinculos():
    db = get_db()
    indicador_id = request.args.get("indicador_id", type=int)
    subgrupo_id = request.args.get("subgrupo_id", type=int)
    cbo_codigo = request.args.get("cbo_codigo", type=str)
    if cbo_codigo in ("", "None", "null"):
        cbo_codigo = None
    periodo = request.args.get("periodo", type=str)

    if not indicador_id:
        primeiro = db.execute("SELECT id FROM indicadores ORDER BY codigo LIMIT 1").fetchone()
        if primeiro:
            indicador_id = primeiro["id"]
        else:
            return jsonify({"ok": False, "erro": "Nenhum indicador cadastrado"}), 400

    ind = db.execute("SELECT id, codigo, nome FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
    if not ind:
        return jsonify({"ok": False, "erro": "Indicador não encontrado"}), 404

    sg = None
    if subgrupo_id:
        sg = db.execute("SELECT id, nome FROM indicador_subgrupo WHERE id = ?", (subgrupo_id,)).fetchone()

    cbo_info = None
    if cbo_codigo:
        rotulo_suf = ""
        if "_PMMB" in str(cbo_codigo):
            rotulo_suf = " (PMMB)"
        elif "_RT" in str(cbo_codigo):
            rotulo_suf = " (RT)"
        cbo_clean = str(cbo_codigo).replace("_PMMB", "").replace("_RT", "")
        cbo_row = db.execute("SELECT codigo, nome_categoria FROM cbo WHERE codigo = ?", (cbo_clean,)).fetchone()
        cbo_info = {
            "codigo": cbo_codigo,
            "nome": (cbo_row["nome_categoria"] if cbo_row else cbo_codigo) + rotulo_suf
        }

    periodo_norm = _normalizar_periodo(periodo) if periodo else None
    periodo_ws = _periodo_para_webssas(periodo_norm) if periodo_norm else None

    # Estabelecimento(s) selecionado(s) na linha
    est_ids = _ids_da_linha(request.args)
    est_nomes_ws = []
    est_info = None
    if est_ids:
        marc_e = ",".join("?" * len(est_ids))
        dp_est_rows = db.execute(
            f"SELECT DISTINCT nome_websass FROM de_para_websaass_unidade WHERE estabelecimento_id IN ({marc_e})",
            est_ids,
        ).fetchall()
        est_nomes_ws = [r["nome_websass"] for r in dp_est_rows if r["nome_websass"]]
        est_cad_rows = db.execute(
            f"SELECT id, nome FROM estabelecimentos WHERE id IN ({marc_e})",
            est_ids,
        ).fetchall()
        for r in est_cad_rows:
            if r["nome"] and r["nome"] not in est_nomes_ws:
                est_nomes_ws.append(r["nome"])
        if len(est_cad_rows) == 1:
            est_info = {"id": est_cad_rows[0]["id"], "ids": str(est_cad_rows[0]["id"]), "nome": est_cad_rows[0]["nome"]}
        elif len(est_cad_rows) > 1:
            est_info = {"id": est_cad_rows[0]["id"], "ids": ",".join(str(r["id"]) for r in est_cad_rows), "nome": f"Grupo Consolidado ({len(est_cad_rows)} unidades)"}

    # Linhas atualmente vinculadas a este indicador
    query_vinc = """
        SELECT d.id, d.cod_producao, d.producao, d.servico, d.codigo_indicador, d.cbo_codigo, d.subgrupo_id,
               sg.nome AS subgrupo_nome
        FROM de_para_websaass_indicador d
        LEFT JOIN indicador_subgrupo sg ON sg.id = d.subgrupo_id
        WHERE d.indicador_id = ?
    """
    params_vinc = [indicador_id]
    if subgrupo_id is not None:
        query_vinc += " AND d.subgrupo_id = ?"
        params_vinc.append(subgrupo_id)
    if cbo_codigo is not None:
        query_vinc += " AND d.cbo_codigo = ?"
        params_vinc.append(cbo_codigo)
    query_vinc += " ORDER BY d.cod_producao"
    vinc_rows = db.execute(query_vinc, params_vinc).fetchall()

    vinculadas = []
    for r in vinc_rows:
        # Total geral da rede
        q_sql = """
            SELECT COALESCE(SUM(qtde_realizada), 0) AS tot
            FROM staging_webssas
            WHERE lower(trim(cod_producao)) = lower(trim(?))
        """
        q_params = [r["cod_producao"]]
        if r["servico"]:
            q_sql += " AND (servico IS NULL OR lower(trim(servico)) = lower(trim(?)))"
            q_params.append(r["servico"])
        if periodo_norm:
            q_sql += " AND (periodo = ? OR periodo = ?)"
            q_params.extend([periodo_norm, periodo_ws])

        tot_geral = db.execute(q_sql, q_params).fetchone()["tot"]

        # Total na unidade específica (se informada)
        tot_unidade = tot_geral
        if est_nomes_ws:
            marc_u = ",".join("?" * len(est_nomes_ws))
            q_sql_u = q_sql + f" AND unidade IN ({marc_u})"
            q_params_u = list(q_params) + est_nomes_ws
            tot_unidade = db.execute(q_sql_u, q_params_u).fetchone()["tot"]

        vinculadas.append({
            "id": r["id"],
            "cod_producao": r["cod_producao"],
            "producao": r["producao"] or "",
            "servico": r["servico"] or "",
            "cbo_codigo": r["cbo_codigo"] or "",
            "subgrupo_nome": r["subgrupo_nome"] or "",
            "total_qtd_periodo": int(tot_unidade or 0),
            "total_qtd_rede": int(tot_geral or 0),
        })

    # Catálogo de linhas do WebSaass
    # 1. Total Geral da Rede
    stg_map = {}
    stg_sql = """
        SELECT cod_producao, producao, servico, SUM(qtde_realizada) AS tot
        FROM staging_webssas
        WHERE cod_producao IS NOT NULL AND trim(cod_producao) != ''
    """
    stg_params = []
    if periodo_norm:
        stg_sql += " AND (periodo = ? OR periodo = ?)"
        stg_params.extend([periodo_norm, periodo_ws])
    stg_sql += " GROUP BY cod_producao, producao, servico"
    for r in db.execute(stg_sql, stg_params).fetchall():
        key = (str(r["cod_producao"] or "").strip().lower(), str(r["servico"] or "").strip().lower())
        stg_map[key] = {
            "cod_producao": r["cod_producao"],
            "producao": r["producao"] or "",
            "servico": r["servico"] or "",
            "total_qtd_rede": int(r["tot"] or 0),
            "total_qtd_periodo": int(r["tot"] or 0),
        }

    # 2. Total na Unidade Selecionada
    if est_nomes_ws:
        marc_u = ",".join("?" * len(est_nomes_ws))
        stg_sql_u = f"""
            SELECT cod_producao, producao, servico, SUM(qtde_realizada) AS tot
            FROM staging_webssas
            WHERE cod_producao IS NOT NULL AND trim(cod_producao) != ''
              AND unidade IN ({marc_u})
        """
        stg_params_u = list(est_nomes_ws)
        if periodo_norm:
            stg_sql_u += " AND (periodo = ? OR periodo = ?)"
            stg_params_u.extend([periodo_norm, periodo_ws])
        stg_sql_u += " GROUP BY cod_producao, producao, servico"
        unidade_counts = {}
        for r in db.execute(stg_sql_u, stg_params_u).fetchall():
            key = (str(r["cod_producao"] or "").strip().lower(), str(r["servico"] or "").strip().lower())
            unidade_counts[key] = int(r["tot"] or 0)

        for key, item in stg_map.items():
            item["total_qtd_periodo"] = unidade_counts.get(key, 0)

    dp_sql = """
        SELECT d.id AS de_para_id, d.cod_producao, d.producao, d.servico,
               d.indicador_id, d.codigo_indicador, d.subgrupo_id, d.cbo_codigo,
               i.codigo AS ind_cod, i.nome AS ind_nome,
               sg.nome AS sg_nome
        FROM de_para_websaass_indicador d
        LEFT JOIN indicadores i ON i.id = d.indicador_id
        LEFT JOIN indicador_subgrupo sg ON sg.id = d.subgrupo_id
        WHERE d.cod_producao IS NOT NULL AND trim(d.cod_producao) != ''
    """
    dp_map = {}
    for r in db.execute(dp_sql).fetchall():
        key = (str(r["cod_producao"] or "").strip().lower(), str(r["servico"] or "").strip().lower())
        dp_map[key] = dict(r)

    todas_chaves = set(stg_map.keys()).union(set(dp_map.keys()))
    disponiveis = []

    for key in sorted(todas_chaves, key=lambda k: (k[0], k[1])):
        dp = dp_map.get(key)
        stg = stg_map.get(key)

        cod_prod = (dp["cod_producao"] if dp else None) or (stg["cod_producao"] if stg else "")
        prod_nome = (stg["producao"] if stg else None) or (dp["producao"] if dp else "")
        serv_nome = (stg["servico"] if stg else None) or ((dp["servico"] if dp else "") or "")
        tot_qtd = stg["total_qtd_periodo"] if stg else 0

        if dp and dp.get("indicador_id"):
            if (dp["indicador_id"] == indicador_id and
                (dp.get("subgrupo_id") or None) == (subgrupo_id or None) and
                (dp.get("cbo_codigo") or None) == (cbo_codigo or None)):
                status = "vinculado_atual"
                vinculo_desc = "Já vinculado a esta regra"
            else:
                status = "vinculado_outro"
                vinculo_desc = f"Vinculado a {dp['ind_cod'] or dp['codigo_indicador'] or 'Outro'}"
                if dp.get("sg_nome"):
                    vinculo_desc += f" ({dp['sg_nome']})"
                if dp.get("cbo_codigo"):
                    vinculo_desc += f" · CBO {dp['cbo_codigo']}"
        else:
            status = "nao_vinculado"
            vinculo_desc = "Não vinculado"

        tot_rede = stg["total_qtd_rede"] if stg else 0

        disponiveis.append({
            "de_para_id": dp["de_para_id"] if dp else None,
            "cod_producao": cod_prod,
            "producao": prod_nome,
            "servico": serv_nome,
            "total_qtd_periodo": tot_qtd,
            "total_qtd_rede": tot_rede,
            "status": status,
            "vinculo_desc": vinculo_desc,
        })

    todos_ind = [
        {"id": r["id"], "codigo": r["codigo"], "nome": r["nome"]}
        for r in db.execute("SELECT id, codigo, nome FROM indicadores ORDER BY codigo").fetchall()
    ]

    subgrupos_ind = [
        {"id": r["id"], "nome": r["nome"]}
        for r in db.execute("SELECT id, nome FROM indicador_subgrupo WHERE indicador_id = ? ORDER BY nome", (indicador_id,)).fetchall()
    ]

    cbos_ind = []
    for r in db.execute("""
        SELECT DISTINCT ic.cbo_codigo, c.nome_categoria
        FROM indicador_cbo ic
        LEFT JOIN cbo c ON c.codigo = replace(replace(ic.cbo_codigo, '_PMMB', ''), '_RT', '')
        WHERE ic.indicador_id = ? AND ic.cbo_codigo IS NOT NULL AND ic.curinga = 0
        ORDER BY ic.cbo_codigo
    """, (indicador_id,)).fetchall():
        rotulo_suf = ""
        if "_PMMB" in str(r["cbo_codigo"]):
            rotulo_suf = " (PMMB)"
        elif "_RT" in str(r["cbo_codigo"]):
            rotulo_suf = " (RT)"
        cbos_ind.append({
            "codigo": r["cbo_codigo"],
            "nome": (r["nome_categoria"] or r["cbo_codigo"]) + rotulo_suf,
        })

    return jsonify({
        "ok": True,
        "indicador": {
            "id": ind["id"],
            "codigo": ind["codigo"],
            "nome": ind["nome"],
            "subgrupo_id": sg["id"] if sg else None,
            "subgrupo_nome": sg["nome"] if sg else None,
            "cbo_codigo": cbo_info["codigo"] if cbo_info else None,
            "cbo_nome": cbo_info["nome"] if cbo_info else None,
        },
        "periodo": periodo or "",
        "estabelecimento": est_info,
        "vinculadas": vinculadas,
        "disponiveis": disponiveis,
        "todos_indicadores": todos_ind,
        "subgrupos_indicador": subgrupos_ind,
        "cbos_indicador": cbos_ind,
    })


@bp.route("/websaass/vincular_linhas", methods=["POST"])
def websaass_vincular_linhas():
    db = get_db()
    dados = request.get_json(force=True) or {}
    indicador_id = dados.get("indicador_id")
    subgrupo_id = dados.get("subgrupo_id")
    cbo_codigo = dados.get("cbo_codigo")
    if cbo_codigo in ("", "None", "null"):
        cbo_codigo = None
    periodo = dados.get("periodo")
    linhas = dados.get("linhas") or []

    if not indicador_id or not linhas:
        return jsonify({"ok": False, "erro": "Indicador e linhas para vincular são obrigatórios"}), 400

    ind = db.execute("SELECT codigo FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
    if not ind:
        return jsonify({"ok": False, "erro": "Indicador não encontrado"}), 404
    codigo_ind = ind["codigo"]

    qtd_vinculadas = 0
    for item in linhas:
        cp = str(item.get("cod_producao") or "").strip()
        prod = str(item.get("producao") or "").strip()
        serv = str(item.get("servico") or "").strip() or None
        dp_id = item.get("de_para_id")

        if not cp and not prod:
            continue

        if dp_id:
            db.execute("""
                UPDATE de_para_websaass_indicador
                SET indicador_id = ?, codigo_indicador = ?, subgrupo_id = ?, cbo_codigo = ?,
                    producao = COALESCE(NULLIF(?, ''), producao),
                    servico = COALESCE(NULLIF(?, ''), servico)
                WHERE id = ?
            """, (indicador_id, codigo_ind, subgrupo_id, cbo_codigo, prod, serv, dp_id))
            qtd_vinculadas += 1
        else:
            row = None
            if cp and serv:
                row = db.execute("""
                    SELECT id FROM de_para_websaass_indicador
                    WHERE lower(trim(cod_producao)) = lower(trim(?))
                      AND lower(trim(servico)) = lower(trim(?))
                    LIMIT 1
                """, (cp, serv)).fetchone()
            if not row and cp:
                row = db.execute("""
                    SELECT id FROM de_para_websaass_indicador
                    WHERE lower(trim(cod_producao)) = lower(trim(?))
                      AND servico IS NULL
                    LIMIT 1
                """, (cp,)).fetchone()
            if not row and prod:
                row = db.execute("""
                    SELECT id FROM de_para_websaass_indicador
                    WHERE lower(trim(producao)) = lower(trim(?))
                    LIMIT 1
                """, (prod,)).fetchone()

            if row:
                db.execute("""
                    UPDATE de_para_websaass_indicador
                    SET indicador_id = ?, codigo_indicador = ?, subgrupo_id = ?, cbo_codigo = ?,
                        cod_producao = COALESCE(NULLIF(?, ''), cod_producao),
                        producao = COALESCE(NULLIF(?, ''), producao),
                        servico = COALESCE(NULLIF(?, ''), servico)
                    WHERE id = ?
                """, (indicador_id, codigo_ind, subgrupo_id, cbo_codigo, cp, prod, serv, row["id"]))
            else:
                db.execute("""
                    INSERT INTO de_para_websaass_indicador (
                        cod_producao, producao, servico, codigo_indicador, cbo_codigo, indicador_id, subgrupo_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cp, prod, serv, codigo_ind, cbo_codigo, indicador_id, subgrupo_id))
            qtd_vinculadas += 1

    db.commit()

    # Recalcula WebSaass para todos os períodos do staging
    periodos_stg = [r[0] for r in db.execute("SELECT DISTINCT periodo FROM staging_webssas WHERE periodo IS NOT NULL").fetchall()]
    for p in periodos_stg:
        calcular_webssas(db, p)

    linhas_res = _resultados_com_status(db)
    linhas_atualizadas = [
        {
            "indicador_id": r["indicador_id"],
            "estabelecimento_id": r["estabelecimento_id"],
            "subgrupo_id": r.get("subgrupo_id"),
            "cbo_codigo": r.get("cbo_codigo"),
            "periodo": r.get("periodo"),
            "valor_apurado": r.get("valor_apurado"),
            "valor_declarado": r.get("valor_declarado"),
            "divergencia": r.get("divergencia"),
            "valor_meta": r.get("valor_meta"),
            "percentual_meta": r.get("percentual_meta"),
            "status_rotulo": r.get("status_rotulo"),
            "status_classe": r.get("status_classe"),
            "auditoria_rotulo": r.get("auditoria_rotulo"),
            "auditoria_classe": r.get("auditoria_classe"),
        }
        for r in linhas_res
        if r["indicador_id"] == indicador_id
    ]

    alertas = _contadores_alerta(db)

    return jsonify({
        "ok": True,
        "mensagem": f"{qtd_vinculadas} linha(s) vinculada(s) ao indicador {codigo_ind} com sucesso!",
        "linhas_atualizadas": linhas_atualizadas,
        "alertas": alertas,
    })


@bp.route("/websaass/desvincular_linha", methods=["POST"])
def websaass_desvincular_linha():
    db = get_db()
    dados = request.get_json(force=True) or {}
    de_para_id = dados.get("de_para_id")
    indicador_id = dados.get("indicador_id")

    if not de_para_id:
        return jsonify({"ok": False, "erro": "de_para_id é obrigatório"}), 400

    row = db.execute("SELECT indicador_id, codigo_indicador, cod_producao, producao FROM de_para_websaass_indicador WHERE id = ?", (de_para_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "erro": "Registro de vínculo não encontrado"}), 404

    ind_id_afetado = row["indicador_id"] or indicador_id

    db.execute("""
        UPDATE de_para_websaass_indicador
        SET indicador_id = NULL, codigo_indicador = NULL, subgrupo_id = NULL, cbo_codigo = NULL
        WHERE id = ?
    """, (de_para_id,))
    db.commit()

    periodos_stg = [r[0] for r in db.execute("SELECT DISTINCT periodo FROM staging_webssas WHERE periodo IS NOT NULL").fetchall()]
    for p in periodos_stg:
        calcular_webssas(db, p)

    linhas_res = _resultados_com_status(db)
    linhas_atualizadas = [
        {
            "indicador_id": r["indicador_id"],
            "estabelecimento_id": r["estabelecimento_id"],
            "subgrupo_id": r.get("subgrupo_id"),
            "cbo_codigo": r.get("cbo_codigo"),
            "periodo": r.get("periodo"),
            "valor_apurado": r.get("valor_apurado"),
            "valor_declarado": r.get("valor_declarado"),
            "divergencia": r.get("divergencia"),
            "valor_meta": r.get("valor_meta"),
            "percentual_meta": r.get("percentual_meta"),
            "status_rotulo": r.get("status_rotulo"),
            "status_classe": r.get("status_classe"),
            "auditoria_rotulo": r.get("auditoria_rotulo"),
            "auditoria_classe": r.get("auditoria_classe"),
        }
        for r in linhas_res
        if r["indicador_id"] == ind_id_afetado
    ]

    alertas = _contadores_alerta(db)

    return jsonify({
        "ok": True,
        "mensagem": f"Vínculo da linha '{row['cod_producao']} - {row['producao']}' desvinculado com sucesso!",
        "linhas_atualizadas": linhas_atualizadas,
        "alertas": alertas,
    })


@bp.route("/api/regra_profissional", methods=["GET"])
def api_regra_profissional():
    """Retorna detalhes da regra de profissional de um procedimento/subgrupo e os profissionais candidatos."""
    db = get_db()
    indicador_id = request.args.get("indicador_id")
    subgrupo_id = _subgrupo_da_linha(request.args.get("subgrupo_id"))
    procedimento_codigo = request.args.get("procedimento_codigo")
    estabelecimento_id = request.args.get("estabelecimento_id")
    periodo = _normalizar_periodo(request.args.get("periodo") or "")

    query = """
        SELECT ip.id, ip.indicador_id, ip.subgrupo_id, ip.procedimento_codigo, ip.nome_profissional,
               p.nome AS procedimento_nome, i.codigo AS indicador_codigo, i.nome AS indicador_nome,
               sg.nome AS subgrupo_nome
        FROM indicador_procedimento ip
        JOIN indicadores i ON i.id = ip.indicador_id
        LEFT JOIN indicador_subgrupo sg ON sg.id = ip.subgrupo_id
        LEFT JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
        WHERE ip.indicador_id = ?
    """
    params = [indicador_id]
    if subgrupo_id is not None:
        query += " AND ip.subgrupo_id = ?"
        params.append(subgrupo_id)
    if procedimento_codigo:
        query += " AND ip.procedimento_codigo = ?"
        params.append(procedimento_codigo)
    query += " ORDER BY (ip.nome_profissional IS NOT NULL AND ip.nome_profissional != '') DESC, ip.id ASC LIMIT 1"

    row = db.execute(query, params).fetchone()
    if not row:
        return jsonify({"ok": False, "erro": "Vínculo de procedimento não encontrado para este indicador/subgrupo."}), 404

    proc_cod = row["procedimento_codigo"]
    prof_atual = (row["nome_profissional"] or "").strip()

    candidatos = []
    candidatos_vistos = set()

    cmes_list = []
    if estabelecimento_id:
        cmes_row = db.execute("SELECT cod_cmes, cod_cnes FROM estabelecimentos WHERE id = ?", (estabelecimento_id,)).fetchone()
        if cmes_row:
            if cmes_row["cod_cmes"]: cmes_list.append(cmes_row["cod_cmes"])
            if cmes_row["cod_cnes"]: cmes_list.append(cmes_row["cod_cnes"])

    sql_stg = """
        SELECT nome_profissional, cod_cbo_sus, nome_cbo1, SUM(quantidade) AS total
        FROM staging_at02
        WHERE cod_procedimento = ? AND nome_profissional IS NOT NULL AND TRIM(nome_profissional) != ''
    """
    params_stg = [proc_cod]
    if cmes_list:
        sql_stg += f" AND (cod_cmes IN ({','.join('?' * len(cmes_list))}) OR cod_cnes IN ({','.join('?' * len(cmes_list))}))"
        params_stg.extend(cmes_list)
        params_stg.extend(cmes_list)
    if periodo:
        sql_stg += " AND ano_mes = ?"
        params_stg.append(periodo)
    sql_stg += " GROUP BY nome_profissional ORDER BY total DESC"

    stg_profs = db.execute(sql_stg, params_stg).fetchall()
    for sp in stg_profs:
        n = (sp["nome_profissional"] or "").strip()
        if n and n not in candidatos_vistos:
            candidatos_vistos.add(n)
            candidatos.append({
                "nome": n,
                "cbo_codigo": sp["cod_cbo_sus"],
                "cbo_nome": sp["nome_cbo1"],
                "quantidade_mes": int(sp["total"] or 0),
                "origem": "AT-02 da Unidade",
            })

    profs_cadastrados = db.execute(
        """SELECT nome, cbo_codigo FROM profissionais WHERE ativo = 1 ORDER BY nome ASC"""
    ).fetchall()
    for pc in profs_cadastrados:
        n = (pc["nome"] or "").strip()
        if n and n not in candidatos_vistos:
            candidatos_vistos.add(n)
            candidatos.append({
                "nome": n,
                "cbo_codigo": pc["cbo_codigo"],
                "cbo_nome": "",
                "quantidade_mes": 0,
                "origem": "Cadastro Geral",
            })

    return jsonify({
        "ok": True,
        "vinculo_id": row["id"],
        "indicador_id": row["indicador_id"],
        "indicador_codigo": row["indicador_codigo"],
        "indicador_nome": row["indicador_nome"],
        "subgrupo_id": row["subgrupo_id"],
        "subgrupo_nome": row["subgrupo_nome"],
        "procedimento_codigo": proc_cod,
        "procedimento_nome": row["procedimento_nome"] or f"Procedimento {proc_cod}",
        "profissional_atual": prof_atual,
        "candidatos": candidatos,
    })


@bp.route("/api/regra_profissional", methods=["POST"])
def api_salvar_regra_profissional():
    """Salva a regra de profissional para o procedimento e recalcula a apuração."""
    db = get_db()
    dados = request.get_json(silent=True) or request.form.to_dict()

    vinculo_id = dados.get("vinculo_id")
    indicador_id = dados.get("indicador_id")
    subgrupo_id = _subgrupo_da_linha(dados.get("subgrupo_id"))
    procedimento_codigo = dados.get("procedimento_codigo")
    novo_profissional = (dados.get("nome_profissional") or "").strip()
    periodo = _normalizar_periodo(dados.get("periodo") or "")

    if vinculo_id:
        db.execute(
            "UPDATE indicador_procedimento SET nome_profissional = ? WHERE id = ?",
            (novo_profissional or None, vinculo_id)
        )
    elif indicador_id and procedimento_codigo:
        db.execute(
            """UPDATE indicador_procedimento
               SET nome_profissional = ?
               WHERE indicador_id = ? AND (subgrupo_id IS ? OR subgrupo_id IS NULL)
                 AND procedimento_codigo = ?""",
            (novo_profissional or None, indicador_id, subgrupo_id, procedimento_codigo)
        )
    else:
        return jsonify({"ok": False, "erro": "Parâmetros insuficientes para atualizar a regra de profissional."}), 400

    db.commit()

    from ..funcoes import calcular_at02
    periodos_afetados = [periodo] if periodo else [
        r[0] for r in db.execute("SELECT DISTINCT ano_mes FROM staging_at02 WHERE ano_mes IS NOT NULL").fetchall()
    ]
    for p in periodos_afetados:
        if p:
            calcular_at02(db, p)

    linhas_res = _resultados_com_status(db)
    linhas_atualizadas = [
        {
            "indicador_id": r["indicador_id"],
            "estabelecimento_id": r["estabelecimento_id"],
            "subgrupo_id": r.get("subgrupo_id"),
            "cbo_codigo": r.get("cbo_codigo"),
            "periodo": r.get("periodo"),
            "valor_apurado": r.get("valor_apurado"),
            "valor_declarado": r.get("valor_declarado"),
            "divergencia": r.get("divergencia"),
            "valor_meta": r.get("valor_meta"),
            "percentual_meta": r.get("percentual_meta"),
            "status_rotulo": r.get("status_rotulo"),
            "status_classe": r.get("status_classe"),
            "auditoria_rotulo": r.get("auditoria_rotulo"),
            "auditoria_classe": r.get("auditoria_classe"),
        }
        for r in linhas_res
        if r["indicador_id"] == int(indicador_id or 0)
    ]

    alertas = _contadores_alerta(db)

    return jsonify({
        "ok": True,
        "mensagem": f"Regra atualizada com sucesso! Procedimento {procedimento_codigo or ''} atribuído ao profissional '{novo_profissional or 'Todos (sem restrição)'}'.",
        "novo_profissional": novo_profissional,
        "linhas_atualizadas": linhas_atualizadas,
        "alertas": alertas,
    })


