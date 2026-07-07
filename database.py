"""
database.py
------------
All SQLite access for the LG Production Dashboard lives here.
Every other module (app.py, chatbot.py, seed_data.py) goes through
these functions instead of writing raw SQL, so the schema only has
to be understood in one place.
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta

import pandas as pd

import config


# ------------------------------------------------------------------
# Connection helper
# ------------------------------------------------------------------
def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ------------------------------------------------------------------
# Password hashing (simple SHA-256; fine for a project/demo system)
# ------------------------------------------------------------------
def hash_password(password: str) -> str:
    salted = f"lg-project-salt::{password}"
    return hashlib.sha256(salted.encode()).hexdigest()


# ------------------------------------------------------------------
# Schema creation + first-run seeding
# ------------------------------------------------------------------
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS production_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','operator','production_head','branch_head')),
            email TEXT,
            assigned_line_id INTEGER,
            FOREIGN KEY(assigned_line_id) REFERENCES production_lines(id)
        );

        CREATE TABLE IF NOT EXISTS daily_production (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            target INTEGER NOT NULL,
            produced INTEGER NOT NULL,
            defected INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(line_id) REFERENCES production_lines(id),
            UNIQUE(line_id, date)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            line_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_to TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(line_id) REFERENCES production_lines(id)
        );
        """
    )
    conn.commit()

    # Seed the three production lines if they don't exist yet
    for name in config.LINE_NAMES:
        cur.execute("INSERT OR IGNORE INTO production_lines (name) VALUES (?)", (name,))
    conn.commit()

    # Seed a default admin account if no users exist yet
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, email, assigned_line_id) "
            "VALUES (?, ?, 'admin', ?, NULL)",
            (
                config.DEFAULT_ADMIN_USERNAME,
                hash_password(config.DEFAULT_ADMIN_PASSWORD),
                config.DEFAULT_ADMIN_EMAIL,
            ),
        )
        conn.commit()

    conn.close()


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------
def create_user(username, password, role, email, assigned_line_id=None):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, email, assigned_line_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(password), role, email, assigned_line_id),
        )
        conn.commit()
        return True, "User created."
    except sqlite3.IntegrityError:
        return False, "That username already exists."
    finally:
        conn.close()


def verify_user(username, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password)),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT u.id, u.username, u.role, u.email, pl.name AS assigned_line
        FROM users u
        LEFT JOIN production_lines pl ON u.assigned_line_id = pl.id
        ORDER BY u.id
        """,
        conn,
    )
    conn.close()
    return df


def get_recipients_for_line(line_id):
    """Everyone who should be emailed when THIS line breaches a threshold:
    the production head assigned to that line, plus every branch head."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT email FROM users
        WHERE email IS NOT NULL AND email != '' AND (
            (role = 'production_head' AND assigned_line_id = ?)
            OR role = 'branch_head'
        )
        """,
        (line_id,),
    ).fetchall()
    conn.close()
    return [r["email"] for r in rows]


# ------------------------------------------------------------------
# Production lines
# ------------------------------------------------------------------
def get_lines():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM production_lines ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_line_id_by_name(name):
    conn = get_connection()
    row = conn.execute("SELECT id FROM production_lines WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row["id"] if row else None


# ------------------------------------------------------------------
# Daily production records
# ------------------------------------------------------------------
def upsert_daily_record(line_id, date, target, produced, defected):
    """Insert today's numbers, or overwrite them if that line/date already exists
    (lets an operator correct a mistaken entry)."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO daily_production (line_id, date, target, produced, defected, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(line_id, date) DO UPDATE SET
            target = excluded.target,
            produced = excluded.produced,
            defected = excluded.defected,
            updated_at = excluded.updated_at
        """,
        (line_id, date, target, produced, defected, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_record(line_id, date):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM daily_production WHERE line_id = ? AND date = ?", (line_id, date)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_today_summary(date):
    """One row per line for the given date, with 0s if nothing was entered yet."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT pl.id AS line_id, pl.name AS line,
               COALESCE(dp.target, 0)   AS target,
               COALESCE(dp.produced, 0) AS produced,
               COALESCE(dp.defected, 0) AS defected
        FROM production_lines pl
        LEFT JOIN daily_production dp ON pl.id = dp.line_id AND dp.date = ?
        ORDER BY pl.id
        """,
        conn,
        params=(date,),
    )
    conn.close()
    df["defect_rate_%"] = df.apply(
        lambda r: round((r["defected"] / r["produced"]) * 100, 2) if r["produced"] else 0.0,
        axis=1,
    )
    return df


def get_history(line_name=None, days=30, end_date=None):
    """History of the last `days` days, optionally filtered to a single line."""
    if end_date is None:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=days - 1)

    conn = get_connection()
    query = """
        SELECT dp.date, pl.name AS line, dp.target, dp.produced, dp.defected
        FROM daily_production dp
        JOIN production_lines pl ON dp.line_id = pl.id
        WHERE dp.date BETWEEN ? AND ?
    """
    params = [start_date.isoformat(), end_date.isoformat()]
    if line_name:
        query += " AND pl.name = ?"
        params.append(line_name)
    query += " ORDER BY dp.date ASC"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    if not df.empty:
        df["defect_rate_%"] = round((df["defected"] / df["produced"].replace(0, pd.NA)) * 100, 2)
    return df


# ------------------------------------------------------------------
# Alerts
# ------------------------------------------------------------------
def log_alert(date, line_id, message, sent_to, status):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO alerts (date, line_id, message, sent_to, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (date, line_id, message, ", ".join(sent_to) if sent_to else "(no recipients configured)",
         status, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_alerts(limit=100):
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT a.created_at, a.date, pl.name AS line, a.message, a.sent_to, a.status
        FROM alerts a
        JOIN production_lines pl ON a.line_id = pl.id
        ORDER BY a.id DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()
    return df
