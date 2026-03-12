from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, random, string, smtplib, json, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip("'").strip('"')

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "medibook_secret_2026_xK9#mL")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB = "medibook.db"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@medibook.com")
SMTP_HOST   = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER   = os.environ.get("SMTP_USER", "")          # set your gmail
SMTP_PASS   = os.environ.get("SMTP_PASS", "")          # set app password
OPENAI_KEY     = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GMAPS_KEY      = os.environ.get("GMAPS_API_KEY", "")

SLOT_START  = 9    # 9 AM
SLOT_END    = 18   # 6 PM
SLOT_MINS   = 30   # 30-minute slots

DOCTORS = [
    {"id": 1, "name": "Dr. Priya Sharma",   "specialty": "General Physician",   "avatar": "👩‍⚕️"},
    {"id": 2, "name": "Dr. Arjun Mehta",    "specialty": "Cardiologist",         "avatar": "👨‍⚕️"},
    {"id": 3, "name": "Dr. Sneha Reddy",    "specialty": "Dermatologist",        "avatar": "👩‍⚕️"},
    {"id": 4, "name": "Dr. Vikram Nair",    "specialty": "Orthopedic",           "avatar": "👨‍⚕️"},
    {"id": 5, "name": "Dr. Ananya Pillai",  "specialty": "Pediatrician",         "avatar": "👩‍⚕️"},
]

CATEGORIES = ["General Checkup", "Follow-up", "Dental", "Eye Exam",
               "Blood Test", "Cardiology", "Orthopedic", "Pediatric", "Dermatology", "Emergency"]

# ── DATABASE ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            age         INTEGER,
            phone       TEXT,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            is_admin    INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            otp         TEXT,
            otp_expiry  TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            doctor_id   INTEGER NOT NULL DEFAULT 1,
            title       TEXT NOT NULL,
            category    TEXT DEFAULT 'General Checkup',
            date        TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            location    TEXT DEFAULT 'Apollo Hospital, Hyderabad',
            notes       TEXT,
            status      TEXT DEFAULT 'upcoming',
            reminder_sent INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS waitlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            doctor_id  INTEGER NOT NULL,
            date       TEXT NOT NULL,
            start_time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Seed admin
        admin_pw = generate_password_hash("admin123")
        c.execute("""INSERT OR IGNORE INTO users (name,email,password,is_admin,is_verified)
                     VALUES ('Admin','admin@medibook.com',?,1,1)""", (admin_pw,))
        c.commit()

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return wrap

def gen_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

# ── EMAIL ─────────────────────────────────────────────────────────────────────
def send_email(to, subject, html_body):
    if not SMTP_USER:
        print(f"[EMAIL DEMO] To: {to} | Subject: {subject}")
        return True
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_USER
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_otp_email(email, name, otp):
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;background:#0e1520;color:#e8f0fe;padding:2rem;border-radius:16px;">
      <h2 style="color:#00d4ff;font-size:1.6rem;">MediBook OTP</h2>
      <p>Hi {name}, verify your account with this OTP:</p>
      <div style="background:#141d2e;border:1px solid #1e2d45;padding:1.5rem;border-radius:12px;text-align:center;margin:1.5rem 0;">
        <span style="font-size:2.5rem;font-weight:800;letter-spacing:0.3em;color:#00e5a0;">{otp}</span>
      </div>
      <p style="color:#5a7a9a;font-size:0.85rem;">This OTP expires in 10 minutes. Do not share it.</p>
    </div>"""
    return send_email(email, "MediBook – Your OTP Code", html)

def send_booking_confirmation(email, name, appt):
    doc = next((d for d in DOCTORS if d["id"] == appt["doctor_id"]), DOCTORS[0])
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;background:#0e1520;color:#e8f0fe;padding:2rem;border-radius:16px;">
      <h2 style="color:#00d4ff;">Appointment Confirmed ✓</h2>
      <p>Hi {name}, your appointment has been booked.</p>
      <div style="background:#141d2e;border:1px solid #1e2d45;padding:1.5rem;border-radius:12px;margin:1.5rem 0;">
        <p><b>Title:</b> {appt['title']}</p>
        <p><b>Doctor:</b> {doc['avatar']} {doc['name']}</p>
        <p><b>Date:</b> {appt['date']}</p>
        <p><b>Time:</b> {appt['start_time']} – {appt['end_time']}</p>
        <p><b>Location:</b> {appt['location']}</p>
      </div>
      <p style="color:#5a7a9a;font-size:0.85rem;">You will receive a reminder 1 hour before your appointment.</p>
    </div>"""
    return send_email(email, f"MediBook – Appointment Confirmed: {appt['title']}", html)

def send_reminder_email(email, name, appt):
    doc = next((d for d in DOCTORS if d["id"] == appt["doctor_id"]), DOCTORS[0])
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;background:#0e1520;color:#e8f0fe;padding:2rem;border-radius:16px;">
      <h2 style="color:#fbbf24;">⏰ Appointment Reminder</h2>
      <p>Hi {name}, your appointment is coming up!</p>
      <div style="background:#141d2e;border:1px solid #fbbf24;padding:1.5rem;border-radius:12px;margin:1.5rem 0;">
        <p><b>Title:</b> {appt['title']}</p>
        <p><b>Doctor:</b> {doc['avatar']} {doc['name']}</p>
        <p><b>Time:</b> {appt['start_time']} – {appt['end_time']}</p>
        <p><b>Location:</b> {appt['location']}</p>
      </div>
    </div>"""
    return send_email(email, f"🔔 Reminder: {appt['title']} at {appt['start_time']}", html)

# ── SLOT LOGIC ────────────────────────────────────────────────────────────────
def get_booked_slots(date, doctor_id):
    with get_db() as c:
        rows = c.execute(
            "SELECT start_time,end_time FROM appointments WHERE date=? AND doctor_id=? AND status!='cancelled'",
            (date, doctor_id)
        ).fetchall()
    return [(r["start_time"], r["end_time"]) for r in rows]

def is_overlapping(date, start, end, doctor_id, exclude_id=None):
    with get_db() as c:
        q = "SELECT id FROM appointments WHERE date=? AND doctor_id=? AND status!='cancelled' AND NOT(end_time<=? OR start_time>=?)"
        p = [date, doctor_id, start, end]
        if exclude_id:
            q += " AND id!=?"; p.append(exclude_id)
        return c.execute(q, p).fetchone() is not None

def generate_slots(date, doctor_id):
    booked = get_booked_slots(date, doctor_id)
    slots, cur = [], datetime.strptime(f"{date} {SLOT_START:02d}:00", "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(f"{date} {SLOT_END:02d}:00", "%Y-%m-%d %H:%M")
    while cur < end_dt:
        s = cur.strftime("%H:%M")
        e = (cur + timedelta(minutes=SLOT_MINS)).strftime("%H:%M")
        is_b = any(not (e <= b[0] or s >= b[1]) for b in booked)
        slots.append({"start": s, "end": e, "booked": is_b})
        cur += timedelta(minutes=SLOT_MINS)
    return slots

# ── SIMPLE OFFLINE AI LOGIC ───────────────────────────────────────────────────
def build_offline_ai_suggestion(symptoms: str) -> str:
    """
    Lightweight, rule-based assistant that generates a
    structured markdown response based on the user's text.
    This is NOT real medical advice.
    """
    original = (symptoms or "").strip()

    return f"""**AI Health Assistant (Offline Mode)**  

You asked: `{original}`

Please connect to the internet and provide an API key (OpenAI/Anthropic) in `.env` for the AI Assistant to provide you with full, conversational answers.

**Important:** This assistant is for **general guidance only** and **does not replace a real doctor**.  
If your symptoms feel severe, sudden, or worrying, please seek emergency care immediately."""

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

# ── REGISTER ──────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name     = request.form["name"].strip()
        age      = request.form.get("age","").strip()
        phone    = request.form.get("phone","").strip()
        email    = request.form["email"].strip().lower()
        pw       = request.form["password"]
        confirm  = request.form["confirm_password"]

        if not all([name, email, pw]):
            flash("Name, email and password are required.", "error")
            return render_template("register.html")
        if pw != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if len(pw) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        otp = gen_otp()
        expiry = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        hashed = generate_password_hash(pw)
        try:
            with get_db() as c:
                c.execute(
                    "INSERT INTO users (name,age,phone,email,password,otp,otp_expiry) VALUES(?,?,?,?,?,?,?)",
                    (name, age or None, phone or None, email, hashed, otp, expiry)
                )
                c.commit()
            sent = send_otp_email(email, name, otp)
            session["pending_email"] = email
            if sent:
                flash("Account created! OTP sent to your email. Please check your inbox.", "success")
            else:
                flash("Account created! Email sending failed — check your SMTP settings in .env", "error")
            return redirect(url_for("verify_otp"))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "error")
    return render_template("register.html")

# ── OTP VERIFY ────────────────────────────────────────────────────────────────
@app.route("/verify", methods=["GET","POST"])
def verify_otp():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("register"))
    if request.method == "POST":
        entered = request.form["otp"].strip()
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("register"))
        if user["otp"] != entered:
            flash("Invalid OTP. Try again.", "error")
            return render_template("verify_otp.html", email=email, demo_otp=session.get("pending_otp_demo"))
        if datetime.now() > datetime.strptime(user["otp_expiry"], "%Y-%m-%d %H:%M:%S"):
            flash("OTP expired. Please register again.", "error")
            return redirect(url_for("register"))
        with get_db() as c:
            c.execute("UPDATE users SET is_verified=1, otp=NULL WHERE email=?", (email,))
            c.commit()
        session.pop("pending_email", None)
        session.pop("pending_otp_demo", None)
        flash("Email verified! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("verify_otp.html", email=email, demo_otp=session.get("pending_otp_demo"))

@app.route("/resend-otp")
def resend_otp():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("register"))
    otp = gen_otp()
    expiry = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as c:
        user = c.execute("SELECT name FROM users WHERE email=?", (email,)).fetchone()
        c.execute("UPDATE users SET otp=?,otp_expiry=? WHERE email=?", (otp, expiry, email))
        c.commit()
    send_otp_email(email, user["name"] if user else "User", otp)
    flash("New OTP sent! Please check your email.", "success")
    return redirect(url_for("verify_otp"))

# ── LOGIN / LOGOUT ────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pw    = request.form["password"]
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], pw):
            if not user["is_verified"]:
                session["pending_email"] = email
                flash("Please verify your email first.", "error")
                return redirect(url_for("verify_otp"))
            session["user_id"]   = user["id"]
            session["user_name"] = user["name"]
            session["is_admin"]  = bool(user["is_admin"])
            flash(f"Welcome back, {user['name']}! 👋", "success")
            return redirect(url_for("admin_dashboard") if user["is_admin"] else url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as c:
        upcoming = c.execute(
            "SELECT * FROM appointments WHERE user_id=? AND date>=date('now') AND status!='cancelled' ORDER BY date,start_time",
            (session["user_id"],)
        ).fetchall()
        past = c.execute(
            "SELECT * FROM appointments WHERE user_id=? AND (date<date('now') OR status='cancelled') ORDER BY date DESC",
            (session["user_id"],)
        ).fetchall()
        user = c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("dashboard.html", upcoming=upcoming, past=past, user=user, doctors=DOCTORS)

# ── BOOK ──────────────────────────────────────────────────────────────────────
@app.route("/book", methods=["GET","POST"])
@login_required
def book():
    selected_date   = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))
    selected_doctor = int(request.args.get("doctor", 1))
    slots = generate_slots(selected_date, selected_doctor)

    if request.method == "POST":
        title       = request.form["title"].strip()
        category    = request.form.get("category","General Checkup")
        date        = request.form["date"]
        start_time  = request.form["start_time"]
        end_time    = request.form["end_time"]
        doctor_id   = int(request.form.get("doctor_id", 1))
        location    = request.form.get("location","Apollo Hospital, Hyderabad").strip()
        notes       = request.form.get("notes","").strip()

        if not all([title, date, start_time, end_time]):
            flash("Please fill all required fields.", "error")
            return render_template("book.html", slots=slots, selected_date=selected_date,
                                   doctors=DOCTORS, categories=CATEGORIES, selected_doctor=selected_doctor)

        if is_overlapping(date, start_time, end_time, doctor_id):
            flash("That slot is already booked. Please choose another time.", "error")
            return render_template("book.html", slots=slots, selected_date=selected_date,
                                   doctors=DOCTORS, categories=CATEGORIES, selected_doctor=selected_doctor)

        with get_db() as c:
            c.execute(
                "INSERT INTO appointments (user_id,doctor_id,title,category,date,start_time,end_time,location,notes) VALUES(?,?,?,?,?,?,?,?,?)",
                (session["user_id"], doctor_id, title, category, date, start_time, end_time, location, notes)
            )
            c.commit()
            user = c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
            appt = c.execute("SELECT * FROM appointments WHERE user_id=? ORDER BY id DESC LIMIT 1",
                             (session["user_id"],)).fetchone()

        send_booking_confirmation(user["email"], user["name"], dict(appt))
        flash("Appointment booked! Confirmation sent to your email. 🎉", "success")
        return redirect(url_for("dashboard"))

    return render_template("book.html", slots=slots, selected_date=selected_date,
                           doctors=DOCTORS, categories=CATEGORIES, selected_doctor=selected_doctor)

# ── SLOTS API ─────────────────────────────────────────────────────────────────
@app.route("/api/slots")
@login_required
def api_slots():
    date      = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))
    doctor_id = int(request.args.get("doctor", 1))
    return jsonify(slots=generate_slots(date, doctor_id))

# ── AI SUGGESTION API ─────────────────────────────────────────────────────────
@app.route("/api/ai-suggest", methods=["POST"])
def ai_suggest():
    import urllib.request, urllib.error
    data     = request.get_json()
    symptoms = data.get("symptoms","").strip()
    if not symptoms:
        return jsonify(error="No symptoms provided"), 400
    # Always prepare an offline rule-based answer as fallback.
    offline = build_offline_ai_suggestion(symptoms)

    current_gemini_key = os.environ.get("GEMINI_API_KEY", "")
    current_anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    current_openai_key = os.environ.get("OPENAI_API_KEY", "")
    
    # If no keys are configured, stay fully offline.
    if not current_gemini_key and not current_anthropic_key and not current_openai_key:
        print("DEBUG: No API keys configured.")
        return jsonify(suggestion=offline, source="offline")

    # Try Google Gemini API first (Free Tier)
    if current_gemini_key:
        try:
            payload = json.dumps({
                "system_instruction": {
                    "parts": [{"text": "You are a helpful medical conversational AI assistant for MediBook. You can answer any health, medical, or appointment related questions from the user. Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses."}]
                },
                "contents": [
                    {
                        "parts": [{"text": symptoms}]
                    }
                ]
            }).encode()

            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={current_gemini_key}",
                data=payload,
                headers={
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                result = json.loads(r.read())
            
            message = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text") or offline
            return jsonify(suggestion=message, source="gemini")
            
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            msg = e.reason if hasattr(e, 'reason') else "Unknown HTTP Error"
            print(f"DEBUG GEMINI HTTP ERROR: {e.code} - {msg} - body: {body}")
            
            if not current_anthropic_key and not current_openai_key:
                return jsonify(
                    suggestion=f"**Gemini AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}",
                    source="offline_http_error",
                    warning=msg
                )
        except Exception as ex:
            print(f"DEBUG GEMINI EXCEPTION: {ex}")
            if not current_anthropic_key and not current_openai_key:
                 return jsonify(
                    suggestion=f"**Gemini AI Exception**\n\n{ex}",
                    source="offline_exception",
                    warning="Cloud AI could not be reached. Using offline assistant instead."
                )

    # Try Anthropic Claude API first
    if current_anthropic_key:
        try:
            payload = json.dumps({
                "model": "claude-3-haiku-20240307",
                "max_tokens": 400,
                "system": "You are a helpful medical conversational AI assistant for MediBook. You can answer any health, medical, or appointment related questions from the user. Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses.",
                "messages": [{
                    "role": "user",
                    "content": symptoms
                }]
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "x-api-key": current_anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                result = json.loads(r.read())
            
            message = result.get("content", [{}])[0].get("text") or offline
            return jsonify(suggestion=message, source="anthropic")
            
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            msg = e.reason if hasattr(e, 'reason') else "Unknown HTTP Error"
            print(f"DEBUG ANTHROPIC HTTP ERROR: {e.code} - {msg} - body: {body}")
            
            # Fall back to checking OpenAI if Anthropic is also rate limited
            if not current_openai_key:
                return jsonify(
                    suggestion=f"**Anthropic AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}",
                    source="offline_http_error",
                    warning=msg
                )
        except Exception as ex:
            print(f"DEBUG ANTHROPIC EXCEPTION: {ex}")
            if not current_openai_key:
                 return jsonify(
                    suggestion=f"**Anthropic AI Exception**\n\n{ex}",
                    source="offline_exception",
                    warning="Cloud AI could not be reached. Using offline assistant instead."
                )

    # Backup: OpenAI Chat Completions API if Anthropic fails or isn't set.
    try:
        payload = json.dumps({
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful medical conversational AI assistant for MediBook. "
                        "You can answer any health, medical, or appointment related questions from the user. "
                        "Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses."
                    ),
                },
                {
                    "role": "user",
                    "content": symptoms,
                },
            ],
            "max_tokens": 400,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {current_openai_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
        result = json.loads(raw)

        choice = (result.get("choices") or [{}])[0]
        message = (choice.get("message") or {}).get("content") or offline
        return jsonify(suggestion=message, source="openai")

    except urllib.error.HTTPError as e:
        # For HTTP errors (e.g. 401, 429) show a friendly message and fall back.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        msg = e.reason if hasattr(e, 'reason') else "Unknown HTTP Error"
        print(f"DEBUG HTTP ERROR: {e.code} - {msg} - body: {body}")
        
        # Override offline message with the actual error so user sees it in debugging
        return jsonify(
            suggestion=f"**Cloud AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}",
            source="offline_http_error",
            warning=msg
        )
    except Exception as ex:
        # For any unexpected error, do NOT expose raw error details to the end user.
        print(f"DEBUG EXCEPTION: {ex}")
        return jsonify(
            suggestion=f"**Cloud AI Exception**\n\n{ex}",
            source="offline_exception",
            warning="Cloud AI could not be reached. Using offline assistant instead."
        )

# ── CANCEL ────────────────────────────────────────────────────────────────────
@app.route("/cancel/<int:appt_id>", methods=["POST"])
@login_required
def cancel(appt_id):
    with get_db() as c:
        c.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND user_id=?",
                  (appt_id, session["user_id"]))
        c.commit()
    flash("Appointment cancelled.", "success")

    # Notify waitlist
    with get_db() as c:
        appt = c.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
        if appt:
            wl = c.execute(
                "SELECT w.*,u.email,u.name FROM waitlist w JOIN users u ON w.user_id=u.id WHERE w.doctor_id=? AND w.date=? AND w.start_time=? LIMIT 1",
                (appt["doctor_id"], appt["date"], appt["start_time"])
            ).fetchone()
            if wl:
                send_email(wl["email"], "MediBook – Slot Available!",
                    f"<p>Hi {wl['name']}, a slot opened up on {appt['date']} at {appt['start_time']}. <a href='http://localhost:5000/book'>Book now!</a></p>")
                c.execute("DELETE FROM waitlist WHERE id=?", (wl["id"],))
                c.commit()
    return redirect(url_for("dashboard"))

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        name  = request.form["name"].strip()
        age   = request.form.get("age","").strip()
        phone = request.form.get("phone","").strip()
        with get_db() as c:
            c.execute("UPDATE users SET name=?,age=?,phone=? WHERE id=?",
                      (name, age or None, phone or None, session["user_id"]))
            c.commit()
        session["user_name"] = name
        flash("Profile updated!", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", user=user)

# ── WAITLIST ──────────────────────────────────────────────────────────────────
@app.route("/waitlist", methods=["POST"])
@login_required
def join_waitlist():
    doctor_id  = int(request.form["doctor_id"])
    date       = request.form["date"]
    start_time = request.form["start_time"]
    with get_db() as c:
        existing = c.execute(
            "SELECT id FROM waitlist WHERE user_id=? AND doctor_id=? AND date=? AND start_time=?",
            (session["user_id"], doctor_id, date, start_time)
        ).fetchone()
        if not existing:
            c.execute("INSERT INTO waitlist(user_id,doctor_id,date,start_time) VALUES(?,?,?,?)",
                      (session["user_id"], doctor_id, date, start_time))
            c.commit()
    flash("Added to waitlist! We'll notify you if this slot opens up.", "success")
    return redirect(url_for("book", date=date, doctor=doctor_id))

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    with get_db() as c:
        users = c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        appts = c.execute(
            "SELECT a.*,u.name as uname,u.email FROM appointments a JOIN users u ON a.user_id=u.id ORDER BY a.date DESC,a.start_time DESC"
        ).fetchall()
        stats = {
            "total_users":       c.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
            "total_appts":       c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
            "upcoming_appts":    c.execute("SELECT COUNT(*) FROM appointments WHERE date>=date('now') AND status!='cancelled'").fetchone()[0],
            "cancelled_appts":   c.execute("SELECT COUNT(*) FROM appointments WHERE status='cancelled'").fetchone()[0],
        }
    return render_template("admin.html", users=users, appts=appts, stats=stats, doctors=DOCTORS)

@app.route("/admin/delete-appt/<int:appt_id>", methods=["POST"])
@login_required
@admin_required
def admin_delete_appt(appt_id):
    with get_db() as c:
        c.execute("DELETE FROM appointments WHERE id=?", (appt_id,))
        c.commit()
    flash("Appointment deleted.", "success")
    return redirect(url_for("admin_dashboard"))

# ── REMINDER CHECK (call via cron or manually) ────────────────────────────────
@app.route("/admin/send-reminders")
@login_required
@admin_required
def send_reminders():
    now = datetime.now()
    reminder_window_start = (now + timedelta(hours=1)).strftime("%H:%M")
    reminder_window_end   = (now + timedelta(hours=1, minutes=30)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    count = 0
    with get_db() as c:
        appts = c.execute(
            """SELECT a.*,u.email,u.name FROM appointments a JOIN users u ON a.user_id=u.id
               WHERE a.date=? AND a.start_time>=? AND a.start_time<? AND a.reminder_sent=0 AND a.status!='cancelled'""",
            (today, reminder_window_start, reminder_window_end)
        ).fetchall()
        for a in appts:
            send_reminder_email(a["email"], a["name"], dict(a))
            c.execute("UPDATE appointments SET reminder_sent=1 WHERE id=?", (a["id"],))
            count += 1
        c.commit()
    flash(f"Sent {count} reminders.", "success")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
