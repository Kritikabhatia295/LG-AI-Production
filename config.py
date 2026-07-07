import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- Database ----------------
DB_PATH = os.path.join(BASE_DIR, "lg_production.db")

# ---------------- Production lines ----------------
LINE_NAMES = ["Refrigerator", "Air Conditioner", "Washing Machine"]

# Aliases the chatbot understands, mapped to the canonical line name
LINE_ALIASES = {
    "refrigerator": "Refrigerator",
    "fridge": "Refrigerator",
    "ref": "Refrigerator",
    "air conditioner": "Air Conditioner",
    "airconditioner": "Air Conditioner",
    "ac": "Air Conditioner",
    "a/c": "Air Conditioner",
    "washing machine": "Washing Machine",
    "washingmachine": "Washing Machine",
    "wm": "Washing Machine",
    "washer": "Washing Machine",
}

# ---------------- Alert thresholds ----------------
# An alert email is triggered if EITHER condition is breached for a line's daily entry
DEFECT_RATE_THRESHOLD = float(os.getenv("DEFECT_RATE_THRESHOLD", 5.0))   # percent
DEFECT_COUNT_THRESHOLD = int(os.getenv("DEFECT_COUNT_THRESHOLD", 25))    # absolute units

# ---------------- Email / SMTP ----------------
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ---------------- Default admin account (created on first run) ----------------
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
