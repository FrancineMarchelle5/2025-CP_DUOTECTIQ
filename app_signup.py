from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)

def insert_user(data):
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO tbl_users
            (first_name, middle_name, last_name, mobile_number, baranggay, street, city, zip_code, password, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('first_name', ''),
            data.get('middle_name', ''),
            data.get('last_name', ''),
            data.get('mobile_number', ''),
            data.get('baranggay', ''),
            data.get('street', ''),
            data.get('city', ''),
            data.get('zip_code', ''),
            data.get('password', ''),
            data.get('role', '')
        ))
        conn.commit()
        return True, "User registered successfully."
    except sqlite3.IntegrityError:
        return False, "Mobile number already exists."
    finally:
        conn.close()

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    required = ['first_name', 'last_name', 'mobile_number', 'password', 'role', 'baranggay']
    if not all(data.get(k) for k in required):
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400
    ok, msg = insert_user(data)
    return jsonify({'success': ok, 'message': msg})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    mobile = data.get('mobile_number')
    password = data.get('password')
    if not mobile or not password:
        return jsonify({'success': False, 'message': 'Missing mobile number or password.'}), 400
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('SELECT * FROM tbl_users WHERE mobile_number=? AND password=?', (mobile, password))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({'success': True, 'message': 'Login successful.'})
    else:
        return jsonify({'success': False, 'message': 'Invalid mobile number or password.'}), 401

@app.route('/profile', methods=['POST'])
def profile():
    data = request.json
    mobile = data.get('mobile_number')
    if not mobile:
        return jsonify({'success': False, 'message': 'Missing mobile number.'}), 400
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('SELECT first_name, middle_name, last_name, mobile_number, baranggay, street, city, zip_code, role FROM tbl_users WHERE mobile_number=?', (mobile,))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({
            'success': True,
            'profile': {
                'first_name': user[0],
                'middle_name': user[1],
                'last_name': user[2],
                'mobile_number': user[3],
                'baranggay': user[4],
                'street': user[5],
                'city': user[6],
                'zip_code': user[7],
                'role': user[8]
            }
        })
    else:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
@app.route('/save_sorting', methods=['POST'])
def save_sorting():
    data = request.json
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('''
        INSERT INTO tbl_sorting (crop_type, condition, color, sorted_to, size)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        data.get('crop_type'),
        data.get('condition'),
        data.get('color'),
        data.get('sorted_to'),
        data.get('size')
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Sorting result saved.'})

@app.route('/system-status', methods=['GET'])
def system_status():
    try:
        # Add your system health checks here
        # For example: check database connection, camera status, etc.
        
        # Simple example - you can expand this
        return jsonify({
            'status': 'online',
            'timestamp': datetime.now().isoformat(),
            'message': 'System is running normally'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)


