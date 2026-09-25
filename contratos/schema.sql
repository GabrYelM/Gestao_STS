-- ============================================================================
-- SCHEMA STSPE - Painel de Indicadores (SQLite)
-- ============================================================================
-- Organizado em 6 blocos:
--   1. Catálogo de fontes de dados
--   2. Cadastros (dimensões): estabelecimentos, profissionais, CBO, procedimentos
--   3. Vigências: termos aditivos (metas) e portarias (indicadores)
--   4. Vínculos indicador <-> CBO / procedimento
--   5. Staging (dados brutos por fonte) e fato_apuracao (consolidado)
--   6. View de resumo para o painel
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. CATÁLOGO DE FONTES DE DADOS
-- ----------------------------------------------------------------------------
-- Cada fonte importada (AT-02, Webssas, e futuras fontes) é cadastrada aqui.
-- granularidade indica se a fonte já vem agregada por indicador ou se precisa
-- ser resolvida via procedimento/CBO.

CREATE TABLE fontes_dados (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT NOT NULL UNIQUE,          -- ex: 'AT02', 'WEBSSAS', 'BPA'
    descricao           TEXT,
    formato_arquivo     TEXT,                          -- 'csv', 'xml', 'xlsx'
    granularidade       TEXT NOT NULL                  -- 'procedimento' | 'indicador'
        CHECK (granularidade IN ('procedimento', 'indicador')),
    ativo               INTEGER NOT NULL DEFAULT 1
);

-- Log de cada arquivo importado, para rastreabilidade e reprocessamento
CREATE TABLE importacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id            INTEGER NOT NULL REFERENCES fontes_dados(id),
    nome_arquivo        TEXT NOT NULL,
    periodo_referencia  TEXT NOT NULL,                 -- formato 'AAAAMM'
    data_importacao     TEXT NOT NULL DEFAULT (datetime('now')),
    linhas_importadas   INTEGER,
    status              TEXT NOT NULL DEFAULT 'concluido'
        CHECK (status IN ('concluido', 'erro', 'processando'))
);

CREATE INDEX idx_importacoes_periodo ON importacoes(periodo_referencia);

-- ----------------------------------------------------------------------------
-- 2. CADASTROS (DIMENSÕES)
-- ----------------------------------------------------------------------------

CREATE TABLE estabelecimentos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_cnes            TEXT,
    cod_cmes            TEXT UNIQUE,
    nome                TEXT NOT NULL,
    tipo_servico        TEXT,                          -- coluna legada, não usada mais - ver estabelecimento_tipo_servico
    complexidade        TEXT,                          -- ex: 'ATENCAO_BASICA', 'MEDIA', 'ALTA'
    regional             TEXT,                          -- coluna legada, não usada mais no cadastro
    categoria_contrato  TEXT,                          -- ex: 'PERTENCE', 'CER', 'NAO_PERTENCE' - texto
        -- livre historicamente, mas a partir da v12 a tela só oferece os
        -- valores cadastrados em categorias_estabelecimento (evita erro de
        -- digitação, já que agora isso afeta o cálculo - ver
        -- categoria_estabelecimento/categoria_estabelecimento_neg em
        -- indicador_procedimento, abaixo, e _candidatos_indicador_subgrupo
        -- em app/etl/calculo.py)
    ativo               INTEGER NOT NULL DEFAULT 1,
    exige_cmes          INTEGER NOT NULL DEFAULT 0     -- v15: 1 = exceção manual da consolidação por
        -- CNES: este estabelecimento é sempre tratado individualmente (por CMES), mesmo
        -- com a consolidação primária em 'CNES' (ver app/etl/consolidacao.py)
);

CREATE INDEX idx_estabelecimentos_cmes ON estabelecimentos(cod_cmes);
CREATE INDEX idx_estabelecimentos_nome ON estabelecimentos(nome);
CREATE INDEX idx_estabelecimentos_cnes ON estabelecimentos(cod_cnes);

-- v15: chave/valor de configuração do sistema. Hoje só 'consolidacao_primaria'
-- ('CMES' = padrão | 'CNES'), editável em Administração > Portaria/TA e no Painel.
CREATE TABLE configuracoes (
    chave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL,
    atualizado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO configuracoes (chave, valor) VALUES ('consolidacao_primaria', 'CMES');

-- Lista de categorias de contrato disponíveis para estabelecimentos.categoria_contrato
-- (e para os campos Categoria +/- do vínculo de procedimento de um indicador).
-- Gerenciável pela própria tela de Estabelecimentos - PERTENCE/CER/NAO_PERTENCE
-- são só os valores iniciais, não uma lista fechada.
CREATE TABLE categorias_estabelecimento (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO categorias_estabelecimento (nome) VALUES ('PERTENCE'), ('CER'), ('NAO_PERTENCE'), ('INTEGRADA');

-- Um estabelecimento pode ter mais de um tipo de serviço (ex.: 'UBS' e
-- 'AMA' ao mesmo tempo) - por isso é uma tabela à parte em vez de uma
-- coluna única. ON DELETE CASCADE: excluir o estabelecimento remove os
-- tipos associados automaticamente.
CREATE TABLE estabelecimento_tipo_servico (
    estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    tipo_servico        TEXT NOT NULL,
    PRIMARY KEY (estabelecimento_id, tipo_servico)
);

CREATE TABLE cbo (
    codigo              TEXT PRIMARY KEY,
    nome_categoria      TEXT NOT NULL
);
CREATE INDEX idx_cbo_nome_categoria ON cbo(nome_categoria);

CREATE TABLE profissionais (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT NOT NULL,
    cns                 TEXT,                          -- Cartão Nacional de Saúde
    cbo_codigo          TEXT REFERENCES cbo(codigo),
    estabelecimento_id  INTEGER REFERENCES estabelecimentos(id),
    rt                  INTEGER NOT NULL DEFAULT 0,     -- 1 = Responsável Técnico
    tipo_equipe         TEXT,                           -- ex: 'eSB', 'eSF', 'NASF-AB', 'CEO'
    pmmb                INTEGER NOT NULL DEFAULT 0,     -- 1 = vinculado ao Programa Mais Médicos p/ o Brasil
    ativo               INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_profissionais_estabelecimento ON profissionais(estabelecimento_id);
CREATE INDEX idx_profissionais_cbo ON profissionais(cbo_codigo);
CREATE INDEX idx_profissionais_cns ON profissionais(cns);
CREATE INDEX idx_profissionais_nome ON profissionais(nome);

CREATE TABLE procedimentos (
    codigo              TEXT PRIMARY KEY,
    nome                TEXT NOT NULL
);
CREATE INDEX idx_procedimentos_nome ON procedimentos(nome);

-- ----------------------------------------------------------------------------
-- 3. VIGÊNCIAS: TERMOS ADITIVOS (metas) E PORTARIAS (indicadores)
-- ----------------------------------------------------------------------------
-- Auto-referência (*_origem_id) permite "clonar" o conteúdo do TA/portaria
-- anterior ao criar um novo, mantendo histórico.

CREATE TABLE termos_aditivos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero              TEXT NOT NULL,
    periodo_inicio      TEXT NOT NULL,                 -- 'AAAA-MM-DD'
    periodo_fim         TEXT NOT NULL,
    ta_origem_id        INTEGER REFERENCES termos_aditivos(id),
    observacoes         TEXT,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE portarias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero              TEXT NOT NULL,
    periodo_inicio      TEXT NOT NULL,
    periodo_fim         TEXT NOT NULL,
    portaria_origem_id  INTEGER REFERENCES portarias(id),
    observacoes         TEXT,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE indicadores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    portaria_id         INTEGER NOT NULL REFERENCES portarias(id),
    codigo              TEXT NOT NULL,                 -- ex: 'P1'
    nome                TEXT NOT NULL,
    tipo                TEXT NOT NULL
        CHECK (tipo IN ('QUALIDADE', 'PRODUCAO', 'MONITORAMENTO')),
    complexidade        TEXT,                          -- casa com estabelecimentos.complexidade
    servico             TEXT,                          -- casa com estabelecimentos.tipo_servico
    fonte_dados         TEXT,                          -- descrição da fonte (exibição). Desde a v17 quem
        -- manda é fonte_id (abaixo, vínculo com fontes_dados); textos antigos livres ficam aqui até
        -- o usuário escolher a fonte na tela de Indicadores.
    usa_profissionais   INTEGER NOT NULL DEFAULT 0,    -- OBSOLETO (v10) - substituído pelos
        -- 3 campos abaixo (v11); mantido só para não quebrar bancos antigos, não usado em
        -- nenhuma tela.
    segmenta_metas_rt          INTEGER NOT NULL DEFAULT 0,  -- 1 = a grade de metas deste
        -- indicador gera uma linha para RT e outra para não-RT por estabelecimento/CBO
        -- (ver profissionais.rt)
    segmenta_metas_tipo_equipe INTEGER NOT NULL DEFAULT 0,  -- 1 = a grade de metas gera uma
        -- linha por tipo de equipe já cadastrado em profissionais.tipo_equipe
    segmenta_metas_pmmb        INTEGER NOT NULL DEFAULT 0,  -- 1 = a grade de metas gera uma
        -- linha para PMMB e outra para não-PMMB (ver profissionais.pmmb)
    fonte_id            INTEGER REFERENCES fontes_dados(id),  -- v17: FONTE DE DADOS oficial do indicador
        -- (select alimentado por fontes_dados). NULL = aceita qualquer fonte (comportamento antigo). O cálculo
        -- só considera o indicador na fonte escolhida (calculo.py); fonte_dados (texto) passa a guardar a
        -- descrição da fonte, só para exibição.
    consolida_cnes      INTEGER NOT NULL DEFAULT 0,  -- v17: 1 = este indicador é consolidado por CNES no painel
        -- e na grade de metas (ver app/etl/consolidacao.py); 0 = por CMES (padrão)
    UNIQUE (portaria_id, codigo)
);

CREATE INDEX idx_indicadores_portaria ON indicadores(portaria_id);

-- Metas: um indicador, uma unidade, um CBO (quando aplicável), sob um TA
-- específico. cbo_codigo é NULL quando o indicador não precisa de meta
-- quebrada por categoria profissional (meta única para o indicador todo);
-- quando o indicador tem metas diferentes por CBO (ex.: consulta médica
-- de ginecologista x de clínico geral), cadastre uma linha de meta por CBO.
-- O percentual de atingimento NÃO é armazenado aqui - é sempre calculado no
-- painel (apurado / meta), para nunca ficar desatualizado em relação ao que
-- foi realmente apurado.
CREATE TABLE metas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ta_id               INTEGER NOT NULL REFERENCES termos_aditivos(id),
    estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id),
    cbo_codigo          TEXT REFERENCES cbo(codigo),
    rt                  TEXT CHECK (rt IN ('SIM', 'NAO')),          -- NULL = não segmenta por RT
    tipo_equipe         TEXT,                                        -- NULL = não segmenta por equipe
    pmmb                TEXT CHECK (pmmb IN ('SIM', 'NAO')),         -- NULL = não segmenta por PMMB
    valor_meta          REAL,
    subgrupo_id         INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE
        -- v14: NULL = meta do indicador como um todo (ou "Geral", sem subgrupo); preenchido
        -- = meta só daquele subgrupo (indicadores com subgrupos, ex.: P42/P44)
);
-- UNIQUE via índice (não como constraint da tabela) porque precisa de
-- COALESCE para tratar NULL como "não segmentado" - mesmo padrão já usado
-- em indicador_cbo/indicador_procedimento com subgrupo_id.
CREATE UNIQUE INDEX idx_metas_unico ON metas (
    ta_id, estabelecimento_id, indicador_id,
    COALESCE(subgrupo_id, -1),
    COALESCE(cbo_codigo, '__GERAL__'),
    COALESCE(rt, '__QUALQUER__'),
    COALESCE(tipo_equipe, '__QUALQUER__'),
    COALESCE(pmmb, '__QUALQUER__')
);

CREATE INDEX idx_metas_ta ON metas(ta_id);
CREATE INDEX idx_metas_estabelecimento ON metas(estabelecimento_id);
CREATE INDEX idx_metas_indicador ON metas(indicador_id);
CREATE INDEX idx_metas_cbo ON metas(cbo_codigo);
CREATE INDEX idx_metas_subgrupo ON metas(subgrupo_id);

-- ----------------------------------------------------------------------------
-- 4. VÍNCULOS INDICADOR <-> CBO / PROCEDIMENTO
-- ----------------------------------------------------------------------------
-- Equivalente relacional da antiga aba PROCS do STSPE_DATA.xlsx.
-- tipo_vinculo distingue inclusão normal de regra negativa (categoria/CMES
-- que, se bater, EXCLUI o registro do cálculo) - lógica herdada dos scripts.

-- Sub-agrupamento dentro de um indicador. Alguns indicadores têm grupos de
-- procedimentos específicos para determinados CBOs (ex.: P42 - CEO, um
-- subgrupo por especialidade odontológica, cada um com seu próprio CBO) ou
-- simplesmente grupos organizados por subitem (ex.: P44 - SADT, um
-- subgrupo por tipo de exame). Um vínculo (de CBO ou de procedimento) com
-- subgrupo_id preenchido só vale DENTRO daquele subgrupo; um vínculo com
-- subgrupo_id NULL continua sendo a regra geral do indicador (mesmo
-- comportamento de sempre, 100% retrocompatível com indicadores que nunca
-- usam subgrupo).
CREATE TABLE indicador_subgrupo (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id   INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    nome           TEXT NOT NULL,             -- ex: "Prótese", "Endodontia", "Ultrassonografia"
    ordem          INTEGER NOT NULL DEFAULT 0,
    criado_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_indicador_subgrupo_indicador ON indicador_subgrupo(indicador_id);

CREATE TABLE indicador_cbo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    cbo_codigo          TEXT REFERENCES cbo(codigo),    -- NULL + curinga = 'any' (qualquer CBO)
    curinga             INTEGER NOT NULL DEFAULT 0,     -- 1 = aceita qualquer CBO (equivalente a 'any')
    subgrupo_id         INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE
        -- NULL = vínculo geral do indicador (comportamento padrão, de
        -- sempre); preenchido = vínculo restrito a este subgrupo - se o
        -- subgrupo tiver algum vínculo de CBO próprio, ele SUBSTITUI a
        -- regra geral do indicador só para os procedimentos daquele
        -- subgrupo (ver app/etl/calculo.py, _cbo_permitido_subgrupo).
);
-- Índice único com COALESCE: o SQLite trata NULL como sempre diferente de
-- NULL em UNIQUE normal, então um UNIQUE(indicador_id, cbo_codigo) comum
-- NÃO impediria duas linhas "curinga" (cbo_codigo NULL) para o mesmo
-- indicador/subgrupo - o COALESCE normaliza o NULL para um valor fixo só
-- para efeito da checagem de unicidade.
CREATE UNIQUE INDEX idx_indicador_cbo_unico
    ON indicador_cbo (indicador_id, COALESCE(subgrupo_id, -1), COALESCE(cbo_codigo, '__CURINGA__'));

-- Exceções no nível do INDICADOR (não em cada vínculo de procedimento) para
-- quando ele aceita "qualquer CBO" (curinga). Sem isso, "curinga" só sabia
-- dizer "sim para todos"; com isso dá para dizer "sim para todos, EXCETO
-- estes CBOs específicos" - uma única lista vale para o indicador inteiro,
-- em vez de precisar repetir a exclusão em cada procedimento vinculado.
CREATE TABLE indicador_cbo_excecao (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id   INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    cbo_codigo     TEXT NOT NULL REFERENCES cbo(codigo),
    criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (indicador_id, cbo_codigo)
);
CREATE INDEX idx_indicador_cbo_excecao_indicador ON indicador_cbo_excecao(indicador_id);

-- Mesma ideia, mas para excluir estabelecimentos específicos da apuração
-- de um indicador (independente da regra de "Serviço" já existente, que é
-- mais grosseira - por tipo de unidade, não por unidade individual).
CREATE TABLE indicador_estabelecimento_excecao (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (indicador_id, estabelecimento_id)
);
CREATE INDEX idx_indicador_estab_excecao_indicador ON indicador_estabelecimento_excecao(indicador_id);

-- (v10 tinha aqui uma tabela indicador_profissional para vincular
-- profissionais NOMINALMENTE a um indicador. Removida na v11: em bancos
-- criados a partir deste schema.sql ela nunca chega a existir. Em bancos
-- antigos que já tinham a tabela, o auto-migration só deixa de usá-la -
-- não apaga, para não perder dado sem avisar; ver app/migrations_auto.py.
-- A vinculação nominal foi substituída pelos critérios estruturados em
-- indicadores.segmenta_metas_* + metas.rt/tipo_equipe/pmmb, abaixo.)

-- CNES alternativo por estabelecimento, por indicador - para fontes que
-- resolvem o estabelecimento por CNES em vez de CMES (hoje só Visita
-- Domiciliar/P6 - ver _resolver_estabelecimento_por_cnes em
-- app/etl/calculo.py). Quando cadastrado, o CNES informado aqui tem
-- prioridade sobre estabelecimentos.cod_cnes para ESTE indicador - inclusive
-- resolvendo casos em que o CNES bate com mais de uma unidade cadastrada
-- (hoje tratados como ambíguos e descartados).
CREATE TABLE indicador_estabelecimento_cnes_alternativo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id        INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id),
    cnes_alternativo    TEXT NOT NULL,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (indicador_id, estabelecimento_id)
);
CREATE INDEX idx_ind_estab_cnes_alt_indicador ON indicador_estabelecimento_cnes_alternativo(indicador_id);
CREATE INDEX idx_ind_estab_cnes_alt_cnes ON indicador_estabelecimento_cnes_alternativo(cnes_alternativo);

CREATE TABLE indicador_procedimento (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    indicador_id            INTEGER NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
    procedimento_codigo     TEXT NOT NULL REFERENCES procedimentos(codigo),
    tipo_vinculo             TEXT NOT NULL DEFAULT 'inclusao'
        CHECK (tipo_vinculo IN ('inclusao', 'exclusao')),
    categoria_estabelecimento      TEXT,                -- filtro positivo por categoria: só
        -- conta se estabelecimentos.categoria_contrato for EXATAMENTE este valor (ex.: 'CER')
    categoria_estabelecimento_neg  TEXT,                -- filtro negativo: conta para
        -- qualquer categoria, EXCETO esta - ambos aplicados em
        -- _candidatos_indicador_subgrupo (app/etl/calculo.py)
    estabelecimento_id             INTEGER REFERENCES estabelecimentos(id),      -- filtro positivo por CMES específico
    estabelecimento_id_neg         INTEGER REFERENCES estabelecimentos(id),      -- filtro negativo por CMES específico
    subgrupo_id                    INTEGER REFERENCES indicador_subgrupo(id) ON DELETE CASCADE
        -- NULL = vínculo geral do indicador; preenchido = este procedimento
        -- só conta dentro do subgrupo (ver indicador_subgrupo acima).
);
-- Mesmo motivo do índice de indicador_cbo acima: sem o COALESCE, o
-- UNIQUE comum deixava duplicar à vontade toda vez que estabelecimento_id
-- ou subgrupo_id ficavam em branco (o caso mais comum) - exatamente o que
-- causava vínculos duplicados ao adicionar o mesmo procedimento mais de
-- uma vez.
CREATE UNIQUE INDEX idx_indicador_procedimento_unico
    ON indicador_procedimento (indicador_id, procedimento_codigo, COALESCE(estabelecimento_id, -1), COALESCE(subgrupo_id, -1));

CREATE INDEX idx_ind_cbo_indicador ON indicador_cbo(indicador_id);
CREATE INDEX idx_ind_cbo_subgrupo ON indicador_cbo(subgrupo_id);
CREATE INDEX idx_ind_proc_indicador ON indicador_procedimento(indicador_id);
CREATE INDEX idx_ind_proc_codigo ON indicador_procedimento(procedimento_codigo);
CREATE INDEX idx_ind_proc_subgrupo ON indicador_procedimento(subgrupo_id);

-- Regra especial herdada do script (aba 'NASF FILTER'): alguns procedimentos,
-- quando lançados por certas unidades, devem ser contabilizados no pool de
-- unidades NASF em vez da própria unidade.
CREATE TABLE regras_pool_unidades (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    estabelecimento_id      INTEGER NOT NULL REFERENCES estabelecimentos(id),
    indicador_id            INTEGER NOT NULL REFERENCES indicadores(id),
    pool_nome               TEXT NOT NULL             -- identifica o conjunto de unidades do pool
);

CREATE TABLE pool_unidades_membros (
    pool_nome               TEXT NOT NULL,
    estabelecimento_id      INTEGER NOT NULL REFERENCES estabelecimentos(id),
    PRIMARY KEY (pool_nome, estabelecimento_id)
);

-- ----------------------------------------------------------------------------
-- 5. STAGING (dados brutos por fonte) E FATO_APURACAO (consolidado)
-- ----------------------------------------------------------------------------
-- Staging preserva o formato original de cada fonte para auditoria e
-- reprocessamento. fato_apuracao é o formato comum que alimenta o cálculo,
-- alimentado por ETL específico de cada fonte (staging_X -> fato_apuracao).

-- Staging AT-02 (granularidade: procedimento/profissional)
CREATE TABLE staging_at02 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id           INTEGER NOT NULL REFERENCES importacoes(id),
    ano_mes                 TEXT,
    cod_cnes                TEXT,
    nome_estabelecimento    TEXT,
    cod_cmes                TEXT,
    tipo_estabelecimento    TEXT,
    cod_cbo_sus             TEXT,
    nome_cbo1               TEXT,
    nome_especialidade2     TEXT,
    cod_procedimento        TEXT,
    nome_procedimento       TEXT,
    nome_profissional       TEXT,
    quantidade               INTEGER,
    quantidade_pacientes     INTEGER
);

-- Guarda o diagnóstico COMPLETO de cada importação/recálculo (não só o
-- top-5 que aparece na mensagem de tela), para consulta posterior em
-- /importar/logs. Sem isso, a única forma de investigar era reler a
-- mensagem de flash (que some depois de recarregar a página) ou vasculhar
-- o log de requisições HTTP do Flask, que não mostra o diagnóstico de negócio.
CREATE TABLE logs_calculo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte                TEXT NOT NULL,          -- 'AT02' ou 'WEBSSAS'
    periodo              TEXT NOT NULL,
    criado_em            TEXT NOT NULL DEFAULT (datetime('now')),
    total_linhas         INTEGER,
    vinculadas           INTEGER,
    sem_estabelecimento  INTEGER,
    sem_indicador        INTEGER,
    detalhes_json        TEXT                     -- listas completas (não só top-5) em JSON
);

CREATE INDEX idx_logs_calculo_periodo ON logs_calculo(periodo);

CREATE INDEX idx_staging_at02_importacao ON staging_at02(importacao_id);

-- Staging Webssas (granularidade: indicador, já agregado por unidade)
CREATE TABLE staging_webssas (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id           INTEGER NOT NULL REFERENCES importacoes(id),
    cod_contrato            TEXT,
    contrato                TEXT,
    contratada               TEXT,
    unidade                  TEXT,
    periodo                  TEXT,
    servico                  TEXT,
    cod_producao             TEXT,
    producao                 TEXT,                     -- nome do indicador declarado
    qtde_realizada           INTEGER,
    qtde_prevista            INTEGER
);

CREATE INDEX idx_staging_webssas_importacao ON staging_webssas(importacao_id);

-- Template para novas fontes: copiar e adaptar as colunas ao layout de origem
-- CREATE TABLE staging_<nova_fonte> (
--     id             INTEGER PRIMARY KEY AUTOINCREMENT,
--     importacao_id  INTEGER NOT NULL REFERENCES importacoes(id),
--     ...colunas no formato original da fonte...
-- );

-- Staging "Visita Domiciliar Periódica" (eSUS/Centralizador municipal) -
-- fonte de dados oficial do indicador P6. O arquivo original é CIDADE
-- INTEIRA (todas as coordenadorias/supervisões), por isso é filtrado por
-- "supervisao" no momento da importação (ver
-- app/etl/visita_domiciliar.py). Granularidade: já agregado por
-- profissional/mês - mais parecido com Webssas do que com o AT-02, mas já
-- traz o CBO do profissional (o Webssas não traz).
CREATE TABLE staging_visita_domiciliar (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id           INTEGER NOT NULL REFERENCES importacoes(id),
    tipo_visita             TEXT,                 -- 'PERIODICA' no arquivo atual
    supervisao              TEXT,                 -- valor usado para filtrar por território na importação
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
);

CREATE INDEX idx_staging_visita_domiciliar_importacao ON staging_visita_domiciliar(importacao_id);

-- Genérica para as 8 fontes "BI SIGA" sem importador próprio ainda (AT-08,
-- AT-11, AT-39, AT-40, AT-48, AT-49, AT-57, AT-61) - ver app/etl/bi_siga.py
-- para o de-para de colunas de cada uma. Um superconjunto de campos: cada
-- fonte só preenche os que tem, o resto fica NULL. Só staging por
-- enquanto - ainda não alimenta fato_apuracao (ver docstring do módulo).
CREATE TABLE staging_bi_siga (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id            INTEGER NOT NULL REFERENCES importacoes(id),
    fonte_at                 TEXT NOT NULL,     -- 'AT08', 'AT11', 'AT39', 'AT40', 'AT48', 'AT49', 'AT57', 'AT61'
    ano_mes                  TEXT,              -- 'AAAAMM', quando a fonte traz pronto
    ano                      TEXT,
    mes                      TEXT,
    cod_cnes                 TEXT,              -- só AT-48/AT-57/AT-61 trazem isso (ver módulo)
    nome_estabelecimento     TEXT,
    nivel2                   TEXT,              -- hierarquia regional do SIGA (CRS)
    nivel3                   TEXT,              -- hierarquia regional do SIGA (STS)
    nivel4                   TEXT,              -- hierarquia regional do SIGA (OSS/prestador)
    cbo_nome                 TEXT,
    especialidade            TEXT,
    procedimento_codigo      TEXT,
    procedimento_nome        TEXT,
    grupo                    TEXT,              -- ex: 'PROCEDIMENTOS COLETIVOS' (AT-57)
    quantidade               REAL,
    quantidade_pacientes     REAL,
    quantidade_vaga_ofertada REAL
);
CREATE INDEX idx_staging_bi_siga_importacao ON staging_bi_siga(importacao_id);
CREATE INDEX idx_staging_bi_siga_fonte_periodo ON staging_bi_siga(fonte_at, ano_mes);

-- DTIC (REL_134) - Atividade Coletiva por Profissional (evento por linha -
-- "quantidade" é contar linhas). Só staging por enquanto - ver app/etl/outras_fontes.py.
CREATE TABLE staging_dtic_rel134 (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id        INTEGER NOT NULL REFERENCES importacoes(id),
    periodo_referencia   TEXT,               -- 'AAAAMM' informado no upload - usado pra
        -- deduplicar reimportação (NÃO usar ano/mes da própria linha pra isso: o valor
        -- pode não bater exatamente com o que foi digitado no formulário)
    coordenadoria        TEXT,
    supervisao           TEXT,
    oss                  TEXT,
    tipo_atividade       TEXT,
    cnes                 TEXT,
    nome_unidade         TEXT,
    cns_prof             TEXT,
    nome_profissional    TEXT,
    cbo_prof             TEXT,               -- código do CBO
    cbo                  TEXT,               -- nome do CBO
    data_atividade       TEXT,
    ano                  TEXT,
    mes                  TEXT,
    num_participantes    TEXT,
    cod_proced_sigtap    TEXT,
    procedimento_sigtap  TEXT
);
CREATE INDEX idx_staging_dtic_rel134_importacao ON staging_dtic_rel134(importacao_id);
CREATE INDEX idx_staging_dtic_rel134_periodo ON staging_dtic_rel134(periodo_referencia);

-- DTIC (REL_130) - eSUS Atendimento Domiciliar (evento por linha - um
-- atendimento). Só staging por enquanto - ver app/etl/outras_fontes.py.
CREATE TABLE staging_dtic_rel130 (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id        INTEGER NOT NULL REFERENCES importacoes(id),
    periodo_referencia   TEXT,               -- 'AAAAMM' informado no upload (a fonte não traz ano/mês por coluna)
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
);
CREATE INDEX idx_staging_dtic_rel130_importacao ON staging_dtic_rel130(importacao_id);
CREATE INDEX idx_staging_dtic_rel130_periodo ON staging_dtic_rel130(periodo_referencia);

-- SISAD - Questionário AD (Excel). É um retrato do cadastro de pacientes
-- (cuidados domiciliares/paliativos) no momento da extração, não uma
-- contagem de produção - por isso não tem colunas de quantidade. Só
-- staging por enquanto - ver docstring de app/etl/outras_fontes.py sobre
-- por que precisa de uma regra própria antes de virar indicador.
CREATE TABLE staging_sisad (
    id                                      INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id                           INTEGER NOT NULL REFERENCES importacoes(id),
    periodo_referencia                      TEXT,   -- 'AAAAMM' do retrato (informado no upload)
    id_sisad                                TEXT,   -- ID original do registro no SISAD
    coordenadoria                           TEXT,
    supervisao                              TEXT,
    unidade                                 TEXT,
    ubs_referencia                          TEXT,
    cns                                     TEXT,
    nome                                    TEXT,
    situacao                                TEXT,   -- ex: 'ATIVO', 'INATIVO'
    classificacao_cuidados_paliativos       TEXT,
    data_criacao                            TEXT,
    data_admissao                           TEXT,
    data_alta                               TEXT,
    motivo_alta                             TEXT,
    data_obito                              TEXT
);
CREATE INDEX idx_staging_sisad_importacao ON staging_sisad(importacao_id);
CREATE INDEX idx_staging_sisad_periodo ON staging_sisad(periodo_referencia);

-- FATO_APURACAO: formato comum para todas as fontes, após ETL de staging.
-- Fontes granulares (AT-02) preenchem procedimento_codigo/cbo_codigo, e o
-- indicador é resolvido via indicador_procedimento/indicador_cbo.
-- Fontes agregadas (Webssas) preenchem indicador_id diretamente.
CREATE TABLE fato_apuracao (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id                INTEGER NOT NULL REFERENCES fontes_dados(id),
    importacao_id           INTEGER NOT NULL REFERENCES importacoes(id),
    estabelecimento_id      INTEGER NOT NULL REFERENCES estabelecimentos(id),
    profissional_id         INTEGER REFERENCES profissionais(id),
    cbo_codigo              TEXT REFERENCES cbo(codigo),
    procedimento_codigo     TEXT REFERENCES procedimentos(codigo),
    indicador_id            INTEGER REFERENCES indicadores(id),
    periodo                 TEXT NOT NULL,             -- 'AAAAMM'
    quantidade              INTEGER NOT NULL,
    tipo_registro           TEXT NOT NULL
        CHECK (tipo_registro IN ('declarado', 'apurado')),
    subgrupo_id             INTEGER REFERENCES indicador_subgrupo(id) ON DELETE SET NULL
        -- v14: subgrupo do indicador ao qual este lançamento foi atribuído no cálculo
        -- (NULL = indicador sem subgrupo, ou lançamento que só casou com a regra geral)
);

CREATE INDEX idx_fato_periodo ON fato_apuracao(periodo);
CREATE INDEX idx_fato_estabelecimento ON fato_apuracao(estabelecimento_id);
CREATE INDEX idx_fato_indicador ON fato_apuracao(indicador_id);
CREATE INDEX idx_fato_procedimento ON fato_apuracao(procedimento_codigo);
CREATE INDEX idx_fato_fonte ON fato_apuracao(fonte_id);
CREATE INDEX idx_fato_subgrupo ON fato_apuracao(subgrupo_id);

-- ----------------------------------------------------------------------------
-- 6. VIEW DE RESUMO PARA O PAINEL
-- ----------------------------------------------------------------------------
-- Agrega fato_apuracao por indicador/estabelecimento/período/CBO (fontes
-- agregadas como o Webssas não têm CBO, então aparecem com cbo_codigo NULL)
-- e cruza com a meta vigente no período (resolvida pelo TA cujo período
-- contém a data do fato, casando também pelo CBO - uma meta com cbo_codigo
-- NULL só casa com fatos sem CBO). O percentual de atingimento é sempre
-- calculado aqui (apurado / meta), nunca armazenado.

-- v14: agrupa também por SUBGRUPO. A meta é a mais recente para a combinação
-- indicador+estabelecimento+subgrupo+CBO entre os TAs cujo período cobre a competência
-- (um TA novo que cobre só algumas unidades não apaga a meta das outras). Só a meta GERAL
-- (sem segmentação por RT/equipe/PMMB) entra aqui: fato_apuracao não sabe qual profissional
-- gerou cada linha. "cbo_agrupado": indicador/subgrupo que aceita qualquer CBO (curinga ou nenhum
-- CBO vinculado) tem a produção de todos os CBOs numa linha só com cbo_codigo NULL = "Curinga / Geral",
-- que é onde a meta GERAL casa; com CBO específico, cada CBO é uma meta independente.
-- v16: a meta vale quando o intervalo do TA SE SOBREPÕE ao mês da competência; metas segmentadas entram
-- somadas se não há meta geral. (mantida em sincronia com VIEW_RESULTADOS_INDICADOR em app/migrations_auto.py)
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
LEFT JOIN cbo c          ON c.codigo = a.cbo_agrupado;

-- ----------------------------------------------------------------------------
-- 7. TABELAS DE DE-PARA WEBSAASS (v18)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS de_para_websaass_indicador (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_producao      TEXT NOT NULL,
    producao          TEXT,
    servico           TEXT,
    codigo_indicador  TEXT,
    cbo_codigo        TEXT,
    indicador_id      INTEGER REFERENCES indicadores(id),
    subgrupo_id       INTEGER REFERENCES indicador_subgrupo(id)
);
CREATE INDEX IF NOT EXISTS idx_depara_ws_cod ON de_para_websaass_indicador(cod_producao);
CREATE INDEX IF NOT EXISTS idx_depara_ws_ind ON de_para_websaass_indicador(indicador_id);
CREATE INDEX IF NOT EXISTS idx_depara_ws_sg ON de_para_websaass_indicador(subgrupo_id);

CREATE TABLE IF NOT EXISTS de_para_websaass_unidade (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_websass        TEXT NOT NULL UNIQUE,
    estabelecimento_id  INTEGER NOT NULL REFERENCES estabelecimentos(id)
);
CREATE INDEX IF NOT EXISTS idx_depara_ws_estab ON de_para_websaass_unidade(estabelecimento_id);

