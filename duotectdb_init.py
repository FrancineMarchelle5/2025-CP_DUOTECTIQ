import sqlite3

def create_users_table(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tbl_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            last_name TEXT NOT NULL,
            mobile_number TEXT NOT NULL UNIQUE,
            baranggay TEXT,
            street TEXT,
            city TEXT,
            zip_code TEXT,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_users_table("duotectdb.sqlite3")
    print("tbl_users table created (if not exists) in duotectdb.sqlite3.")
