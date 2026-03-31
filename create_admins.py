from app import get_db, hash_password

conn = get_db()
cursor = conn.cursor()

cursor.execute("INSERT INTO admins (username, password, role) VALUES (?, ?, ?)",
               ("elder", hash_password("elder123"), "elder"))
cursor.execute("INSERT INTO admins (username, password, role) VALUES (?, ?, ?)",
               ("youth", hash_password("youth123"), "youth"))

conn.commit()
conn.close()

print("Elder and Youth accounts created!")
