from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
import csv
import io
import os
from functools import wraps
from flask_cors import CORS

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'reel-cinemas-secret-key-change-in-production')

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# CORS Configuration
CORS(app,
     resources={r"/*": {"origins": ["http://localhost:3000", "https://reel-technical-ops.netlify.app"]}},
     supports_credentials=True,
     methods=["GET", "POST", "OPTIONS"],
     allow_headers=["Content-Type"])

# Configuration
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
TECHNICIAN_PASSWORD = os.getenv('TECHNICIAN_PASSWORD')

# Timezone for India (IST)
IST = pytz.timezone('Asia/Kolkata')

# Database Model
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
    
    def __repr__(self):
        return f'<Operation {self.id}: {self.button_name} - {self.status}>'

# Create tables
with app.app_context():
    db.create_all()

# Session storage (in-memory for simplicity)
sessions = {}

def get_session_id():
    """Get session ID from request headers or cookies"""
    return request.headers.get('X-Session-ID') or request.cookies.get('session_id')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = get_session_id()
        if not session_id or session_id not in sessions:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = get_session_id()
        if not session_id or sessions.get(session_id, {}).get('user_type') != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_type = data.get('userType')
    password = data.get('password')
    
    if user_type == 'Admin' and password == ADMIN_PASSWORD:
        session_id = os.urandom(24).hex()
        sessions[session_id] = {'user_type': 'Admin'}
        response = jsonify({'success': True, 'userType': 'Admin'})
        response.set_cookie(
    'session_id',
    session_id,
    httponly=True,
    samesite='Lax',
    secure=False
) 
        return response
    elif user_type == 'Technician' and password == TECHNICIAN_PASSWORD:
        session_id = os.urandom(24).hex()
        sessions[session_id] = {'user_type': 'Technician'}
        response = jsonify({'success': True, 'userType': 'Technician'})
        response.set_cookie(
    'session_id',
    session_id,
    httponly=True,
    samesite='Lax',
    secure=False
) 
        return response
    else:
        return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    session_id = get_session_id()
    if session_id and session_id in sessions:
        return jsonify({'authenticated': True, 'userType': sessions[session_id]['user_type']})
    return jsonify({'authenticated': False}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session_id = get_session_id()
    if session_id and session_id in sessions:
        del sessions[session_id]
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
    
    # Get current date and time in IST
    now_ist = datetime.now(IST)
    current_date = now_ist.strftime('%d/%m/%Y')
    current_time = now_ist.strftime('%H:%M:%S')
    
    try:
        # Insert records into database
        for button in button_states:
            operation = Operation(
                date=current_date,
                time=current_time,
                timeslot=timeslot,
                technician_name=technician_name,
                button_name=button['name'],
                status=button['status']
            )
            db.session.add(operation)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Data saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['GET'])
@login_required
def download_csv():
    try:
        # Fetch all operations from database
        operations = Operation.query.order_by(Operation.created_at.desc()).all()
        
        if not operations:
            return jsonify({'error': 'No data available'}), 404
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'Time', 'Timeslot', 'Technician Name', 'Button Name', 'Status'])
        
        # Write data rows
        for op in operations:
            writer.writerow([
                op.date,
                op.time,
                op.timeslot,
                op.technician_name,
                op.button_name,
                op.status
            ])
        
        # Convert to bytes
        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name='reel_operations.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete', methods=['POST'])
@admin_required
def delete_logs():
    try:
        # Delete all records from the table
        db.session.query(Operation).delete()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Logs deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)