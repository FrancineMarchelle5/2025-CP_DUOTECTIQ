from flask import Flask, jsonify
from datetime import datetime
import sqlite3

app = Flask(__name__)

def save_to_db(crop, color, condition, size, sorted_bin, time):
    conn = sqlite3.connect('crops.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO crop_results (crop, color, condition, size, sorted, time)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (crop, color, condition, size, sorted_bin, time))
    conn.commit()
    conn.close()

@app.route('/api/crop_results')
def crop_results():
    # Simulated detection
    crop_data = {
        "crop": "Tomato",
        "color": "Green",
        "condition": "Not Damaged",
        "size": "M",
        "sorted": "Left Bin",
        "time": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    }

    # Save to DB
    save_to_db(**crop_data)

    # Return ALL data
    conn = sqlite3.connect('crops.db')
    cursor = conn.cursor()
    cursor.execute("SELECT crop, color, condition, size, sorted, time FROM crop_results ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    # Format for JSON
    results = [
        {
            "crop": r[0],
            "color": r[1],
            "condition": r[2],
            "size": r[3],
            "sorted": r[4],
            "time": r[5]
        }
        for r in rows
    ]

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
