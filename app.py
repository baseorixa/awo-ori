import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from models import db, RegistroDiario
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
import google_auth_oauthlib.flow
from googleapiclient.discovery import build

# Load environment variables from .env
load_dotenv()

# Bypass HTTPS requirement for local OAuth testing in development
if os.environ.get('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)

# Render runs behind a reverse proxy (HTTPS termination). ProxyFix parses the correct protocol/host headers.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# Configure secret key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key_awo_ori_12345')

# Configure database
db_url = os.environ.get('DATABASE_URL')
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    db_url = "sqlite:///teste_local.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Ensure tables are created
with app.app_context():
    db.create_all()

# Google OAuth helper
def get_google_flow(state=None):
    client_config = {
        "web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ.get("GOOGLE_REDIRECT_URI", "")]
        }
    }
    scopes = ['https://www.googleapis.com/auth/userinfo.email', 'openid']
    
    return google_auth_oauthlib.flow.Flow.from_client_config(
        client_config,
        scopes=scopes,
        state=state,
        redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI")
    )

def is_professor():
    """Helper to check if the logged in user matches the professor's credentials."""
    is_logged = session.get('logged_in')
    user_email = session.get('email')
    prof_email = os.environ.get('PROFESSOR_EMAIL')
    
    # In local testing, if Google credentials are not set, password login is used.
    # We allow bypass if GOOGLE_CLIENT_ID is not configured and session says logged_in.
    google_configured = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    if not google_configured:
        return bool(is_logged)
        
    return bool(is_logged and user_email and prof_email and user_email.lower() == prof_email.lower())

@app.route('/')
def index():
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('registro_novo.html', today=today, action="novo", registro=None)

@app.route('/dashboard')
def dashboard():
    if not is_professor():
        flash('Acesso restrito. Por favor, faça login como professor.', 'error')
        return redirect(url_for('login_professor'))
        
    aluno_filter = request.args.get('aluno', '').strip()
    
    # Base query for daily logs
    query = RegistroDiario.query
    
    if aluno_filter:
        query = query.filter(RegistroDiario.nome_aluno.ilike(f"%{aluno_filter}%"))
        
    registros = query.order_by(RegistroDiario.data.desc(), RegistroDiario.id.desc()).all()
    
    # Calculate statistics from the database (handling empty database scenarios gracefully)
    total_registros = db.session.query(db.func.count(RegistroDiario.id)).scalar() or 0
    alunos_unicos = db.session.query(db.func.count(db.func.distinct(RegistroDiario.nome_aluno))).scalar() or 0
    
    # Count how many logs have dream entries filled
    sonhos_count = db.session.query(db.func.count(RegistroDiario.id)).filter(
        RegistroDiario.diario_sonhos.isnot(None), RegistroDiario.diario_sonhos != ''
    ).scalar() or 0
    
    # Count how many logs have asana practice entries filled
    asanas_count = db.session.query(db.func.count(RegistroDiario.id)).filter(
        RegistroDiario.pratica_mes_asana.isnot(None), RegistroDiario.pratica_mes_asana != ''
    ).scalar() or 0
    
    stats = {
        'total': total_registros,
        'alunos': alunos_unicos,
        'sonhos': sonhos_count,
        'asanas': asanas_count
    }
    
    # Get all distinct student names for the dashboard filter dropdown
    unique_students_query = db.session.query(RegistroDiario.nome_aluno).distinct().order_by(RegistroDiario.nome_aluno).all()
    unique_students = [r[0] for r in unique_students_query]

    return render_template('index.html', 
                           registros=registros, 
                           stats=stats, 
                           unique_students=unique_students, 
                           current_filter=aluno_filter)

@app.route('/registro/novo', methods=['GET', 'POST'])
def novo_registro():
    # Student route - no auth required, just renders student form or processes submission
    if request.method == 'POST':
        nome_aluno = request.form.get('nome_aluno', '').strip()
        data_str = request.form.get('data', '')
        diario_sonhos = request.form.get('diario_sonhos', '').strip()
        banimento_matutino = request.form.get('banimento_matutino', '').strip()
        pratica_mes_asana = request.form.get('pratica_mes_asana', '').strip()
        
        # Asana Time
        asana_tempo_str = request.form.get('asana_tempo', '').strip()
        asana_tempo = int(asana_tempo_str) if asana_tempo_str.isdigit() else None
        
        banimento_noturno = request.form.get('banimento_noturno', '').strip()
        diario_magico = request.form.get('diario_magico', '').strip()
        
        # Metrics
        fase_lua = request.form.get('fase_lua', '').strip()
        humor_predominante = request.form.get('humor_predominante', '').strip()
        clima = request.form.get('clima', '').strip()
        metricas_opcionais = f"Humor: {humor_predominante} | Clima: {clima} | Lua: {fase_lua}"
        
        ideias_insights = request.form.get('ideias_insights', '').strip()
        
        if not nome_aluno or not data_str:
            flash('Nome do Aluno e Data são obrigatórios!', 'error')
            return redirect(url_for('index'))
            
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de data inválido!', 'error')
            return redirect(url_for('index'))
            
        novo = RegistroDiario(
            nome_aluno=nome_aluno,
            data=data,
            diario_sonhos=diario_sonhos,
            banimento_matutino=banimento_matutino,
            pratica_mes_asana=pratica_mes_asana,
            asana_tempo=asana_tempo,
            banimento_noturno=banimento_noturno,
            diario_magico=diario_magico,
            metricas_opcionais=metricas_opcionais,
            fase_lua=fase_lua,
            humor_predominante=humor_predominante,
            clima=clima,
            ideias_insights=ideias_insights
        )
        
        db.session.add(novo)
        db.session.commit()
        flash('Registro diário adicionado com sucesso!', 'success')
        return redirect(url_for('meu_historico', aluno=nome_aluno))
        
    return redirect(url_for('index'))

@app.route('/registro/<int:id>')
def visualizar_registro(id):
    registro = RegistroDiario.query.get_or_404(id)
    
    is_admin = is_professor()
    student_query = request.args.get('aluno', '').strip()
    
    # Security Filter: restrict access to admin or the specific student
    if not is_admin and (not student_query or student_query.lower() != registro.nome_aluno.lower()):
        flash('Acesso recusado. Apenas o próprio iniciado ou o professor podem ler este diário.', 'error')
        return redirect(url_for('index'))
        
    return render_template('visualizar.html', registro=registro)

@app.route('/registro/<int:id>/editar', methods=['GET', 'POST'])
def editar_registro(id):
    if not is_professor():
        flash('Acesso restrito a professores para editar registros.', 'error')
        return redirect(url_for('login_professor'))
        
    registro = RegistroDiario.query.get_or_404(id)
    
    if request.method == 'POST':
        nome_aluno = request.form.get('nome_aluno', '').strip()
        data_str = request.form.get('data', '')
        diario_sonhos = request.form.get('diario_sonhos', '').strip()
        banimento_matutino = request.form.get('banimento_matutino', '').strip()
        pratica_mes_asana = request.form.get('pratica_mes_asana', '').strip()
        
        # Asana Time
        asana_tempo_str = request.form.get('asana_tempo', '').strip()
        asana_tempo = int(asana_tempo_str) if asana_tempo_str.isdigit() else None
        
        banimento_noturno = request.form.get('banimento_noturno', '').strip()
        diario_magico = request.form.get('diario_magico', '').strip()
        
        # Metrics
        fase_lua = request.form.get('fase_lua', '').strip()
        humor_predominante = request.form.get('humor_predominante', '').strip()
        clima = request.form.get('clima', '').strip()
        metricas_opcionais = f"Humor: {humor_predominante} | Clima: {clima} | Lua: {fase_lua}"
        
        ideias_insights = request.form.get('ideias_insights', '').strip()
        
        if not nome_aluno or not data_str:
            flash('Nome do Aluno e Data são obrigatórios!', 'error')
            return redirect(url_for('editar_registro', id=id))
            
        try:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Formato de data inválido!', 'error')
            return redirect(url_for('editar_registro', id=id))
            
        registro.nome_aluno = nome_aluno
        registro.data = data
        registro.diario_sonhos = diario_sonhos
        registro.banimento_matutino = banimento_matutino
        registro.pratica_mes_asana = pratica_mes_asana
        registro.asana_tempo = asana_tempo
        registro.banimento_noturno = banimento_noturno
        registro.diario_magico = diario_magico
        registro.metricas_opcionais = metricas_opcionais
        registro.fase_lua = fase_lua
        registro.humor_predominante = humor_predominante
        registro.clima = clima
        registro.ideias_insights = ideias_insights
        
        db.session.commit()
        flash('Registro diário atualizado com sucesso!', 'success')
        return redirect(url_for('visualizar_registro', id=id))
        
    formatted_date = registro.data.strftime('%Y-%m-%d')
    return render_template('registro_novo.html', registro=registro, today=formatted_date, action="editar")

@app.route('/registro/<int:id>/deletar', methods=['POST'])
def deletar_registro(id):
    if not is_professor():
        flash('Acesso restrito a professores para remover registros.', 'error')
        return redirect(url_for('login_professor'))
        
    registro = RegistroDiario.query.get_or_404(id)
    db.session.delete(registro)
    db.session.commit()
    flash('Registro diário removido com sucesso!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/formulario')
def formulario():
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('formulario.html', today=today)

@app.route('/enviar_rotina', methods=['POST'])
def enviar_rotina():
    nome_aluno = request.form.get('nome_aluno', '').strip()
    data_str = request.form.get('data', '')
    diario_sonhos = request.form.get('diario_sonhos', '').strip()
    banimento_matutino = request.form.get('banimento_matutino', '').strip()
    
    # Prática de Asana (Obrigatória do Mês)
    asana_tempo_str = request.form.get('asana_tempo', '').strip()
    asana_tempo = int(asana_tempo_str) if asana_tempo_str.isdigit() else None
    
    pratica_mes_asana = request.form.get('pratica_mes_asana', '').strip()
    if not pratica_mes_asana:
        pratica_mes_asana = request.form.get('asana_impressoes', '').strip()
    
    banimento_noturno = request.form.get('banimento_noturno', '').strip()
    diario_magico = request.form.get('diario_magico', '').strip()
    
    # Metrics (checking both dropdown names and legacy inputs)
    fase_lua = request.form.get('fase_lua', '').strip()
    
    humor_predominante = request.form.get('humor_predominante', '').strip()
    icon_humor = request.form.get('humor', '').strip()
    if icon_humor and not humor_predominante:
        humor_predominante = icon_humor
        
    clima = request.form.get('clima', '').strip()
    metricas_opcionais = f"Humor: {humor_predominante} | Clima: {clima} | Lua: {fase_lua}"
    
    # Insights
    ideias_insights = request.form.get('ideias_insights', '').strip()
    if not ideias_insights:
        ideias_insights = request.form.get('insights', '').strip()
    
    if not nome_aluno or not data_str:
        flash('Nome do Aluno e Data são obrigatórios!', 'error')
        return redirect(url_for('index'))
        
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Formato de data inválido!', 'error')
        return redirect(url_for('index'))
        
    novo = RegistroDiario(
        nome_aluno=nome_aluno,
        data=data,
        diario_sonhos=diario_sonhos,
        banimento_matutino=banimento_matutino,
        pratica_mes_asana=pratica_mes_asana,
        asana_tempo=asana_tempo,
        banimento_noturno=banimento_noturno,
        diario_magico=diario_magico,
        metricas_opcionais=metricas_opcionais,
        fase_lua=fase_lua,
        humor_predominante=humor_predominante,
        clima=clima,
        ideias_insights=ideias_insights
    )
    
    db.session.add(novo)
    db.session.commit()
    flash('Relatório diário enviado e consagrado com sucesso!', 'success')
    return redirect(url_for('meu_historico', aluno=nome_aluno))

@app.route('/login_professor', methods=['GET', 'POST'])
def login_professor():
    google_configured = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    
    if request.method == 'POST':
        # If Google is configured, we initiate OAuth.
        # If not, we allow password authentication as a local bypass.
        if google_configured:
            try:
                flow = get_google_flow()
                authorization_url, state = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )
                session['oauth_state'] = state
                return redirect(authorization_url)
            except Exception as e:
                flash(f'Erro ao iniciar o login com o Google: {str(e)}', 'error')
                return redirect(url_for('login_professor'))
        else:
            # Local password bypass
            password = request.form.get('password', '')
            admin_password = os.environ.get('ADMIN_PASSWORD', 'ori_admin_2026')
            
            if password == admin_password:
                session['logged_in'] = True
                session['email'] = os.environ.get('PROFESSOR_EMAIL', 'professor@dev.local')
                flash('Login local realizado (Sem Google OAuth).', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Chave alquímica incorreta.', 'error')
                return redirect(url_for('login_professor'))
            
    return render_template('login_professor.html', google_configured=google_configured)

@app.route('/login/google/callback')
def google_callback():
    try:
        state = session.get('oauth_state')
        flow = get_google_flow(state=state)
        
        # Fetch tokens using the callback URL parameters
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Query user info using Google API Client
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info.get('email', '')
        
        prof_email = os.environ.get('PROFESSOR_EMAIL')
        if email and prof_email and email.lower() == prof_email.lower():
            session['logged_in'] = True
            session['email'] = email
            flash('Autenticação com o Google realizada com sucesso.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(f'Acesso Negado: O e-mail {email} não possui privilégios de professor.', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        flash(f'Erro na autenticação do Google: {str(e)}', 'error')
        return redirect(url_for('login_professor'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('email', None)
    session.pop('oauth_state', None)
    flash('Conexão encerrada com sucesso.', 'success')
    return redirect(url_for('index'))

@app.route('/meu_historico')
def meu_historico():
    student_name = request.args.get('aluno', '').strip()
    search_performed = 'aluno' in request.args
    registros = []
    
    if student_name:
        registros = RegistroDiario.query.filter(RegistroDiario.nome_aluno.ilike(student_name)).order_by(RegistroDiario.data.desc()).all()
        
    return render_template('meu_historico.html', 
                           registros=registros, 
                           student_name=student_name, 
                           search_performed=search_performed)

if __name__ == '__main__':
    app.run(debug=True)
