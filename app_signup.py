# app_signup.py
from datetime import datetime
import sqlite3
import time

from flask import Flask, request, jsonify, Response, render_template
from flask_cors import CORS
import bcrypt # hashing lib

from camera import (
    start_capture, stop_capture, detect_crop, mjpeg_generator,
    get_latest_result, mark_sorting_start, set_current_crop
)
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/"
)
CORS(app)

DB_PATH = "duotectdb.sqlite3"

# -------- DB helper --------
def _db():
    return sqlite3.connect(DB_PATH)

# signup route

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json or {}
    required = ['first_name', 'last_name', 'mobile_number', 'password', 'role', 'baranggay']
    
    if not all(data.get(k) for k in required):
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400

    # START OF NEW HASHING LOGIC
    # 1. Encode the plaintext password to bytes (required by bcrypt)
    password_bytes = data['password'].encode('utf-8')
    
    # 2. Generate the salt and hash the password in one step
    hashed_password_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    
    # 3. Decode the hash back to a string to store in SQLite
    hashed_password_str = hashed_password_bytes.decode('utf-8')
    # END OF NEW HASHING LOGIC

    conn = _db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO tbl_users
            (first_name, middle_name, last_name, mobile_number, baranggay, street, city, zip_code, password, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('first_name', ''),
            data.get('middle_name', ''),
            data.get('last_name', ''),
            data.get('mobile_number', ''),
            data.get('baranggay', ''),
            data.get('street', ''),
            data.get('city', ''),
            data.get('zip_code', ''),
            hashed_password_str,  # <--- **THIS IS THE CRUCIAL CHANGE** - The hash is stored here
            data.get('role', '')
        ))
        conn.commit()
        return jsonify({'success': True, 'message': 'User registered successfully. You can now log in.'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Mobile number already exists. Please use a different one.'}), 409
    finally:
        conn.close()

# login route

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    mobile = data.get('mobile_number')
    password = data.get('password')
    
    if not mobile or not password:
        return jsonify({'success': False, 'message': 'Missing mobile number or password.'}), 400

    conn = _db()
    c = conn.cursor()
    
    # 1. Fetch only the HASHED password from the database
    c.execute('SELECT password FROM tbl_users WHERE mobile_number=?', (mobile,))
    user_row = c.fetchone()
    conn.close()

    if not user_row:
        # User not found (return generic error for security)
        return jsonify({'success': False, 'message': 'Invalid mobile number or password.'}), 401

    stored_hash_str = user_row[0]
    
    # START OF VERIFICATION LOGIC
    # Convert plaintext password and stored hash back to bytes (required by bcrypt)
    password_bytes = password.encode('utf-8')
    stored_hash_bytes = stored_hash_str.encode('utf-8')

    # 2. Use checkpw() to safely compare the plaintext password with the stored hash
    # This function hashes the input password with the salt embedded in the stored hash
    if bcrypt.checkpw(password_bytes, stored_hash_bytes):
        return jsonify({'success': True, 'message': 'Login successful.'})
    else:
        # Passwords do not match (return generic error for security)
        return jsonify({'success': False, 'message': 'Invalid mobile number or password.'}), 401
    # END OF VERIFICATION LOGIC

@app.route('/profile', methods=['POST'])
def profile():
    data = request.json or {}
    mobile = data.get('mobile_number')
    if not mobile:
        return jsonify({'success': False, 'message': 'Missing mobile number.'}), 400
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT first_name, middle_name, last_name, mobile_number,
               baranggay, street, city, zip_code, role
        FROM tbl_users WHERE mobile_number=?
    """, (mobile,))
    u = c.fetchone()
    conn.close()
    if not u:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    return jsonify({
        'success': True,
        'profile': {
            'first_name': u[0], 'middle_name': u[1], 'last_name': u[2],
            'mobile_number': u[3], 'baranggay': u[4], 'street': u[5],
            'city': u[6], 'zip_code': u[7], 'role': u[8]
        }
    })

# -------- Sorting & detection --------
@app.route('/set_crop_type', methods=['POST'])
def set_crop_type_route():
    data = request.get_json(silent=True) or {}
    set_current_crop((data.get('crop_type') or '').strip())
    return jsonify({'success': True})

@app.route('/start_sorting', methods=['POST'])
def start_sorting():
    """
    Arms detection, then waits for a *brand-new* detection.
    If none arrives within timeout, returns success=False (no UI update).
    """
    _ = (request.get_json(silent=True) or {}).get('crop_type')
    start_token = mark_sorting_start()

    timeout = 12.0
    poll = 0.20
    end = time.time() + timeout
    detected = None

    while time.time() < end:
        res = detect_crop()  # None until real, stable crop present
        if res and res.get('seq', 0) > start_token:
            detected = res
            break
        time.sleep(poll)

    if not detected:
        return jsonify({'success': False, 'message': 'No crop detected'}), 200

    # Save row (only now)
    conn = _db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tbl_sorting (crop_type, condition, color, sorted_to, size, time_detected)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        detected.get('crop_type', ''),
        detected.get('condition', ''),
        detected.get('color', ''),
        detected.get('sorted_to', ''),
        detected.get('size', ''),
        detected.get('time_detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'result': detected}), 200

@app.route('/get_latest_detection', methods=['GET'])
def get_latest_detection():
    res = detect_crop()
    if res:
        return jsonify({'success': True, 'result': res}), 200
    return jsonify({'success': False, 'message': 'No crop detected'}), 200

@app.route('/get_activity_log', methods=['GET'])
def get_activity_log():
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT time_detected, crop_type, color, condition, sorted_to, size
        FROM tbl_sorting
        ORDER BY time_detected DESC
    """)
    rows = [{
        'time_detected': r[0], 'crop_type': r[1], 'color': r[2],
        'condition': r[3], 'sorted_to': r[4], 'size': r[5]
    } for r in c.fetchall()]
    conn.close()
    return jsonify({'success': True, 'activity_log': rows}), 200

@app.route('/get_latest_sorting', methods=['GET'])
def get_latest_sorting():
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT crop_type, condition, color, sorted_to, size, time_detected
        FROM tbl_sorting ORDER BY id DESC LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({}), 404
    return jsonify({
        'crop_type': row[0], 'condition': row[1], 'color': row[2],
        'sorted_to': row[3], 'size': row[4], 'time_detected': row[5]
    })

@app.route('/system-status', methods=['GET'])
def system_status():
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'message': 'System is running normally'
    }), 200

@app.route('/get_summary_data', methods=['POST'])
def get_summary_data():
    """Get sorting summary data for the dashboard table"""
    data = request.json or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date') 
    sort_type = data.get('sort_type', 'all')
    
    conn = _db()
    c = conn.cursor()
    try:
        # If no date range specified, get only latest date
        if not start_date or not end_date:
            # Get the most recent date with data
            c.execute("""
                SELECT DATE(time_detected) as latest_date
                FROM tbl_sorting 
                WHERE crop_type IS NOT NULL AND crop_type != ''
                ORDER BY time_detected DESC 
                LIMIT 1
            """)
            latest = c.fetchone()
            if latest:
                start_date = end_date = latest[0]
            else:
                return jsonify({'success': False, 'message': 'No data found'})
        
        # Build WHERE clause for date range
        date_filter = "DATE(time_detected) BETWEEN ? AND ?"
        params = [start_date, end_date]
        
        # Get summary data grouped by crop type and condition
        query = f"""
            SELECT 
                crop_type,
                condition,
                color,
                COUNT(*) as count
            FROM tbl_sorting 
            WHERE {date_filter}
            AND crop_type IS NOT NULL 
            AND crop_type != ''
            GROUP BY crop_type, condition, color
            ORDER BY crop_type, condition, color
        """
        
        c.execute(query, params)
        rows = c.fetchall()
        
        # Get total count for the period
        c.execute(f"""
            SELECT COUNT(*) as total
            FROM tbl_sorting 
            WHERE {date_filter}
            AND crop_type IS NOT NULL 
            AND crop_type != ''
        """, params)
        total_crops = c.fetchone()[0]
        
        # Process the data into the format expected by the existing table
        summary_data = {
            'tomato': {'not_damaged': {'red': 0, 'green': 0}, 'damaged': 0},
            'bell_pepper': {'not_damaged': {'red': 0, 'green': 0}, 'damaged': 0},
            'total_crops': total_crops,
            'date_range': f"{start_date} to {end_date}" if start_date != end_date else start_date
        }
        
        # Group data by crop type and condition
        for row in rows:
            crop_type, condition, color, count = row
            
            # Handle different crop type variations
            crop_normalized = crop_type.lower().strip()
            if 'bell' in crop_normalized and 'pepper' in crop_normalized:
                crop_key = 'bell_pepper'
            elif 'tomato' in crop_normalized:
                crop_key = 'tomato'
            else:
                continue  # Skip unknown crop types
            
            if crop_key in summary_data:
                if condition and 'not damaged' in condition.lower():
                    if color and color.lower() in ['red', 'green']:
                        summary_data[crop_key]['not_damaged'][color.lower()] += count
                elif condition and 'damaged' in condition.lower():
                    summary_data[crop_key]['damaged'] += count
        
        return jsonify({'success': True, 'data': summary_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/sorting-summary', methods=['POST'])
def sorting_summary():
    """Original sorting summary endpoint for backward compatibility"""
    data = request.json or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date') 
    sort_type = data.get('sort_type', 'all')
    
    conn = _db()
    c = conn.cursor()
    try:
        # Simple compatibility layer - return basic data structure
        if not start_date or not end_date:
            # Default to today
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            start_date = end_date = today
        
        # Get basic counts
        c.execute("""
            SELECT 
                crop_type,
                condition,
                color,
                COUNT(*) as count
            FROM tbl_sorting 
            WHERE DATE(time_detected) BETWEEN ? AND ?
            AND crop_type IS NOT NULL 
            AND crop_type != ''
            GROUP BY crop_type, condition, color
        """, [start_date, end_date])
        
        rows = c.fetchall()
        
        # Format for original expected structure
        data = {
            'tomato': {'red': 0, 'green': 0, 'damaged': 0},
            'bellpepper': {'red': 0, 'green': 0, 'damaged': 0}
        }
        
        for row in rows:
            crop_type, condition, color, count = row
            crop_key = 'tomato' if 'tomato' in crop_type.lower() else 'bellpepper'
            
            if condition and 'damaged' not in condition.lower() and color:
                data[crop_key][color.lower()] = count
            elif condition and 'damaged' in condition.lower():
                data[crop_key]['damaged'] += count
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# -------- pages --------
@app.route('/')
def root():
    return render_template("HomePage.html")

@app.route('/HomePage.html')
def homepage():
    return render_template("HomePage.html")

@app.route('/sorting.html')
def sorting():
    return render_template("sorting.html")

@app.route('/dashboard.html')
def dashboard():
    return render_template("dashboard.html")

@app.route('/history.html')
def history():
    return render_template("history.html")

# -------- stream & stop --------
@app.route('/video_feed')
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/stop_sorting', methods=['POST'])
def stop_sorting():
    stop_capture()
    return jsonify({'success': True, 'message': 'Sorting stopped.'})

# -------- main --------
if __name__ == '__main__':
    start_capture()
    app.run(host="0.0.0.0", port=8000, threaded=True, debug=True, use_reloader=False)
