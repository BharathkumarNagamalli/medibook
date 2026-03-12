import os, sqlite3, random, string, smtplib, json, urllib.request, urllib.error
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from functools import wraps

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import generate_password_hash, check_password_hash

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

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "medibook_secret_2026_xK9#mL"))

templates = Jinja2Templates(directory="templates")

# Try mounting static if exists
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB = "medibook.db"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@medibook.com")
SMTP_HOST   = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER   = os.environ.get("SMTP_USER", "")          
SMTP_PASS   = os.environ.get("SMTP_PASS", "")          
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
    conn = sqlite3.connect(DB, check_same_thread=False)
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
        admin_pw = generate_password_hash("admin123")
        c.execute("""INSERT OR IGNORE INTO users (name,email,password,is_admin,is_verified)
                     VALUES ('Admin','admin@medibook.com',?,1,1)""", (admin_pw,))
        c.commit()

# ── FLASK EMULATORS FOR STARLETTE ─────────────────────────────────────────────
def flash(request: Request, message: str, category: str = "message"):
    if "_flashes" not in request.session:
        request.session["_flashes"] = []
    request.session["_flashes"].append((category, message))

def get_flashed_messages(request: Request, with_categories=False):
    flashes = request.session.pop("_flashes", [])
    if with_categories:
        return flashes
    return [x[1] for x in flashes]

def render(request: Request, name: str, **context):
    context["request"] = request
    context["session"] = request.session
    context["get_flashed_messages"] = lambda with_categories=False: get_flashed_messages(request, with_categories)
    return templates.TemplateResponse(name, context)

class RequiresLoginException(Exception): pass
class RequiresAdminException(Exception): pass

@app.exception_handler(RequiresLoginException)
async def requires_login_exception_handler(request: Request, exc: RequiresLoginException):
    flash(request, "Please log in first.", "error")
    return RedirectResponse(request.url_for("login"), status_code=303)

@app.exception_handler(RequiresAdminException)
async def requires_admin_exception_handler(request: Request, exc: RequiresAdminException):
    flash(request, "Admin access required.", "error")
    return RedirectResponse(request.url_for("dashboard"), status_code=303)

def login_required(request: Request):
    if "user_id" not in request.session:
        raise RequiresLoginException()
    return request.session

def admin_required(request: Request):
    if not request.session.get("is_admin"):
        raise RequiresAdminException()
    return request.session

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
    original = (symptoms or "").strip()
    return f"""**AI Health Assistant (Offline Mode)**  \n\nYou asked: `{original}`\n\nPlease connect to the internet and provide an API key (OpenAI/Anthropic/Gemini) in `.env` for the AI Assistant to provide you with full, conversational answers.\n\n**Important:** This assistant is for **general guidance only** and **does not replace a real doctor**.  \nIf your symptoms feel severe, sudden, or worrying, please seek emergency care immediately."""

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.get("/")
async def index(request: Request):
    if "user_id" in request.session:
        return RedirectResponse(request.url_for("dashboard"), status_code=303)
    return render(request, "index.html")

# ── REGISTER ──────────────────────────────────────────────────────────────────
@app.get("/register")
async def register(request: Request):
    return render(request, "register.html")

@app.post("/register")
async def register_post(request: Request, name: str = Form(...), age: str = Form(""), phone: str = Form(""), email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    name = name.strip()
    email = email.strip().lower()
    
    if not all([name, email, password]):
        flash(request, "Name, email and password are required.", "error")
        return render(request, "register.html")
    if password != confirm_password:
        flash(request, "Passwords do not match.", "error")
        return render(request, "register.html")
    if len(password) < 6:
        flash(request, "Password must be at least 6 characters.", "error")
        return render(request, "register.html")

    otp = gen_otp()
    expiry = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    hashed = generate_password_hash(password)
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO users (name,age,phone,email,password,otp,otp_expiry) VALUES(?,?,?,?,?,?,?)",
                (name, age or None, phone or None, email, hashed, otp, expiry)
            )
            c.commit()
        sent = send_otp_email(email, name, otp)
        request.session["pending_email"] = email
        if sent:
            flash(request, "Account created! OTP sent to your email. Please check your inbox.", "success")
        else:
            flash(request, "Account created! Email sending failed — check your SMTP settings in .env", "error")
        return RedirectResponse(request.url_for("verify_otp"), status_code=303)
    except sqlite3.IntegrityError:
        flash(request, "Email already registered.", "error")
    return render(request, "register.html")

# ── OTP VERIFY ────────────────────────────────────────────────────────────────
@app.get("/verify")
async def verify_otp(request: Request):
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse(request.url_for("register"), status_code=303)
    return render(request, "verify_otp.html", email=email, demo_otp=request.session.get("pending_otp_demo"))

@app.post("/verify")
async def verify_otp_post(request: Request, otp: str = Form(...)):
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse(request.url_for("register"), status_code=303)
    entered = otp.strip()
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse(request.url_for("register"), status_code=303)
    if user["otp"] != entered:
        flash(request, "Invalid OTP. Try again.", "error")
        return render(request, "verify_otp.html", email=email, demo_otp=request.session.get("pending_otp_demo"))
    if datetime.now() > datetime.strptime(user["otp_expiry"], "%Y-%m-%d %H:%M:%S"):
        flash(request, "OTP expired. Please register again.", "error")
        return RedirectResponse(request.url_for("register"), status_code=303)
    with get_db() as c:
        c.execute("UPDATE users SET is_verified=1, otp=NULL WHERE email=?", (email,))
        c.commit()
    request.session.pop("pending_email", None)
    request.session.pop("pending_otp_demo", None)
    flash(request, "Email verified! You can now log in.", "success")
    return RedirectResponse(request.url_for("login"), status_code=303)

@app.get("/resend-otp")
async def resend_otp(request: Request):
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse(request.url_for("register"), status_code=303)
    otp = gen_otp()
    expiry = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as c:
        user = c.execute("SELECT name FROM users WHERE email=?", (email,)).fetchone()
        c.execute("UPDATE users SET otp=?,otp_expiry=? WHERE email=?", (otp, expiry, email))
        c.commit()
    send_otp_email(email, user["name"] if user else "User", otp)
    flash(request, "New OTP sent! Please check your email.", "success")
    return RedirectResponse(request.url_for("verify_otp"), status_code=303)

# ── LOGIN / LOGOUT ────────────────────────────────────────────────────────────
@app.get("/login")
async def login(request: Request):
    return render(request, "login.html")

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if user and check_password_hash(user["password"], password):
        if not user["is_verified"]:
            request.session["pending_email"] = email
            flash(request, "Please verify your email first.", "error")
            return RedirectResponse(request.url_for("verify_otp"), status_code=303)
        request.session["user_id"]   = user["id"]
        request.session["user_name"] = user["name"]
        request.session["is_admin"]  = bool(user["is_admin"])
        flash(request, f"Welcome back, {user['name']}! 👋", "success")
        return RedirectResponse(request.url_for("admin_dashboard") if user["is_admin"] else request.url_for("dashboard"), status_code=303)
    flash(request, "Invalid email or password.", "error")
    return render(request, "login.html")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    flash(request, "Logged out successfully.", "success")
    return RedirectResponse(request.url_for("index"), status_code=303)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.get("/dashboard")
async def dashboard(request: Request, _=Depends(login_required)):
    with get_db() as c:
        upcoming = c.execute(
            "SELECT * FROM appointments WHERE user_id=? AND date>=date('now') AND status!='cancelled' ORDER BY date,start_time",
            (request.session["user_id"],)
        ).fetchall()
        past = c.execute(
            "SELECT * FROM appointments WHERE user_id=? AND (date<date('now') OR status='cancelled') ORDER BY date DESC",
            (request.session["user_id"],)
        ).fetchall()
        user = c.execute("SELECT * FROM users WHERE id=?", (request.session["user_id"],)).fetchone()
    return render(request, "dashboard.html", upcoming=upcoming, past=past, user=user, doctors=DOCTORS)

# ── BOOK ──────────────────────────────────────────────────────────────────────
@app.get("/book")
async def book(request: Request, date: str = None, doctor: int = 1, _=Depends(login_required)):
    if not date:
        date = datetime.today().strftime("%Y-%m-%d")
    slots = generate_slots(date, doctor)
    return render(request, "book.html", slots=slots, selected_date=date,
                   doctors=DOCTORS, categories=CATEGORIES, selected_doctor=doctor)

@app.post("/book")
async def book_post(request: Request, title: str = Form(...), category: str = Form("General Checkup"), 
                    date: str = Form(...), start_time: str = Form(...), end_time: str = Form(...), 
                    doctor_id: int = Form(1), location: str = Form("Apollo Hospital, Hyderabad"), 
                    notes: str = Form(""), _=Depends(login_required)):
    title = title.strip()
    location = location.strip()
    notes = notes.strip()
    slots = generate_slots(date, doctor_id)
    if not all([title, date, start_time, end_time]):
        flash(request, "Please fill all required fields.", "error")
        return render(request, "book.html", slots=slots, selected_date=date,
                               doctors=DOCTORS, categories=CATEGORIES, selected_doctor=doctor_id)

    if is_overlapping(date, start_time, end_time, doctor_id):
        flash(request, "That slot is already booked. Please choose another time.", "error")
        return render(request, "book.html", slots=slots, selected_date=date,
                               doctors=DOCTORS, categories=CATEGORIES, selected_doctor=doctor_id)

    with get_db() as c:
        c.execute(
            "INSERT INTO appointments (user_id,doctor_id,title,category,date,start_time,end_time,location,notes) VALUES(?,?,?,?,?,?,?,?,?)",
            (request.session["user_id"], doctor_id, title, category, date, start_time, end_time, location, notes)
        )
        c.commit()
        user = c.execute("SELECT * FROM users WHERE id=?", (request.session["user_id"],)).fetchone()
        appt = c.execute("SELECT * FROM appointments WHERE user_id=? ORDER BY id DESC LIMIT 1",
                         (request.session["user_id"],)).fetchone()

    send_booking_confirmation(user["email"], user["name"], dict(appt))
    flash(request, "Appointment booked! Confirmation sent to your email. 🎉", "success")
    return RedirectResponse(request.url_for("dashboard"), status_code=303)

# ── SLOTS API ─────────────────────────────────────────────────────────────────
@app.get("/api/slots")
async def api_slots(request: Request, date: str = None, doctor: int = 1, _=Depends(login_required)):
    if not date:
        date = datetime.today().strftime("%Y-%m-%d")
    return {"slots": generate_slots(date, doctor)}

# ── AI SUGGESTION API ─────────────────────────────────────────────────────────
@app.post("/api/ai-suggest")
async def ai_suggest(request: Request):
    data = await request.json()
    symptoms = data.get("symptoms","").strip()
    if not symptoms:
        return JSONResponse({"error": "No symptoms provided"}, status_code=400)
    
    offline = build_offline_ai_suggestion(symptoms)

    current_gemini_key = os.environ.get("GEMINI_API_KEY", "")
    current_anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    current_openai_key = os.environ.get("OPENAI_API_KEY", "")
    
    if not current_gemini_key and not current_anthropic_key and not current_openai_key:
        return {"suggestion": offline, "source": "offline"}

    if current_gemini_key:
        try:
            payload = json.dumps({
                "system_instruction": {"parts": [{"text": "You are a helpful medical conversational AI assistant for MediBook. You can answer any health, medical, or appointment related questions from the user. Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses."}]},
                "contents": [{"parts": [{"text": symptoms}]}]
            }).encode()

            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={current_gemini_key}",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                result = json.loads(r.read())
            
            message = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text") or offline
            return {"suggestion": message, "source": "gemini"}
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            msg = getattr(e, 'reason', "Unknown Error")
            if not current_anthropic_key and not current_openai_key:
                return {"suggestion": f"**Gemini AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}", "source": "offline_http_error", "warning": msg}
        except Exception as ex:
            if not current_anthropic_key and not current_openai_key:
                return {"suggestion": f"**Gemini AI Exception**\n\n{ex}", "source": "offline_exception"}

    if current_anthropic_key:
        try:
            payload = json.dumps({
                "model": "claude-3-haiku-20240307",
                "max_tokens": 400,
                "system": "You are a helpful medical conversational AI assistant for MediBook. You can answer any health, medical, or appointment related questions from the user. Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses.",
                "messages": [{"role": "user", "content": symptoms}]
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
            return {"suggestion": message, "source": "anthropic"}
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            msg = getattr(e, 'reason', "Unknown Error")
            if not current_openai_key:
                return {"suggestion": f"**Anthropic AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}", "source": "offline_http_error", "warning": msg}
        except Exception as ex:
            if not current_openai_key:
                return {"suggestion": f"**Anthropic AI Exception**\n\n{ex}", "source": "offline_exception"}

    try:
        payload = json.dumps({
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": "You are a helpful medical conversational AI assistant for MediBook. You can answer any health, medical, or appointment related questions from the user. Always remind users that you are NOT a substitute for a real doctor if they ask for diagnoses."},
                {"role": "user", "content": symptoms},
            ],
            "max_tokens": 400,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {current_openai_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
        result = json.loads(raw)
        choice = (result.get("choices") or [{}])[0]
        message = (choice.get("message") or {}).get("content") or offline
        return {"suggestion": message, "source": "openai"}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        msg = getattr(e, 'reason', "Unknown Error")
        return {"suggestion": f"**Cloud AI Error**\n\nCode: {e.code}\nMessage: {msg}\nDetail: {body}", "source": "offline_http_error", "warning": msg}
    except Exception as ex:
        return {"suggestion": f"**Cloud AI Exception**\n\n{ex}", "source": "offline_exception"}

# ── CANCEL ────────────────────────────────────────────────────────────────────
@app.post("/cancel/{appt_id}")
async def cancel(request: Request, appt_id: int, _=Depends(login_required)):
    with get_db() as c:
        c.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND user_id=?",
                  (appt_id, request.session["user_id"]))
        c.commit()
    flash(request, "Appointment cancelled.", "success")

    with get_db() as c:
        appt = c.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
        if appt:
            wl = c.execute(
                "SELECT w.*,u.email,u.name FROM waitlist w JOIN users u ON w.user_id=u.id WHERE w.doctor_id=? AND w.date=? AND w.start_time=? LIMIT 1",
                (appt["doctor_id"], appt["date"], appt["start_time"])
            ).fetchone()
            if wl:
                send_email(wl["email"], "MediBook – Slot Available!",
                    f"<p>Hi {wl['name']}, a slot opened up on {appt['date']} at {appt['start_time']}.</p>")
                c.execute("DELETE FROM waitlist WHERE id=?", (wl["id"],))
                c.commit()
    return RedirectResponse(request.url_for("dashboard"), status_code=303)

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.get("/profile")
async def profile(request: Request, _=Depends(login_required)):
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE id=?", (request.session["user_id"],)).fetchone()
    return render(request, "profile.html", user=user)

@app.post("/profile")
async def profile_post(request: Request, name: str = Form(...), age: str = Form(""), phone: str = Form(""), _=Depends(login_required)):
    name = name.strip()
    with get_db() as c:
        c.execute("UPDATE users SET name=?,age=?,phone=? WHERE id=?",
                  (name, age or None, phone or None, request.session["user_id"]))
        c.commit()
    request.session["user_name"] = name
    flash(request, "Profile updated!", "success")
    return RedirectResponse(request.url_for("profile"), status_code=303)

# ── WAITLIST ──────────────────────────────────────────────────────────────────
@app.post("/waitlist")
async def join_waitlist(request: Request, doctor_id: int = Form(...), date: str = Form(...), start_time: str = Form(...), _=Depends(login_required)):
    with get_db() as c:
        existing = c.execute(
            "SELECT id FROM waitlist WHERE user_id=? AND doctor_id=? AND date=? AND start_time=?",
            (request.session["user_id"], doctor_id, date, start_time)
        ).fetchone()
        if not existing:
            c.execute("INSERT INTO waitlist(user_id,doctor_id,date,start_time) VALUES(?,?,?,?)",
                      (request.session["user_id"], doctor_id, date, start_time))
            c.commit()
    flash(request, "Added to waitlist! We'll notify you if this slot opens up.", "success")
    # Redirect with query params is easiest this way:
    return RedirectResponse(f"/book?date={date}&doctor={doctor_id}", status_code=303)

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.get("/admin")
async def admin_dashboard(request: Request, _=Depends(login_required), __=Depends(admin_required)):
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
    return render(request, "admin.html", users=users, appts=appts, stats=stats, doctors=DOCTORS)

@app.post("/admin/delete-appt/{appt_id}")
async def admin_delete_appt(request: Request, appt_id: int, _=Depends(login_required), __=Depends(admin_required)):
    with get_db() as c:
        c.execute("DELETE FROM appointments WHERE id=?", (appt_id,))
        c.commit()
    flash(request, "Appointment deleted.", "success")
    return RedirectResponse(request.url_for("admin_dashboard"), status_code=303)

@app.get("/admin/send-reminders")
async def send_reminders(request: Request, _=Depends(login_required), __=Depends(admin_required)):
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
    flash(request, f"Sent {count} reminders.", "success")
    return RedirectResponse(request.url_for("admin_dashboard"), status_code=303)

if __name__ == "__main__":
    init_db()
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
