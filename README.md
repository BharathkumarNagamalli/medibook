# 🏥 MediBook – AI-Powered Appointment Scheduler

A full-stack Flask web application for medical appointment scheduling.  
Upgraded from a Python CLI project to a complete web app with AI, maps, OTP, and more.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🔐 Register + OTP | Email OTP verification on signup |
| 🔒 Secure Login | Werkzeug password hashing |
| 🗓️ Smart Slots | Only available slots shown, booked ones hidden |
| ⚡ No Overlap | Conflict detection prevents double-booking |
| 👨‍⚕️ Doctor Selection | 5 specialists, each with own schedule |
| 📋 Categories | 10 appointment types |
| 🤖 AI Assistant | Claude AI suggests specialist + urgency from symptoms |
| 📧 Email Notifications | Booking confirmation + 1hr reminder |
| 📍 Maps | Google Maps embed for clinic location |
| ⏳ Waitlist | Join queue for booked slots, auto-notified on cancellation |
| 📊 Admin Dashboard | All users, appointments, stats, manual reminder trigger |
| 👤 Profile | Edit name, age, phone |
| 📱 Responsive | Mobile-friendly design |

---

## 🛠️ Technologies

### Previous (CLI)
- Python, SQLite, `dataclasses`, `datetime`, CLI menu

### New (Web App)
| Layer | Technology |
|---|---|
| Backend | **Flask 3**, Python stdlib |
| Auth | **Werkzeug** (bcrypt hashing), session |
| Database | **SQLite** (sqlite3) |
| Email | **smtplib** (Gmail SMTP) |
| AI | **Anthropic Claude API** (claude-sonnet) |
| Maps | **Google Maps Embed API** |
| Frontend | **HTML5, CSS3, JavaScript (ES6)** |
| Templating | **Jinja2** |
| Fonts | Google Fonts (Syne + Instrument Sans) |

---

## 🚀 Setup & Run

### 1. Clone
```bash
git clone https://github.com/BharathkumarNagamalli/Appointment_Scheduler.git
cd Appointment_Scheduler
```

### 2. Install dependencies
```bash
pip install flask werkzeug
```

### 3. Configure environment (optional but recommended)
```bash
cp .env.example .env
# Edit .env with your Gmail credentials and Anthropic API key
```

### 4. Run
```bash
python app.py
```

Open http://localhost:5000

---

## 🔑 Demo Credentials

- **Admin:** admin@medibook.com / admin123
- **OTP:** Shown on screen in demo mode (no email config needed)

---

## 📧 Enable Real Emails

1. Go to your Google Account → Security → App Passwords
2. Generate an app password for "Mail"
3. Set in `.env`:
```
SMTP_USER=your@gmail.com
SMTP_PASS=your_app_password
```

## 🤖 Enable AI Assistant

1. Get API key from https://console.anthropic.com
2. Set in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 📁 Project Structure

```
appointment_app/
├── app.py              # All routes, logic, email, AI
├── requirements.txt
├── .env.example
└── templates/
    ├── base.html       # Nav, flash messages, shared CSS
    ├── index.html      # Landing page + tech stack
    ├── register.html   # Registration form
    ├── verify_otp.html # 6-digit OTP input
    ├── login.html      # Login
    ├── dashboard.html  # User appointment overview
    ├── book.html       # Slot picker + AI + Maps
    ├── profile.html    # Edit profile
    └── admin.html      # Admin control center
```

---

## 🔮 Future Improvements

- [ ] SMS reminders via Twilio
- [ ] PostgreSQL for production
- [ ] Deploy to Render / Railway
- [ ] Reschedule appointments
- [ ] PDF appointment receipts
- [ ] Doctor login + their own dashboard
