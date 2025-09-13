# app_signup.py
from datetime import datetime
import sqlite3
import time

from flask import Flask, request, jsonify, Response, render_template
from flask_cors import CORS

# Camera helpers
from camera import (
    start_capture, stop_capture, detect_crop, mjpeg_generator,
    get_latest_result, mark_sorting_start
)

# --------------------------------------------------
# Flask app
# --------------------------------------------------
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/"  # serve /static/* from root paths
)
CORS(app)

# --------------------------------------------------
# DB helpers
# --------------------------------------------------
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

# --------------------------------------------------
# API: Auth & Profile
# --------------------------------------------------
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json or {}
    required = ['first_name', 'last_name', 'mobile_number', 'password', 'role', 'baranggay']
    if not all(data.get(k) for k in required):
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400
    ok, msg = insert_user(data)
    return jsonify({'success': ok, 'message': msg})

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
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
    data = request.json or {}
    mobile = data.get('mobile_number')
    if not mobile:
        return jsonify({'success': False, 'message': 'Missing mobile number.'}), 400

    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('''SELECT first_name, middle_name, last_name, mobile_number,
                        baranggay, street, city, zip_code, role
                 FROM tbl_users WHERE mobile_number=?''', (mobile,))
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

# --------------------------------------------------
# API: Sorting / Detection
# --------------------------------------------------
@app.route('/save_sorting', methods=['POST'])
def save_sorting():
    data = request.json or {}
    crop_type = data.get('crop_type', '').strip()
    color = data.get('color', '').strip()
    # Only save if crop_type and color are present and valid
    if not crop_type or crop_type.lower() == 'unknown' or not color:
        return jsonify({'success': False, 'message': 'Invalid detection. Not saved.'}), 400
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('''
        INSERT INTO tbl_sorting (crop_type, condition, color, sorted_to, size, time_detected)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        crop_type,
        data.get('condition', ''),
        color,
        data.get('sorted_to', ''),
        data.get('size', ''),
        data.get('time_detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Sorting result saved.'})

@app.route('/get_latest_sorting', methods=['GET'])
def get_latest_sorting():
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('''
        SELECT crop_type, condition, color, sorted_to, size, time_detected
        FROM tbl_sorting ORDER BY id DESC LIMIT 1
    ''')
    row = c.fetchone()
    conn.close()

    if row:
        result = {
            'crop_type': row[0],
            'condition': row[1],
            'color': row[2],
            'sorted_to': row[3],
            'size': row[4],
            'time_detected': row[5]
        }
        return jsonify(result)
    else:
        return jsonify({}), 404

@app.route('/system-status', methods=['GET'])
def system_status():
    try:
        return jsonify({
            'status': 'online',
            'timestamp': datetime.now().isoformat(),
            'message': 'System is running normally'
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_result', methods=['GET'])
def get_result():
    """
    Return the latest classification result. If not present, return success=False.
    (Suppressed during 'armed' window inside camera.get_latest_result.)
    """
    result = get_latest_result()
    if result and result.get("present"):
        out = {
            'crop_type':     result.get('crop_type', ''),
            'condition':     result.get('condition', ''),
            'color':         result.get('color', ''),
            'sorted_to':     result.get('sorted_to', ''),
            'size':          result.get('size', ''),
            'time_detected': result.get('time_detected', ''),
            'present':       True,
            'confidence':    float(result.get('confidence', 0.0)),
            'seq':           int(result.get('seq', 0)),
        }
        return jsonify({'success': True, 'result': out}), 200
    else:
        return jsonify({'success': False, 'message': 'No result yet'}), 200

last_saved_seq = None  # You can use a global variable or query the DB for the last seq

@app.route('/start_sorting', methods=['POST'])
def start_sorting():
    """
    Arm detection and wait (short timeout) for a *new* detection that occurs
    after this call. Save it to DB and return it. If no crop appears, return success=False.
    """
    _ = (request.get_json(silent=True) or {}).get('crop_type')

    # 1) Arm: clear any cached detection and record the current seq token
    start_token = mark_sorting_start()

    # 2) Wait for a brand-new detection (seq > start_token)
    timeout = 12.0
    poll_interval = 0.20
    end_time = time.time() + timeout

    # Query DB for last saved seq
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('SELECT seq FROM tbl_sorting ORDER BY time_detected DESC LIMIT 1')
    row = c.fetchone()
    last_saved_seq = row[0] if row else None
    conn.close()

    detected = None
    while time.time() < end_time:
        res = detect_crop()
        seq_val = res.get("seq", 0) if res else 0
        # Only accept if seq is new and greater than both start_token and last_saved_seq
        if res and seq_val > start_token and (last_saved_seq is None or seq_val > last_saved_seq):
            detected = res
            last_saved_seq = seq_val
            break
        time.sleep(poll_interval)

    if not detected:
        return jsonify({'success': False, 'message': 'No crop detected'}), 200

    # 3) Save to DB only if crop is present
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()

    # Before saving to DB, check if seq is already present
    c.execute('SELECT COUNT(*) FROM tbl_sorting WHERE seq=?', (detected.get('seq', 0),))
    if c.fetchone()[0] == 0:
        # Save only if seq is not already in DB
        c.execute('''
            INSERT INTO tbl_sorting (crop_type, condition, color, sorted_to, size, time_detected, seq)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            detected.get('crop_type', ''),
            detected.get('condition', ''),
            detected.get('color', ''),
            detected.get('sorted_to', ''),
            detected.get('size', ''),
            detected.get('time_detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            detected.get('seq', 0)
        ))
        conn.commit()
    conn.close()

    return jsonify({'success': True, 'result': detected}), 200

@app.route('/get_activity_log', methods=['GET'])
def get_activity_log():
    conn = sqlite3.connect('duotectdb.sqlite3')
    c = conn.cursor()
    c.execute('''
        SELECT time_detected, crop_type, color, condition, sorted_to, size
        FROM tbl_sorting
        ORDER BY time_detected DESC
    ''')
    rows = c.fetchall()
    conn.close()
    result = [
        {
            'time_detected': row[0],
            'crop_type': row[1],
            'color': row[2],
            'condition': row[3],
            'sorted_to': row[4],
            'size': row[5]
        }
        for row in rows
    ]
    return jsonify({'success': True, 'activity_log': result})

# --------------------------------------------------
# Web pages
# --------------------------------------------------
@app.route('/')
def root():
    return render_template("HomePage.html")

@app.route('/HomePage.html')
def homepage():
    return render_template("HomePage.html")

@app.route('/sorting.html')
def sorting():
    # NOTE: the old start_capture() here was unreachable after return.
    # Camera thread is started in __main__ below.
    return render_template("sorting.html")

@app.route('/dashboard.html')
def dashboard():
    return render_template("dashboard.html")

@app.route('/history.html')
def history():
    return render_template("history.html")

# --------------------------------------------------
# Camera stream
# --------------------------------------------------
@app.route('/video_feed')
def video_feed():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route('/stop_sorting', methods=['POST'])
def stop_sorting():
    stop_capture()
    return jsonify({'success': True, 'message': 'Sorting stopped.'})

@app.route('/get_latest_detection', methods=['GET'])
def get_latest_detection():
    result = get_latest_result()
    # Suppress result if seq <= _armed_token (cached or old)
    from camera import _armed_token
    seq_val = result.get("seq", 0) if result else 0
    if result and result.get("present") and seq_val > _armed_token:
        return jsonify({'success': True, 'result': result}), 200
    else:
        return jsonify({'success': False, 'message': 'No crop detected'}), 200

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == '__main__':
    start_capture()  # start camera thread for streaming + background inference
    app.run(host="0.0.0.0", port=8000, threaded=True, debug=True, use_reloader=False)
