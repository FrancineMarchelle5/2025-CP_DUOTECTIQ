import sqlite3

conn = sqlite3.connect('crops.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS crop_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop TEXT,
    color TEXT,
    condition TEXT,
    size TEXT,
    sorted TEXT,
    time TEXT
)
''')

conn.commit()
conn.close()

print("Database initialized!")
