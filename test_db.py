import sqlite3
import os

# # Path to your database
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB_NAME = os.path.join(BASE_DIR, "brc_website.db")

# conn = sqlite3.connect(DB_NAME)
# cursor = conn.cursor()

# # 1) List all tables
# cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
# tables = cursor.fetchall()
# print("Tables in database:", tables)

# # 2) Check columns of the 'members' table (if it exists)
# if ('members',) in tables:
#     cursor.execute("PRAGMA table_info(members);")
#     columns = cursor.fetchall()
#     print("\nColumns in 'members' table:")
#     for col in columns:
#         print(col)
# else:
#     print("\nNo table named 'members' found!")

# # 3) Optional: list all rows in 'members' table
# try:
#     cursor.execute("SELECT * FROM members;")
#     rows = cursor.fetchall()
#     print("\nRows in 'members' table:")
#     for row in rows:
#         print(row)
# except sqlite3.OperationalError:
#     print("\n'members' table does not exist or is empty.")

# conn.close()

# # List all tables in the database
# conn = sqlite3.connect("brc_website.db")
# cursor = conn.cursor()
# cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
# print(cursor.fetchall())
# conn.close()
# List all tables in the database
conn = sqlite3.connect("brc_website.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cursor.fetchall())
conn.close()