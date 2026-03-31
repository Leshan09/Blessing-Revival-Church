from app import get_db

def add_status_column():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'pending'")
        conn.commit()
        print("✅ Status column added successfully!")
    except Exception as e:
        print("⚠️ Error:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    add_status_column()
