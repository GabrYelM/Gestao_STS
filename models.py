# cria classes para mapear as tabelas no db
from database import db
from werkzeug.security import generate_password_hash, check_password_hash

class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
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
    tipo_agenda = db.Column(db.String(30), nullable=False)
    coordenadoria = db.Column(db.String(50), nullable=False)
    supervisao = db.Column(db.String(50), nullable=False)
    estabelecimento = db.Column(db.String(100), nullable=False)
    cnes = db.Column(db.Integer, default=0)
    especialidade = db.Column(db.String(100), nullable=False)
    tipo_atendimento = db.Column(db.String(20), nullable=False)
    procedimento = db.Column(db.String(200), nullable=False)
    situacao_agendamento = db.Column(db.String(50), nullable=False)
    entidade = db.Column(db.String(100), nullable=False)
    quantidade_agendamento = db.Column(db.Integer, default=0)

class AT02(db.Model):
    __tablename__ = 'AT-02'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    cnes = db.Column(db.Integer, default=0)
    estabelecimento = db.Column(db.String(100), nullable=False)
    cmes = db.Column(db.Integer, default=0)
    coordenadoria = db.Column(db.String(50), nullable=False)
    supervisao = db.Column(db.String(50), nullable=False)
    oss = db.Column(db.String(50), nullable=False)
    tipo_estabelecimento = db.Column(db.String(100), nullable=False)
    cbo_no_sus = db.Column(db.Integer, default=0)
    nome_cbo = db.Column(db.String(150), nullable=False)
    especialidade = db.Column(db.String(100), nullable=False)
    cod_procedimento = db.Column(db.Integer, default=0)
    procedimento = db.Column(db.String(200), nullable=False)
    profissional = db.Column(db.String(200), nullable=False)
    quantidade_procedimento = db.Column(db.Integer, default=0)
    contagem_paciente = db.Column(db.Integer, default=0)

class AT03(db.Model):
    __tablename__ = 'AT-03'

    id = db.Column(db.Integer, primary_key=True)
    ano_mes = db.Column(db.Integer, default=0)
    mes = db.Column(db.String(15), nullable=False)
    coordenadoria = db.Column(db.String(50), nullable=False)
    estabelecimento = db.Column(db.String(100), nullable=False)
    faixa_etaria = db.Column(db.String(20), nullable=False)
    nome_cbo = db.Column(db.String(150), nullable=False)
    procedimento = db.Column(db.String(200), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    quantidade_procedimento = db.Column(db.Integer, default=0)

class CG01(db.Model):
    __tablename__ = 'CG-01'

    id = db.Column(db.Integer, primary_key=True)
    