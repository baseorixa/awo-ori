import os
import threading
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from dotenv import load_dotenv
from models import db, RegistroDiario
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
import google_auth_oauthlib.flow
from googleapiclient.discovery import build

# ReportLab for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

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

# Ensure tables are created and migrate schema if necessary
with app.app_context():
    db.create_all()
    # Dynamic migration to add email_aluno to registers table if it doesn't exist
    try:
        db.session.execute(db.text("SELECT email_aluno FROM registros_diarios LIMIT 1"))
    except Exception:
        db.session.rollback()
        try:
            # Check database dialect to alter table accordingly
            db.session.execute(db.text("ALTER TABLE registros_diarios ADD COLUMN email_aluno VARCHAR(120)"))
            db.session.commit()
            print("Successfully added email_aluno column to registros_diarios table.")
        except Exception as alter_err:
            print(f"Failed to add column email_aluno: {alter_err}")
            db.session.rollback()

def generate_pdf(registro):
    """Generates a beautiful mystical/clean PDF report of the daily log."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=inch*0.75, 
        leftMargin=inch*0.75,
        topMargin=inch*0.75, 
        bottomMargin=inch*0.75
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles matching the mystical portal theme but optimized for print readability
    title_style = ParagraphStyle(
        'MysticTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=colors.HexColor('#dfb76c'), # Gold
        spaceAfter=15,
        alignment=1 # Center
    )
    
    subtitle_style = ParagraphStyle(
        'MysticSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor=colors.HexColor('#64748b'), # Slate 500
        spaceAfter=25,
        alignment=1 # Center
    )
    
    heading_style = ParagraphStyle(
        'MysticHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor('#8b5cf6'), # Purple
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = ParagraphStyle(
        'MysticBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#1e293b'), # Dark Slate
        spaceAfter=10,
        leading=14
    )
    
    meta_style = ParagraphStyle(
        'MysticMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0f172a'),
        leading=14
    )

    story = []
    
    # Header
    story.append(Paragraph("AWÓ ORÍ — DIÁRIO INICIÁTICO", title_style))
    story.append(Paragraph(f"Registro Consagrado em {registro.data.strftime('%d/%m/%Y')}", subtitle_style))
    
    # Metadata Table
    meta_data = [
        [Paragraph("Iniciado / Aluno:", meta_style), Paragraph(registro.nome_aluno, body_style)],
        [Paragraph("Data do Registro:", meta_style), Paragraph(registro.data.strftime('%d/%m/%Y'), body_style)],
        [Paragraph("E-mail do Aluno:", meta_style), Paragraph(registro.email_aluno or "Não informado", body_style)]
    ]
    
    if registro.fase_lua:
        meta_data.append([Paragraph("Fase da Lua:", meta_style), Paragraph(registro.fase_lua, body_style)])
    if registro.humor_predominante:
        meta_data.append([Paragraph("Humor Predominante:", meta_style), Paragraph(registro.humor_predominante, body_style)])
    if registro.clima:
        meta_data.append([Paragraph("Clima:", meta_style), Paragraph(registro.clima, body_style)])
        
    t = Table(meta_data, colWidths=[150, 350])
    t.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Dream Diary
    if registro.diario_sonhos:
        story.append(Paragraph("Diário de Sonhos", heading_style))
        story.append(Paragraph(registro.diario_sonhos.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    # Morning Banishing
    if registro.banimento_matutino:
        story.append(Paragraph("Ritual de Banimento Matutino", heading_style))
        story.append(Paragraph(registro.banimento_matutino.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    # Asana Practice
    if registro.pratica_mes_asana or registro.asana_tempo:
        story.append(Paragraph("Prática de Asana", heading_style))
        asana_details = f"Tempo de Prática: {registro.asana_tempo} minutos" if registro.asana_tempo else ""
        if asana_details:
            story.append(Paragraph(asana_details, meta_style))
        if registro.pratica_mes_asana:
            story.append(Paragraph(registro.pratica_mes_asana.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    # Night Banishing
    if registro.banimento_noturno:
        story.append(Paragraph("Ritual de Banimento Noturno", heading_style))
        story.append(Paragraph(registro.banimento_noturno.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    # Magic Diary
    if registro.diario_magico:
        story.append(Paragraph("Diário Mágico", heading_style))
        story.append(Paragraph(registro.diario_magico.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    # Insights & Ideas
    if registro.ideias_insights:
        story.append(Paragraph("Ideias & Insights", heading_style))
        story.append(Paragraph(registro.ideias_insights.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 10))
        
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

def send_email_with_pdf(nome_aluno, email_aluno, data_str, pdf_bytes, fase_lua=None, humor=None):
    """Sends the PDF report via SMTP to the professor (rhormidas@gmail.com)."""
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    try:
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    except ValueError:
        smtp_port = 587
        
    smtp_username = os.environ.get('SMTP_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    sender_email = os.environ.get('MAIL_DEFAULT_SENDER', smtp_username)
    
    # Destination email is the professor email
    recipient_email = os.environ.get('PROFESSOR_EMAIL', 'rhormidas@gmail.com')
    
    if not smtp_username or not smtp_password:
        print("Email sending skipped: SMTP credentials (SMTP_USERNAME / SMTP_PASSWORD) not configured.")
        return False
        
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"Novo Diário Consagrado - {nome_aluno} ({data_str})"
        
        # Email Body
        body = f"""Olá, Professor.

Um novo diário de práticas iniciáticas foi enviado e consagrado no portal Awó Orí.

Aluno: {nome_aluno}
E-mail: {email_aluno or 'Não informado'}
Data: {data_str}
Fase da Lua: {fase_lua or 'Não informada'}
Humor Predominante: {humor or 'Não informado'}

O relatório detalhado está em anexo em formato PDF.

---
Portal Awó Orí
"""
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Attachment
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        safe_name = nome_aluno.replace(' ', '_').replace('/', '_')
        filename = f"Diario_{safe_name}_{data_str.replace('/', '')}.pdf"
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)
        
        # Connect and Send
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"PDF email sent successfully to {recipient_email}!")
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

def trigger_email_send(registro, pdf_bytes):
    """Spawns a background thread to send the email and avoid blocking the web request."""
    data_str = registro.data.strftime('%d/%m/%Y')
    thread = threading.Thread(
        target=send_email_with_pdf,
        args=(registro.nome_aluno, registro.email_aluno, data_str, pdf_bytes, registro.fase_lua, registro.humor_predominante)
    )
    thread.daemon = True
    thread.start()

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
    """Helper to check if the logged in user is the professor."""
    return bool(session.get('logged_in') and session.get('role') == 'professor')

@app.before_request
def require_login():
    """Enforces authentication for all routes except login, callback, logout, and static files."""
    allowed_endpoints = ['login', 'google_callback', 'logout', 'static']
    if request.path.startswith('/static'):
        return
    if not session.get('logged_in'):
        if request.endpoint and request.endpoint not in allowed_endpoints:
            return redirect(url_for('login'))

def calculate_crc16(payload):
    """Calculates CRC16 CCITT (used for Pix BR Code verification)."""
    crc = 0xFFFF
    for char in payload:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"

def generate_pix_payload(pix_key, name="Ricardo", city="SAO PAULO"):
    """Generates a valid static EMV BR Code (Pix Payload) from a Pix Key."""
    import unicodedata
    def clean_string(s, max_len):
        # Remove accents
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        # Keep only alphanumeric and spaces
        s = ''.join(c for c in s if c.isalnum() or c == ' ')
        s = s.upper().strip()
        return s[:max_len]

    clean_name = clean_string(name, 25)
    clean_city = clean_string(city, 15)
    
    # Tag 26: Merchant Account Information
    gui_part = "0014br.gov.bcb.pix"
    key_part = f"01{len(pix_key):02d}{pix_key}"
    merchant_info = f"26{len(gui_part + key_part):02d}{gui_part}{key_part}"
    
    f52 = "52040000"  # Merchant Category Code
    f53 = "5303986"   # Transaction Currency (986 = Real)
    f58 = "5802BR"    # Country Code
    f59 = f"59{len(clean_name):02d}{clean_name}"
    f60 = f"60{len(clean_city):02d}{clean_city}"
    f62 = "62070503***"  # Additional Data Field Template (Reference label)
    
    base_payload = f"000201{merchant_info}{f52}{f53}{f58}{f59}{f60}{f62}6304"
    crc = calculate_crc16(base_payload)
    return base_payload + crc

@app.context_processor
def inject_global_vars():
    """Injects Pix donation details globally into all template contexts."""
    # Default to user's credentials if not set in environment variables
    pix_key = os.environ.get('PIX_KEY', '2198079125')
    pix_copia_cola = os.environ.get('PIX_COPIA_COLA', '')
    pix_name = os.environ.get('PIX_NAME', 'Ricardo')
    pix_city = os.environ.get('PIX_CITY', 'RIO DE JANEIRO')
    
    # Auto-format Brazilian phone keys (10 or 11 digits, numeric) to include country code +55
    # This is required by the Central Bank specification for phone number keys.
    if pix_key.isdigit() and len(pix_key) in [10, 11]:
        pix_key = f"+55{pix_key}"
    
    # Dynamically generate the Copia e Cola payload if not configured
    if not pix_copia_cola and pix_key and pix_key != 'seu-email-ou-chave-pix@provedor.com':
        try:
            pix_copia_cola = generate_pix_payload(pix_key, name=pix_name, city=pix_city)
        except Exception as e:
            print(f"Error generating Pix payload: {e}")
            
    # Generate dynamic QR Code URL
    qr_data = pix_copia_cola if pix_copia_cola else f"pix:{pix_key}"
    encoded_qr_data = urllib.parse.quote(qr_data)
    pix_qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={encoded_qr_data}"
    
    return {
        'pix_key': pix_key,
        'pix_copia_cola': pix_copia_cola,
        'pix_qr_url': pix_qr_url
    }


@app.route('/')
def index():
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('registro_novo.html', today=today, action="novo", registro=None)

@app.route('/dashboard')
def dashboard():
    if not is_professor():
        flash('Acesso restrito. Por favor, faça login como professor.', 'error')
        return redirect(url_for('login'))
        
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
            email_aluno=session.get('email'),
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
        
        # Generate and send PDF in background
        try:
            pdf_bytes = generate_pdf(novo)
            trigger_email_send(novo, pdf_bytes)
            flash('Registro diário consagrado e enviado com sucesso ao professor!', 'success')
        except Exception as pdf_err:
            print(f"Failed to generate or send PDF: {pdf_err}")
            flash('Registro diário consagrado com sucesso! (Erro ao enviar e-mail com anexo)', 'success')
            
        return redirect(url_for('meu_historico'))
        
    return redirect(url_for('index'))

@app.route('/registro/<int:id>')
def visualizar_registro(id):
    registro = RegistroDiario.query.get_or_404(id)
    
    is_admin = is_professor()
    student_query = request.args.get('aluno', '').strip()
    user_email = session.get('email')
    
    # Security Filter: restrict access to admin or the specific student by email
    has_access = False
    if is_admin:
        has_access = True
    elif user_email and registro.email_aluno and user_email.lower() == registro.email_aluno.lower():
        has_access = True
    elif not registro.email_aluno and student_query and student_query.lower() == registro.nome_aluno.lower():
        # Legacy compatibility fallback
        has_access = True
        
    if not has_access:
        flash('Acesso recusado. Apenas o próprio iniciado ou o professor podem ler este diário.', 'error')
        return redirect(url_for('index'))
        
    return render_template('visualizar.html', registro=registro)

@app.route('/registro/<int:id>/pdf')
def download_pdf(id):
    registro = RegistroDiario.query.get_or_404(id)
    
    is_admin = is_professor()
    student_query = request.args.get('aluno', '').strip()
    user_email = session.get('email')
    
    # Security Filter: restrict access to admin or the specific student by email
    has_access = False
    if is_admin:
        has_access = True
    elif user_email and registro.email_aluno and user_email.lower() == registro.email_aluno.lower():
        has_access = True
    elif not registro.email_aluno and student_query and student_query.lower() == registro.nome_aluno.lower():
        # Legacy compatibility fallback
        has_access = True
        
    if not has_access:
        flash('Acesso recusado. Apenas o próprio iniciado ou o professor podem baixar este diário.', 'error')
        return redirect(url_for('index'))
        
    try:
        pdf_bytes = generate_pdf(registro)
        safe_name = registro.nome_aluno.replace(' ', '_').replace('/', '_')
        filename = f"Diario_{safe_name}_{registro.data.strftime('%Y%m%d')}.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Erro ao gerar o download do PDF: {str(e)}', 'error')
        return redirect(url_for('visualizar_registro', id=id))

@app.route('/registro/<int:id>/editar', methods=['GET', 'POST'])
def editar_registro(id):
    if not is_professor():
        flash('Acesso restrito a professores para editar registros.', 'error')
        return redirect(url_for('login'))
        
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
        return redirect(url_for('login'))
        
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
        email_aluno=session.get('email'),
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
    
    # Generate and send PDF in background
    try:
        pdf_bytes = generate_pdf(novo)
        trigger_email_send(novo, pdf_bytes)
        flash('Relatório diário enviado, consagrado e enviado com sucesso ao professor!', 'success')
    except Exception as pdf_err:
        print(f"Failed to generate or send PDF: {pdf_err}")
        flash('Relatório diário enviado e consagrado com sucesso! (Erro ao enviar e-mail com anexo)', 'success')
        
    return redirect(url_for('meu_historico'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    google_configured = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    
    if request.method == 'POST':
        action_type = request.form.get('action_type', '')
        
        # If Google is configured and they clicked OAuth
        if google_configured and action_type == 'google_oauth':
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
                return redirect(url_for('login'))
                
        # Local bypass logins (when testing locally)
        elif action_type == 'bypass_professor':
            password = request.form.get('password', '')
            admin_password = os.environ.get('ADMIN_PASSWORD', 'ori_admin_2026')
            
            if password == admin_password:
                session['logged_in'] = True
                session['email'] = os.environ.get('PROFESSOR_EMAIL', 'rhormidas@gmail.com')
                session['name'] = 'Professor'
                session['role'] = 'professor'
                flash('Login local realizado como Professor (Sem Google OAuth).', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Chave alquímica incorreta.', 'error')
                return redirect(url_for('login'))
                
        elif action_type == 'bypass_student':
            student_email = request.form.get('student_email', 'aluno@teste.com').strip()
            student_name = request.form.get('student_name', 'Iniciado Teste').strip()
            
            if not student_email or not student_name:
                flash('Nome e e-mail são obrigatórios para o bypass!', 'error')
                return redirect(url_for('login'))
                
            session['logged_in'] = True
            session['email'] = student_email
            session['name'] = student_name
            session['role'] = 'aluno'
            flash(f'Login local realizado como Aluno: {student_name} (Sem Google OAuth).', 'success')
            return redirect(url_for('index'))
            
    return render_template('login.html', google_configured=google_configured)

@app.route('/login/google/callback')
def google_callback():
    try:
        state = session.get('oauth_state')
        flow = get_google_flow(state=state)
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info.get('email', '')
        name = user_info.get('name', 'Iniciado')
        
        prof_email = os.environ.get('PROFESSOR_EMAIL', 'rhormidas@gmail.com')
        
        session['logged_in'] = True
        session['email'] = email
        session['name'] = name
        
        if email and prof_email and email.lower() == prof_email.lower():
            session['role'] = 'professor'
            flash('Autenticação com o Google realizada com sucesso. Bem-vindo, Professor.', 'success')
            return redirect(url_for('dashboard'))
        else:
            session['role'] = 'aluno'
            flash(f'Autenticação realizada com sucesso. Bem-vindo(a), {name}.', 'success')
            return redirect(url_for('index'))
            
    except Exception as e:
        flash(f'Erro na autenticação do Google: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('email', None)
    session.pop('name', None)
    session.pop('role', None)
    session.pop('oauth_state', None)
    flash('Conexão encerrada com sucesso.', 'success')
    return redirect(url_for('login'))

@app.route('/meu_historico')
def meu_historico():
    if is_professor():
        flash('Professores podem ver todos os registros no Dashboard.', 'info')
        return redirect(url_for('dashboard'))
        
    user_email = session.get('email')
    registros = []
    
    if user_email:
        registros = RegistroDiario.query.filter(RegistroDiario.email_aluno.ilike(user_email)).order_by(RegistroDiario.data.desc()).all()
        
    return render_template('meu_historico.html', registros=registros, student_email=user_email)

if __name__ == '__main__':
    app.run(debug=True)
