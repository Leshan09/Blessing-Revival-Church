import sqlite3
import os

DB_NAME = r"C:\Users\Administrator\Documents\BRC_website\brc_website.db"

# Verify the file exists
if not os.path.exists(DB_NAME):
    raise FileNotFoundError(f"Database not found at {DB_NAME}")

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Add the reset_code column safely
try:
    cursor.execute("ALTER TABLE members ADD COLUMN reset_code TEXT")
    print("reset_code column added successfully!")
except sqlite3.OperationalError as e:
    print("Error:", e)

conn.commit()
conn.close()