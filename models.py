from database import db
from werkzeug.security import generate_password_hash, check_password_hash

class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    senha = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def hash_senha(self, senha):
        self.senha = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha, senha)

class AG04(db.Model):
    __tablename__ = 'AG-04'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    tipo_agenda = db.Column(db.String(255), nullable=True)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cnes = db.Column(db.Integer, default=0)
    especialidade = db.Column(db.String(255), nullable=True)
    tipo_atendimento_agenda = db.Column(db.String(255), nullable=True)
    procedimento = db.Column(db.String(255), nullable=True)
    situacao_agendamento = db.Column(db.String(255), nullable=True)
    tipo_entidade = db.Column(db.String(255), nullable=True)
    quantidade_agendamento = db.Column(db.Integer, default=0)

class AT02(db.Model):
    __tablename__ = 'AT-02'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cmes = db.Column(db.Integer, default=0)
    tipo_estabelecimento = db.Column(db.String(255), nullable=True)
    cbo_no_sus = db.Column(db.Integer, default=0)
    nome_cbo = db.Column(db.String(255), nullable=True)
    especialidade = db.Column(db.String(255), nullable=True)
    codigo_procedimento = db.Column(db.Integer, default=0)
    procedimento = db.Column(db.String(255), nullable=True)
    profissional = db.Column(db.String(255), nullable=True)
    quantidade_procedimento = db.Column(db.Integer, default=0)
    contagem_paciente = db.Column(db.Integer, default=0)

class AT03(db.Model):
    __tablename__ = 'AT-03'

    id = db.Column(db.Integer, primary_key=True)
    ano = db.Column(db.Integer, default=0)
    mes = db.Column(db.String(255), nullable=True)
    sts = db.Column(db.String(255), nullable=True)
    estabelecimento = db.Column(db.String(255), nullable=True)
    faixa_etaria = db.Column(db.String(255), nullable=True)
    nome_cbo = db.Column(db.String(255), nullable=True)
    nome_procedimento = db.Column(db.String(255), nullable=True)
    sexo = db.Column(db.String(255), nullable=True)
    quantidade_procedimento = db.Column(db.Integer, default=0)

class FE02(db.Model):
    __tablename__ = 'FE-02'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    sts = db.Column(db.String(255), nullable=True)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cnes = db.Column(db.Integer, default=0)
    nome_procedimento = db.Column(db.String(255), nullable=True)
    nome_especialidade = db.Column(db.String(255), nullable=True)
    entrou_em_espera = db.Column(db.String(255), nullable=True)
    saiu_da_espera = db.Column(db.String(255), nullable=True)
    pacientes_ativos = db.Column(db.String(255), nullable=True)

class VG02(db.Model):
    __tablename__ = 'VG-02'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    procedimento = db.Column(db.String(255), nullable=True)
    nome_especialidade = db.Column(db.String(255), nullable=True)
    tipo_agenda = db.Column(db.String(255), nullable=True)
    tipo_atendimento_agenda = db.Column(db.String(255), nullable=True)
    situacao_vaga = db.Column(db.String(255), nullable=True)
    qtde_vaga_ofertada = db.Column(db.Integer, default=0)

class VG04(db.Model):
    __tablename__ = 'VG-04'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    tipo_agenda = db.Column(db.String(255), nullable=True)
    tipo_atendimento_agenda = db.Column(db.String(255), nullable=True)
    nome_procedimento = db.Column(db.String(255), nullable=True)
    nome_especialidade = db.Column(db.String(255), nullable=True)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    entidade = db.Column(db.String(255), nullable=True)
    qtde_vaga_ofertada = db.Column(db.Integer, default=0)
    qtde_agendamento = db.Column(db.Integer, default=0)
    qtde_atendimento = db.Column(db.Integer, default=0)

class CG01(db.Model):
    __tablename__ = 'CG-01'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes_extracao = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cnes = db.Column(db.Integer, default=0)
    qtde_gestantes = db.Column(db.Integer, default=0)
    atendimentos_maior_igual_9 = db.Column(db.Integer, default=0)

class CG05(db.Model):
    __tablename__ = 'CG-05'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes_extracao = db.Column(db.Integer, default=0)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cpf = db.Column(db.Integer, default=0)
    cns = db.Column(db.Integer, default=0)
    pessoa = db.Column(db.String(255), nullable=True)
    sisprenatal = db.Column(db.Integer, default=0)
    data_acolhimento = db.Column(db.Date)
    data_ultima_menstruacao = db.Column(db.Date)
    data_previsao_parto = db.Column(db.Date)
    dias_acolhimento_dum = db.Column(db.Integer, default=0)
    nr_semana_decorrido_ingresso = db.Column(db.Integer, default=0)
    qtde_consultas = db.Column(db.Integer, default=0)

class CG06(db.Model):
    __tablename__ = 'CG-06'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes_extracao = db.Column(db.Integer, default=0)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    pessoa = db.Column(db.String(255), nullable=True)
    sisprenatal = db.Column(db.Integer, default=0)
    data_acolhimento = db.Column(db.Date)
    dum = db.Column(db.Date)
    data_previsao_parto = db.Column(db.Date)
    dias_acolhimento_dum = db.Column(db.Integer, default=0)
    nr_semana_decorrido_ingresso = db.Column(db.Integer, default=0)
    glicemia = db.Column(db.String(255), nullable=True)
    hiv = db.Column(db.String(255), nullable=True)
    hbsag = db.Column(db.String(255), nullable=True)
    urina = db.Column(db.String(255), nullable=True)
    pesquisa_strepto_b = db.Column(db.String(255), nullable=True)
    vdrl = db.Column(db.String(255), nullable=True)
    totg_75g = db.Column(db.String(255), nullable=True)

class GAC02(db.Model):
    __tablename__ = 'GAC-02'

    id = db.Column(db.Integer, primary_key=True)
    data_extracao = db.Column(db.String(10), nullable=True)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(255), nullable=True)
    cns = db.Column(db.Integer, default=0)
    nome = db.Column(db.String(255), nullable=True)
    dc_raca = db.Column(db.String(255), nullable=True)
    qtde_consultas = db.Column(db.Integer, default=0)
