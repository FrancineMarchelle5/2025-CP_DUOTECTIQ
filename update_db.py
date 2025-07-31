import sqlite3

conn = sqlite3.connect('duotectdb.sqlite3')
c = conn.cursor()
c.execute('ALTER TABLE tbl_users ADD COLUMN role TEXT;')
conn.commit()
conn.close()
print("Role column added.")