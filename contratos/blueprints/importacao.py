import os
import zipfile

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..etl import (
    BI_SIGA_CONFIGS,
    BI_SIGA_ROTULOS,
    importar_at02,
    importar_bi_siga,
    importar_dtic_rel130,
    importar_dtic_rel134,
    importar_sisad,
    importar_visita_domiciliar,
    importar_webssas,
)
from ..funcoes import (
    auto_cadastrar_pendentes,
    carga_base,
    diagnostico_metas,
    pendencias,
    recalcular_periodo,
    registrar_log,
)

# =============================================================================
# COMO ADICIONAR UMA NOVA FONTE DE IMPORTAÇÃO (ex.: um 3º sistema além de
# AT-02 e Webssas) SEM QUEBRAR AS DUAS JÁ EXISTENTES
# =============================================================================
# Cada fonte é totalmente isolada das outras (staging própria, rota própria,
# card próprio na tela) - adicionar uma nova NUNCA exige alterar o código de
# importação do AT-02 ou do Webssas. Roteiro, nesta ordem:
#
#   1. app/schema.sql: criar `staging_<nova_fonte>` (ver o comentário-modelo
#      logo acima de `staging_webssas` no arquivo) e rodar `python run.py`
#      de novo (ou apagar o stspe.db de teste) para a tabela existir.
#      Cadastrar a fonte em `fontes_dados` (INSERT direto ou pela seed) com
#      um `nome` em maiúsculas (ex.: 'SIGTAP') - é esse nome que amarra tudo.
#   2. app/etl/<nova_fonte>.py: função `importar_<nova_fonte>(caminho,
#      periodo, db, nome_arquivo, ...)` que lê o arquivo e grava em
#      `staging_<nova_fonte>` + numa linha em `importacoes` - use
#      app/etl/webssas.py como modelo mais simples (um arquivo, uma tabela
#      de staging) ou app/etl/at02.py se a fonte for por linha/procedimento.
#   3. app/etl/calculo.py: função `calcular_<nova_fonte>(db, periodo,
#      importacao_id=None)` que lê `staging_<nova_fonte>` e grava em
#      `fato_apuracao` (ver `calcular_webssas` para o formato agregado por
#      indicador, ou `calcular_at02` para o formato granular por
#      procedimento/CBO) - e adicionar um novo `elif` em `recalcular_periodo`
#      (procure o comentário "PONTO DE EXTENSÃO" logo abaixo, no mesmo
#      arquivo) apontando para essa função nova.
#   4. app/blueprints/importacao.py (este arquivo): uma nova rota
#      `/importar/<nova_fonte>` (copie `upload_webssas` como modelo) chamando
#      a função do passo 2 e depois `recalcular_periodo(db, periodo,
#      'NOVA_FONTE')`.
#   5. app/templates/importar.html: um novo card de upload (copie o card do
#      Webssas) com o `action` apontando para a rota do passo 4 - procure o
#      comentário "PONTO DE EXTENSÃO" no arquivo.
#
# Nenhum desses passos precisa tocar em código do AT-02/Webssas - o painel e
# os relatórios já leem de `fato_apuracao`/`resultados_indicador`, que são
# genéricos para qualquer fonte (basta a linha existir lá).
# =============================================================================

bp = Blueprint("importacao", __name__, url_prefix="/contratos/importar")


def _salvar_upload(arquivo):
    """
    Salva o upload com um nome ÚNICO gerado no disco (uuid + extensão
    original), em vez de usar o nome original sanitizado.

    Isso evita dois problemas vistos no Windows:
    1. secure_filename() pode corromper nomes com acento (ex.: 'mês.csv'
       virando 'mU00eas.csv'), gerando um caminho inválido.
    2. Reenviar um arquivo com o mesmo nome de um upload anterior podia
       colidir com um arquivo ainda aberto/travado por outro programa
       (Excel, antivírus, sincronização do OneDrive), dando
       PermissionError ao tentar sobrescrever.

    O nome ORIGINAL do arquivo (não o nome no disco) é sempre preservado à
    parte para exibição/log - ver o retorno da função.
    """
    import uuid

    pasta_upload = (
        current_app.config.get("STSPE_UPLOAD_FOLDER")
        or current_app.config.get("UPLOAD_FOLDER")
        or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads_tmp")
    )
    os.makedirs(pasta_upload, exist_ok=True)
    nome_original = arquivo.filename or "arquivo"
    extensao = os.path.splitext(nome_original)[1]
    nome_no_disco = f"{uuid.uuid4().hex}{extensao}"
    caminho = os.path.join(pasta_upload, nome_no_disco)

    try:
        arquivo.save(caminho)
    except PermissionError as exc:
        raise PermissionError(
            "Não foi possível salvar o arquivo temporário em "
            f"'{pasta_upload}'. Verifique se a pasta "
            "não está sendo bloqueada por antivírus/OneDrive, e se o "
            "usuário que roda o Flask tem permissão de escrita nela."
        ) from exc

    return caminho, nome_original


def _top(lista, n=5):
    return lista[:n]


def _montar_mensagem_at02(prefixo, resumo):
    msg = (
        f"{prefixo}: {resumo['total_linhas']} linhas processadas. Vinculadas a "
        f"indicadores: {resumo['linhas_vinculadas']} | sem estabelecimento cadastrado: "
        f"{resumo['sem_estabelecimento']} | sem indicador correspondente: "
        f"{resumo['sem_indicador']} "
        f"(procedimento sem vínculo: {resumo['sem_indicador_procedimento_nao_vinculado']}, "
        f"CBO não autorizado pelo indicador: {resumo['sem_indicador_cbo_nao_autorizado']}, "
        f"serviço da unidade incompatível com o indicador: {resumo['sem_indicador_servico_incompativel']})"
    )
    if resumo.get("linhas_casadas_por_cnes"):
        msg += (f"\n{resumo['linhas_casadas_por_cnes']} linha(s) casaram com o estabelecimento pelo CNES "
                "(o CMES da linha não está cadastrado, mas o CNES aponta para um cadastro).")
    if resumo["cmes_nao_encontrados"]:
        msg += "\nCMES não cadastrados (top 5 de %d): " % len(resumo["cmes_nao_encontrados"]) + ", ".join(
            f"{cmes} ({n}x)" for cmes, n in _top(resumo["cmes_nao_encontrados"])
        )
    if resumo["cbo_nao_cadastrados"]:
        msg += "\nCBOs do arquivo não cadastrados (top 5 de %d): " % len(resumo["cbo_nao_cadastrados"]) + ", ".join(
            f"{cbo} ({n}x)" for cbo, n in _top(resumo["cbo_nao_cadastrados"])
        )
    if resumo["procedimentos_sem_indicador"]:
        msg += "\nProcedimentos sem NENHUM vínculo de indicador (top 5 de %d): " % len(resumo["procedimentos_sem_indicador"]) + ", ".join(
            f"{p} ({n}x)" for p, n in _top(resumo["procedimentos_sem_indicador"])
        )
    if resumo["cbo_removeu_indicador"]:
        msg += (
            "\nProcedimento tem indicador vinculado, mas o CBO da linha não está "
            "autorizado nesse indicador (top 5 de %d): " % len(resumo["cbo_removeu_indicador"]) + ", ".join(
                f"{c} ({n}x)" for c, n in _top(resumo["cbo_removeu_indicador"])
            )
        )
    if resumo["servico_removeu_indicador"]:
        msg += (
            "\nProcedimento/CBO batem, mas a unidade não tem o tipo de serviço "
            "que o indicador exige (top 5 de %d): " % len(resumo["servico_removeu_indicador"]) + ", ".join(
                f"{u} ({n}x)" for u, n in _top(resumo["servico_removeu_indicador"])
            )
        )
    msg += "\nVeja o diagnóstico completo (sem limite de 5) em Importar dados > Ver logs."
    return msg


# =============================================================================
# IDENTIFICAÇÃO AUTOMÁTICA DE ARQUIVO PELO NOME + UPLOAD MÚLTIPLO
# =============================================================================
# Cada entrada é (pedaço do nome do arquivo em minúsculas, código da fonte).
# Verificado na ordem abaixo - o primeiro que bater "casa" o arquivo com
# aquela fonte, então entradas mais específicas vêm antes das mais genéricas.
# Casa por CONTER o pedaço, não por bater exato, porque os relatórios saem
# com sufixo de data/hora no nome (ex.: "..._20260915_0100.csv").
DETECCAO_POR_NOME_ARQUIVO = [
    ("at-02", "AT02"),
    ("at-08", "AT08"),
    ("at-11", "AT11"),
    ("at-39", "AT39"),
    ("at-40", "AT40"),
    ("at-48", "AT48"),
    ("at-49", "AT49"),
    ("at-57", "AT57"),
    ("at-61", "AT61"),
    ("visita_domiciliar_periodica", "VISITA_DOMICILIAR"),
    ("atividade_coletiva_por_profissional", "DTIC_REL134"),
    ("esus_atend_domiciliar", "DTIC_REL130"),
    ("questionario ad", "SISAD"),
    ("questionário ad", "SISAD"),
    ("rel_siga_producao_hospital_dia", "IGNORAR"),
    ("demonstrativo de apontamentos", "WEBSSAS"),
    ("webssas", "WEBSSAS"),
]


def _detectar_fonte_por_nome(nome_arquivo, caminho_disco=None):
    nome = (nome_arquivo or "").lower()
    for pedaco, fonte in DETECCAO_POR_NOME_ARQUIVO:
        if pedaco in nome:
            return fonte

    # Se for um ZIP e o nome externo não casou, inspeciona os nomes internos do arquivo
    if caminho_disco and (nome.endswith(".zip") or (os.path.exists(caminho_disco) and zipfile.is_zipfile(caminho_disco))):
        try:
            with zipfile.ZipFile(caminho_disco) as z:
                for interno in z.namelist():
                    nome_int = interno.lower()
                    for pedaco, fonte in DETECCAO_POR_NOME_ARQUIVO:
                        if pedaco in nome_int:
                            return fonte
        except Exception:
            pass

    return None


@bp.route("/multiplo", methods=["POST"])
def upload_multiplo():
    """
    Upload de um ou vários arquivos de uma vez, cada um identificado
    automaticamente pelo nome (ver DETECCAO_POR_NOME_ARQUIVO) e roteado
    para o importador certo - sem precisar escolher manualmente o card
    de cada fonte. Fontes já com cálculo (AT-02, Webssas, Visita
    Domiciliar) recalculam o painel na hora; as fontes novas (BI SIGA
    AT-08/11/39/40/48/49/57/61, DTIC REL_134/REL_130, SISAD) só ficam
    staged por enquanto (ver README 6.30).
    """
    arquivos = [a for a in request.files.getlist("arquivos") if a and a.filename]
    periodo = (request.form.get("periodo") or "").strip()

    if not arquivos:
        flash("Selecione um ou mais arquivos.", "erro")
        return redirect(url_for("importacao.formulario"))
    if not periodo or len(periodo) != 6 or not periodo.isdigit():
        flash("Informe o período de referência no formato AAAAMM (ex.: 202608).", "erro")
        return redirect(url_for("importacao.formulario"))

    db = get_db()
    linhas_resultado = []
    houve_erro = False

    for arquivo in arquivos:
        caminho_arquivo, nome_salvo = _salvar_upload(arquivo)
        fonte = _detectar_fonte_por_nome(arquivo.filename, caminho_arquivo)

        if fonte is None:
            linhas_resultado.append(
                f"❓ {arquivo.filename}: não consegui identificar a fonte pelo nome do "
                f"arquivo - se for uma das fontes conhecidas, importe pelo card específico abaixo."
            )
            continue
        if fonte == "IGNORAR":
            linhas_resultado.append(f"⏭ {arquivo.filename}: esta fonte está marcada para ignorar.")
            continue

        try:
            if fonte == "AT02":
                _, n = importar_at02(caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, "AT02")
                registrar_log(db, "AT02", periodo, resumo)
                linhas_resultado.append(
                    f"✅ {arquivo.filename} (SIGA AT-02): {n} linhas, "
                    f"{resumo['linhas_vinculadas']} vinculadas ao painel."
                )
            elif fonte == "WEBSSAS":
                _, n = importar_webssas(caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, "WEBSSAS")
                registrar_log(db, "WEBSSAS", periodo, resumo)
                linhas_resultado.append(
                    f"✅ {arquivo.filename} (Websaass): {n} linhas, "
                    f"{resumo['linhas_vinculadas']} vinculadas ao painel."
                )
            elif fonte == "VISITA_DOMICILIAR":
                _, n = importar_visita_domiciliar(caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, "VISITA_DOMICILIAR")
                registrar_log(db, "VISITA_DOMICILIAR", periodo, resumo)
                linhas_resultado.append(
                    f"✅ {arquivo.filename} (DTIC REL_142 - Visita Domiciliar): {n} linhas, "
                    f"{resumo['linhas_vinculadas']} vinculadas ao painel."
                )
            elif fonte in BI_SIGA_CONFIGS:
                _, n = importar_bi_siga(fonte, caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, fonte)
                vinculadas = resumo.get("linhas_vinculadas", 0) if isinstance(resumo, dict) else 0
                linhas_resultado.append(
                    f"✅ {arquivo.filename} ({BI_SIGA_ROTULOS[fonte]}): {n} linhas importadas, "
                    f"{vinculadas} vinculadas ao painel."
                )
            elif fonte == "DTIC_REL134":
                _, n = importar_dtic_rel134(caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, "DTIC_REL134")
                linhas_resultado.append(
                    f"✅ {arquivo.filename} (DTIC REL_134): {n} linhas importadas, "
                    f"{resumo.get('linhas_vinculadas', 0)} vinculadas ao painel."
                )
            elif fonte == "DTIC_REL130":
                _, n = importar_dtic_rel130(caminho_arquivo, periodo, db, nome_salvo)
                resumo = recalcular_periodo(db, periodo, "DTIC_REL130")
                linhas_resultado.append(
                    f"✅ {arquivo.filename} (DTIC REL_130): {n} linhas importadas, "
                    f"{resumo.get('linhas_vinculadas', 0)} vinculadas ao painel."
                )
            elif fonte == "SISAD":
                _, n = importar_sisad(caminho_arquivo, periodo, db, nome_salvo)
                linhas_resultado.append(
                    f"📥 {arquivo.filename} (SISAD): {n} linhas importadas (staging)."
                )
        except Exception as exc:  # noqa: BLE001
            houve_erro = True
            linhas_resultado.append(f"❌ {arquivo.filename}: erro ao importar - {exc}")

    flash("\n".join(linhas_resultado), "erro" if houve_erro else "sucesso")
    return redirect(url_for("importacao.formulario"))


@bp.route("/", methods=["GET"])
def formulario():
    # Acesso direto (sem ?partial=1) - inclusive o redirect de TODA importação/recálculo
    # concluído: abre dentro do Painel de Administração, para o menu de abas continuar
    # visível junto do resultado. A aba pede este mesmo endereço com ?partial=1.
    if request.args.get("partial") != "1":
        return redirect(url_for("cadastros.administracao", aba="importar"))
    db = get_db()
    importacoes = db.execute(
        """SELECT imp.*, f.nome AS fonte_nome
           FROM importacoes imp JOIN fontes_dados f ON f.id = imp.fonte_id
           ORDER BY imp.id DESC LIMIT 50"""
    ).fetchall()
    periodos_at02 = [
        r["ano_mes"] for r in db.execute(
            "SELECT DISTINCT ano_mes FROM staging_at02 ORDER BY ano_mes DESC"
        ).fetchall()
    ]
    periodos_webssas = [
        r["periodo"] for r in db.execute(
            "SELECT DISTINCT periodo FROM staging_webssas ORDER BY periodo DESC"
        ).fetchall()
    ]
    total_importacoes = db.execute("SELECT COUNT(*) AS c FROM importacoes").fetchone()["c"]
    total_linhas_apuradas = db.execute("SELECT COUNT(*) AS c FROM fato_apuracao WHERE tipo_registro='apurado'").fetchone()["c"]
    total_linhas_declaradas = db.execute("SELECT COUNT(*) AS c FROM fato_apuracao WHERE tipo_registro='declarado'").fetchone()["c"]
    periodos_apurados = [
        r["periodo"] for r in db.execute("SELECT DISTINCT periodo FROM fato_apuracao ORDER BY periodo DESC").fetchall()
    ]

    return render_template("contratos/importar.html",
        importacoes=importacoes,
        periodos_at02=periodos_at02,
        periodos_webssas=periodos_webssas,
        total_importacoes=total_importacoes,
        total_linhas_apuradas=total_linhas_apuradas,
        total_linhas_declaradas=total_linhas_declaradas,
        periodos_apurados=periodos_apurados,
        portarias=db.execute("SELECT id, numero FROM portarias ORDER BY id DESC").fetchall(),
        tas=db.execute("SELECT id, numero, periodo_inicio, periodo_fim FROM termos_aditivos ORDER BY id DESC").fetchall(),
        partial=request.args.get("partial") == "1",
    )


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir_importacao(id):
    """
    Exclui uma importação específica pelo ID:
    - Remove registros das tabelas de staging vinculadas
    - Remove apurações geradas em fato_apuracao
    - Remove o registro da tabela importacoes
    - Recalcula a competência se houver dados remanescentes
    """
    db = get_db()
    imp = db.execute(
        """SELECT imp.*, f.nome AS fonte_nome
           FROM importacoes imp
           JOIN fontes_dados f ON f.id = imp.fonte_id
           WHERE imp.id = ?""",
        (id,),
    ).fetchone()

    if not imp:
        flash(f"Importação #{id} não encontrada.", "erro")
        return redirect(url_for("importacao.formulario"))

    fonte_nome = imp["fonte_nome"]
    periodo = imp["periodo_referencia"]
    nome_arquivo = imp["nome_arquivo"]

    try:
        tabelas_staging = [
            "staging_at02",
            "staging_webssas",
            "staging_visita_domiciliar",
            "staging_bi_siga",
            "staging_dtic_rel134",
            "staging_dtic_rel130",
            "staging_sisad",
        ]
        for tab in tabelas_staging:
            db.execute(f"DELETE FROM {tab} WHERE importacao_id = ?", (id,))

        db.execute("DELETE FROM fato_apuracao WHERE importacao_id = ?", (id,))
        db.execute("DELETE FROM importacoes WHERE id = ?", (id,))
        db.commit()

        # Recalcula o período para manter a consistência da apuração
        if periodo and fonte_nome:
            try:
                recalcular_periodo(db, periodo, fonte_nome)
                db.commit()
            except Exception:
                pass

        flash(f"Importação #{id} ({fonte_nome} - {nome_arquivo}) excluída com sucesso!", "sucesso")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(f"Erro ao excluir importação #{id}: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))


@bp.route("/excluir_todas", methods=["POST"])
def excluir_todas_importacoes():
    """
    Exclusão em massa de todas as importações:
    Limpa todo o histórico de importações, staging e produções apuradas (fato_apuracao),
    permitindo reiniciar o ciclo de importações do zero sem afetar cadastros base
    (portarias, metas, indicadores, unidades, etc.).
    """
    db = get_db()
    try:
        tabelas_limpeza = [
            "staging_at02",
            "staging_webssas",
            "staging_visita_domiciliar",
            "staging_bi_siga",
            "staging_dtic_rel134",
            "staging_dtic_rel130",
            "staging_sisad",
            "fato_apuracao",
            "logs_calculo",
            "importacoes",
        ]
        for tab in tabelas_limpeza:
            db.execute(f"DELETE FROM {tab}")

        try:
            placeholders = ",".join("?" for _ in tabelas_limpeza)
            db.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", tabelas_limpeza)
        except Exception:
            pass

        db.commit()
        flash(
            "Todas as importações e dados apurados foram excluídos com sucesso. "
            "Os cadastros contratuais (Portarias, Metas, Estabelecimentos, CBOs e Procedimentos) foram preservados.",
            "sucesso",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        flash(f"Erro ao excluir todas as importações: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))



# ---------------------------------------------------------------------------
# CARGA EM LOTE PELA INTERFACE: indicadores + vínculos e metas do TA (arquivo base CSV/JSON)
# Formatos e regras: docstring de app/etl/carga_base.py. Modelos: /importar/modelo/<nome>.
# ---------------------------------------------------------------------------

def _resumo_erros(titulo, itens, limite=12):
    if not itens:
        return ""
    msg = f"\n{titulo} ({len(itens)}):\n- " + "\n- ".join(itens[:limite])
    if len(itens) > limite:
        msg += f"\n- ... e mais {len(itens) - limite}"
    return msg


@bp.route("/modelo/<nome>", methods=["GET"])
def baixar_modelo(nome):
    """Arquivos-modelo para preencher e importar (indicadores.csv / metas.csv)."""
    modelos = {"indicadores.csv": carga_base.MODELO_INDICADORES_CSV, "metas.csv": carga_base.MODELO_METAS_CSV}
    if nome not in modelos:
        flash("Modelo desconhecido.", "erro")
        return redirect(url_for("importacao.formulario"))
    return Response(
        "\ufeff" + modelos[nome], mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=modelo_{nome}"},
    )


@bp.route("/indicadores_base", methods=["POST"])
def importar_indicadores_base():
    """Carga de Indicadores + vínculos (procedimentos/CBOs/subgrupos) de um arquivo base CSV ou JSON."""
    db = get_db()
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Escolha o arquivo base de indicadores (CSV ou JSON).", "erro")
        return redirect(url_for("importacao.formulario"))

    portaria_id = request.form.get("portaria_id", type=int)
    numero_novo = (request.form.get("portaria_nova_numero") or "").strip()
    if numero_novo:
        ini, fim = request.form.get("portaria_nova_inicio"), request.form.get("portaria_nova_fim")
        if not ini or not fim:
            flash("Para criar uma Portaria nova informe também o início e o fim da vigência.", "erro")
            return redirect(url_for("importacao.formulario"))
        portaria_id = db.execute(
            "INSERT INTO portarias (numero, periodo_inicio, periodo_fim) VALUES (?, ?, ?)", (numero_novo, ini, fim)
        ).lastrowid
        db.commit()
    if not portaria_id or not db.execute("SELECT 1 FROM portarias WHERE id = ?", (portaria_id,)).fetchone():
        flash("Escolha a Portaria dos indicadores (ou informe o número de uma nova).", "erro")
        return redirect(url_for("importacao.formulario"))

    try:
        registros = carga_base.registros_de_indicadores(arquivo.filename, arquivo.read())
        r = carga_base.importar_indicadores(db, registros, portaria_id, substituir=bool(request.form.get("substituir")))
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível importar o arquivo de indicadores (nada foi gravado): {exc}", "erro")
        return redirect(url_for("importacao.formulario"))

    msg = (f"Indicadores importados: {r['criados']} criado(s), {r['atualizados']} atualizado(s); "
           f"{r['vinculos_proc']} vínculo(s) de procedimento e {r['vinculos_cbo']} de CBO novos; "
           f"{r['subgrupos_criados']} subgrupo(s) criado(s); {r['proc_criados']} procedimento(s) cadastrado(s) só com o código "
           "(complete os nomes em Procedimentos, ou importe a tabela SIGTAP).")
    msg += _resumo_erros("Avisos", r["avisos"]) + _resumo_erros("Erros", r["erros"])
    flash(msg, "erro" if r["erros"] and not (r["criados"] or r["atualizados"]) else "sucesso")
    return redirect(url_for("importacao.formulario"))


@bp.route("/metas_base", methods=["POST"])
def importar_metas_base():
    """Carga de Metas de um Termo Aditivo (CSV codigo_indicador;subgrupo;cod_cmes_ou_cnes;codigo_cbo;valor_meta) com UPSERT."""
    from .cadastros import _gravar_metas

    db = get_db()
    arquivo = request.files.get("arquivo")
    ta_id = request.form.get("ta_id", type=int)
    if not arquivo or not arquivo.filename or not ta_id or not db.execute("SELECT 1 FROM termos_aditivos WHERE id = ?", (ta_id,)).fetchone():
        flash("Escolha o Termo Aditivo e o arquivo CSV de metas.", "erro")
        return redirect(url_for("importacao.formulario"))
    try:
        itens, origem, erros = carga_base.preparar_metas(db, arquivo.read(), request.form.get("portaria_id", type=int))
        resultados = _gravar_metas(db, ta_id, itens, remover_vazios=False)
    except Exception as exc:  # noqa: BLE001
        flash(f"Não foi possível importar as metas (nada foi gravado): {exc}", "erro")
        return redirect(url_for("importacao.formulario"))
    for res in resultados:
        if res["status"] == "erro":
            erros.append(f"linha {origem[res['indice']]}: {res.get('mensagem')}")
    salvas = sum(1 for res in resultados if res["status"] == "salvo")
    ta = db.execute("SELECT numero FROM termos_aditivos WHERE id = ?", (ta_id,)).fetchone()
    msg = f"Metas do TA {ta['numero']}: {salvas} meta(s) gravada(s) (inseridas ou atualizadas), {len(erros)} linha(s) com problema."
    msg += _resumo_erros("Linhas ignoradas", erros)
    flash(msg, "erro" if erros and not salvas else "sucesso")
    return redirect(url_for("importacao.formulario"))


@bp.route("/recalcular", methods=["POST"])
def recalcular():
    """
    Reprocessa o staging de um período contra o cadastro ATUAL (estabelecimentos,
    CBO, procedimentos, vínculos). Aceita fontes individuais ou 'TODAS'.
    """
    periodo = request.form.get("periodo")
    fonte = request.form.get("fonte") or "TODAS"

    if not periodo:
        flash("Selecione o período para recalcular.", "erro")
        return redirect(url_for("importacao.formulario"))

    db = get_db()
    try:
        resumo = recalcular_periodo(db, periodo, fonte)
        if isinstance(resumo, dict) and "AT02" in resumo:
            msg = f"Recálculo geral de todas as fontes para {periodo} concluído com sucesso!"
        elif fonte == "AT02":
            registrar_log(db, "AT02", periodo, resumo)
            msg = _montar_mensagem_at02(f"Recálculo de AT-02 para {periodo}", resumo)
        elif fonte in ("WEBSSAS", "WEBSAAS"):
            registrar_log(db, "WEBSSAS", periodo, resumo)
            msg = (
                f"Recálculo de Websaass para {periodo}: {resumo['total_linhas']} linhas | "
                f"vinculadas: {resumo['linhas_vinculadas']} | sem estabelecimento: "
                f"{resumo['sem_estabelecimento']} | sem indicador: {resumo['sem_indicador']}"
            )
        else:
            msg = f"Recálculo da fonte {fonte} para {periodo} concluído com sucesso!"
        flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao recalcular: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))


@bp.route("/cadastrar_pendentes_e_recalcular", methods=["POST"])
def cadastrar_e_recalcular():
    """
    Botão do aviso do Painel: cadastra as unidades (CMES/CNES) e CBOs do AT-02 que não estão na base e recalcula
    TODAS as competências de AT-02 já importadas, num clique. Ver etl/pendencias.py.
    """
    db = get_db()
    pend = pendencias.pendencias_at02(db)
    estabs, cbos = pendencias.cadastrar_pendentes(db, pend)
    recalculados, erros = [], []
    for periodo in pend["periodos"]:
        try:
            resumo = recalcular_periodo(db, periodo, "AT02")
            registrar_log(db, "AT02", periodo, resumo)
            recalculados.append(f"{periodo} ({resumo['linhas_vinculadas']} de {resumo['total_linhas']} linhas vinculadas)")
        except Exception as exc:  # noqa: BLE001
            erros.append(f"{periodo}: {exc}")
    msg = (f"{estabs} unidade(s) e {cbos} CBO(s) cadastrados; competências recalculadas: "
           + (", ".join(recalculados) or "nenhuma") + ".")
    if pend["sem_servico"]:
        msg += (f"\nAtenção: {pend['sem_servico']} estabelecimento(s) com produção estão SEM tipo de serviço - indicadores "
                "que exigem Serviço só contam quando o cadastro for completado (Administração > Estabelecimentos).")
    flash(msg, "erro" if erros else "sucesso")
    for e in erros:
        flash(f"Erro ao recalcular {e}", "erro")
    return redirect(url_for("painel.index"))


@bp.route("/auto_cadastrar_pendentes", methods=["POST"])
def auto_cadastrar():
    """
    Cadastra automaticamente os estabelecimentos (por CMES) e CBOs (por
    código oficial) que apareceram no AT-02 do período mas ainda não
    estavam cadastrados - usa o mesmo diagnóstico que já é calculado ao
    importar/recalcular. Não recalcula sozinho: depois de cadastrar, rode
    "Recalcular" para os novos cadastros passarem a valer no painel.
    """
    periodo = request.form.get("periodo")
    if not periodo:
        flash("Informe o período (AAAAMM) para cadastrar os pendentes.", "erro")
        return redirect(url_for("importacao.formulario"))

    db = get_db()
    try:
        estab_criados, cbo_criados, cbo_sem_codigo = auto_cadastrar_pendentes(db, periodo)
        msg = (
            f"Cadastro automático para {periodo}: {estab_criados} estabelecimento(s) "
            f"e {cbo_criados} CBO(s) criados a partir do que apareceu no AT-02. "
            "Os estabelecimentos entraram sem tipo de serviço/complexidade - complete "
            "em Cadastros > Estabelecimentos (dá para editar vários de uma vez com a "
            "edição em massa). Agora rode \"Recalcular\" para os novos cadastros "
            "valerem no painel."
        )
        if cbo_sem_codigo:
            msg += (
                f"\n{len(cbo_sem_codigo)} CBO(s) não puderam ser criados automaticamente "
                "por não terem código no arquivo (versões antigas do AT-02 sem a coluna "
                "Código_CBO_no_SUS): " + ", ".join(cbo_sem_codigo[:10])
            )
        flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao cadastrar pendentes: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))


@bp.route("/logs", methods=["GET"])
def logs():
    """Histórico de diagnósticos completos (sem limite de top-5) de cada
    importação/recálculo, para investigar por que uma linha não apareceu
    no painel sem depender da mensagem de tela (que some depois)."""
    if request.args.get("partial") != "1":
        return redirect(url_for("cadastros.administracao", aba="logs", periodo=request.args.get("periodo") or None))
    db = get_db()
    periodo_filtro = request.args.get("periodo")
    query = "SELECT * FROM logs_calculo"
    params = []
    if periodo_filtro:
        query += " WHERE periodo = ?"
        params.append(periodo_filtro)
    query += " ORDER BY id DESC LIMIT 30"
    registros = db.execute(query, params).fetchall()

    import json
    logs_processados = []
    for r in registros:
        item = dict(r)
        item["detalhes"] = json.loads(r["detalhes_json"]) if r["detalhes_json"] else {}
        logs_processados.append(item)

    problemas_metas = diagnostico_metas.diagnosticar(db)
    return render_template("contratos/logs.html",
        logs=logs_processados,
        periodo_filtro=periodo_filtro,
        problemas_metas=problemas_metas,
        resumo_problemas_metas=diagnostico_metas.resumir(problemas_metas),
        partial=request.args.get("partial") == "1",
    )


@bp.route("/at02", methods=["POST"])
def upload_at02():
    arquivo = request.files.get("arquivo")
    periodo = request.form.get("periodo")  # formato AAAAMM

    if not arquivo or not periodo:
        flash("Selecione o arquivo CSV e informe o período (AAAAMM).", "erro")
        return redirect(url_for("importacao.formulario"))

    caminho, nome_arquivo = _salvar_upload(arquivo)
    db = get_db()

    try:
        importacao_id, linhas = importar_at02(caminho, periodo, db, nome_arquivo)
        # recalcular_periodo (não calcular_at02 direto) para garantir que
        # fato_apuracao também não acumule de uma importação anterior desse
        # mesmo período - ver comentário em importar_at02.
        resumo = recalcular_periodo(db, periodo, "AT02")
        registrar_log(db, "AT02", periodo, resumo)
        msg = _montar_mensagem_at02(f"AT-02 importado ({linhas} linhas)", resumo)
        flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001 - mostra o erro real ao usuário
        flash(f"Erro ao importar AT-02: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))


@bp.route("/webssas", methods=["POST"])
def upload_webssas():
    arquivo = request.files.get("arquivo")
    periodo = request.form.get("periodo")
    mes_filtro = request.form.get("mes_filtro") or None  # ex: "JUL 2026"

    if not arquivo or not periodo:
        flash("Selecione o arquivo XML e informe o período (AAAAMM).", "erro")
        return redirect(url_for("importacao.formulario"))

    caminho, nome_arquivo = _salvar_upload(arquivo)
    db = get_db()

    try:
        importacao_id, linhas = importar_webssas(
            caminho, periodo, db, nome_arquivo, mes_filtro=mes_filtro
        )
        resumo = recalcular_periodo(db, periodo, "WEBSSAS")
        registrar_log(db, "WEBSSAS", periodo, resumo)
        msg = (
            f"Webssas importado: {linhas} linhas. Vinculadas a indicadores: "
            f"{resumo['linhas_vinculadas']} | sem estabelecimento: "
            f"{resumo['sem_estabelecimento']} | sem indicador correspondente: "
            f"{resumo['sem_indicador']}"
        )
        if resumo["unidades_nao_encontradas"]:
            msg += "\nUnidades não cadastradas (top 5): " + ", ".join(
                f"{u} ({n}x)" for u, n in _top(resumo["unidades_nao_encontradas"])
            )
        if resumo["producoes_nao_encontradas"]:
            msg += "\nProduções sem indicador correspondente (top 5): " + ", ".join(
                f"{p} ({n}x)" for p, n in _top(resumo["producoes_nao_encontradas"])
            )
        flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao importar Webssas: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))


@bp.route("/visita_domiciliar", methods=["POST"])
def upload_visita_domiciliar():
    arquivo = request.files.get("arquivo")
    periodo = request.form.get("periodo")
    supervisao_filtro = request.form.get("supervisao_filtro") or None

    if not arquivo or not periodo:
        flash("Selecione o arquivo CSV e informe a competência (AAAAMM).", "erro")
        return redirect(url_for("importacao.formulario"))

    caminho, nome_arquivo = _salvar_upload(arquivo)
    db = get_db()

    try:
        importacao_id, linhas = importar_visita_domiciliar(
            caminho, periodo, db, nome_arquivo, supervisao_filtro=supervisao_filtro
        )
        resumo = recalcular_periodo(db, periodo, "VISITA_DOMICILIAR")
        registrar_log(db, "VISITA_DOMICILIAR", periodo, resumo)
        if resumo.get("erro"):
            flash(f"Arquivo importado ({linhas} linhas), mas: {resumo['erro']}", "erro")
        else:
            msg = (
                f"Visita Domiciliar Periódica importada: {linhas} linhas "
                f"(já filtradas pela supervisão informada). Vinculadas ao indicador P6: "
                f"{resumo['linhas_vinculadas']} | CNES não cadastrado: "
                f"{resumo['sem_estabelecimento']} | CNES ambíguo (mais de um "
                f"estabelecimento cadastrado - não atribuído automaticamente): "
                f"{resumo['estabelecimento_ambiguo']}"
            )
            if resumo.get("cnes_ambiguos"):
                msg += "\nCNES ambíguos (top 5): " + ", ".join(
                    f"{u} ({n}x)" for u, n in _top(resumo["cnes_ambiguos"])
                )
            flash(msg, "sucesso")
    except Exception as exc:  # noqa: BLE001
        flash(f"Erro ao importar Visita Domiciliar Periódica: {exc}", "erro")

    return redirect(url_for("importacao.formulario"))
