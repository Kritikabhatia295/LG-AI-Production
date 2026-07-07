# LG Electronics — Production Dashboard & AI Assistant

A Python/Streamlit project that monitors three production lines
(Refrigerator, Air Conditioner, Washing Machine): daily target, units
produced, units defected, historical trends, automatic email alerts on
defect breaches, a login system with roles, and a rule-based chatbot
assistant.

## 1. Setup

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional but recommended) configure email alerts
cp .env.example .env
# then edit .env with your SMTP / Gmail app-password details

# 4. Seed the database with sample users + 45 days of history
python seed_data.py

# 5. Run the app
streamlit run app.py
```

Streamlit will open the app at `http://localhost:8501`.

## 2. Login credentials (created by seed_data.py)

| Username      | Password | Role             | Notes                              |
|---------------|----------|------------------|-------------------------------------|
| admin         | admin123 | admin            | full access, manage users           |
| op_fridge     | pass123  | operator         | can enter daily production data     |
| head_fridge   | pass123  | production_head  | assigned to Refrigerator line       |
| head_ac       | pass123  | production_head  | assigned to Air Conditioner line    |
| head_wm       | pass123  | production_head  | assigned to Washing Machine line    |
| branch_head   | pass123  | branch_head      | receives alerts for ALL lines       |

## 3. How it's built

```
lg_dashboard/
├── app.py            Streamlit UI: login, dashboard, chatbot, history, alerts, user mgmt
├── database.py        All SQLite access (schema + queries) - single source of truth
├── chatbot.py          Rule-based NLU that answers questions from the database
├── email_alert.py    Builds & sends the breach email, decides when a breach happened
├── seed_data.py       One-time script: sample users + realistic historical data
├── config.py           Thresholds, line names/aliases, DB path, SMTP settings
├── requirements.txt
└── .env.example       Template for SMTP credentials (copy to .env)
```

**Database (SQLite, file `lg_production.db`)**
- `production_lines` — the 3 lines
- `users` — username, hashed password, role, email, assigned line (for production heads)
- `daily_production` — one row per (line, date): target / produced / defected
- `alerts` — a log of every alert email attempt (sent or failed) for audit history

**Roles**
- `operator` — enters/updates the day's numbers for a line
- `production_head` — assigned to one line, gets alerted when *their* line breaches
- `branch_head` — gets alerted for *every* line
- `admin` — everything above, plus can create/view users

**Alert logic** (`email_alert.check_and_alert`)
An alert fires when, for a given day's entry, **either**:
- defect rate (`defected / produced`) ≥ `DEFECT_RATE_THRESHOLD` (default 5%), **or**
- absolute defected units ≥ `DEFECT_COUNT_THRESHOLD` (default 25)

Both are configurable in `.env`. When triggered, it emails everyone returned
by `get_recipients_for_line()` (the line's production head + all branch heads)
and logs the attempt — success or failure — into the `alerts` table, visible
on the "Alerts Log" page.

**Chatbot** (`chatbot.py`)
It's intentionally rule-based (regex/keyword matching against the database),
not an external LLM call — so the whole project runs offline with no API
key or cost. It recognizes line names/aliases ("AC", "fridge", "WM"...) and
metrics (target, produced, defects, defect rate, history, summary). If you
later want richer natural-language understanding, `chatbot.answer(query)`
already returns a plain string, so you could swap its internals for a call
to an LLM API without touching `app.py`.

## 4. Setting up real email alerts (Gmail example)

1. Turn on 2-Step Verification on the Gmail account you'll send from.
2. Create an **App Password**: Google Account → Security → App passwords.
3. Put that 16-character password (not your normal Gmail password) into
   `.env` as `EMAIL_PASSWORD`, and the Gmail address as `EMAIL_ADDRESS`.
4. Make sure the users you want alerted (production heads / branch head)
   have real email addresses set — either via `seed_data.py` or the
   "Manage Users" page as admin.

If `.env` isn't configured, the app still works fully — alerts are still
detected and logged in the Alerts Log, just marked `FAILED - SMTP
credentials not configured` instead of `SENT`.

## 5. Extending this project

Ideas if you want to take this further for a college/internship submission:
- Swap SQLite for MySQL/PostgreSQL for a multi-user production deployment.
- Add shift-wise tracking (morning/evening/night) instead of one row per day.
- Add password hashing with `bcrypt` instead of salted SHA-256.
- Add SMS alerts (Twilio) alongside email.
- Replace the rule-based chatbot with an LLM call for free-form Q&A.
- Add a "defect reason/category" field (e.g. compressor fault, paint defect)
  for root-cause analytics.
