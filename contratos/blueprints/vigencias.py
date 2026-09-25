"""
Rotas para criar/editar um Termo Aditivo (metas) ou Portaria (indicadores).
Criar um novo pode clonar todo o conteúdo do anterior - conforme pedido:
'uma vez que um TA estiver completamente registrado, os demais poderão ser
atualizados manualmente, copiando todos os dados, bastando indicar o
número e o período de referência'.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..funcoes import consolidacao

bp = Blueprint("vigencias", __name__, url_prefix="/contratos/vigencias")


@bp.route("/")
def listar():
    """Tela avulsa antiga: agora só leva para a aba Portaria/TA do Painel de Administração
    (é para cá que voltam as ações de criar/editar/excluir Portaria e TA)."""
    return redirect(url_for("cadastros.administracao", aba="portaria"))


@bp.route("/consolidacao", methods=["POST"])
def salvar_consolidacao():
    """Atalho em massa da consolidação: aplica CMES (padrão) ou CNES a TODOS os indicadores de uma vez e
    guarda o modo como padrão dos indicadores novos. A escolha fina é POR INDICADOR (Indicadores >
    "Consolidar por CNES"). Vale na hora, sem recalcular - ver app/etl/consolidacao.py."""
    db = get_db()
    modo = (request.form.get("modo") or "").upper()
    try:
        qtd = consolidacao.aplicar_a_todos(db, modo)
        flash(
            f"{qtd} indicador(es) passaram a consolidar por CNES: cadastros que compartilham o mesmo CNES aparecem como uma unidade."
            if modo == "CNES" else f"{qtd} indicador(es) voltaram a consolidar por CMES (um estabelecimento por linha).",
            "sucesso",
        )
    except ValueError as erro:
        flash(str(erro), "erro")
    if request.form.get("voltar") == "painel":
        return redirect(url_for("painel.index"))
    return redirect(url_for("cadastros.administracao", aba="portaria"))


@bp.route("/ta/novo", methods=["POST"])
def novo_ta():
    """Cria um novo Termo Aditivo. Se ta_origem_id for informado, clona as metas."""
    numero = request.form.get("numero")
    periodo_inicio = request.form.get("periodo_inicio")
    periodo_fim = request.form.get("periodo_fim")
    ta_origem_id = request.form.get("ta_origem_id") or None

    db = get_db()
    cursor = db.execute(
        """INSERT INTO termos_aditivos (numero, periodo_inicio, periodo_fim, ta_origem_id)
           VALUES (?, ?, ?, ?)""",
        (numero, periodo_inicio, periodo_fim, ta_origem_id),
    )
    novo_id = cursor.lastrowid

    if ta_origem_id:
        db.execute(
            # subgrupo_id (v14) e rt/tipo_equipe/pmmb (v11) também vão junto - sem eles
            # as metas de subgrupos/segmentos diferentes colidiriam no índice único
            """INSERT INTO metas (ta_id, estabelecimento_id, indicador_id, cbo_codigo, valor_meta,
                                  subgrupo_id, rt, tipo_equipe, pmmb)
               SELECT ?, estabelecimento_id, indicador_id, cbo_codigo, valor_meta,
                      subgrupo_id, rt, tipo_equipe, pmmb
               FROM metas WHERE ta_id = ?""",
            (novo_id, ta_origem_id),
        )
        flash(f"Termo Aditivo {numero} criado, clonando as metas do TA de origem.", "sucesso")
    else:
        flash(f"Termo Aditivo {numero} criado (sem metas - cadastro do zero).", "sucesso")

    db.commit()
    return redirect(url_for("vigencias.listar"))


@bp.route("/ta/<int:ta_id>/editar", methods=["GET"])
def form_editar_ta(ta_id):
    db = get_db()
    ta = db.execute("SELECT * FROM termos_aditivos WHERE id=?", (ta_id,)).fetchone()
    return render_template("contratos/editar_ta.html", ta=ta)


@bp.route("/ta/<int:ta_id>/editar", methods=["POST"])
def editar_ta(ta_id):
    db = get_db()
    db.execute(
        "UPDATE termos_aditivos SET numero=?, periodo_inicio=?, periodo_fim=?, observacoes=? WHERE id=?",
        (
            request.form.get("numero"),
            request.form.get("periodo_inicio"),
            request.form.get("periodo_fim"),
            request.form.get("observacoes"),
            ta_id,
        ),
    )
    db.commit()
    flash("Termo Aditivo atualizado.", "sucesso")
    return redirect(url_for("vigencias.listar"))


@bp.route("/ta/<int:ta_id>/excluir", methods=["POST"])
def excluir_ta(ta_id):
    db = get_db()
    try:
        db.execute("DELETE FROM termos_aditivos WHERE id=?", (ta_id,))
        db.commit()
        flash("Termo Aditivo excluído.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(
            f"Não foi possível excluir: {exc}. Exclua ou mova as metas "
            "vinculadas a este TA antes, ou os TAs que o clonaram.",
            "erro",
        )
    return redirect(url_for("vigencias.listar"))


@bp.route("/portaria/nova", methods=["POST"])
def nova_portaria():
    """Cria uma nova Portaria. Se portaria_origem_id for informado, clona
    indicadores e seus vínculos (CBO e procedimento)."""
    numero = request.form.get("numero")
    periodo_inicio = request.form.get("periodo_inicio")
    periodo_fim = request.form.get("periodo_fim")
    portaria_origem_id = request.form.get("portaria_origem_id") or None

    db = get_db()
    cursor = db.execute(
        """INSERT INTO portarias (numero, periodo_inicio, periodo_fim, portaria_origem_id)
           VALUES (?, ?, ?, ?)""",
        (numero, periodo_inicio, periodo_fim, portaria_origem_id),
    )
    nova_portaria_id = cursor.lastrowid

    if portaria_origem_id:
        indicadores_origem = db.execute(
            "SELECT * FROM indicadores WHERE portaria_id = ?", (portaria_origem_id,)
        ).fetchall()

        for ind in indicadores_origem:
            novo_ind = db.execute(
                """INSERT INTO indicadores (portaria_id, codigo, nome, tipo, complexidade, servico)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (nova_portaria_id, ind["codigo"], ind["nome"], ind["tipo"],
                 ind["complexidade"], ind["servico"]),
            )
            novo_indicador_id = novo_ind.lastrowid

            db.execute(
                """INSERT INTO indicador_cbo (indicador_id, cbo_codigo, curinga)
                   SELECT ?, cbo_codigo, curinga FROM indicador_cbo WHERE indicador_id = ?""",
                (novo_indicador_id, ind["id"]),
            )
            db.execute(
                """INSERT INTO indicador_procedimento (
                       indicador_id, procedimento_codigo, tipo_vinculo,
                       categoria_estabelecimento, categoria_estabelecimento_neg,
                       estabelecimento_id, estabelecimento_id_neg)
                   SELECT ?, procedimento_codigo, tipo_vinculo,
                          categoria_estabelecimento, categoria_estabelecimento_neg,
                          estabelecimento_id, estabelecimento_id_neg
                   FROM indicador_procedimento WHERE indicador_id = ?""",
                (novo_indicador_id, ind["id"]),
            )

        flash(
            f"Portaria {numero} criada, clonando {len(indicadores_origem)} "
            "indicadores e seus vínculos da portaria de origem.",
            "sucesso",
        )
    else:
        flash(f"Portaria {numero} criada (sem indicadores - cadastro do zero).", "sucesso")

    db.commit()
    return redirect(url_for("vigencias.listar"))


@bp.route("/portaria/<int:portaria_id>/editar", methods=["GET"])
def form_editar_portaria(portaria_id):
    db = get_db()
    portaria = db.execute("SELECT * FROM portarias WHERE id=?", (portaria_id,)).fetchone()
    return render_template("contratos/editar_portaria.html", portaria=portaria)


@bp.route("/portaria/<int:portaria_id>/editar", methods=["POST"])
def editar_portaria(portaria_id):
    db = get_db()
    db.execute(
        "UPDATE portarias SET numero=?, periodo_inicio=?, periodo_fim=?, observacoes=? WHERE id=?",
        (
            request.form.get("numero"),
            request.form.get("periodo_inicio"),
            request.form.get("periodo_fim"),
            request.form.get("observacoes"),
            portaria_id,
        ),
    )
    db.commit()
    flash("Portaria atualizada.", "sucesso")
    return redirect(url_for("vigencias.listar"))


@bp.route("/portaria/<int:portaria_id>/excluir", methods=["POST"])
def excluir_portaria(portaria_id):
    """
    Exclui a Portaria EM CASCATA, numa única transação: metas, regras de pool, apuração (fato_apuracao) e
    vínculos dos indicadores (procedimento, CBO, exceções, profissionais, subgrupos), depois os indicadores e
    por fim a portaria. Antes dava FOREIGN KEY constraint failed e era preciso apagar indicador por indicador.
    Se a portaria for a ORIGEM de outra portaria clonada, não exclui e diz qual tratar primeiro.
    Qualquer erro desfaz tudo (rollback) - nunca fica meio apagada.
    """
    db = get_db()
    portaria = db.execute("SELECT * FROM portarias WHERE id=?", (portaria_id,)).fetchone()
    if not portaria:
        flash("Portaria não encontrada.", "erro")
        return redirect(url_for("vigencias.listar"))

    clones = db.execute(
        "SELECT numero FROM portarias WHERE portaria_origem_id = ? ORDER BY numero", (portaria_id,)
    ).fetchall()
    if clones:
        nomes = ", ".join(f"'{c['numero']}'" for c in clones)
        flash(
            f"Não é possível excluir a Portaria '{portaria['numero']}': ela é a origem da(s) Portaria(s) {nomes} "
            f"(criada(s) como cópia dela). Trate {'essa portaria' if len(clones) == 1 else 'essas portarias'} primeiro "
            "(exclua-a ou edite-a para trocar a portaria de origem) e tente de novo.",
            "erro",
        )
        return redirect(url_for("vigencias.listar"))

    ids_ind = "(SELECT id FROM indicadores WHERE portaria_id = ?)"
    # ordem: dependências dos indicadores -> subgrupos -> indicadores -> portaria (tabelas que o banco ainda não
    # tenha, em bancos antigos, são ignoradas)
    ordem = (
        "metas", "regras_pool_unidades", "fato_apuracao", "indicador_procedimento", "indicador_cbo_excecao",
        "indicador_cbo", "indicador_estabelecimento_excecao", "indicador_estabelecimento_cnes_alternativo",
        "indicador_profissional", "indicador_subgrupo",
    )
    try:
        existentes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        removidos = {}
        for tabela in ordem:
            if tabela in existentes:
                removidos[tabela] = db.execute(
                    f"DELETE FROM {tabela} WHERE indicador_id IN {ids_ind}", (portaria_id,)
                ).rowcount
        qtd_ind = db.execute("DELETE FROM indicadores WHERE portaria_id = ?", (portaria_id,)).rowcount
        db.execute("DELETE FROM portarias WHERE id = ?", (portaria_id,))
        db.commit()
        flash(
            f"Portaria '{portaria['numero']}' excluída em cascata: {qtd_ind} indicador(es), "
            f"{removidos.get('metas', 0)} meta(s), {removidos.get('indicador_procedimento', 0)} vínculo(s) de procedimento, "
            f"{removidos.get('indicador_cbo', 0)} vínculo(s) de CBO e {removidos.get('fato_apuracao', 0)} linha(s) de apuração "
            "(recalcule os períodos se precisar delas de novo).",
            "sucesso",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(f"Não foi possível excluir a Portaria (nada foi apagado): {exc}", "erro")
    return redirect(url_for("vigencias.listar"))
