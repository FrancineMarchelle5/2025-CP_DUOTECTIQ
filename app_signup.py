

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

def insert_user(data):
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO tbl_users
            (first_name, middle_name, last_name, mobile_number, barangay, street, city, zip_code, password, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['first_name'],
            data['middle_name'],
            data['last_name'],
            data['mobile_number'],
            data['barangay'],
            data['street'],
            data['city'],
            data['zip_code'],
            data['password'],
            data['role']
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
    required = ['first_name', 'last_name', 'mobile_number', 'password', 'role']  # <-- Add 'role'
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
    c.execute('SELECT first_name, middle_name, last_name, mobile_number, barangay, street, city, zip_code, role FROM tbl_users WHERE mobile_number=?', (mobile,))
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
                'barangay': user[4],
                'street': user[5],
                'city': user[6],
                'zip_code': user[7],
                'role': user[8]
            }
        })
    else:
        return jsonify({'success': False, 'message': 'User not found.'}), 404


if __name__ == '__main__':
    app.run(debug=True)


    