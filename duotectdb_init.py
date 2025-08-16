import sqlite3

def create_tables(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create tbl_users
    c.execute('''
        CREATE TABLE IF NOT EXISTS tbl_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            last_name TEXT NOT NULL,
            mobile_number TEXT NOT NULL UNIQUE,
            barangay TEXT,
            street TEXT,
            city TEXT,
            zip_code TEXT,
            password TEXT NOT NULL
        )
    ''')

    # Create tbl_sorting
    c.execute('''
        CREATE TABLE IF NOT EXISTS tbl_sorting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_type TEXT,
            condition TEXT,
            color TEXT,
            sorted_to TEXT,
            size TEXT,
            time_detected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create tbl_activity_log
    c.execute('''
        CREATE TABLE IF NOT EXISTS tbl_actlog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_type TEXT,
            condition TEXT,
            color TEXT,
            sorted_to TEXT,
            size TEXT,
            time_detected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_tables("duotectdb.sqlite3")
    print("Tables created successfylly in duotectdb.sqlite3.")
