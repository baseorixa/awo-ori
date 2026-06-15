from flask_sqlalchemy import SQLAlchemy
from datetime import date

db = SQLAlchemy()

class RegistroDiario(db.Model):
    """
    Model representing a student's daily tracking journal for the Awó Orí course.
    """
    __tablename__ = 'registros_diarios'
    
    id = db.Column(db.Integer, primary_key=True)
    nome_aluno = db.Column(db.String(100), nullable=False, index=True)
    email_aluno = db.Column(db.String(120), nullable=True, index=True)
    data = db.Column(db.Date, nullable=False, default=date.today, index=True)
    diario_sonhos = db.Column(db.Text, nullable=True)
    banimento_matutino = db.Column(db.String(255), nullable=True) # Horário e notas
    pratica_mes_asana = db.Column(db.Text, nullable=True)        # Impressões da imobilidade
    asana_tempo = db.Column(db.Integer, nullable=True)           # Tempo de Prática (minutos)
    banimento_noturno = db.Column(db.String(255), nullable=True)  # Horário e notas
    diario_magico = db.Column(db.Text, nullable=True)             # Diário Mágico
    metricas_opcionais = db.Column(db.String(255), nullable=True) # Humor, Clima, Fase da Lua (legacy compatibility)
    fase_lua = db.Column(db.String(50), nullable=True)            # Fase da Lua dropdown
    humor_predominante = db.Column(db.String(50), nullable=True)   # Humor Predominante dropdown
    clima = db.Column(db.String(100), nullable=True)               # Clima/Condições do Dia
    ideias_insights = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<RegistroDiario {self.nome_aluno} - {self.data}>"
