import os
import io
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file, session
from werkzeug.utils import secure_filename
from decorators import admin_required
from services.fila_espera import (
    get_db,
    init_db,
    obter_metricas_cards,
    obter_resumo_fe,
    obter_resumo_fr,
    obter_estabelecimentos_e_especialidades,
    carregar_arquivos_locais_pasta,
    processar_arquivos_fila,
    recalcular_validacoes_cid,
    exportar_excel_completo
)

bp = Blueprint("fila_espera", __name__, url_prefix="/fila_espera")


@bp.before_app_request
def ensure_db():
    # Garante tabelas criadas no startup
    pass


@bp.route("/")
def index():
    init_db()
    metricas = obter_metricas_cards()
    estabelecimentos, especialidades = obter_estabelecimentos_e_especialidades()

    # Filtros padrão da requisição
    estab_filtro = request.args.get("estabelecimento", "")
    espec_filtro = request.args.get("especialidade", "")
    status_cid_filtro = request.args.get("status_cid", "")
    aba_ativa = request.args.get("aba", "resumo_fe")

    # Carregar os resumos diretamente para renderização rápida inicial
    resumo_fe = obter_resumo_fe(
        estab_filtro=estab_filtro,
        espec_filtro=espec_filtro,
        status_cid_filtro=status_cid_filtro
    )
    resumo_fr = obter_resumo_fr(
        estab_filtro=estab_filtro,
        espec_filtro=espec_filtro,
        status_cid_filtro=status_cid_filtro
    )

    return render_template(
        "fila_espera/index.html",
        metricas=metricas,
        estabelecimentos=estabelecimentos,
        especialidades=especialidades,
        estab_selecionado=estab_filtro,
        espec_selecionada=espec_filtro,
        status_cid_selecionado=status_cid_filtro,
        aba_ativa=aba_ativa,
        resumo_fe=resumo_fe,
        resumo_fr=resumo_fr
    )


@bp.route("/dados_nominal_fe")
def dados_nominal_fe():
    """Endpoint server-side para DataTables da Fila de Espera Nominal (SIGA)."""
    conn = get_db()
    draw = int(request.args.get("draw", 1))
    start = int(request.args.get("start", 0))
    length = int(request.args.get("length", 25))

    estab_filtro = request.args.get("estabelecimento", "").strip()
    espec_filtro = request.args.get("especialidade", "").strip()
    status_cid_filtro = request.args.get("status_cid", "").strip()
    search_value = request.args.get("search[value]", "").strip()

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

    if search_value:
        filtros.append("""(
            nome_paciente LIKE ? OR
            cns_paciente LIKE ? OR
            protocolo LIKE ? OR
            cid LIKE ? OR
            especialidade LIKE ? OR
            nome_solicitante LIKE ?
        )""")
        val = f"%{search_value}%"
        params.extend([val, val, val, val, val, val])

    where_clause = "WHERE " + " AND ".join(filtros) if filtros else ""

    # Total sem filtros
    total_records = conn.execute("SELECT COUNT(*) FROM fila_espera_nominal").fetchone()[0]

    # Total com filtros
    filtered_records = conn.execute(f"SELECT COUNT(*) FROM fila_espera_nominal {where_clause}", params).fetchone()[0]

    # Ordenação
    order_col_idx = request.args.get("order[0][column]", "0")
    order_dir = request.args.get("order[0][dir]", "desc")
    order_dir_clean = "DESC" if order_dir.lower() == "desc" else "ASC"

    # Mapeamento de colunas do DataTable
    col_map = {
        "0": "data_inclusao",
        "1": "nome_solicitante",
        "2": "especialidade",
        "3": "cbo_codigo",
        "4": "procedimento",
        "5": "tipo_atendimento",
        "6": "protocolo",
        "7": "nome_paciente",
        "8": "cns_paciente",
        "9": "prioridade",
        "10": "cid",
        "11": "cid_status"
    }
    col_order = col_map.get(str(order_col_idx), "data_inclusao")

    query = f"""
        SELECT
            data_inclusao, nome_solicitante, especialidade, cbo_codigo, procedimento,
            tipo_atendimento, protocolo, nome_paciente, cns_paciente, idade, sexo,
            prioridade, cid, cid_status, cid_esperado, observacoes
        FROM fila_espera_nominal
        {where_clause}
        ORDER BY {col_order} {order_dir_clean}
        LIMIT ? OFFSET ?
    """
    params_query = list(params) + [length, start]
    rows = conn.execute(query, params_query).fetchall()
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

        data.append([
            r["data_inclusao"] or "-",
            r["nome_solicitante"] or "-",
            r["especialidade"] or "-",
            f'<span class="badge bg-light text-dark border font-monospace">{r["cbo_codigo"]}</span>' if r["cbo_codigo"] else '<span class="text-muted">-</span>',
            r["procedimento"] or "-",
            r["tipo_atendimento"] or "-",
            f'<span class="font-monospace fw-semibold">{r["protocolo"]}</span>' if r["protocolo"] else "-",
            f'<span class="fw-semibold text-primary">{r["nome_paciente"]}</span>' if r["nome_paciente"] else "-",
            f'<span class="font-monospace small text-muted">{r["cns_paciente"]}</span>' if r["cns_paciente"] else "-",
            r["prioridade"] or "-",
            f'<span class="badge bg-light text-primary border font-monospace fw-bold">{r["cid"]}</span>' if r["cid"] else "-",
            badge
        ])

    return jsonify({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": filtered_records,
        "data": data
    })


@bp.route("/dados_nominal_fr")
def dados_nominal_fr():
    """Endpoint server-side para DataTables da Fila do Regulador Nominal (FR-03 + FR-04)."""
    conn = get_db()
    draw = int(request.args.get("draw", 1))
    start = int(request.args.get("start", 0))
    length = int(request.args.get("length", 25))

    estab_filtro = request.args.get("estabelecimento", "").strip()
    espec_filtro = request.args.get("especialidade", "").strip()
    status_cid_filtro = request.args.get("status_cid", "").strip()
    search_value = request.args.get("search[value]", "").strip()

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

    if search_value:
        filtros.append("""(
            nome_paciente LIKE ? OR
            cns_paciente LIKE ? OR
            numero_solicitacao LIKE ? OR
            codigo_cid LIKE ? OR
            nome_cid LIKE ? OR
            especialidade LIKE ? OR
            estabelecimento_solicitante LIKE ?
        )""")
        val = f"%{search_value}%"
        params.extend([val, val, val, val, val, val, val])

    where_clause = "WHERE " + " AND ".join(filtros) if filtros else ""

    total_records = conn.execute("SELECT COUNT(*) FROM fila_regulador_nominal").fetchone()[0]
    filtered_records = conn.execute(f"SELECT COUNT(*) FROM fila_regulador_nominal {where_clause}", params).fetchone()[0]

    order_col_idx = request.args.get("order[0][column]", "0")
    order_dir = request.args.get("order[0][dir]", "desc")
    order_dir_clean = "DESC" if order_dir.lower() == "desc" else "ASC"

    col_map = {
        "0": "data_entrada_fila",
        "1": "estabelecimento_solicitante",
        "2": "especialidade",
        "3": "cbo_codigo",
        "4": "procedimento",
        "5": "prioridade",
        "6": "numero_solicitacao",
        "7": "nome_paciente",
        "8": "codigo_cid",
        "9": "cid_status",
        "10": "situacao_fila_regulador"
    }
    col_order = col_map.get(str(order_col_idx), "data_entrada_fila")

    query = f"""
        SELECT
            data_entrada_fila, estabelecimento_solicitante, especialidade, cbo_codigo, procedimento,
            prioridade, numero_solicitacao, nome_paciente, cns_paciente, idade, sexo,
            codigo_cid, nome_cid, cid_status, cid_esperado, situacao_fila_regulador,
            motivo_encaminhamento, regulador
        FROM fila_regulador_nominal
        {where_clause}
        ORDER BY {col_order} {order_dir_clean}
        LIMIT ? OFFSET ?
    """
    params_query = list(params) + [length, start]
    rows = conn.execute(query, params_query).fetchall()
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

        data.append([
            r["data_entrada_fila"] or "-",
            r["estabelecimento_solicitante"] or "-",
            r["especialidade"] or "-",
            f'<span class="badge bg-light text-dark border font-monospace">{r["cbo_codigo"]}</span>' if r["cbo_codigo"] else '<span class="text-muted">-</span>',
            r["procedimento"] or "-",
            prio_badge,
            f'<span class="font-monospace fw-semibold">{r["numero_solicitacao"]}</span>' if r["numero_solicitacao"] else "-",
            f'<span class="fw-semibold text-primary">{r["nome_paciente"]}</span>' if r["nome_paciente"] else "-",
            f'<span class="badge bg-light text-primary border font-monospace fw-bold">{r["codigo_cid"]}</span>' if r["codigo_cid"] else "-",
            badge,
            f'<span class="badge bg-light text-dark border small">{r["situacao_fila_regulador"]}</span>' if r["situacao_fila_regulador"] else "-"
        ])

    return jsonify({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": filtered_records,
        "data": data
    })


@bp.route("/importar", methods=["POST"])
@admin_required
def importar_arquivos():
    """Recebe upload dos 3 arquivos (SIGA, FR-03 e FR-04) e processa."""
    siga_file = request.files.get("arquivo_siga")
    fr03_file = request.files.get("arquivo_fr03")
    fr04_file = request.files.get("arquivo_fr04")

    if not (siga_file or fr03_file):
        flash("Selecione pelo menos o arquivo SIGA ou os arquivos FR-03 e FR-04.", "warning")
        return redirect(url_for("fila_espera.index"))

    upload_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "uploads_fila_espera")
    os.makedirs(upload_dir, exist_ok=True)

    path_siga = None
    path_fr03 = None
    path_fr04 = None

    if siga_file and siga_file.filename:
        path_siga = os.path.join(upload_dir, secure_filename(siga_file.filename))
        siga_file.save(path_siga)

    if fr03_file and fr03_file.filename:
        path_fr03 = os.path.join(upload_dir, secure_filename(fr03_file.filename))
        fr03_file.save(path_fr03)

    if fr04_file and fr04_file.filename:
        path_fr04 = os.path.join(upload_dir, secure_filename(fr04_file.filename))
        fr04_file.save(path_fr04)

    try:
        resumo = processar_arquivos_fila(
            path_siga, path_fr03, path_fr04,
            nome_siga=siga_file.filename if siga_file else "Nenhum",
            nome_fr03=fr03_file.filename if fr03_file else "Nenhum",
            nome_fr04=fr04_file.filename if fr04_file else "Nenhum"
        )
        flash(f"Ingestão concluída com sucesso! Fila de Espera: {resumo['total_fe']} registros | Fila do Regulador: {resumo['total_fr']} registros.", "success")
    except Exception as e:
        flash(f"Erro ao processar os arquivos da fila de espera: {e}", "danger")

    return redirect(url_for("fila_espera.index"))


@bp.route("/importar_pasta", methods=["POST"])
@admin_required
def importar_pasta():
    """Atalho para processar diretamente os arquivos já existentes na pasta ARQUIVOS ORIGINAIS/Fila de espera."""
    resumo, erro = carregar_arquivos_locais_pasta()
    if erro:
        flash(erro, "danger")
    else:
        flash(f"Arquivos da pasta processados com sucesso! Fila de Espera: {resumo['total_fe']} registros | Fila do Regulador: {resumo['total_fr']} registros.", "success")
    return redirect(url_for("fila_espera.index"))


@bp.route("/cids")
def gerenciar_cids():
    """Tela de configuração e alteração dos CIDs definidos."""
    conn = get_db()
    regras = [dict(r) for r in conn.execute("""
        SELECT id, especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome,
               cid, cid_descricao, observacoes, ativo, atualizado_em
        FROM fila_cid_config
        ORDER BY especialidade, cid
    """).fetchall()]

    especialidades_conhecidas = [r[0] for r in conn.execute("""
        SELECT DISTINCT especialidade FROM (
            SELECT especialidade FROM fila_cid_config
            UNION
            SELECT especialidade FROM fila_espera_nominal WHERE especialidade LIKE '%ODONTO%'
            UNION
            SELECT especialidade FROM fila_regulador_nominal WHERE especialidade LIKE '%ODONTO%' OR especialidade LIKE '%Odont%'
        ) WHERE especialidade IS NOT NULL AND especialidade != ''
        ORDER BY especialidade
    """).fetchall()]
    conn.close()
    return render_template("fila_espera/cids.html", regras=regras, especialidades_conhecidas=especialidades_conhecidas)


@bp.route("/cids/salvar", methods=["POST"])
def salvar_cid():
    """Adiciona ou edita uma regra de CID definido."""
    regra_id = request.form.get("id")
    especialidade = request.form.get("especialidade", "").strip()
    cbo_codigo = request.form.get("cbo_codigo", "").strip()
    cbo_nome = request.form.get("cbo_nome", "").strip()
    procedimento_codigo = request.form.get("procedimento_codigo", "").strip()
    procedimento_nome = request.form.get("procedimento_nome", "").strip()
    cid = request.form.get("cid", "").strip().upper()
    cid_descricao = request.form.get("cid_descricao", "").strip()
    observacoes = request.form.get("observacoes", "").strip()

    if not especialidade or not cid:
        flash("Especialidade e CID são campos obrigatórios.", "warning")
        return redirect(url_for("fila_espera.gerenciar_cids"))

    conn = get_db()
    with conn:
        if regra_id and regra_id.isdigit():
            conn.execute("""
                UPDATE fila_cid_config
                SET especialidade = ?, cbo_codigo = ?, cbo_nome = ?,
                    procedimento_codigo = ?, procedimento_nome = ?,
                    cid = ?, cid_descricao = ?, observacoes = ?,
                    atualizado_em = datetime('now', 'localtime')
                WHERE id = ?
            """, (especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome, cid, cid_descricao, observacoes, int(regra_id)))
            flash(f"Regra para o CID {cid} atualizada com sucesso!", "success")
        else:
            conn.execute("""
                INSERT INTO fila_cid_config (
                    especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome,
                    cid, cid_descricao, observacoes, ativo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (especialidade, cbo_codigo, cbo_nome, procedimento_codigo, procedimento_nome, cid, cid_descricao, observacoes))
            flash(f"Nova regra para o CID {cid} cadastrada com sucesso!", "success")
    conn.close()

    # Recalcula validações em lote
    fe_recalc, fr_recalc = recalcular_validacoes_cid()
    flash(f"Validações recalculadas: {fe_recalc} linhas de Fila de Espera e {fr_recalc} de Fila do Regulador atualizadas.", "info")

    return redirect(url_for("fila_espera.gerenciar_cids"))


@bp.route("/cids/excluir/<int:id>", methods=["POST"])
def excluir_cid(id):
    """Exclui uma regra de CID definido."""
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM fila_cid_config WHERE id = ?", (id,))
    conn.close()

    fe_recalc, fr_recalc = recalcular_validacoes_cid()
    flash("Regra excluída com sucesso e validações recalculadas nas filas.", "success")
    return redirect(url_for("fila_espera.gerenciar_cids"))


@bp.route("/cids/restaurar", methods=["POST"])
def restaurar_cids():
    """Restaura as regras padrão oficiais da portaria e variantes clínicas."""
    from services.fila_espera import CIDS_DEFINIDOS_PADRAO
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM fila_cid_config")
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

    recalcular_validacoes_cid()
    flash("Configuração de CIDs restaurada com sucesso com todos os padrões oficiais e variantes clínicas!", "success")
    return redirect(url_for("fila_espera.gerenciar_cids"))


@bp.route("/exportar_excel")
def exportar_excel():
    """Gera e faz o download da planilha Excel com as 4 abas e a aba de CIDs definidos."""
    try:
        wb = exportar_excel_completo()
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        nome_arquivo = f"Fila_Espera_e_Regulador_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        flash(f"Erro ao exportar a planilha: {e}", "danger")
        return redirect(url_for("fila_espera.index"))
