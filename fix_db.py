import sqlite3

conn = sqlite3.connect("brc_website.db")
cursor = conn.cursor()

cursor.execute("ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'admin'")

conn.commit()
conn.close()

print("Database updated successfully")