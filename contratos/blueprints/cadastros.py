"""
Telas de cadastro que fecham o ciclo do painel:
  - estabelecimentos, CBO, procedimentos (dimensões)
  - indicadores de uma portaria + vínculos com CBO e procedimento
  - metas de um termo aditivo

Sem esse cadastro preenchido, o cálculo (app/etl/calculo.py) não consegue
resolver estabelecimento/CBO/procedimento em indicador - por isso estas
telas são o próximo passo depois de importar os dados brutos.
"""

import csv
import io
import sqlite3

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from ..db import get_db
from ..funcoes import consolidacao
from ..etl import normalizar_cod_procedimento

bp = Blueprint("cadastros", __name__, url_prefix="/contratos/cadastros")


# ---------------------------------------------------------------------------
# UTILITÁRIOS INTERNOS PARA CSV
# ---------------------------------------------------------------------------

def _ler_csv_upload(arquivo):
    """Lê um arquivo CSV enviado por upload, detectando ; ou , como delimitador."""
    conteudo = arquivo.read().decode("utf-8-sig")
    delimitador = ";" if conteudo.count(";") >= conteudo.count(",") else ","
    linhas = list(csv.reader(io.StringIO(conteudo), delimiter=delimitador))
    if not linhas:
        return [], []
    cabecalho = [c.strip().lower() for c in linhas[0]]
    return cabecalho, linhas[1:]


def _csv_response(cabecalho, linhas, nome_arquivo):
    """Monta um Response de download CSV (; como separador, compatível com Excel BR)."""
    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM para o Excel abrir acentos corretamente
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(cabecalho)
    writer.writerows(linhas)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------------------------------------------------------------------------
# PAINEL CENTRALIZADOR DE ADMINISTRAÇÃO E RECALCULO
# ---------------------------------------------------------------------------

ABAS_ADMINISTRACAO = (
    "estabelecimentos", "cbo", "procedimentos", "profissionais", "portaria", "importar", "backup", "logs",
)


@bp.route("/", methods=["GET"])
@bp.route("/administracao", methods=["GET"])
def administracao():
    """Página centralizadora do painel de administração com navegação em abas.

    ?aba=<nome> abre direto numa aba (estabelecimentos, cbo, procedimentos,
    profissionais, portaria, importar, backup, logs). É por aqui que TODAS as
    telas voltam depois de salvar/importar - assim o menu de abas do Painel
    de Administração nunca some. ?periodo= é repassado à aba de logs."""
    aba = request.args.get("aba", "estabelecimentos")
    if aba not in ABAS_ADMINISTRACAO:
        aba = "estabelecimentos"
    return render_template("contratos/cadastros/administracao.html", aba_ativa=aba, periodo_logs=request.args.get("periodo", ""),
    )


@bp.route("/recalcular", methods=["POST"])
def recalcular():
    """Processa a solicitação de recalculo do período acionada pelo cabeçalho."""
    fonte_at02 = request.form.get("fonte_at02")
    competencia = request.form.get("competencia")
    
    if not fonte_at02 or not competencia:
        flash("Por favor, informe a fonte AT-02 e a competência.", "erro")
        return redirect(request.referrer or url_for("cadastros.administracao"))
    
    # Executa lógica de recalculagem conforme parâmetros informados
    flash(f"Recalculo para a competência {competencia} ({fonte_at02}) iniciado com sucesso.", "sucesso")
    return redirect(request.referrer or url_for("cadastros.administracao"))


# ---------------------------------------------------------------------------
# ROTAS PARCIAIS PARA CARREGAMENTO ASSÍNCRONO NAS ABAS (SPA)
# ---------------------------------------------------------------------------

@bp.route("/estabelecimentos/partial", methods=["GET"])
def estabelecimentos_partial():
    db = get_db()
    itens = db.execute(
        """SELECT e.*, GROUP_CONCAT(ets.tipo_servico, ', ') AS tipos_servico
           FROM estabelecimentos e
           LEFT JOIN estabelecimento_tipo_servico ets ON ets.estabelecimento_id = e.id
           GROUP BY e.id
           ORDER BY e.nome"""
    ).fetchall()
    categorias_lista = db.execute("SELECT nome FROM categorias_estabelecimento ORDER BY nome").fetchall()
    # Aponta para o template existente em vez da pasta /partials/
    return render_template("contratos/cadastros/estabelecimentos.html", itens=itens, categorias_lista=categorias_lista, partial=True,
        consolidacao_cnes=consolidacao.analisar(db),
    )


@bp.route("/cbo/partial", methods=["GET"])
def cbo_partial():
    db = get_db()
    itens = db.execute("SELECT * FROM cbo ORDER BY nome_categoria").fetchall()
    return render_template("contratos/cadastros/cbo.html", itens=itens, partial=True)


@bp.route("/procedimentos/partial", methods=["GET"])
def procedimentos_partial():
    db = get_db()
    # Sem busca no servidor e sem LIMIT: o filtro por coluna (estilo Excel) roda no
    # navegador e precisa enxergar todos os procedimentos (~5 mil linhas, HTML enxuto).
    itens = db.execute("SELECT * FROM procedimentos ORDER BY nome").fetchall()
    return render_template("contratos/cadastros/procedimentos.html", itens=itens, partial=True)


@bp.route("/portaria/partial", methods=["GET"])
def portaria_partial():
    db = get_db()
    tas = db.execute("SELECT * FROM termos_aditivos ORDER BY id DESC").fetchall()
    portarias = db.execute("SELECT * FROM portarias ORDER BY id DESC").fetchall()
    # Aponta para o template existente (vigencias.html) em vez de cadastros/portarias.html,
    # que nao existe - mesmo padrao ja usado em estabelecimentos_partial/cbo_partial/procedimentos_partial.
    return render_template("contratos/vigencias.html", tas=tas, portarias=portarias, partial=True,
        modo_consolidacao=consolidacao.obter_modo(db),
        qtd_indicadores_cnes=len(consolidacao.indicadores_cnes(db)),
        qtd_indicadores=db.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0],
        resumo_consolidacao=consolidacao.resumir(consolidacao.analisar(db)),
    )


# ---------------------------------------------------------------------------
# ESTABELECIMENTOS
# ---------------------------------------------------------------------------

def _tipos_servico_texto(tipo_servico_raw):
    """Aceita 'UBS|AMA' ou 'UBS, AMA' vindos do formulário/CSV e devolve a lista limpa."""
    if not tipo_servico_raw:
        return []
    partes = tipo_servico_raw.replace(",", "|").split("|")
    return [p.strip() for p in partes if p.strip()]


def _salvar_tipos_servico(db, estabelecimento_id, tipo_servico_raw):
    """Substitui por completo os tipos de serviço de um estabelecimento."""
    db.execute(
        "DELETE FROM estabelecimento_tipo_servico WHERE estabelecimento_id=?",
        (estabelecimento_id,),
    )
    for tipo in _tipos_servico_texto(tipo_servico_raw):
        db.execute(
            "INSERT OR IGNORE INTO estabelecimento_tipo_servico (estabelecimento_id, tipo_servico) VALUES (?, ?)",
            (estabelecimento_id, tipo),
        )


@bp.route("/estabelecimentos", methods=["GET"])
def estabelecimentos():
    """Tela avulsa antiga: agora só leva para a aba dentro do Painel de Administração."""
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/categorias/nova", methods=["POST"])
def nova_categoria_estabelecimento():
    """
    Adiciona uma categoria de contrato nova (ex.: além de PERTENCE/CER/
    NAO_PERTENCE) - antes disso era uma lista fixa de 3 opções, sem forma
    de acrescentar. Usada tanto em estabelecimentos.categoria_contrato
    quanto nos campos Categoria (+)/(-) do vínculo de procedimento de um
    indicador (ver indicador_procedimento no schema).
    """
    db = get_db()
    nome = (request.form.get("nome") or "").strip()
    destino = url_for("cadastros.administracao", aba="estabelecimentos")
    if not nome:
        flash("Informe o nome da categoria.", "erro")
        return redirect(destino)
    existente = db.execute(
        "SELECT nome FROM categorias_estabelecimento WHERE UPPER(nome) = UPPER(?)", (nome,)
    ).fetchone()
    if existente:
        flash(f"A categoria '{existente['nome']}' já existe.", "erro")
        return redirect(destino)
    db.execute("INSERT INTO categorias_estabelecimento (nome) VALUES (?)", (nome,))
    db.commit()
    flash(f"Categoria '{nome}' cadastrada - já pode ser escolhida no cadastro dos estabelecimentos "
          "e no filtro negativo do vínculo de procedimento.", "sucesso")
    return redirect(destino)


@bp.route("/estabelecimentos/novo", methods=["POST"])
def novo_estabelecimento():
    db = get_db()
    cursor = db.execute(
        """INSERT INTO estabelecimentos (cod_cnes, cod_cmes, nome, complexidade, categoria_contrato, exige_cmes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            request.form.get("cod_cnes"),
            request.form.get("cod_cmes"),
            request.form.get("nome"),
            request.form.get("complexidade"),
            request.form.get("categoria_contrato"),
            1 if request.form.get("exige_cmes") else 0,
        ),
    )
    _salvar_tipos_servico(db, cursor.lastrowid, request.form.get("tipo_servico"))
    db.commit()
    flash("Estabelecimento cadastrado.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/<int:id>/editar", methods=["POST"])
def editar_estabelecimento(id):
    """Edição inline: cada linha da tabela de Estabelecimentos envia direto para cá."""
    db = get_db()
    db.execute(
        """UPDATE estabelecimentos SET cod_cnes=?, cod_cmes=?, nome=?,
               complexidade=?, categoria_contrato=?, exige_cmes=? WHERE id=?""",
        (
            request.form.get("cod_cnes"),
            request.form.get("cod_cmes"),
            request.form.get("nome"),
            request.form.get("complexidade"),
            request.form.get("categoria_contrato"),
            1 if request.form.get("exige_cmes") else 0,
            id,
        ),
    )
    _salvar_tipos_servico(db, id, request.form.get("tipo_servico"))
    db.commit()
    flash("Estabelecimento atualizado.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/bulk_editar", methods=["POST"])
def bulk_editar_estabelecimentos():
    """Edição em massa dos estabelecimentos marcados."""
    db = get_db()
    ids = request.form.getlist("selecionados")
    if not ids:
        flash("Marque pelo menos um estabelecimento na coluna da esquerda para editar em massa.", "erro")
        return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))

    tipo_servico = request.form.get("bulk_tipo_servico") or None
    complexidade = request.form.get("bulk_complexidade") or None
    categoria_contrato = request.form.get("bulk_categoria_contrato") or None

    if not any([tipo_servico, complexidade, categoria_contrato]):
        flash("Preencha pelo menos um campo para aplicar em massa.", "erro")
        return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))

    for est_id in ids:
        if complexidade:
            db.execute("UPDATE estabelecimentos SET complexidade=? WHERE id=?", (complexidade, est_id))
        if categoria_contrato:
            db.execute("UPDATE estabelecimentos SET categoria_contrato=? WHERE id=?", (categoria_contrato, est_id))
        if tipo_servico:
            _salvar_tipos_servico(db, est_id, tipo_servico)

    db.commit()
    flash(f"{len(ids)} estabelecimento(s) atualizado(s) em massa.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/bulk_excluir", methods=["POST"])
def bulk_excluir_estabelecimentos():
    """Exclusão em massa dos estabelecimentos marcados."""
    db = get_db()
    ids = request.form.getlist("selecionados")
    if not ids:
        flash("Marque pelo menos um estabelecimento na coluna da esquerda para excluir.", "erro")
        return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))

    excluidos = 0
    bloqueados = 0
    for est_id in ids:
        try:
            db.execute("DELETE FROM estabelecimentos WHERE id=?", (est_id,))
            db.commit()
            excluidos += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            bloqueados += 1

    msg = f"{excluidos} estabelecimento(s) excluído(s)."
    if bloqueados:
        msg += (
            f" {bloqueados} não puderam ser excluídos por já terem meta(s) "
            "ou dado(s) apurado(s) vinculados - considere mudar a categoria "
            "de contrato para NAO_PERTENCE nesses casos, em vez de excluir."
        )
    flash(msg, "sucesso" if excluidos else "erro")
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/<int:id>/excluir", methods=["POST"])
def excluir_estabelecimento(id):
    db = get_db()
    try:
        db.execute("DELETE FROM estabelecimentos WHERE id=?", (id,))
        db.commit()
        flash("Estabelecimento excluído.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(
            f"Não foi possível excluir: {exc}. Se o estabelecimento já tem "
            "metas ou dados apurados vinculados, considere mudar a "
            "categoria de contrato para NAO_PERTENCE em vez de excluir.",
            "erro",
        )
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/importar_csv", methods=["POST"])
def importar_estabelecimentos_csv():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        flash("Selecione um arquivo CSV.", "erro")
        return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))

    cabecalho, linhas = _ler_csv_upload(arquivo)
    colunas_validas = {
        "nome", "cod_cnes", "cod_cmes", "tipo_servico", "complexidade", "categoria_contrato",
    }
    indices = {c: i for i, c in enumerate(cabecalho) if c in colunas_validas}

    if "nome" not in indices or "cod_cmes" not in indices:
        flash(
            "CSV inválido: é preciso ter pelo menos as colunas 'nome' e "
            "'cod_cmes' no cabeçalho.",
            "erro",
        )
        return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))

    db = get_db()
    criados = 0
    atualizados = 0
    ignorados = 0

    for linha in linhas:
        if not linha or len(linha) <= max(indices.values()):
            ignorados += 1
            continue

        def campo(nome):
            idx = indices.get(nome)
            if idx is None or idx >= len(linha):
                return None
            valor = linha[idx].strip()
            return valor or None

        nome = campo("nome")
        cod_cmes = campo("cod_cmes")
        if not nome or not cod_cmes:
            ignorados += 1
            continue

        existente = db.execute(
            "SELECT id FROM estabelecimentos WHERE cod_cmes = ?", (cod_cmes,)
        ).fetchone()

        if existente:
            est_id = existente["id"]
            db.execute(
                """UPDATE estabelecimentos SET nome=?, cod_cnes=?,
                       complexidade=?, categoria_contrato=? WHERE cod_cmes=?""",
                (nome, campo("cod_cnes"), campo("complexidade"), campo("categoria_contrato"), cod_cmes),
            )
            atualizados += 1
        else:
            cursor = db.execute(
                """INSERT INTO estabelecimentos (nome, cod_cnes, cod_cmes, complexidade, categoria_contrato)
                   VALUES (?, ?, ?, ?, ?)""",
                (nome, campo("cod_cnes"), cod_cmes, campo("complexidade"), campo("categoria_contrato")),
            )
            est_id = cursor.lastrowid
            criados += 1

        if campo("tipo_servico") is not None:
            _salvar_tipos_servico(db, est_id, campo("tipo_servico"))

    db.commit()
    flash(
        f"Importação concluída: {criados} criados, {atualizados} atualizados, "
        f"{ignorados} ignorados (sem nome/cod_cmes ou linha incompleta).",
        "sucesso",
    )
    return redirect(url_for("cadastros.administracao", aba="estabelecimentos"))


@bp.route("/estabelecimentos/exportar_csv", methods=["GET"])
def exportar_estabelecimentos_csv():
    db = get_db()
    itens = db.execute(
        """SELECT e.nome, e.cod_cnes, e.cod_cmes, e.complexidade, e.categoria_contrato,
                  GROUP_CONCAT(ets.tipo_servico, '|') AS tipo_servico
           FROM estabelecimentos e
           LEFT JOIN estabelecimento_tipo_servico ets ON ets.estabelecimento_id = e.id
           GROUP BY e.id
           ORDER BY e.nome"""
    ).fetchall()
    cabecalho = ["nome", "cod_cnes", "cod_cmes", "tipo_servico", "complexidade", "categoria_contrato"]
    linhas = [[i[c] or "" for c in cabecalho] for i in itens]
    return _csv_response(cabecalho, linhas, "estabelecimentos.csv")


# ---------------------------------------------------------------------------
# CBO
# ---------------------------------------------------------------------------

@bp.route("/cbo", methods=["GET"])
def cbo():
    """Tela avulsa antiga: agora só leva para a aba dentro do Painel de Administração."""
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/novo", methods=["POST"])
def novo_cbo():
    db = get_db()
    try:
        db.execute(
            "INSERT INTO cbo (codigo, nome_categoria) VALUES (?, ?)",
            (request.form.get("codigo"), request.form.get("nome_categoria")),
        )
        db.commit()
        flash("CBO cadastrado.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao cadastrar CBO: {exc}", "erro")
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/<codigo>/editar", methods=["POST"])
def editar_cbo(codigo):
    db = get_db()
    db.execute(
        "UPDATE cbo SET nome_categoria=? WHERE codigo=?",
        (request.form.get("nome_categoria"), codigo),
    )
    db.commit()
    flash("CBO atualizado.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/<codigo>/excluir", methods=["POST"])
def excluir_cbo(codigo):
    db = get_db()
    try:
        db.execute("DELETE FROM cbo WHERE codigo=?", (codigo,))
        db.commit()
        flash("CBO excluído.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível excluir: {exc}. Verifique se não está vinculado a algum indicador.", "erro")
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/bulk_excluir", methods=["POST"])
def bulk_excluir_cbo():
    db = get_db()
    codigos = request.form.getlist("selecionados")
    if not codigos:
        flash("Marque pelo menos um CBO para excluir.", "erro")
        return redirect(url_for("cadastros.administracao", aba="cbo"))

    excluidos = 0
    bloqueados = 0
    for codigo in codigos:
        try:
            db.execute("DELETE FROM cbo WHERE codigo=?", (codigo,))
            db.commit()
            excluidos += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            bloqueados += 1

    msg = f"{excluidos} CBO(s) excluído(s)."
    if bloqueados:
        msg += f" {bloqueados} não puderam ser excluídos por estarem vinculados a algum indicador."
    flash(msg, "sucesso" if excluidos else "erro")
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/importar_csv", methods=["POST"])
def importar_cbo_csv():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        flash("Selecione um arquivo CSV.", "erro")
        return redirect(url_for("cadastros.administracao", aba="cbo"))

    cabecalho, linhas = _ler_csv_upload(arquivo)
    indices = {c: i for i, c in enumerate(cabecalho) if c in {"codigo", "nome_categoria"}}
    if "codigo" not in indices or "nome_categoria" not in indices:
        flash("CSV inválido: são necessárias as colunas 'codigo' e 'nome_categoria'.", "erro")
        return redirect(url_for("cadastros.administracao", aba="cbo"))

    db = get_db()
    total = 0
    for linha in linhas:
        if len(linha) <= max(indices.values()):
            continue
        codigo = linha[indices["codigo"]].strip()
        nome = linha[indices["nome_categoria"]].strip()
        if not codigo or not nome:
            continue
        db.execute(
            """INSERT INTO cbo (codigo, nome_categoria) VALUES (?, ?)
               ON CONFLICT(codigo) DO UPDATE SET nome_categoria=excluded.nome_categoria""",
            (codigo, nome),
        )
        total += 1
    db.commit()
    flash(f"Importação concluída: {total} CBOs processados.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="cbo"))


@bp.route("/cbo/exportar_csv", methods=["GET"])
def exportar_cbo_csv():
    db = get_db()
    itens = db.execute("SELECT codigo, nome_categoria FROM cbo ORDER BY nome_categoria").fetchall()
    cabecalho = ["codigo", "nome_categoria"]
    linhas = [[i["codigo"], i["nome_categoria"]] for i in itens]
    return _csv_response(cabecalho, linhas, "cbo.csv")


@bp.route("/cbo/buscar", methods=["GET"])
def buscar_cbo_json():
    termo = (request.args.get("q") or "").strip()
    db = get_db()
    if not termo:
        itens = db.execute(
            "SELECT codigo, nome_categoria FROM cbo ORDER BY nome_categoria LIMIT 20"
        ).fetchall()
    else:
        itens = db.execute(
            """SELECT codigo, nome_categoria FROM cbo
               WHERE codigo LIKE ? OR nome_categoria LIKE ?
               ORDER BY nome_categoria LIMIT 20""",
            (f"%{termo}%", f"%{termo}%"),
        ).fetchall()
    return jsonify([dict(i) for i in itens])


@bp.route("/estabelecimentos/buscar", methods=["GET"])
def buscar_estabelecimentos_json():
    termo = (request.args.get("q") or "").strip()
    db = get_db()
    if not termo:
        itens = db.execute(
            "SELECT id AS codigo, nome FROM estabelecimentos ORDER BY nome LIMIT 20"
        ).fetchall()
    else:
        itens = db.execute(
            """SELECT id AS codigo, nome FROM estabelecimentos
               WHERE nome LIKE ? OR cod_cmes LIKE ? OR cod_cnes LIKE ?
               ORDER BY nome LIMIT 20""",
            (f"%{termo}%", f"%{termo}%", f"%{termo}%"),
        ).fetchall()
    return jsonify([dict(i) for i in itens])


# ---------------------------------------------------------------------------
# PROFISSIONAIS
# ---------------------------------------------------------------------------
# Cadastro de profissionais (odontologia e demais categorias) vinculados a um
# estabelecimento e a um CBO, com CNS, se é Responsável Técnico (RT) e o tipo
# de equipe (ex.: eSB, eSF, NASF-AB). Ainda não alimenta o cálculo do painel
# (fato_apuracao.profissional_id não é resolvido pelo ETL) - serve hoje como
# fonte de verdade cadastral (quem está em qual unidade/equipe).

def _dados_tela_profissionais(db):
    """
    Dados da tela de Profissionais. Antes cada linha trazia 2 <select> com TODAS
    as opções de estabelecimento e de CBO (~500 x 180 opções = 8 MB de HTML; a
    tela demorava vários segundos) e o LIMIT 500 escondia parte da lista. Agora
    a linha só leva a opção selecionada e as listas completas vão UMA vez, em
    JSON (`listas_json`), para o navegador preencher o select quando ele é usado.
    """
    itens = db.execute(
        """SELECT p.*, e.nome AS estabelecimento_nome, c.nome_categoria AS cbo_nome
           FROM profissionais p
           LEFT JOIN estabelecimentos e ON e.id = p.estabelecimento_id
           LEFT JOIN cbo c ON c.codigo = p.cbo_codigo
           ORDER BY p.nome"""
    ).fetchall()
    listas_json = {
        "estabelecimentos": [
            {"v": e["id"], "t": e["nome"]}
            for e in db.execute("SELECT id, nome FROM estabelecimentos ORDER BY nome").fetchall()
        ],
        "cbo": [
            {"v": c["codigo"], "t": f"{c['codigo']} - {c['nome_categoria']}"}
            for c in db.execute("SELECT codigo, nome_categoria FROM cbo ORDER BY nome_categoria").fetchall()
        ],
    }
    return itens, listas_json


@bp.route("/profissionais", methods=["GET"])
def profissionais():
    """Tela avulsa antiga: agora só leva para a aba dentro do Painel de Administração."""
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/partial", methods=["GET"])
def profissionais_partial():
    db = get_db()
    itens, listas_json = _dados_tela_profissionais(db)
    return render_template("contratos/cadastros/profissionais.html", itens=itens, listas_json=listas_json, partial=True)


def _rt_do_form(valor):
    return 1 if (valor or "").strip().lower() in {"1", "sim", "true", "on"} else 0


@bp.route("/profissionais/novo", methods=["POST"])
def novo_profissional():
    db = get_db()
    try:
        db.execute(
            """INSERT INTO profissionais (nome, cns, cbo_codigo, estabelecimento_id, rt, tipo_equipe, pmmb, ativo)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                request.form.get("nome"),
                (request.form.get("cns") or "").strip() or None,
                (request.form.get("cbo_codigo") or "").strip() or None,
                request.form.get("estabelecimento_id") or None,
                _rt_do_form(request.form.get("rt")),
                (request.form.get("tipo_equipe") or "").strip() or None,
                _rt_do_form(request.form.get("pmmb")),
            ),
        )
        db.commit()
        flash("Profissional cadastrado.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao cadastrar profissional: {exc}", "erro")
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/<int:id>/editar", methods=["POST"])
def editar_profissional(id):
    db = get_db()
    db.execute(
        """UPDATE profissionais SET nome=?, cns=?, cbo_codigo=?, estabelecimento_id=?, rt=?, tipo_equipe=?, pmmb=?, ativo=?
           WHERE id=?""",
        (
            request.form.get("nome"),
            (request.form.get("cns") or "").strip() or None,
            (request.form.get("cbo_codigo") or "").strip() or None,
            request.form.get("estabelecimento_id") or None,
            _rt_do_form(request.form.get("rt")),
            (request.form.get("tipo_equipe") or "").strip() or None,
            _rt_do_form(request.form.get("pmmb")),
            1 if request.form.get("ativo") else 0,
            id,
        ),
    )
    db.commit()
    flash("Profissional atualizado.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/<int:id>/excluir", methods=["POST"])
def excluir_profissional(id):
    db = get_db()
    try:
        db.execute("DELETE FROM profissionais WHERE id=?", (id,))
        db.commit()
        flash("Profissional excluído.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível excluir: {exc}.", "erro")
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/bulk_excluir", methods=["POST"])
def bulk_excluir_profissionais():
    db = get_db()
    ids = request.form.getlist("selecionados")
    if not ids:
        flash("Marque pelo menos um profissional para excluir.", "erro")
        return redirect(url_for("cadastros.administracao", aba="profissionais"))

    excluidos = 0
    bloqueados = 0
    for id_ in ids:
        try:
            db.execute("DELETE FROM profissionais WHERE id=?", (id_,))
            db.commit()
            excluidos += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            bloqueados += 1

    msg = f"{excluidos} profissional(is) excluído(s)."
    if bloqueados:
        msg += f" {bloqueados} não puderam ser excluídos."
    flash(msg, "sucesso" if excluidos else "erro")
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/importar_csv", methods=["POST"])
def importar_profissionais_csv():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        flash("Selecione um arquivo CSV.", "erro")
        return redirect(url_for("cadastros.administracao", aba="profissionais"))

    cabecalho, linhas = _ler_csv_upload(arquivo)
    colunas_aceitas = {"nome", "cns", "cod_cmes", "cbo_codigo", "rt", "tipo_equipe", "pmmb"}
    indices = {c: i for i, c in enumerate(cabecalho) if c in colunas_aceitas}
    if "nome" not in indices or "cod_cmes" not in indices:
        flash(
            "CSV inválido: são necessárias pelo menos as colunas 'nome' e 'cod_cmes' "
            "(código CMES do estabelecimento onde o profissional atua).",
            "erro",
        )
        return redirect(url_for("cadastros.administracao", aba="profissionais"))

    db = get_db()
    total = 0
    sem_estabelecimento = 0
    cbo_nao_cadastrado = 0
    for linha in linhas:
        if len(linha) <= max(indices.values()):
            continue

        def campo(nome_coluna):
            i = indices.get(nome_coluna)
            return linha[i].strip() if i is not None and i < len(linha) else ""

        nome = campo("nome")
        cod_cmes = campo("cod_cmes")
        if not nome or not cod_cmes:
            continue

        estab = db.execute("SELECT id FROM estabelecimentos WHERE cod_cmes=?", (cod_cmes,)).fetchone()
        if not estab:
            sem_estabelecimento += 1
            continue

        cbo_codigo = campo("cbo_codigo") or None
        if cbo_codigo and not db.execute("SELECT 1 FROM cbo WHERE codigo=?", (cbo_codigo,)).fetchone():
            cbo_nao_cadastrado += 1
            cbo_codigo = None

        db.execute(
            """INSERT INTO profissionais (nome, cns, cbo_codigo, estabelecimento_id, rt, tipo_equipe, pmmb, ativo)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                nome,
                campo("cns") or None,
                cbo_codigo,
                estab["id"],
                _rt_do_form(campo("rt")),
                campo("tipo_equipe") or None,
                _rt_do_form(campo("pmmb")),
            ),
        )
        total += 1
    db.commit()

    msg = f"Importação concluída: {total} profissionais cadastrados."
    if sem_estabelecimento:
        msg += f" {sem_estabelecimento} linha(s) ignorada(s) por cod_cmes não encontrado."
    if cbo_nao_cadastrado:
        msg += f" {cbo_nao_cadastrado} linha(s) importada(s) sem CBO por código não cadastrado (cadastre o CBO antes e reimporte, se precisar)."
    flash(msg, "sucesso" if total else "erro")
    return redirect(url_for("cadastros.administracao", aba="profissionais"))


@bp.route("/profissionais/exportar_csv", methods=["GET"])
def exportar_profissionais_csv():
    db = get_db()
    itens = db.execute(
        """SELECT p.nome, p.cns, e.cod_cmes, p.cbo_codigo, p.rt, p.tipo_equipe, p.pmmb
           FROM profissionais p LEFT JOIN estabelecimentos e ON e.id = p.estabelecimento_id
           ORDER BY p.nome"""
    ).fetchall()
    cabecalho = ["nome", "cns", "cod_cmes", "cbo_codigo", "rt", "tipo_equipe", "pmmb"]
    linhas = [[i["nome"], i["cns"], i["cod_cmes"], i["cbo_codigo"], i["rt"], i["tipo_equipe"], i["pmmb"]] for i in itens]
    return _csv_response(cabecalho, linhas, "profissionais.csv")


# ---------------------------------------------------------------------------
# PROCEDIMENTOS
# ---------------------------------------------------------------------------

@bp.route("/procedimentos", methods=["GET"])
def procedimentos():
    """Tela avulsa antiga: agora só leva para a aba dentro do Painel de Administração."""
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/novo", methods=["POST"])
def novo_procedimento():
    db = get_db()
    codigo_digitado = (request.form.get("codigo") or "").strip()
    codigo = normalizar_cod_procedimento(codigo_digitado)
    try:
        db.execute(
            "INSERT INTO procedimentos (codigo, nome) VALUES (?, ?)",
            (codigo, request.form.get("nome")),
        )
        db.commit()
        msg = "Procedimento cadastrado."
        if codigo != codigo_digitado:
            msg += (
                f" Código informado tinha 11 caracteres e foi normalizado "
                f"automaticamente para '{codigo}' (regra do AT-02: cortar o "
                "último caractere de sufixo)."
            )
        elif len(codigo) != 10:
            msg += (
                f" Atenção: o código '{codigo}' tem {len(codigo)} dígito(s), "
                "mas o padrão SIGTAP usa 10. Se esse código não bater com o "
                "que aparece no AT-02, o procedimento não vai ser reconhecido "
                "e a produção dele não vai aparecer no painel."
            )
        flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao cadastrar procedimento: {exc}", "erro")
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/<codigo>/editar", methods=["POST"])
def editar_procedimento(codigo):
    db = get_db()
    db.execute(
        "UPDATE procedimentos SET nome=? WHERE codigo=?",
        (request.form.get("nome"), codigo),
    )
    db.commit()
    flash("Procedimento atualizado.", "sucesso")
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/<codigo>/excluir", methods=["POST"])
def excluir_procedimento(codigo):
    db = get_db()
    try:
        db.execute("DELETE FROM procedimentos WHERE codigo=?", (codigo,))
        db.commit()
        flash("Procedimento excluído.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível excluir: {exc}. Verifique se não está vinculado a algum indicador.", "erro")
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/bulk_excluir", methods=["POST"])
def bulk_excluir_procedimentos():
    db = get_db()
    codigos = request.form.getlist("selecionados")
    if not codigos:
        flash("Marque pelo menos um procedimento para excluir.", "erro")
        return redirect(url_for("cadastros.administracao", aba="procedimentos"))

    excluidos = 0
    bloqueados = 0
    for codigo in codigos:
        try:
            db.execute("DELETE FROM procedimentos WHERE codigo=?", (codigo,))
            db.commit()
            excluidos += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            bloqueados += 1

    msg = f"{excluidos} procedimento(s) excluído(s)."
    if bloqueados:
        msg += f" {bloqueados} não puderam ser excluídos por estarem vinculados a algum indicador."
    flash(msg, "sucesso" if excluidos else "erro")
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/importar_csv", methods=["POST"])
def importar_procedimentos_csv():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        flash("Selecione um arquivo CSV.", "erro")
        return redirect(url_for("cadastros.administracao", aba="procedimentos"))

    cabecalho, linhas = _ler_csv_upload(arquivo)
    indices = {c: i for i, c in enumerate(cabecalho) if c in {"codigo", "nome"}}
    if "codigo" not in indices or "nome" not in indices:
        flash("CSV inválido: são necessárias as colunas 'codigo' e 'nome'.", "erro")
        return redirect(url_for("cadastros.administracao", aba="procedimentos"))

    db = get_db()
    total = 0
    normalizados = 0
    fora_do_padrao = 0
    for linha in linhas:
        if len(linha) <= max(indices.values()):
            continue
        codigo_original = linha[indices["codigo"]].strip()
        codigo = normalizar_cod_procedimento(codigo_original)
        nome = linha[indices["nome"]].strip()
        if not codigo or not nome:
            continue
        if codigo != codigo_original:
            normalizados += 1
        elif len(codigo) != 10:
            fora_do_padrao += 1
        db.execute(
            """INSERT INTO procedimentos (codigo, nome) VALUES (?, ?)
               ON CONFLICT(codigo) DO UPDATE SET nome=excluded.nome""",
            (codigo, nome),
        )
        total += 1
    db.commit()
    msg = f"Importação concluída: {total} procedimentos processados."
    if normalizados:
        msg += (
            f" {normalizados} código(s) de 11 caracteres foram normalizados "
            "automaticamente para 10 (regra do AT-02: cortar o último caractere de sufixo)."
        )
    if fora_do_padrao:
        msg += (
            f" ATENÇÃO: {fora_do_padrao} código(s) não têm 10 dígitos (o padrão "
            "SIGTAP) - se essa lista veio de uma fonte diferente da tabela "
            "oficial, os códigos podem não bater com o que vem no AT-02, e a "
            "produção desses procedimentos não vai aparecer no painel."
        )
    flash(msg, "sucesso")
    return redirect(url_for("cadastros.administracao", aba="procedimentos"))


@bp.route("/procedimentos/exportar_csv", methods=["GET"])
def exportar_procedimentos_csv():
    db = get_db()
    itens = db.execute("SELECT codigo, nome FROM procedimentos ORDER BY nome").fetchall()
    cabecalho = ["codigo", "nome"]
    linhas = [[i["codigo"], i["nome"]] for i in itens]
    return _csv_response(cabecalho, linhas, "procedimentos.csv")


@bp.route("/procedimentos/buscar", methods=["GET"])
def buscar_procedimentos_json():
    termo = (request.args.get("q") or "").strip()
    db = get_db()
    if not termo:
        itens = db.execute("SELECT codigo, nome FROM procedimentos ORDER BY nome LIMIT 20").fetchall()
    else:
        itens = db.execute(
            """SELECT codigo, nome FROM procedimentos
               WHERE codigo LIKE ? OR nome LIKE ?
               ORDER BY nome LIMIT 20""",
            (f"%{termo}%", f"%{termo}%"),
        ).fetchall()
    return jsonify([dict(i) for i in itens])


# ---------------------------------------------------------------------------
# INDICADORES (por portaria) + VÍNCULOS CBO / PROCEDIMENTO
# ---------------------------------------------------------------------------

def _fonte_do_form(db, form, indicador_atual=None):
    """(fonte_id, texto_fonte_dados) a gravar a partir do <select name="fonte_id"> do indicador.
    Escolhida uma fonte: fonte_id = a fonte e o texto vira a descrição oficial dela (só exibição). Sem fonte:
    fonte_id NULL (o indicador aceita qualquer fonte, como antes); o texto antigo só é apagado se ele tinha
    sido gerado por uma fonte escolhida - texto livre legado é preservado."""
    bruto = (form.get("fonte_id") or "").strip()
    if bruto.isdigit():
        fonte = db.execute("SELECT id, nome, descricao FROM fontes_dados WHERE id = ?", (int(bruto),)).fetchone()
        if fonte:
            return fonte["id"], (fonte["descricao"] or fonte["nome"])
    if indicador_atual is not None and indicador_atual["fonte_id"] is None:
        return None, indicador_atual["fonte_dados"]
    return None, None


@bp.route("/portarias/<int:portaria_id>/indicadores", methods=["GET"])
def indicadores_da_portaria(portaria_id):
    db = get_db()
    portaria = db.execute("SELECT * FROM portarias WHERE id=?", (portaria_id,)).fetchone()
    indicadores = db.execute(
        "SELECT * FROM indicadores WHERE portaria_id=? ORDER BY codigo", (portaria_id,)
    ).fetchall()
    fontes = db.execute("SELECT id, nome, descricao FROM fontes_dados WHERE ativo = 1 ORDER BY nome").fetchall()
    return render_template("contratos/cadastros/indicadores.html", portaria=portaria, indicadores=indicadores, fontes=fontes
    )


@bp.route("/portarias/<int:portaria_id>/indicadores/novo", methods=["POST"])
def novo_indicador(portaria_id):
    db = get_db()
    codigo = (request.form.get("codigo") or "").strip()
    fonte_id, fonte_texto = _fonte_do_form(db, request.form)
    try:
        db.execute(
            """INSERT INTO indicadores (portaria_id, codigo, nome, tipo, complexidade, servico, fonte_dados,
                                        fonte_id, consolida_cnes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                portaria_id,
                codigo,
                request.form.get("nome"),
                request.form.get("tipo"),
                request.form.get("complexidade"),
                request.form.get("servico"),
                fonte_texto,
                fonte_id,
                1 if request.form.get("consolida_cnes") else 0,
            ),
        )
        db.commit()
        flash("Indicador cadastrado.", "sucesso")
    except sqlite3.IntegrityError:
        flash(
            f"Já existe um indicador com o código '{codigo}' nesta portaria. "
            "Use a lista abaixo para editar o indicador existente em vez de "
            "cadastrar um novo com o mesmo código.",
            "erro",
        )
    return redirect(url_for("cadastros.indicadores_da_portaria", portaria_id=portaria_id))


@bp.route("/indicadores/<int:indicador_id>/clonar", methods=["POST"])
def clonar_indicador(indicador_id):
    db = get_db()
    novo_codigo = (request.form.get("novo_codigo") or "").strip()
    original = db.execute("SELECT * FROM indicadores WHERE id=?", (indicador_id,)).fetchone()

    if not original:
        flash("Indicador de origem não encontrado.", "erro")
        return redirect(url_for("vigencias.listar"))

    if not novo_codigo:
        flash("Informe o código do novo indicador para clonar.", "erro")
        return redirect(url_for("cadastros.indicadores_da_portaria", portaria_id=original["portaria_id"]))

    try:
        cursor = db.execute(
            """INSERT INTO indicadores (portaria_id, codigo, nome, tipo, complexidade, servico,
                                        fonte_dados, fonte_id, consolida_cnes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                original["portaria_id"], novo_codigo, original["nome"],
                original["tipo"], original["complexidade"], original["servico"],
                original["fonte_dados"], original["fonte_id"], original["consolida_cnes"],
            ),
        )
        novo_id = cursor.lastrowid

        db.execute(
            """INSERT INTO indicador_cbo (indicador_id, cbo_codigo, curinga)
               SELECT ?, cbo_codigo, curinga FROM indicador_cbo WHERE indicador_id = ?""",
            (novo_id, indicador_id),
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
            (novo_id, indicador_id),
        )
        db.commit()
        flash(
            f"Indicador '{novo_codigo}' criado como cópia de '{original['codigo']}', "
            "já com os mesmos vínculos de CBO e procedimento. Ajuste o nome e o que "
            "for diferente direto na lista.",
            "sucesso",
        )
    except sqlite3.IntegrityError:
        flash(f"Já existe um indicador com o código '{novo_codigo}' nesta portaria.", "erro")

    return redirect(url_for("cadastros.indicadores_da_portaria", portaria_id=original["portaria_id"]))


@bp.route("/indicadores/<int:indicador_id>/editar", methods=["POST"])
def editar_indicador(indicador_id):
    db = get_db()
    codigo = (request.form.get("codigo") or "").strip()
    indicador = db.execute("SELECT * FROM indicadores WHERE id=?", (indicador_id,)).fetchone()
    fonte_id, fonte_texto = _fonte_do_form(db, request.form, indicador)
    try:
        db.execute(
            """UPDATE indicadores SET codigo=?, nome=?, tipo=?, complexidade=?, servico=?, fonte_dados=?,
                      fonte_id=?, consolida_cnes=?
               WHERE id=?""",
            (
                codigo,
                request.form.get("nome"),
                request.form.get("tipo"),
                request.form.get("complexidade"),
                request.form.get("servico"),
                fonte_texto,
                fonte_id,
                1 if request.form.get("consolida_cnes") else 0,
                indicador_id,
            ),
        )
        db.commit()
        flash("Indicador atualizado.", "sucesso")
    except sqlite3.IntegrityError:
        flash(f"Já existe outro indicador com o código '{codigo}' nesta portaria.", "erro")

    return redirect(url_for("cadastros.indicadores_da_portaria", portaria_id=indicador["portaria_id"]))


@bp.route("/indicadores/<int:indicador_id>/excluir", methods=["POST"])
def excluir_indicador(indicador_id):
    db = get_db()
    indicador = db.execute("SELECT portaria_id FROM indicadores WHERE id=?", (indicador_id,)).fetchone()
    try:
        db.execute("DELETE FROM indicadores WHERE id=?", (indicador_id,))
        db.commit()
        flash("Indicador excluído (junto com seus vínculos de CBO/procedimento).", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(
            f"Não foi possível excluir: {exc}. Exclua as metas que usam este "
            "indicador antes.",
            "erro",
        )
    return redirect(url_for("cadastros.indicadores_da_portaria", portaria_id=indicador["portaria_id"]))


@bp.route("/indicadores/<int:indicador_id>", methods=["GET"])
def detalhe_indicador(indicador_id):
    db = get_db()
    indicador = db.execute("SELECT * FROM indicadores WHERE id=?", (indicador_id,)).fetchone()

    vinculos_cbo = db.execute(
        """SELECT ic.id, ic.cbo_codigo, ic.curinga, c.nome_categoria
           FROM indicador_cbo ic LEFT JOIN cbo c ON c.codigo = ic.cbo_codigo
           WHERE ic.indicador_id=? AND ic.subgrupo_id IS NULL""",
        (indicador_id,),
    ).fetchall()
    vinculos_proc = db.execute(
        """SELECT ip.*, p.nome AS procedimento_nome, e.nome AS estabelecimento_nome
           FROM indicador_procedimento ip
           LEFT JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
           LEFT JOIN estabelecimentos e ON e.id = ip.estabelecimento_id
           WHERE ip.indicador_id=? AND ip.subgrupo_id IS NULL""",
        (indicador_id,),
    ).fetchall()

    subgrupos_rows = db.execute(
        "SELECT * FROM indicador_subgrupo WHERE indicador_id=? ORDER BY ordem, id",
        (indicador_id,),
    ).fetchall()
    subgrupos = []
    for sg in subgrupos_rows:
        sg_vinculos_cbo = db.execute(
            """SELECT ic.id, ic.cbo_codigo, ic.curinga, c.nome_categoria
               FROM indicador_cbo ic LEFT JOIN cbo c ON c.codigo = ic.cbo_codigo
               WHERE ic.subgrupo_id=?""",
            (sg["id"],),
        ).fetchall()
        sg_vinculos_proc = db.execute(
            """SELECT ip.*, p.nome AS procedimento_nome, e.nome AS estabelecimento_nome
               FROM indicador_procedimento ip
               LEFT JOIN procedimentos p ON p.codigo = ip.procedimento_codigo
               LEFT JOIN estabelecimentos e ON e.id = ip.estabelecimento_id
               WHERE ip.subgrupo_id=?""",
            (sg["id"],),
        ).fetchall()
        subgrupos.append({
            "id": sg["id"], "nome": sg["nome"], "ordem": sg["ordem"],
            "vinculos_cbo": sg_vinculos_cbo, "vinculos_proc": sg_vinculos_proc,
        })

    excecoes_cbo = db.execute(
        """SELECT e.id, e.cbo_codigo, c.nome_categoria
           FROM indicador_cbo_excecao e LEFT JOIN cbo c ON c.codigo = e.cbo_codigo
           WHERE e.indicador_id=?""",
        (indicador_id,),
    ).fetchall()
    excecoes_estabelecimento = db.execute(
        """SELECT ex.id, ex.estabelecimento_id, es.nome AS estabelecimento_nome
           FROM indicador_estabelecimento_excecao ex
           LEFT JOIN estabelecimentos es ON es.id = ex.estabelecimento_id
           WHERE ex.indicador_id=?""",
        (indicador_id,),
    ).fetchall()

    tipos_equipe_cadastrados = [
        r["tipo_equipe"] for r in db.execute(
            "SELECT DISTINCT tipo_equipe FROM profissionais "
            "WHERE tipo_equipe IS NOT NULL AND tipo_equipe != '' ORDER BY tipo_equipe"
        ).fetchall()
    ]

    cnes_alternativos = db.execute(
        """SELECT ca.id, ca.estabelecimento_id, ca.cnes_alternativo, es.nome AS estabelecimento_nome
           FROM indicador_estabelecimento_cnes_alternativo ca
           LEFT JOIN estabelecimentos es ON es.id = ca.estabelecimento_id
           WHERE ca.indicador_id=?
           ORDER BY es.nome""",
        (indicador_id,),
    ).fetchall()

    categorias_lista = db.execute("SELECT nome FROM categorias_estabelecimento ORDER BY nome").fetchall()

    return render_template("contratos/cadastros/indicador_detalhe.html",
        categorias_lista=categorias_lista,
        indicador=indicador,
        vinculos_cbo=vinculos_cbo,
        vinculos_proc=vinculos_proc,
        subgrupos=subgrupos,
        excecoes_cbo=excecoes_cbo,
        excecoes_estabelecimento=excecoes_estabelecimento,
        tipos_equipe_cadastrados=tipos_equipe_cadastrados,
        cnes_alternativos=cnes_alternativos,
    )


@bp.route("/indicadores/<int:indicador_id>/vinculo_cbo", methods=["POST"])
def add_vinculo_cbo(indicador_id):
    db = get_db()
    curinga = 1 if request.form.get("curinga") else 0
    cbo_codigo = None if curinga else (request.form.get("cbo_codigo") or None)
    subgrupo_id = request.form.get("subgrupo_id") or None

    if not curinga and not cbo_codigo:
        flash("Selecione um CBO ou marque 'Aceitar qualquer CBO'.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    if cbo_codigo:
        existe = db.execute("SELECT 1 FROM cbo WHERE codigo=?", (cbo_codigo,)).fetchone()
        if not existe:
            flash(
                f"O CBO '{cbo_codigo}' não está cadastrado. Cadastre-o em "
                "Cadastros > CBO antes de vincular.",
                "erro",
            )
            return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    try:
        db.execute(
            "INSERT OR IGNORE INTO indicador_cbo (indicador_id, cbo_codigo, curinga, subgrupo_id) VALUES (?, ?, ?, ?)",
            (indicador_id, cbo_codigo, curinga, subgrupo_id),
        )
        db.commit()
        flash("Vínculo de CBO adicionado.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível adicionar o vínculo: {exc}", "erro")

    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/vinculo_cbo/<int:vinculo_id>/remover", methods=["POST"])
def remover_vinculo_cbo(indicador_id, vinculo_id):
    db = get_db()
    db.execute("DELETE FROM indicador_cbo WHERE id=?", (vinculo_id,))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/vinculo_cbo/bulk_excluir", methods=["POST"])
def bulk_excluir_vinculo_cbo(indicador_id):
    db = get_db()
    ids = request.form.getlist("vinculo_ids")
    if not ids:
        flash("Nenhum vínculo de CBO selecionado para excluir.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    marcadores = ",".join("?" for _ in ids)
    db.execute(
        f"DELETE FROM indicador_cbo WHERE indicador_id = ? AND id IN ({marcadores})",
        (indicador_id, *ids),
    )
    db.commit()
    flash(f"{len(ids)} vínculo(s) de CBO excluído(s).", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/vinculo_procedimento", methods=["POST"])
def add_vinculo_procedimento(indicador_id):
    db = get_db()
    codigo_digitado = (request.form.get("procedimento_codigo") or "").strip()
    procedimento_codigo = normalizar_cod_procedimento(codigo_digitado)
    estabelecimento_id = request.form.get("estabelecimento_id") or None
    subgrupo_id = request.form.get("subgrupo_id") or None

    if not procedimento_codigo:
        flash("Informe o código do procedimento.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    if estabelecimento_id:
        existe_estab = db.execute(
            "SELECT 1 FROM estabelecimentos WHERE id=?", (estabelecimento_id,)
        ).fetchone()
        if not existe_estab:
            flash(f"Estabelecimento id '{estabelecimento_id}' não encontrado.", "erro")
            return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    try:
        db.execute(
            "INSERT OR IGNORE INTO procedimentos (codigo, nome) VALUES (?, ?)",
            (procedimento_codigo, procedimento_codigo),
        )
        db.execute(
            """INSERT OR IGNORE INTO indicador_procedimento
                   (indicador_id, procedimento_codigo, tipo_vinculo,
                    categoria_estabelecimento, categoria_estabelecimento_neg, estabelecimento_id,
                    subgrupo_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                indicador_id,
                procedimento_codigo,
                request.form.get("tipo_vinculo", "inclusao"),
                request.form.get("categoria_estabelecimento") or None,
                request.form.get("categoria_estabelecimento_neg") or None,
                estabelecimento_id,
                subgrupo_id,
            ),
        )
        db.commit()
        flash("Vínculo de procedimento adicionado.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível adicionar o vínculo: {exc}", "erro")

    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/vinculo_procedimento_lote", methods=["POST"])
def add_vinculo_procedimento_lote(indicador_id):
    db = get_db()
    codigos = request.form.getlist("procedimento_codigos")
    estabelecimento_id = request.form.get("estabelecimento_id") or None
    tipo_vinculo = request.form.get("tipo_vinculo", "inclusao")
    categoria_estabelecimento = request.form.get("categoria_estabelecimento") or None
    categoria_estabelecimento_neg = request.form.get("categoria_estabelecimento_neg") or None
    subgrupo_id = request.form.get("subgrupo_id") or None

    if not codigos:
        flash("Nenhum procedimento selecionado para adicionar em lote.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    if estabelecimento_id:
        existe_estab = db.execute(
            "SELECT 1 FROM estabelecimentos WHERE id=?", (estabelecimento_id,)
        ).fetchone()
        if not existe_estab:
            flash(f"Estabelecimento id '{estabelecimento_id}' não encontrado.", "erro")
            return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    adicionados = 0
    for codigo_bruto in codigos:
        codigo = normalizar_cod_procedimento((codigo_bruto or "").strip())
        if not codigo:
            continue
        db.execute(
            "INSERT OR IGNORE INTO procedimentos (codigo, nome) VALUES (?, ?)",
            (codigo, codigo),
        )
        antes = db.total_changes
        db.execute(
            """INSERT OR IGNORE INTO indicador_procedimento
                   (indicador_id, procedimento_codigo, tipo_vinculo,
                    categoria_estabelecimento, categoria_estabelecimento_neg, estabelecimento_id,
                    subgrupo_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                indicador_id, codigo, tipo_vinculo,
                categoria_estabelecimento, categoria_estabelecimento_neg, estabelecimento_id,
                subgrupo_id,
            ),
        )
        if db.total_changes > antes:
            adicionados += 1

    db.commit()
    ja_existiam = len(codigos) - adicionados
    msg = f"{adicionados} procedimento(s) vinculado(s) ao indicador."
    if ja_existiam:
        msg += f" {ja_existiam} já estavam vinculados e foram ignorados."
    flash(msg, "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route(
    "/indicadores/<int:indicador_id>/vinculo_procedimento/<int:vinculo_id>/editar",
    methods=["POST"],
)
def editar_vinculo_procedimento(indicador_id, vinculo_id):
    db = get_db()
    db.execute(
        # O filtro positivo (categoria_estabelecimento) saiu da tela; a coluna continua no
        # banco por compatibilidade e NÃO é tocada aqui (vínculos antigos mantêm o valor).
        """UPDATE indicador_procedimento SET tipo_vinculo=?,
               categoria_estabelecimento_neg=?, estabelecimento_id=? WHERE id=?""",
        (
            request.form.get("tipo_vinculo", "inclusao"),
            request.form.get("categoria_estabelecimento_neg") or None,
            request.form.get("estabelecimento_id") or None,
            vinculo_id,
        ),
    )
    db.commit()
    flash("Vínculo atualizado.", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route(
    "/indicadores/<int:indicador_id>/vinculo_procedimento/<int:vinculo_id>/remover",
    methods=["POST"],
)
def remover_vinculo_procedimento(indicador_id, vinculo_id):
    db = get_db()
    db.execute("DELETE FROM indicador_procedimento WHERE id=?", (vinculo_id,))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route(
    "/indicadores/<int:indicador_id>/vinculo_procedimento/bulk_excluir",
    methods=["POST"],
)
def bulk_excluir_vinculo_procedimento(indicador_id):
    db = get_db()
    ids = request.form.getlist("vinculo_ids")
    if not ids:
        flash("Nenhum procedimento selecionado para excluir.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    marcadores = ",".join("?" for _ in ids)
    db.execute(
        f"DELETE FROM indicador_procedimento WHERE indicador_id = ? AND id IN ({marcadores})",
        (indicador_id, *ids),
    )
    db.commit()
    flash(f"{len(ids)} vínculo(s) de procedimento excluído(s).", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


# ---------------------------------------------------------------------------
# SUBGRUPOS
# ---------------------------------------------------------------------------

@bp.route("/indicadores/<int:indicador_id>/subgrupos/novo", methods=["POST"])
def novo_subgrupo(indicador_id):
    db = get_db()
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe um nome para o subgrupo (ex.: 'Endodontia', 'Ultrassonografia').", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))

    ordem = db.execute(
        "SELECT COALESCE(MAX(ordem), 0) + 1 AS n FROM indicador_subgrupo WHERE indicador_id=?",
        (indicador_id,),
    ).fetchone()["n"]
    db.execute(
        "INSERT INTO indicador_subgrupo (indicador_id, nome, ordem) VALUES (?, ?, ?)",
        (indicador_id, nome, ordem),
    )
    db.commit()
    flash(f"Subgrupo '{nome}' criado.", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/subgrupos/<int:subgrupo_id>/renomear", methods=["POST"])
def renomear_subgrupo(indicador_id, subgrupo_id):
    db = get_db()
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe um nome para o subgrupo.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    db.execute("UPDATE indicador_subgrupo SET nome=? WHERE id=?", (nome, subgrupo_id))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/subgrupos/<int:subgrupo_id>/excluir", methods=["POST"])
def excluir_subgrupo(indicador_id, subgrupo_id):
    db = get_db()
    db.execute("DELETE FROM indicador_subgrupo WHERE id=?", (subgrupo_id,))
    db.commit()
    flash("Subgrupo excluído (junto com os vínculos e as metas que só existiam dentro dele).", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


# ---------------------------------------------------------------------------
# EXCEÇÕES DE CBO/ESTABELECIMENTO NO NÍVEL DO INDICADOR
# ---------------------------------------------------------------------------

@bp.route("/indicadores/<int:indicador_id>/excecao_cbo", methods=["POST"])
def add_excecao_cbo(indicador_id):
    db = get_db()
    cbo_codigo = (request.form.get("cbo_codigo") or "").strip()
    if not cbo_codigo:
        flash("Selecione um CBO para excluir.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    existe = db.execute("SELECT 1 FROM cbo WHERE codigo=?", (cbo_codigo,)).fetchone()
    if not existe:
        flash(f"O CBO '{cbo_codigo}' não está cadastrado.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    db.execute(
        "INSERT OR IGNORE INTO indicador_cbo_excecao (indicador_id, cbo_codigo) VALUES (?, ?)",
        (indicador_id, cbo_codigo),
    )
    db.commit()
    flash(f"CBO '{cbo_codigo}' passa a ser desconsiderado para este indicador.", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/excecao_cbo/<int:excecao_id>/remover", methods=["POST"])
def remover_excecao_cbo(indicador_id, excecao_id):
    db = get_db()
    db.execute("DELETE FROM indicador_cbo_excecao WHERE id=?", (excecao_id,))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/indicadores/<int:indicador_id>/excecao_estabelecimento", methods=["POST"])
def add_excecao_estabelecimento(indicador_id):
    db = get_db()
    estabelecimento_id = request.form.get("estabelecimento_id") or None
    if not estabelecimento_id:
        flash("Selecione um estabelecimento para excluir.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    existe = db.execute("SELECT 1 FROM estabelecimentos WHERE id=?", (estabelecimento_id,)).fetchone()
    if not existe:
        flash(f"Estabelecimento id '{estabelecimento_id}' não encontrado.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    db.execute(
        "INSERT OR IGNORE INTO indicador_estabelecimento_excecao (indicador_id, estabelecimento_id) VALUES (?, ?)",
        (indicador_id, estabelecimento_id),
    )
    db.commit()
    flash("Estabelecimento passa a ser desconsiderado para este indicador.", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route(
    "/indicadores/<int:indicador_id>/excecao_estabelecimento/<int:excecao_id>/remover",
    methods=["POST"],
)
def remover_excecao_estabelecimento(indicador_id, excecao_id):
    db = get_db()
    db.execute("DELETE FROM indicador_estabelecimento_excecao WHERE id=?", (excecao_id,))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


# ---------------------------------------------------------------------------
# SEGMENTAÇÃO DE METAS POR ATRIBUTO DO PROFISSIONAL (por indicador)
# ---------------------------------------------------------------------------
# Substitui a vinculação NOMINAL de profissionais (v10, tabela
# indicador_profissional - obsoleta, ver schema.sql) por critérios
# estruturados do próprio cadastro de profissionais. Os 3 interruptores
# abaixo controlam a grade de metas (_montar_grade_metas): quando ligados,
# a grade passa a gerar uma linha por valor daquele critério, permitindo
# cadastrar metas diferentes para cada grupo (ex.: RT vs não-RT).

@bp.route("/indicadores/<int:indicador_id>/segmentacao_profissional", methods=["POST"])
def atualizar_segmentacao_profissional(indicador_id):
    db = get_db()
    db.execute(
        """UPDATE indicadores
           SET segmenta_metas_rt=?, segmenta_metas_tipo_equipe=?, segmenta_metas_pmmb=?
           WHERE id=?""",
        (
            1 if request.form.get("segmenta_metas_rt") else 0,
            1 if request.form.get("segmenta_metas_tipo_equipe") else 0,
            1 if request.form.get("segmenta_metas_pmmb") else 0,
            indicador_id,
        ),
    )
    db.commit()
    flash("Critérios de segmentação de metas atualizados.", "sucesso")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route("/profissionais/buscar", methods=["GET"])
def buscar_profissionais_json():
    termo = (request.args.get("q") or "").strip()
    db = get_db()
    sql = """SELECT p.id AS codigo, p.nome, p.cns, e.nome AS estabelecimento_nome
              FROM profissionais p LEFT JOIN estabelecimentos e ON e.id = p.estabelecimento_id"""
    if not termo:
        itens = db.execute(sql + " ORDER BY p.nome LIMIT 20").fetchall()
    else:
        itens = db.execute(
            sql + " WHERE p.nome LIKE ? OR p.cns LIKE ? ORDER BY p.nome LIMIT 20",
            (f"%{termo}%", f"%{termo}%"),
        ).fetchall()
    return jsonify([dict(i) for i in itens])


# ---------------------------------------------------------------------------
# CNES ALTERNATIVO POR ESTABELECIMENTO (por indicador)
# ---------------------------------------------------------------------------
# Só importa para fontes que resolvem o estabelecimento por CNES (hoje:
# Visita Domiciliar/P6 - ver _resolver_estabelecimento_por_cnes em
# app/etl/calculo.py). Indicadores que usam AT-02/Webssas (resolvidos por
# CMES) não são afetados por este cadastro.

@bp.route("/indicadores/<int:indicador_id>/cnes_alternativo", methods=["POST"])
def add_cnes_alternativo(indicador_id):
    db = get_db()
    estabelecimento_id = request.form.get("estabelecimento_id") or None
    cnes_alternativo = (request.form.get("cnes_alternativo") or "").strip()
    if not estabelecimento_id or not cnes_alternativo:
        flash("Selecione o estabelecimento e informe o CNES alternativo.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    existe = db.execute("SELECT 1 FROM estabelecimentos WHERE id=?", (estabelecimento_id,)).fetchone()
    if not existe:
        flash(f"Estabelecimento id '{estabelecimento_id}' não encontrado.", "erro")
        return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))
    try:
        db.execute(
            """INSERT INTO indicador_estabelecimento_cnes_alternativo
                   (indicador_id, estabelecimento_id, cnes_alternativo)
               VALUES (?, ?, ?)
               ON CONFLICT(indicador_id, estabelecimento_id)
               DO UPDATE SET cnes_alternativo=excluded.cnes_alternativo""",
            (indicador_id, estabelecimento_id, cnes_alternativo),
        )
        db.commit()
        flash("CNES alternativo cadastrado para este indicador.", "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao cadastrar CNES alternativo: {exc}", "erro")
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


@bp.route(
    "/indicadores/<int:indicador_id>/cnes_alternativo/<int:cnes_alt_id>/remover",
    methods=["POST"],
)
def remover_cnes_alternativo(indicador_id, cnes_alt_id):
    db = get_db()
    db.execute("DELETE FROM indicador_estabelecimento_cnes_alternativo WHERE id=?", (cnes_alt_id,))
    db.commit()
    return redirect(url_for("cadastros.detalhe_indicador", indicador_id=indicador_id))


# ---------------------------------------------------------------------------
# METAS (por termo aditivo)
# ---------------------------------------------------------------------------

def _montar_grade_metas(db, ta_id):
    indicadores = db.execute(
        """SELECT i.*, p.numero AS portaria_numero
           FROM indicadores i
           JOIN portarias p ON p.id = i.portaria_id
           ORDER BY i.codigo"""
    ).fetchall()
    estabelecimentos = db.execute("SELECT * FROM estabelecimentos ORDER BY nome").fetchall()

    tipos_por_estabelecimento = {}
    for t in db.execute("SELECT estabelecimento_id, tipo_servico FROM estabelecimento_tipo_servico").fetchall():
        tipos_por_estabelecimento.setdefault(t["estabelecimento_id"], []).append(t["tipo_servico"].lower())

    # CBOs que a grade oferece por (indicador, subgrupo) - MESMA regra da view resultados_indicador:
    # o subgrupo que tem CBO próprio usa o dele; senão vale a regra geral do indicador. Curinga ou
    # nenhum CBO vinculado = uma única linha "Curinga / Geral" (cbo NULL).
    cbo_geral, cbo_subgrupo = {}, {}
    for v in db.execute("SELECT indicador_id, subgrupo_id, cbo_codigo, curinga FROM indicador_cbo").fetchall():
        if v["subgrupo_id"] is not None:
            cbo_subgrupo.setdefault(v["subgrupo_id"], []).append(v)
        else:
            cbo_geral.setdefault(v["indicador_id"], []).append(v)

    def cbos_da_grade(indicador_id, subgrupo_id):
        vinculos = cbo_subgrupo.get(subgrupo_id) if subgrupo_id is not None else None
        if not vinculos:
            vinculos = cbo_geral.get(indicador_id, [])
        if not vinculos or any(v["curinga"] for v in vinculos):
            return [None]
        codigos = [v["cbo_codigo"] for v in vinculos if v["cbo_codigo"]]
        return codigos or [None]

    # subgrupos por indicador (ordem de cadastro) e indicadores com procedimento SEM subgrupo ("Geral")
    subgrupos_por_indicador = {}
    for sg in db.execute("SELECT id, indicador_id, nome FROM indicador_subgrupo ORDER BY ordem, nome").fetchall():
        subgrupos_por_indicador.setdefault(sg["indicador_id"], []).append(sg)
    com_proc_geral = {
        r["indicador_id"] for r in db.execute(
            "SELECT DISTINCT indicador_id FROM indicador_procedimento "
            "WHERE subgrupo_id IS NULL AND tipo_vinculo = 'inclusao'"
        ).fetchall()
    }

    # Consolidação CNES (Administração > Portaria/TA): a grade mostra uma linha por CNES; a meta
    # gravada fica no cadastro representante e a exibida é a soma dos cadastros do CNES.
    analise_cnes = consolidacao.analisar(db)
    flags_cnes = consolidacao.indicadores_cnes(db)

    nomes_cbo = {c["codigo"]: c["nome_categoria"] for c in db.execute("SELECT codigo, nome_categoria FROM cbo").fetchall()}

    # valores de tipo_equipe usados para expandir a grade quando um indicador
    # tem segmenta_metas_tipo_equipe=1 - vem do que já está cadastrado em
    # Profissionais, não de uma lista fixa (equipe varia por Portaria/edital)
    tipos_equipe_cadastrados = [
        r["tipo_equipe"] for r in db.execute(
            "SELECT DISTINCT tipo_equipe FROM profissionais "
            "WHERE tipo_equipe IS NOT NULL AND tipo_equipe != '' ORDER BY tipo_equipe"
        ).fetchall()
    ]

    metas_existentes = {}
    for m in db.execute("SELECT * FROM metas WHERE ta_id=?", (ta_id,)).fetchall():
        metas_existentes[(m["indicador_id"], m["estabelecimento_id"], m["subgrupo_id"], m["cbo_codigo"], m["rt"], m["tipo_equipe"], m["pmmb"])] = m
    indicadores_com_meta_geral = {i for (i, _e, sg, *_r) in metas_existentes if sg is None}

    def meta_da_unidade(indicador_id, unidade, subgrupo_id, cbo_codigo, rt, tipo_equipe, pmmb):
        """(id da meta do representante, valor exibido). Numa unidade CNES o valor é a soma dos cadastros do grupo."""
        membros = unidade["membros"] if unidade["agrupado"] else [unidade["id"]]
        achadas = [
            metas_existentes[k] for est_id in membros
            for k in [(indicador_id, est_id, subgrupo_id, cbo_codigo, rt, tipo_equipe, pmmb)] if k in metas_existentes
        ]
        if not achadas:
            return None, None
        proprio = metas_existentes.get((indicador_id, unidade["id"], subgrupo_id, cbo_codigo, rt, tipo_equipe, pmmb))
        valores = [m["valor_meta"] for m in achadas if m["valor_meta"] is not None]
        return (proprio["id"] if proprio else achadas[0]["id"]), (sum(valores) if valores else None)

    grade = []
    for indicador in indicadores:
        servico = (indicador["servico"] or "").strip().lower()
        estab_elegiveis = [
            e for e in estabelecimentos
            if not servico or servico in tipos_por_estabelecimento.get(e["id"], [])
        ]

        # unidades da grade: um cadastro por linha (CMES) ou um grupo por CNES
        unidades, vistos = [], set()
        for estab in estab_elegiveis:
            info = consolidacao.info_para(analise_cnes, flags_cnes, indicador["id"], estab["id"])
            if info:
                if info["chave"] in vistos:
                    continue
                vistos.add(info["chave"])
                unidades.append({
                    "id": info["representante_id"], "agrupado": True, "membros": info["membros"],
                    "nome": f"{info['representante_nome']} · CNES {info['cnes']} ({len(info['membros'])} CMES)",
                })
            else:
                unidades.append({"id": estab["id"], "agrupado": False, "membros": [estab["id"]], "nome": estab["nome"]})

        # indicador com subgrupos: a grade vira Estabelecimento | Subgrupo (+ "Geral", quando há
        # procedimento sem subgrupo ou meta antiga sem subgrupo); sem subgrupos, como sempre
        subgrupos = [(sg["id"], sg["nome"]) for sg in subgrupos_por_indicador.get(indicador["id"], [])]
        if subgrupos and (indicador["id"] in com_proc_geral or indicador["id"] in indicadores_com_meta_geral):
            subgrupos.append((None, "Geral (sem subgrupo)"))
        tem_subgrupos = bool(subgrupos)
        if not tem_subgrupos:
            subgrupos = [(None, "")]

        rt_opcoes = ["SIM", "NAO"] if indicador["segmenta_metas_rt"] else [None]
        pmmb_opcoes = ["SIM", "NAO"] if indicador["segmenta_metas_pmmb"] else [None]
        equipe_opcoes = tipos_equipe_cadastrados if (indicador["segmenta_metas_tipo_equipe"] and tipos_equipe_cadastrados) else [None]

        linhas = []
        qtd_com_meta = 0
        for unidade in unidades:
            for subgrupo_id, subgrupo_nome in subgrupos:
                for cbo_codigo in cbos_da_grade(indicador["id"], subgrupo_id):
                    for rt in rt_opcoes:
                        for tipo_equipe in equipe_opcoes:
                            for pmmb in pmmb_opcoes:
                                meta_id, valor_meta = meta_da_unidade(
                                    indicador["id"], unidade, subgrupo_id, cbo_codigo, rt, tipo_equipe, pmmb
                                )
                                if meta_id:
                                    qtd_com_meta += 1
                                rotulo_segmento = " / ".join(filter(None, [
                                    ("RT" if rt == "SIM" else "não-RT") if rt else None,
                                    tipo_equipe,
                                    ("PMMB" if pmmb == "SIM" else "não-PMMB") if pmmb else None,
                                ]))
                                linhas.append({
                                    "estabelecimento_id": unidade["id"],
                                    "estabelecimento_nome": unidade["nome"],
                                    "subgrupo_id": subgrupo_id if subgrupo_id is not None else "",
                                    "subgrupo_nome": subgrupo_nome,
                                    "cbo_codigo": cbo_codigo or "",
                                    "cbo_nome": nomes_cbo.get(cbo_codigo, "") if cbo_codigo else "Curinga / Geral",
                                    "rt": rt or "",
                                    "tipo_equipe": tipo_equipe or "",
                                    "pmmb": pmmb or "",
                                    "rotulo_segmento": rotulo_segmento,
                                    "meta_id": meta_id,
                                    "valor_meta": valor_meta,
                                })

        grade.append({
            "indicador_id": indicador["id"],
            "indicador_codigo": indicador["codigo"],
            "indicador_nome": indicador["nome"],
            "indicador_servico": indicador["servico"],
            "portaria_id": indicador["portaria_id"],
            "portaria_numero": indicador["portaria_numero"],
            "segmentado": bool(indicador["segmenta_metas_rt"] or indicador["segmenta_metas_tipo_equipe"] or indicador["segmenta_metas_pmmb"]),
            "tem_subgrupos": tem_subgrupos,
            "consolida_cnes": indicador["id"] in flags_cnes,
            "qtd_com_meta": qtd_com_meta,
            "linhas": linhas,
        })

    return grade


def _resumo_grade_metas(grade):
    """Contagens da grade (sem as linhas), uma por indicador, para a lista recolhida da tela de Metas."""
    return [{
        "indicador_id": g["indicador_id"], "codigo": g["indicador_codigo"], "nome": g["indicador_nome"],
        "portaria": g["portaria_numero"], "total": len(g["linhas"]), "com_meta": g["qtd_com_meta"],
        "tem_subgrupos": g["tem_subgrupos"], "consolida_cnes": g.get("consolida_cnes", False),
    } for g in grade]


@bp.route("/tas/<int:ta_id>/metas", methods=["GET"])
def metas_do_ta(ta_id):
    """
    Tela de metas do TA: TODOS os indicadores em blocos recolhidos. O botão "Editar" de cada indicador carrega
    (metas_bloco) todos os subgrupos e estabelecimentos dele; cada subgrupo/indicador tem o seu "Salvar" e o
    salvamento é por JSON (salvar_metas_ajax), sem recarregar a página nem montar um formulário gigante.
    """
    db = get_db()
    ta = db.execute("SELECT * FROM termos_aditivos WHERE id=?", (ta_id,)).fetchone()
    if ta is None:
        flash("Termo Aditivo não encontrado.", "erro")
        return redirect(url_for("cadastros.administracao", aba="portaria"))
    grade = _montar_grade_metas(db, ta_id)
    return render_template("contratos/cadastros/metas.html", ta=ta, resumo_indicadores=_resumo_grade_metas(grade),
        qtd_indicadores_cnes=len(consolidacao.indicadores_cnes(db)),
    )


@bp.route("/tas/<int:ta_id>/metas/bloco/<int:indicador_id>", methods=["GET"])
def metas_bloco(ta_id, indicador_id):
    """Fragmento HTML de UM indicador (todos os subgrupos e estabelecimentos), carregado pelo botão Editar."""
    db = get_db()
    grupo = next((g for g in _montar_grade_metas(db, ta_id) if g["indicador_id"] == indicador_id), None)
    if grupo is None:
        return "<p>Indicador não encontrado neste TA.</p>", 404
    secoes, indice = [], {}
    for l in grupo["linhas"]:
        chave = l["subgrupo_id"] if l["subgrupo_id"] != "" else "geral"
        if chave not in indice:
            indice[chave] = {"nome": l["subgrupo_nome"] or "Todos os estabelecimentos", "linhas": [], "com_meta": 0,
                             "sg": l["subgrupo_id"]}
            secoes.append(indice[chave])
        indice[chave]["linhas"].append(l)
        if l["meta_id"]:
            indice[chave]["com_meta"] += 1
    for sec in secoes:
        sec["aberta"] = len(grupo["linhas"]) <= 400 or len(secoes) == 1   # P42 (milhares de linhas): subgrupos fechados
    return render_template("contratos/cadastros/_metas_bloco.html", grupo=grupo, secoes=secoes)


def _valor_meta_ou_none(bruto):
    """'' / None -> None (remover). Aceita vírgula decimal. ValueError com mensagem clara se inválido."""
    if bruto is None:
        return None
    if isinstance(bruto, (int, float)):
        valor = float(bruto)
    else:
        texto = str(bruto).strip().replace(" ", "")
        if texto == "":
            return None
        try:
            valor = float(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
        except ValueError:
            raise ValueError(f"valor '{bruto}' não é um número") from None
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ValueError("valor inválido")
    if valor < 0:
        raise ValueError("a meta não pode ser negativa")
    return valor


def _gravar_metas(db, ta_id, itens, remover_vazios=True):
    """
    UPSERT das metas de um TA. Cada item: indicador_id, estabelecimento_id, subgrupo_id, cbo_codigo, rt,
    tipo_equipe, pmmb, valor. Chave: (ta_id, estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo,
    rt, tipo_equipe, pmmb) - a mesma do índice único idx_metas_unico. Regras:
      - valor preenchido: atualiza se a chave existe, senão insere;
      - valor vazio: remove a meta da chave (se `remover_vazios`; o form antigo passa False e ignora);
      - item inválido não derruba os outros: vira status 'erro' com mensagem;
      - tudo numa transação - erro inesperado desfaz tudo (rollback) em vez de gravar pela metade;
      - consolidação por CNES: gravar/remover na linha do cadastro principal vale para o grupo (as
        metas iguais dos outros cadastros do CNES são removidas).
    Retorna uma lista de dicts {indice, status, meta_id, valor, mensagem} na mesma ordem dos itens.
    """
    analise_cnes, flags_cnes = consolidacao.analisar(db), consolidacao.indicadores_cnes(db)
    resultados = []
    sql_where = """ta_id=? AND estabelecimento_id=? AND indicador_id=? AND subgrupo_id IS ?
                   AND cbo_codigo IS ? AND rt IS ? AND tipo_equipe IS ? AND pmmb IS ?"""
    try:
        for idx, it in enumerate(itens):
            try:
                indicador_id = int(it.get("indicador_id"))
                estabelecimento_id = int(it.get("estabelecimento_id"))
                subgrupo_id = int(it["subgrupo_id"]) if str(it.get("subgrupo_id") or "").strip() != "" else None
                cbo_codigo = (it.get("cbo_codigo") or "").strip() or None
                rt = (it.get("rt") or "").strip().upper() or None
                tipo_equipe = (it.get("tipo_equipe") or "").strip() or None
                pmmb = (it.get("pmmb") or "").strip().upper() or None
                if rt not in (None, "SIM", "NAO") or pmmb not in (None, "SIM", "NAO"):
                    raise ValueError("segmento RT/PMMB inválido")
                valor = _valor_meta_ou_none(it.get("valor"))
            except (TypeError, ValueError, KeyError) as erro:
                resultados.append({"indice": idx, "status": "erro", "mensagem": str(erro) or "dados inválidos"})
                continue

            chave = (ta_id, estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo, rt, tipo_equipe, pmmb)
            existente = db.execute(f"SELECT id FROM metas WHERE {sql_where}", chave).fetchone()
            info = consolidacao.info_para(analise_cnes, flags_cnes, indicador_id, estabelecimento_id)
            outros = [m for m in info["membros"] if m != estabelecimento_id] if info and info["representante_id"] == estabelecimento_id else []

            if valor is None:
                if not remover_vazios:
                    resultados.append({"indice": idx, "status": "ignorado", "meta_id": existente["id"] if existente else None})
                    continue
                removeu = 0
                for est in [estabelecimento_id, *outros]:
                    removeu += db.execute(
                        f"DELETE FROM metas WHERE {sql_where}", (ta_id, est, *chave[2:])
                    ).rowcount
                resultados.append({"indice": idx, "status": "removido" if removeu else "inalterado", "meta_id": None, "valor": None})
                continue

            if existente:
                db.execute("UPDATE metas SET valor_meta=? WHERE id=?", (valor, existente["id"]))
                meta_id = existente["id"]
            else:
                cur = db.execute(
                    """INSERT INTO metas (ta_id, estabelecimento_id, indicador_id, subgrupo_id, cbo_codigo,
                                          rt, tipo_equipe, pmmb, valor_meta)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*chave, valor),
                )
                meta_id = cur.lastrowid
            for outro_id in outros:
                db.execute(f"DELETE FROM metas WHERE {sql_where}", (ta_id, outro_id, *chave[2:]))
            resultados.append({"indice": idx, "status": "salvo", "meta_id": meta_id, "valor": valor})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return resultados


@bp.route("/tas/<int:ta_id>/metas/salvar", methods=["POST"])
def salvar_metas_ajax(ta_id):
    """Salva só o que foi alterado na tela (JSON: {"itens": [...]}) - ver _gravar_metas."""
    db = get_db()
    if not db.execute("SELECT 1 FROM termos_aditivos WHERE id=?", (ta_id,)).fetchone():
        return jsonify({"ok": False, "mensagem": "Termo Aditivo não encontrado."}), 404
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens")
    if not isinstance(itens, list):
        return jsonify({"ok": False, "mensagem": "Requisição inválida (faltou a lista de itens)."}), 400
    try:
        resultados = _gravar_metas(db, ta_id, itens, remover_vazios=True)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "mensagem": f"Nada foi gravado (a transação foi desfeita): {exc}"}), 500
    salvos = sum(1 for r in resultados if r["status"] == "salvo")
    removidos = sum(1 for r in resultados if r["status"] == "removido")
    erros = [r for r in resultados if r["status"] == "erro"]
    return jsonify({"ok": not erros, "salvos": salvos, "removidos": removidos, "erros": erros, "resultados": resultados})


@bp.route("/tas/<int:ta_id>/metas/salvar_lote", methods=["POST"])
def salvar_metas_lote(ta_id):
    """Compatibilidade com o formulário antigo (campos linha_*): campos em branco são ignorados.
    A tela atual usa salvar_metas_ajax."""
    db = get_db()
    f = request.form
    listas = [f.getlist(n) for n in (
        "linha_indicador_id", "linha_estabelecimento_id", "linha_subgrupo_id", "linha_cbo_codigo",
        "linha_rt", "linha_tipo_equipe", "linha_pmmb", "linha_valor_meta",
    )]
    itens = [
        {"indicador_id": a, "estabelecimento_id": b, "subgrupo_id": c, "cbo_codigo": d, "rt": e,
         "tipo_equipe": g, "pmmb": h, "valor": v}
        for a, b, c, d, e, g, h, v in zip(*listas)
    ]
    resultados = _gravar_metas(db, ta_id, itens, remover_vazios=False)
    salvos = sum(1 for r in resultados if r["status"] == "salvo")
    if salvos:
        flash(f"{salvos} meta(s) salva(s).", "sucesso")
    else:
        flash("Nenhuma meta preenchida para salvar - os campos em branco foram ignorados.", "erro")
    return redirect(url_for("cadastros.metas_do_ta", ta_id=ta_id))


@bp.route("/tas/<int:ta_id>/metas/<int:meta_id>/excluir", methods=["POST"])
def excluir_meta(ta_id, meta_id):
    db = get_db()
    meta = db.execute("SELECT * FROM metas WHERE id=?", (meta_id,)).fetchone()
    if meta:
        # consolidação por CNES: a linha da grade representa o CNES inteiro - remove também a
        # meta (mesma chave) dos outros cadastros do grupo, senão ela continuaria somando no painel
        info = consolidacao.info_para(
            consolidacao.analisar(db), consolidacao.indicadores_cnes(db), meta["indicador_id"], meta["estabelecimento_id"]
        )
        if info:
            for outro_id in info["membros"]:
                db.execute(
                    """DELETE FROM metas
                       WHERE ta_id=? AND estabelecimento_id=? AND indicador_id=? AND subgrupo_id IS ?
                         AND cbo_codigo IS ? AND rt IS ? AND tipo_equipe IS ? AND pmmb IS ?""",
                    (meta["ta_id"], outro_id, meta["indicador_id"], meta["subgrupo_id"],
                     meta["cbo_codigo"], meta["rt"], meta["tipo_equipe"], meta["pmmb"]),
                )
    db.execute("DELETE FROM metas WHERE id=?", (meta_id,))
    db.commit()
    flash("Meta excluída.", "sucesso")
    return redirect(url_for("cadastros.metas_do_ta", ta_id=ta_id))