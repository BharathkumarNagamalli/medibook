# 🏥 MediBook – AI-Powered Appointment Scheduler

A full-stack **FastAPI** web application for medical appointment scheduling.  
Upgraded from a Python CLI project to a complete asynchronous web app with AI, maps, OTP, and more.

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

## 🛠️ Technologies & Skills Used

This project demonstrates a fully functional, modern web application stack, integrating front-end design, back-end logic, database management, and third-party APIs.

### Backend & Core Logic
- **Python 3**: Core programming language.
- **FastAPI & Uvicorn**: Blazing-fast asynchronous web application framework.
- **Werkzeug**: Used for secure password hashing and session management.
- **SQLite3**: Relational database for storing users and appointments.

### APIs & Integrations
- **Google Gemini API**: Native integration for the AI Health Assistant.
- **Anthropic Claude API**: Supported alternative for AI responses.
- **OpenAI API**: Supported fallback for AI responses.
- **Google Maps Embed API**: Dynamic maps for clinic locations.
- **SMTP (smtplib)**: Real email integration for sending OTPs and booking confirmations.

### Frontend
- **HTML5 & CSS3**: Custom modern styling with responsive design.
- **JavaScript (ES6)**: Dynamic slot filtering and AJAX requests for the AI.
- **Jinja2**: HTML templating engine adapted for Starlette/FastAPI.
- **Google Fonts**: Custom typography using Syne and Instrument Sans.

---

## 🚀 Setup & Run

### 1. Clone the repository
```bash
git clone https://github.com/BharathkumarNagamalli/medibook.git
cd medibook
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
Create a `.env` file in the root directory and add your credentials:
```
SECRET_KEY=your_secret_key
ADMIN_EMAIL=admin@medibook.com

# For real emails
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password

# For AI Assistant
GEMINI_API_KEY=your_gemini_key
```

### 4. Run the application
```bash
python app.py
```
*(Alternatively: `uvicorn app:app --reload`)*

Open http://127.0.0.1:8000 in your browser.

---

## 🔑 Demo Credentials

- **Admin Account:** `admin@medibook.com` / `admin123`
- **OTP Verification:** Look at the server console or configure real SMTP.

---

## 📁 Project Structure

```
MediBook/
├── app.py              # Application routing, database logic, AI integration
├── .gitignore          # Protected files (e.g., .env, databases, caches)
├── templates/          # HTML templates
│   ├── base.html       # Base layout
│   ├── index.html      # Landing page
│   ├── register.html   # Registration and OTP verification
│   ├── login.html      # Authentication
│   ├── dashboard.html  # User dashboard
│   ├── book.html       # Appointment booking and AI assistant
│   ├── profile.html    # User profile management
│   └── admin.html      # Admin dashboard
└── static/             # CSS and Images
    └── uploads/        # User-uploaded avatars
```

---

## 🔮 Future Improvements

- [ ] SMS reminders via Twilio
- [ ] PostgreSQL for production
- [ ] Deploy to Render / Railway
- [ ] Reschedule appointments
- [ ] PDF appointment receipts
- [ ] Doctor login + their own dashboard
