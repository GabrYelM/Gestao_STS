import os
import io
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor
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
    exportar_excel_completo,
    obter_nominal_fe_json,
    obter_nominal_fr_json,
    executar_extracao_bi_fr,
    obter_unidades_auditadas_cid,
    gerar_exportacao_auditoria_cids,
    resolver_arquivo_ou_zip,
    extrair_e_identificar_pacote_zip
)

bp = Blueprint("fila_espera", __name__, url_prefix="/fila_espera")

executor_extracao_fr = ThreadPoolExecutor(max_workers=1)
evento_cancelar_fr = threading.Event()
status_extracao_fr = {
    "em_andamento": False,
    "concluido": False,
    "cancelado": False,
    "progresso": "",
    "porcentagem": 0,
    "logs": [],
    "total_fr": 0,
    "erro": None
}


def worker_extracao_fr(usuario, senha, relatorio_opcao):
    global status_extracao_fr, evento_cancelar_fr
    evento_cancelar_fr.clear()
    status_extracao_fr["em_andamento"] = True
    status_extracao_fr["concluido"] = False
    status_extracao_fr["cancelado"] = False
    status_extracao_fr["progresso"] = "Iniciando robô de extração..."
    status_extracao_fr["porcentagem"] = 5
    status_extracao_fr["logs"] = []
    status_extracao_fr["erro"] = None

    def callback(msg, pct):
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_extracao_fr["logs"].append(f"[{timestamp}] {msg}")
        status_extracao_fr["progresso"] = msg
        if pct is not None:
            status_extracao_fr["porcentagem"] = pct

    resumo, erro = executar_extracao_bi_fr(
        usuario=usuario,
        senha=senha,
        relatorio_opcao=relatorio_opcao,
        callback_status=callback,
        cancel_event=evento_cancelar_fr
    )

    status_extracao_fr["em_andamento"] = False
    status_extracao_fr["concluido"] = True

    if evento_cancelar_fr.is_set():
        status_extracao_fr["cancelado"] = True
        status_extracao_fr["progresso"] = "Extração cancelada pelo usuário."
    elif erro:
        status_extracao_fr["erro"] = erro
        status_extracao_fr["progresso"] = f"Erro: {erro}"
    else:
        status_extracao_fr["total_fr"] = resumo.get("total_fr", 0) if resumo else 0
        status_extracao_fr["porcentagem"] = 100
        status_extracao_fr["progresso"] = "Extração e substituição concluídas com sucesso!"


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

    # Carregar lista de unidades com linhas auditadas para o modal de exportação por unidade
    unidades_auditadas = obter_unidades_auditadas_cid()

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
        resumo_fr=resumo_fr,
        unidades_auditadas=unidades_auditadas
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


@bp.route("/dados_nominal_fe_json")
def dados_nominal_fe_json():
    """Retorna todos os registros da Fila de Espera Nominal para o DataTable client-side com Excel Filter."""
    estab_filtro = request.args.get("estabelecimento", "").strip()
    espec_filtro = request.args.get("especialidade", "").strip()
    status_cid_filtro = request.args.get("status_cid", "").strip()
    return jsonify(obter_nominal_fe_json(estab_filtro, espec_filtro, status_cid_filtro))


@bp.route("/dados_nominal_fr_json")
def dados_nominal_fr_json():
    """Retorna todos os registros da Fila do Regulador Nominal para o DataTable client-side com Excel Filter."""
    estab_filtro = request.args.get("estabelecimento", "").strip()
    espec_filtro = request.args.get("especialidade", "").strip()
    status_cid_filtro = request.args.get("status_cid", "").strip()
    return jsonify(obter_nominal_fr_json(estab_filtro, espec_filtro, status_cid_filtro))


@bp.route("/extracao")
def tela_extracao():
    """Tela de extração automatizada de relatórios do BI e upload manual com substituição total."""
    init_db()
    metricas = obter_metricas_cards()
    return render_template("fila_espera/extracao.html", metricas=metricas)


@bp.route("/iniciar_extracao", methods=["POST"])
def iniciar_extracao():
    """Dispara a extração em segundo plano dos relatórios FR-03 e FR-04 via Playwright."""
    global status_extracao_fr
    if status_extracao_fr.get("em_andamento", False):
        return jsonify({"erro": "Já existe uma extração em andamento."}), 400

    if request.is_json:
        data = request.get_json() or {}
        usuario = data.get("usuario", "").strip()
        senha = data.get("senha", "").strip()
        relatorio = data.get("relatorio", "FR_TODOS").strip()
    else:
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()
        relatorio = request.form.get("relatorio", "FR_TODOS").strip()

    if not usuario or not senha:
        return jsonify({"erro": "Informe o Usuário e Senha corporativos do BI (SIGA Saúde / Prodam)."}), 400

    executor_extracao_fr.submit(worker_extracao_fr, usuario, senha, relatorio)
    return jsonify({"mensagem": "Extração iniciada com sucesso!", "status": "em_andamento"}), 200


@bp.route("/status_extracao")
def status_extracao_route():
    """Consulta o progresso e logs da extração em segundo plano."""
    return jsonify(status_extracao_fr)


@bp.route("/cancelar_extracao", methods=["POST"])
def cancelar_extracao_route():
    """Interrompe a execução do robô de extração do BI."""
    global evento_cancelar_fr, status_extracao_fr
    if not status_extracao_fr.get("em_andamento", False):
        return jsonify({"mensagem": "Nenhuma extração em andamento."}), 200

    evento_cancelar_fr.set()
    status_extracao_fr["cancelado"] = True
    status_extracao_fr["em_andamento"] = False
    status_extracao_fr["concluido"] = True
    status_extracao_fr["progresso"] = "Extração cancelada pelo usuário."
    return jsonify({"mensagem": "Cancelamento solicitado com sucesso."}), 200


@bp.route("/upload_manual", methods=["POST"])
@bp.route("/importar", methods=["POST"])
def upload_manual():
    """Recebe upload dos arquivos e substitui integralmente os registros anteriores. Aceita .CSV, .TXT e .ZIP."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")

    relatorio = request.form.get("relatorio", "").strip()
    arquivo_geral = request.files.get("arquivo")
    siga_file = request.files.get("arquivo_siga")
    fr03_file = request.files.get("arquivo_fr03")
    fr04_file = request.files.get("arquivo_fr04")

    # Mapeamento do campo geral idêntico ao modelo de upload do BI
    if arquivo_geral and arquivo_geral.filename:
        nome_arq_lower = arquivo_geral.filename.lower()
        if relatorio in ["SIGA", "siga"]:
            siga_file = arquivo_geral
        elif relatorio in ["FR03", "fr03"]:
            fr03_file = arquivo_geral
        elif relatorio in ["FR04", "fr04"]:
            fr04_file = arquivo_geral
        else:
            # TODOS ou PACOTE
            if nome_arq_lower.endswith(".zip"):
                siga_file = arquivo_geral
            elif "fr-03" in nome_arq_lower or "fr03" in nome_arq_lower:
                fr03_file = arquivo_geral
            elif "fr-04" in nome_arq_lower or "fr04" in nome_arq_lower:
                fr04_file = arquivo_geral
            else:
                siga_file = arquivo_geral

    if not (siga_file or fr03_file or fr04_file):
        msg = "Selecione pelo menos um arquivo (.csv/.txt/.zip) para upload e substituição."
        if is_ajax:
            return jsonify({"status": "error", "mensagem": msg}), 400
        flash(msg, "warning")
        return redirect(url_for("fila_espera.tela_extracao"))

    upload_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "uploads_fila_espera")
    os.makedirs(upload_dir, exist_ok=True)

    path_siga = None
    path_fr03 = None
    path_fr04 = None
    nome_siga = None
    nome_fr03 = None
    nome_fr04 = None

    if siga_file and siga_file.filename:
        nome_siga = secure_filename(siga_file.filename)
        path_siga = os.path.join(upload_dir, nome_siga)
        siga_file.save(path_siga)

    if fr03_file and fr03_file.filename:
        nome_fr03 = secure_filename(fr03_file.filename)
        path_fr03 = os.path.join(upload_dir, nome_fr03)
        fr03_file.save(path_fr03)

    if fr04_file and fr04_file.filename:
        nome_fr04 = secure_filename(fr04_file.filename)
        path_fr04 = os.path.join(upload_dir, nome_fr04)
        fr04_file.save(path_fr04)

    # 1. Caso especial: Um arquivo .ZIP foi enviado no campo SIGA/Geral e contém múltiplos relatórios (SIGA e/ou FR-03/FR-04)
    if path_siga and (path_siga.lower().endswith(".zip") or zipfile.is_zipfile(path_siga)):
        pacote = extrair_e_identificar_pacote_zip(path_siga, upload_dir)
        if pacote:
            if pacote["siga_path"]:
                path_siga = pacote["siga_path"]
                nome_siga = pacote["siga_nome"]
            if not path_fr03 and pacote["fr03_path"]:
                path_fr03 = pacote["fr03_path"]
                nome_fr03 = pacote["fr03_nome"]
            if not path_fr04 and pacote["fr04_path"]:
                path_fr04 = pacote["fr04_path"]
                nome_fr04 = pacote["fr04_nome"]

    # 2. Resolução individual de arquivos .ZIP caso tenham sido enviados separadamente
    if path_siga and (path_siga.lower().endswith(".zip") or zipfile.is_zipfile(path_siga)):
        p, n = resolver_arquivo_ou_zip(path_siga, upload_dir, tipo_esperado="siga")
        if p:
            path_siga = p
            nome_siga = n

    if path_fr03 and (path_fr03.lower().endswith(".zip") or zipfile.is_zipfile(path_fr03)):
        p, n = resolver_arquivo_ou_zip(path_fr03, upload_dir, tipo_esperado="fr03")
        if p:
            path_fr03 = p
            nome_fr03 = n

    if path_fr04 and (path_fr04.lower().endswith(".zip") or zipfile.is_zipfile(path_fr04)):
        p, n = resolver_arquivo_ou_zip(path_fr04, upload_dir, tipo_esperado="fr04")
        if p:
            path_fr04 = p
            nome_fr04 = n

    try:
        resumo = processar_arquivos_fila(
            path_siga, path_fr03, path_fr04,
            nome_siga=nome_siga,
            nome_fr03=nome_fr03,
            nome_fr04=nome_fr04
        )
        msg_sucesso = (
            f"Arquivo(s) processado(s) com sucesso! Registros anteriores substituídos. "
            f"Fila de Espera: {resumo['total_fe']:,} | Fila do Regulador: {resumo['total_fr']:,}."
        ).replace(",", ".")

        if is_ajax:
            return jsonify({
                "status": "success",
                "mensagem": msg_sucesso,
                "total_fe": resumo["total_fe"],
                "total_fr": resumo["total_fr"]
            }), 200

        flash(msg_sucesso, "success")
        return redirect(url_for("fila_espera.index"))
    except Exception as e:
        msg_erro = f"Erro ao processar os arquivos da fila: {e}"
        if is_ajax:
            return jsonify({"status": "error", "mensagem": msg_erro}), 400
        flash(msg_erro, "danger")
        return redirect(url_for("fila_espera.tela_extracao"))


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
    """Restaura as 20 regras oficiais da tabela regulatória."""
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

    fe_recalc, fr_recalc = recalcular_validacoes_cid()
    flash(f"Configuração de CIDs restaurada com sucesso com as 20 regras oficiais! ({fe_recalc} linhas de Fila de Espera e {fr_recalc} de Regulação recalculadas).", "success")
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


@bp.route("/exportar_auditoria_cids", methods=["GET", "POST"])
def exportar_auditoria_cids_route():
    """
    Gera e exporta planilhas com as linhas auditadas de CIDs (CORRETO ou INCORRETO):
    - 1 unidade selecionada: download direto do arquivo .xlsx dessa unidade.
    - 2 ou mais unidades (ou todas): download de arquivo .zip com 1 planilha .xlsx por unidade.
    """
    if request.method == "POST":
        unidades = request.form.getlist("unidades")
        status_filtro = request.form.get("status_filtro", "TODOS").strip()
    else:
        unidade_param = request.args.get("unidade", "").strip()
        unidades = [unidade_param] if unidade_param else []
        status_filtro = request.args.get("status_filtro", "TODOS").strip()

    if not unidades:
        flash("Selecione pelo menos uma unidade para exportação.", "warning")
        return redirect(url_for("fila_espera.index"))

    try:
        buffer, nome_arquivo, mimetype = gerar_exportacao_auditoria_cids(unidades, status_filtro)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype=mimetype
        )
    except Exception as e:
        flash(f"Erro ao exportar auditoria de CIDs por unidade: {e}", "danger")
        return redirect(url_for("fila_espera.index"))
