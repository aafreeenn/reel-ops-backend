from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session  # New: Persistent sessions
from datetime import datetime
import pytz
import csv
import io
import os
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'reel-cinemas-fallback-key')

# 2. SECURITY & COOKIE SETTINGS 
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_PATH='/',
)

# Session Configuration (Stores sessions in your DB)
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_COOKIE_SAMESITE'] = "None"
app.config['SESSION_COOKIE_SECURE'] = True  # Required for Cross-Site (Netlify to Render)
app.config['SESSION_PERMANENT'] = True

db = SQLAlchemy(app)
app.config['SESSION_SQLALCHEMY'] = db
Session(app) # Initialize Session extension

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:3000",
        "https://reel-technical-ops.netlify.app"
    ]
)

IST = pytz.timezone('Asia/Kolkata')

# --- Models ---
class Operation(db.Model):
    __tablename__ = 'operations'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    timeslot = db.Column(db.String(10), nullable=False)
    technician_name = db.Column(db.String(100), nullable=False)
    button_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

with app.app_context():
    db.create_all()

# --- Auth Decorators ---
# We now use the built-in Flask 'session' object instead of a global dict
from flask import session

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_type' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('user_type') != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return wrapper

# --- Routes ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_type = data.get('userType')
    password = data.get('password')

    admin_pass = os.getenv('ADMIN_PASSWORD')
    tech_pass = os.getenv('TECHNICIAN_PASSWORD')

    if (user_type == 'Admin' and password == admin_pass) or \
       (user_type == 'Technician' and password == tech_pass):
        
        session.clear()
        session['user_type'] = user_type
        session.permanent = True 
        
        return jsonify({'success': True, 'userType': user_type})

    return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_type' in session:
        return jsonify({
            'authenticated': True,
            'userType': session['user_type']
        })
    return jsonify({'authenticated': False}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/save', methods=['POST'])
@login_required
def save_operations():
    data = request.json
    button_states = data.get('buttonStates', [])
    timeslot = data.get('timeslot')
    technician_name = data.get('technicianName', '')

    now_ist = datetime.now(IST)
    try:
        for button in button_states:
            db.session.add(Operation(
                date=now_ist.strftime('%d/%m/%Y'),
                time=now_ist.strftime('%H:%M:%S'),
                timeslot=timeslot,
                technician_name=technician_name,
                button_name=button['name'],
                status=button['status']
            ))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['GET'])
@login_required
def download_csv():
    ops = Operation.query.order_by(Operation.created_at.desc()).all()
    if not ops: return jsonify({'error': 'No data'}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'Timeslot', 'Technician', 'Button', 'Status'])
    for op in ops:
        writer.writerow([op.date, op.time, op.timeslot, op.technician_name, op.button_name, op.status])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='reel_operations.csv'
    )

@app.route('/api/delete', methods=['POST'])
@login_required
@admin_required
def delete_logs():
    db.session.query(Operation).delete()
    db.session.commit()
    return jsonify({'success': True})

@app.after_request
def add_cookie_headers(response):
    # This manually forces the browser to accept the cookie settings
    # even if the Flask-Session extension struggles with cross-domains
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

if __name__ == '__main__':
    app.run(debug=False) # Production mode