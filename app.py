from flask import Flask, render_template, request, jsonify, redirect, session
from flask_cors import CORS
import sqlite3
import hashlib
import json
import os
import random
import csv
import io
from io import StringIO
from flask import render_template, request, redirect, send_file, make_response
import string
from dotenv import load_dotenv

load_dotenv()

# reportlab may require optional cairo support in some environments.
# If reportlab cannot be installed, we still allow the app startup and disable PDF download.
try:
    from reportlab.pdfgen import canvas
except ImportError:
    canvas = None
# --------------------------
# Configuration
# --------------------------

EVENT_FILE = "events.json"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "brc_website.db")
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv("SECRET_KEY", "dev_fallback_key_not_secure")

# --------------------------
# Helper Functions
# --------------------------
# --------------------------
# Helper Functions
# --------------------------
class AdaptiveCursor:
    def __init__(self, cursor, paramstyle):
        self._cursor = cursor
        self.paramstyle = paramstyle

    def execute(self, query, params=None):
        if self.paramstyle == "pyformat":
            query = query.replace("?", "%s")
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

    def executemany(self, query, seq_of_params):
        if self.paramstyle == "pyformat":
            query = query.replace("?", "%s")
        return self._cursor.executemany(query, seq_of_params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def get_db():
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

        def cursor_wrapper(*args, **kwargs):
            return AdaptiveCursor(conn.cursor(*args, **kwargs), "pyformat")

        conn.cursor = cursor_wrapper
        return conn

    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# --------------------------
# DATABASE INITIALIZATION
# --------------------------
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    def execute(sql, params=None):
        if USE_POSTGRES:
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            sql = sql.replace("TEXT DEFAULT CURRENT_TIMESTAMP", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
            sql = sql.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP")
        if params is None:
            return cursor.execute(sql)
        return cursor.execute(sql, params)

    execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        reset_code TEXT
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        message TEXT NOT NULL,
        date_sent TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_reset (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        code TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        event_date TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_name TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT CHECK(type IN ('donation','expense')) NOT NULL,
    description TEXT,
    date TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        reset_code TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS join_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        message TEXT,
        status TEXT DEFAULT 'pending',
        date_requested TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)



    # CHECK ADMIN
    execute(
        "SELECT * FROM admins WHERE username = ?",
        ("pastor",)
    )
    admin = cursor.fetchone()

    if admin is None:
        execute(
            "INSERT INTO admins (username, password, role) VALUES (?, ?, ?)",
            ("pastor", hash_password("pastor123"), "pastor")
        )

    conn.commit()
    conn.close()
# --------------------------
# Page Routes
# --------------------------

def ensure_db_initialized():
    init_db()

# init DB for all servers (Gunicorn, development, etc.)
try:
    ensure_db_initialized()
except Exception:
    pass


@app.route("/")
def page_home():
    return render_template("main.html")

@app.route("/about")
def page_about():
    return render_template("about.html")

@app.route("/services")
def page_services():
    return render_template("services.html")

# @app.route("/finance")
# def page_finance():
#     conn = get_db()
#     cursor = conn.cursor()

#     # Recent transactions
#     cursor.execute("SELECT donor_name, amount, type, description, date FROM donations ORDER BY date DESC LIMIT 5")
#     transactions = [dict(row) for row in cursor.fetchall()]

#     # Monthly donations summary
#     cursor.execute("""
#         SELECT strftime('%m', date) as month, SUM(amount) as total
#         FROM donations WHERE type='donation'
#         GROUP BY month
#     """)
#     monthly_donations = cursor.fetchall()
#     donation_labels = [row["month"] for row in monthly_donations]
#     donation_values = [row["total"] for row in monthly_donations]

#     # Expense breakdown
#     cursor.execute("""
#         SELECT description, SUM(amount) as total
#         FROM donations WHERE type='expense'
#         GROUP BY description
#     """)
#     expenses = cursor.fetchall()
#     expense_labels = [row["description"] for row in expenses]
#     expense_values = [row["total"] for row in expenses]

#     conn.close()

#     return render_template("finance.html",
#                            transactions=transactions,
#                            donation_labels=donation_labels,
#                            donation_values=donation_values,
#                            expense_labels=expense_labels,
#                            expense_values=expense_values)


@app.route("/finance")
def page_finance():
    conn = get_db()
    cursor = conn.cursor()

    # Recent transactions
    cursor.execute("""
        SELECT donor_name, amount, type, description, date 
        FROM donations 
        ORDER BY date DESC 
        LIMIT 5
    """)
    transactions = [dict(row) for row in cursor.fetchall()]

    # ✅ TOTAL DONATIONS (same as elder page)
    cursor.execute("SELECT SUM(amount) as total FROM donations WHERE type='donation'")
    total_donations = cursor.fetchone()["total"] or 0

    # Monthly donations summary
    cursor.execute("""
        SELECT strftime('%m', date) as month, SUM(amount) as total
        FROM donations 
        WHERE type='donation'
        GROUP BY month
    """)
    monthly_donations = cursor.fetchall()
    donation_labels = [row["month"] for row in monthly_donations]
    donation_values = [row["total"] for row in monthly_donations]

    # Expense breakdown
    cursor.execute("""
        SELECT description, SUM(amount) as total
        FROM donations 
        WHERE type='expense'
        GROUP BY description
    """)
    expenses = cursor.fetchall()
    expense_labels = [row["description"] for row in expenses]
    expense_values = [row["total"] for row in expenses]

    conn.close()

    return render_template("finance.html",
                           transactions=transactions,
                           donation_labels=donation_labels,
                           donation_values=donation_values,
                           expense_labels=expense_labels,
                           expense_values=expense_values,
                           total_donations=total_donations)


@app.route("/communication")
def page_communication():
    return render_template("communication.html")

@app.route("/contact")
def page_contact():
    return render_template("contact.html")

@app.route("/visitor")
def page_visitor():
    return render_template("visitor.html")

@app.route("/member/login")
def page_member_login():
    return render_template("login.html")

@app.route("/member/signup", methods=["GET", "POST"])
def page_member_signup():
    email = request.args.get("email")

    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM join_requests WHERE email=?", (email,))
        record = cursor.fetchone()

        if not record or record["status"] != "approved":
            conn.close()
            return "You must be approved by an elder before signing up.", 403

        cursor.execute(
            "INSERT INTO members (fullname, email, password, status) VALUES (?, ?, ?, ?)",
            (fullname, email, hash_password(password), "approved")
        )
        conn.commit()
        conn.close()
        return redirect("/member/login")

    return render_template("signup.html", email=email)


@app.route("/join")
def page_join():
    email = request.args.get("email")  # passed from approval link
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM join_requests WHERE email=?", (email,))
    record = cursor.fetchone()
    conn.close()

    if not record or record["status"] != "approved":
        return "You must be approved by an elder before signing up.", 403

    return render_template("join.html", email=email)

# --------------------------
# ✅ JSON Signup API
# --------------------------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.get_json() or {}
    fullname = data.get("fullname")
    email = data.get("email")
    password = data.get("password")

    if not fullname or not email or not password:
        return jsonify({"status": "fail", "message": "All fields are required."}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
        "INSERT INTO members (fullname, email, password, status) VALUES (?, ?, ?, ?)",
        (fullname, email, hash_password(password), "pending")
        )

        conn.commit()
        return jsonify({"status": "success", "message": "Account created successfully!"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "fail", "message": "Email already exists."}), 409
    finally:
        conn.close()



@app.route("/member/dashboard")
def page_member_dashboard():
    if not session.get("admin_logged_in") and not session.get("member_logged_in"):
        return redirect("/member/login")

    conn = get_db()
    cursor = conn.cursor()

    # Member count
    cursor.execute("SELECT COUNT(*) as total FROM members")
    total_members = cursor.fetchone()["total"]

    # Upcoming events (only approved)
    cursor.execute("SELECT title, event_date, description FROM events WHERE status='approved' ORDER BY event_date ASC")
    events = cursor.fetchall()

    # Announcements/messages
    cursor.execute("SELECT name, message, date_sent FROM messages ORDER BY date_sent DESC LIMIT 5")
    messages = cursor.fetchall()

    conn.close()

    return render_template("index.html",
                           total_members=total_members,
                           events=events,
                           messages=messages)



@app.route("/member")
def member_root():
    return redirect("/member/dashboard")

@app.route("/member")
def member():
    events = load_events()
    return render_template("member.html", events=events)

# --------------------------
# ADMIN
# --------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        data = request.form
        username = data.get("username")
        password = data.get("password")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = ?", (username,))
        admin = cursor.fetchone()
        conn.close()

        if admin and admin["password"] == hash_password(password):
            session["admin_logged_in"] = True
            session["admin_role"] = admin["role"]

            # Redirect based on role
            if admin["role"] == "pastor":
                return redirect("/admin/pastor")
            elif admin["role"] == "elder":
                return redirect("/admin/elder")
            elif admin["role"] == "youth":
                return redirect("/admin/youth")
            else:
                return redirect("/admin")

        return "Invalid credentials", 401

    return render_template("admin_login.html")

@app.route("/admin/pastor")
def admin_pastor_dashboard():
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")
    return render_template("admin_dashboard_pastor.html")

@app.route("/admin/elder")
def admin_elder_dashboard():
    if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
        return redirect("/admin/login")
    return render_template("admin_dashboard_elder.html")

@app.route("/admin/youth")
def admin_youth_dashboard():
    if not session.get("admin_logged_in") or session.get("admin_role") != "youth":
        return redirect("/admin/login")
    return render_template("admin_dashboard_youth.html")

# --------------------------
# ADMIN FEATURE ROUTES
# --------------------------

@app.route("/admin/manage-members")
def admin_manage_members():
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fullname, email FROM members ORDER BY id ASC")
    members = cursor.fetchall()
    conn.close()

    return render_template("admin_manage_members.html", members=members)


@app.route("/admin/member/add", methods=["GET", "POST"])
def add_member():
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")

    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO members (fullname, email, password) VALUES (?, ?, ?)",
                       (fullname, email, hash_password("default123")))
        conn.commit()
        conn.close()

    return render_template("add_member.html")


@app.route("/member/events")
def member_events():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, event_date, description FROM events WHERE status='approved' ORDER BY event_date ASC")
    events = cursor.fetchall()
    conn.close()
    return render_template("member_events.html", events=events)



@app.route("/admin/youth-events")
def admin_youth_events():
    if not session.get("admin_logged_in") or session.get("admin_role") != "youth":
        return redirect("/admin/login")
    return render_template("admin_youth_events.html")
@app.route("/admin/finance/add", methods=["GET", "POST"])
def add_transaction():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    if request.method == "POST":
        donor_name = request.form.get("donor_name")
        amount = float(request.form.get("amount"))
        type = request.form.get("type")  # 'donation' or 'expense'
        description = request.form.get("description")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO donations (donor_name, amount, type, description) VALUES (?, ?, ?, ?)",
                       (donor_name, amount, type, description))
        conn.commit()
        conn.close()

        return redirect("/admin/finance")

    return render_template("add_transaction.html")


@app.route("/admin/youth-messages")
def admin_youth_messages():
    if not session.get("admin_logged_in") or session.get("admin_role") != "youth":
        return redirect("/admin/login")
    return render_template("admin_youth_messages.html")


# @app.route("/admin/youth-activities")
# def admin_youth_activities():
#     if not session.get("admin_logged_in") or session.get("admin_role") != "youth":
#         return redirect("/admin/login")

#     conn = get_db()
#     cursor = conn.cursor()
#     cursor.execute("SELECT title, event_date, description FROM events WHERE created_by='youth' ORDER BY event_date DESC")
#     events = cursor.fetchall()
#     cursor.execute("SELECT name, message, date_sent FROM messages WHERE email LIKE '%youth%' ORDER BY date_sent DESC")
#     messages = cursor.fetchall()
#     conn.close()

#     return render_template("admin_youth_activities.html", events=events, messages=messages)


# --------------------------
# ADMIN FEATURE ROUTES
# --------------------------
def admin_manage_members():
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")
    return render_template("admin_manage_members.html")

@app.route("/admin/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        cursor.execute("UPDATE members SET fullname=?, email=? WHERE id=?", (fullname, email, member_id))
        conn.commit()
        conn.close()

    cursor.execute("SELECT * FROM members WHERE id=?", (member_id,))
    member = cursor.fetchone()
    conn.close()
    return render_template("edit_member.html", member=member)


@app.route("/admin/member/delete/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()

@app.route("/admin/event/approve/<int:event_id>", methods=["POST"])
def approve_event(event_id):
    if not session.get("admin_logged_in") or session.get("admin_role") not in ["pastor","elder"]:
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status='approved' WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


@app.route("/admin/event/reject/<int:event_id>", methods=["POST"])
def reject_event(event_id):
    if not session.get("admin_logged_in") or session.get("admin_role") not in ["pastor","elder"]:
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status='rejected' WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


@app.route("/admin/event/delete/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    if not session.get("admin_logged_in") or session.get("admin_role") not in ["pastor","elder"]:
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()

@app.route("/api/messages", methods=["POST"])
def api_messages():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    data = request.form
    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (name, email, message, date_sent) VALUES (?, ?, ?, DATE('now'))",
                   (name, email, message))
    conn.commit()
    conn.close()

    return redirect(request.referrer or "/admin/messages")


@app.route("/admin/messages")
def admin_messages():
    if not session.get("admin_logged_in") or session.get("admin_role") == "pastor":
        return render_template("admin_messages.html")
    return redirect("/admin/login")

# --------------------------
# ADMIN FEATURE ROUTES
# --------------------------


# @app.route("/admin/manage-members")
# def admin_manage_members():
#     if not session.get("admin_logged_in") or session.get("admin_role") != "pastor":
#         return redirect("/admin/login")
    
#     conn = get_db()
#     cursor = conn.cursor()
#     cursor.execute("SELECT id, fullname, email FROM members ORDER BY id ASC")
#     members = cursor.fetchall()
#     conn.close()

#     return render_template("admin_manage_members.html", members=members)


@app.route("/admin/finance")
def admin_finance():
    if not session.get("admin_logged_in") or session.get("admin_role") not in ["pastor","elder"]:
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT date_sent, name, message FROM messages ORDER BY date_sent DESC")
    donations = cursor.fetchall()
    conn.close()

    return render_template("admin_finance.html", donations=donations)

@app.route("/admin/youth-activities")
def admin_youth_activities():
    if not session.get("admin_logged_in") or session.get("admin_role") != "youth":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    # Pull youth events
    cursor.execute("SELECT title, event_date, description FROM events WHERE category='youth' ORDER BY event_date DESC")
    events = cursor.fetchall()
    # Pull youth messages
    cursor.execute("SELECT name, message, date_sent FROM messages WHERE email LIKE '%youth%' ORDER BY date_sent DESC")
    messages = cursor.fetchall()
    conn.close()

    return render_template("admin_youth_activities.html", events=events, messages=messages)


@app.route("/admin")
def page_admin_portal():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    return render_template("admin_dashboard.html")

@app.route("/admin/add_event", methods=["POST"])
def add_event():
    title = request.form.get("title")
    date = request.form.get("date")
    description = request.form.get("description")

    events = load_events()

    new_event = {
        "title": title,
        "date": date,
        "description": description
    }

    events.append(new_event)
    save_events(events)

    return "Event added successfully!"

# @app.route("/admin/add-event", methods=["POST"])
# def add_event():
#     if not session.get("admin_logged_in"):
#         return jsonify({"status": "fail", "message": "Unauthorized"}), 403

#     data = request.get_json() or request.form

#     title = data.get("title")
#     description = data.get("description")
#     event_date = data.get("event_date")

#     if not title or not event_date:
#         return jsonify({"status": "fail", "message": "Title and date required"}), 400

#     conn = get_db()
#     cursor = conn.cursor()

#     cursor.execute("""
#         INSERT INTO events (title, description, event_date, created_by)
#         VALUES (?, ?, ?, ?)
#     """, (title, description, event_date, "admin"))

#     conn.commit()
#     conn.close()

#     return jsonify({"status": "success", "message": "Event added"})

@app.route("/api/events", methods=["GET"])
def get_events():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events ORDER BY event_date ASC")
    rows = cursor.fetchall()

    conn.close()

    return jsonify([
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "event_date": r["event_date"]
        }
        for r in rows
    ])

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/")

# --------------------------
# MESSAGES API
# --------------------------
@app.route("/api/messages", methods=["POST"])
def save_message():
    data = request.get_json() or {}

    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    if not name or not message:
        return jsonify({
            "status": "fail",
            "message": "Name and message are required."
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages (name, email, message)
        VALUES (?, ?, ?)
    """, (name, email, message))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "Message saved successfully!"
    })

@app.route("/api/messages", methods=["GET"])
def get_messages():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM messages ORDER BY id DESC")
    rows = cursor.fetchall()

    conn.close()

    return jsonify([
        {
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "message": r["message"],
            "date_sent": r["date_sent"]
        }
        for r in rows
    ])

# --------------------------
# PASSWORD RESET
# --------------------------
@app.route("/request-reset", methods=["POST"])
def request_reset():
    data = request.get_json() or {}
    email = data.get("email")

    if not email:
        return jsonify({"status": "fail", "message": "Email is required."}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE email=?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"status": "fail", "message": "No account found with that email."}), 404

    code = str(random.randint(100000, 999999))

    cursor.execute("""
        INSERT OR REPLACE INTO password_reset (email, code, created_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (email, code))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"Reset code generated: {code}"})


@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")

    if not email or not code or not new_password:
        return jsonify({"status": "fail", "message": "Missing fields."}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT code FROM password_reset WHERE email=?", (email,))
    record = cursor.fetchone()

    if not record:
        conn.close()
        return jsonify({"status": "fail", "message": "No reset request found."}), 404

    if record["code"] != code:
        conn.close()
        return jsonify({"status": "fail", "message": "Invalid code."}), 401

    cursor.execute(
        "UPDATE members SET password=? WHERE email=?",
        (hash_password(new_password), email)
    )

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "Password reset successful!"})

# --------------------------
# LOGIN API
# --------------------------
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM members WHERE email=?", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({"status": "fail", "message": "Email not found."}), 404

    if user["password"] != hash_password(password):
        return jsonify({"status": "fail", "message": "Incorrect password."}), 401

    return jsonify({"status": "success", "user_id": user["id"]})

# --------------------------
# STATIC APIs
# --------------------------
@app.route("/api/stats")
def get_stats():
    return {"members": 150, "events": 25, "donations": 15000, "ministries": 5}

@app.route("/api/user")
def get_user():
    return {"logged_in": True, "name": "Admin"}

about_data = {
    "name": "Blessing Revival Centric",
    "mission": "",
    "vision": "",
    "description": ""
}

@app.route("/api/about")
def get_about():
    return about_data

def load_events():
    if not os.path.exists(EVENT_FILE):
        return []
    with open(EVENT_FILE, "r") as f:
        return json.load(f)
    
def save_events(events):
    with open(EVENT_FILE, "w") as f:
        json.dump(events, f, indent=4)

# --------------------------
# STARTUP
# --------------------------
@app.route("/admin/elder/approve/<int:member_id>", methods=["POST"])
def elder_approve_member(member_id):
    if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET status='approved' WHERE id=?", (member_id,))
    conn.commit()
    conn.close()

    return redirect("/admin/elder/pending")

@app.route("/api/join-request", methods=["POST"])
def api_join_request():
    fullname = request.form.get("fullname")
    email = request.form.get("email")
    message = request.form.get("message")

    if not fullname or not email:
        return "All fields required", 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO join_requests (fullname, email, message) VALUES (?, ?, ?)",
            (fullname, email, message)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return "Email already requested", 409
    finally:
        conn.close()

    return "Request submitted! Await elder approval."

@app.route("/admin/elder/approve-request/<int:req_id>", methods=["POST"])
def approve_request(req_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE join_requests SET status='approved' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    return redirect("/admin/elder/requests")

@app.route("/admin/elder/reject-request/<int:req_id>", methods=["POST"])
def reject_request(req_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE join_requests SET status='rejected' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    return redirect("/admin/elder/requests")


@app.route("/admin/elder/requests")
def elder_requests():
    if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM join_requests WHERE status='pending'")
    requests = cursor.fetchall()
    conn.close()

    return render_template("elder_requests.html", requests=requests)


@app.route("/admin/elder/contributions", methods=["GET", "POST"])
def elder_contributions():
    if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        donor_name = request.form.get("donor_name")
        amount = float(request.form.get("amount"))
        description = request.form.get("description")

        cursor.execute(
            "INSERT INTO donations (donor_name, amount, type, description) VALUES (?, ?, 'donation', ?)",
            (donor_name, amount, description)
        )
        conn.commit()

    cursor.execute("SELECT donor_name, amount, description, date FROM donations WHERE type='donation' ORDER BY date DESC")
    contributions = cursor.fetchall()

    cursor.execute("SELECT SUM(amount) as total FROM donations WHERE type='donation'")
    total = cursor.fetchone()["total"]

    conn.close()

    return render_template("elder_contributions.html", contributions=contributions, total=total)


# @app.route("/admin/elder/contribution", methods=["GET", "POST"])
# def elder_contribution():
#     if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
#         return redirect("/admin/login")

#     if request.method == "POST":
#         donor_name = request.form.get("donor_name")
#         amount = float(request.form.get("amount"))
#         description = request.form.get("description")

#         conn = get_db()
#         cursor = conn.cursor()
#         cursor.execute(
#             "INSERT INTO donations (donor_name, amount, type, description) VALUES (?, ?, 'donation', ?)",
#             (donor_name, amount, description)
#         )
#         conn.commit()
#         conn.close()

#         return redirect("/finance")  # redirect to totals page

#     return render_template("elder_contribution.html")


@app.route("/admin/elder/reject/<int:member_id>", methods=["POST"])
def elder_reject_member(member_id):
    if not session.get("admin_logged_in") or session.get("admin_role") != "elder":
        return redirect("/admin/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET status='rejected' WHERE id=?", (member_id,))
    conn.commit()
    conn.close()

    return redirect("/admin/elder/pending")

@app.route("/finance/download/csv")
def download_csv():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT donor_name, amount, type, description, date
        FROM donations
        ORDER BY date DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Donor Name", "Amount", "Type", "Description", "Date"])

    for row in rows:
        writer.writerow([
            row["donor_name"],
            row["amount"],
            row["type"],
            row["description"],
            row["date"]
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=finance_report.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@app.route("/finance/download/pdf")
def download_pdf():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT donor_name, amount, type, description, date
        FROM donations
        ORDER BY date DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if canvas is None:
        return "PDF generation is unavailable; some dependencies are missing on this platform.", 503

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)

    y = 800
    p.setFont("Helvetica-Bold", 14)
    p.drawString(180, y, "Church Finance Report")

    y -= 40
    p.setFont("Helvetica", 10)

    for row in rows:
        text = f"{row['date']} | {row['type']} | KES {row['amount']} | {row['description']}"
        p.drawString(30, y, text)
        y -= 20

        if y < 50:
            p.showPage()
            y = 800

    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="finance_report.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)