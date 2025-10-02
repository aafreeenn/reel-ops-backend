from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from datetime import datetime
import pytz
import csv
import os
from functools import wraps

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = 'reel-cinemas-secret-key-change-in-production'
CORS(app, 
     supports_credentials=True, 
     origins=['https://reel-technical-ops.netlify.app/'],
     allow_headers=['Content-Type'],
     methods=['GET', 'POST', 'OPTIONS'])

# Configuration
CSV_FILE = os.path.join('data', 'operations.csv')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
TECHNICIAN_PASSWORD = os.getenv('TECHNICIAN_PASSWORD')

# Timezone for India (IST)
IST = pytz.timezone('Asia/Kolkata')

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Initialize CSV file with headers if it doesn't exist
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Time', 'Timeslot', 'Technician Name', 'Button Name', 'Status'])

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_type' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_type = data.get('userType')
    password = data.get('password')
    
    if user_type == 'Admin' and password == ADMIN_PASSWORD:
        session['user_type'] = 'Admin'
        return jsonify({'success': True, 'userType': 'Admin'})
    elif user_type == 'Technician' and password == TECHNICIAN_PASSWORD:
        session['user_type'] = 'Technician'
        return jsonify({'success': True, 'userType': 'Technician'})
    else:
        return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_type' in session:
        return jsonify({'authenticated': True, 'userType': session['user_type']})
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
    
    # Get current date and time in IST
    now_ist = datetime.now(IST)
    current_date = now_ist.strftime('%Y-%m-%d')
    current_time = now_ist.strftime('%H:%M:%S')
    
    try:
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for button in button_states:
                writer.writerow([
                    current_date,
                    current_time,
                    timeslot,
                    technician_name,
                    button['name'],
                    button['status']
                ])
        
        return jsonify({'success': True, 'message': 'Data saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['GET'])
@login_required
def download_csv():
    if os.path.exists(CSV_FILE):
        return send_file(CSV_FILE, as_attachment=True, download_name='reel_operations.csv')
    return jsonify({'error': 'No data available'}), 404

@app.route('/api/delete', methods=['POST'])
@admin_required
def delete_logs():
    try:
        # Recreate CSV with just headers
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Time', 'Timeslot', 'Technician Name', 'Button Name', 'Status'])
        
        return jsonify({'success': True, 'message': 'Logs deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)