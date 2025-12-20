from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
import csv
import io
import os
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

IS_PROD = os.getenv("FLASK_ENV") == "production"

app.secret_key = os.getenv(
    'SECRET_KEY',
    'reel-cinemas-secret-key-change-in-production'
)

app.config.update(
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
)

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:3000",
        "https://reel-technical-ops.netlify.app"
    ]
)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
TECHNICIAN_PASSWORD = os.getenv('TECHNICIAN_PASSWORD')

IST = pytz.timezone('Asia/Kolkata')

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

sessions = {}

def get_session_id():
    return (
        request.headers.get('X-Session-ID')
        or request.cookies.get('session_id')
    )

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        session_id = get_session_id()
        if not session_id or session_id not in sessions:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        session_id = get_session_id()
        if sessions.get(session_id, {}).get('user_type') != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return wrapper

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_type = data.get('userType')
    password = data.get('password')

    if (
        (user_type == 'Admin' and password == ADMIN_PASSWORD)
        or
        (user_type == 'Technician' and password == TECHNICIAN_PASSWORD)
    ):
        session_id = os.urandom(24).hex()
        sessions[session_id] = {'user_type': user_type}

        response = jsonify({'success': True, 'userType': user_type})
        response.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            samesite='None',
            secure=True
        )

        return response

    return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    session_id = get_session_id()
    if session_id in sessions:
        return jsonify({
            'authenticated': True,
            'userType': sessions[session_id]['user_type']
        })
    return jsonify({'authenticated': False}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session_id = get_session_id()
    sessions.pop(session_id, None)
    response = jsonify({'success': True})
    response.set_cookie('session_id', '', expires=0)
    return response

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
            db.session.add(
                Operation(
                    date=now_ist.strftime('%d/%m/%Y'),
                    time=now_ist.strftime('%H:%M:%S'),
                    timeslot=timeslot,
                    technician_name=technician_name,
                    button_name=button['name'],
                    status=button['status']
                )
            )
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['GET'])
@login_required
def download_csv():
    ops = Operation.query.order_by(Operation.created_at.desc()).all()
    if not ops:
        return jsonify({'error': 'No data'}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'Timeslot', 'Technician', 'Button', 'Status'])

    for op in ops:
        writer.writerow([
            op.date, op.time, op.timeslot,
            op.technician_name, op.button_name, op.status
        ])

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

@app.route('/api/debug-session')
def debug_session():
    return jsonify({
        'cookies': request.cookies,
        'sessions': list(sessions.keys())
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
