"""
seed_data.py
------------
Run this once (`python seed_data.py`) to populate the database with:
- sample users for each role (so you can log in and test alerts immediately)
- 45 days of realistic historical production data for all 3 lines,
  including a few days that intentionally breach the defect threshold
  so you can see the alert system in action.

Safe to re-run: it only inserts users/lines if missing, and it
overwrites (upserts) daily records for the generated date range.
"""

import random
from datetime import datetime, timedelta

import database
import config

random.seed(42)

LINE_TARGETS = {
    "Refrigerator": 500,
    "Air Conditioner": 400,
    "Washing Machine": 450,
}


def seed_users():
    database.create_user(
        "op_fridge", "pass123", "operator", "operator.fridge@example.com"
    )
    fridge_id = database.get_line_id_by_name("Refrigerator")
    ac_id = database.get_line_id_by_name("Air Conditioner")
    wm_id = database.get_line_id_by_name("Washing Machine")

    database.create_user(
        "head_fridge", "pass123", "production_head",
        "prodhead.fridge@example.com", assigned_line_id=fridge_id,
    )
    database.create_user(
        "head_ac", "pass123", "production_head",
        "prodhead.ac@example.com", assigned_line_id=ac_id,
    )
    database.create_user(
        "head_wm", "pass123", "production_head",
        "prodhead.wm@example.com", assigned_line_id=wm_id,
    )
    database.create_user(
        "branch_head", "pass123", "branch_head", "branchhead@example.com"
    )
    print("Sample users created (username / password: pass123, admin/admin123).")


def seed_history(days=45):
    today = datetime.now().date()
    lines = database.get_lines()

    for line in lines:
        target = LINE_TARGETS.get(line["name"], 450)
        for offset in range(days, 0, -1):
            date = (today - timedelta(days=offset)).isoformat()

            # Normal day: produced close to target, defect rate 1-4%
            daily_target = target + random.randint(-20, 20)
            produced = daily_target - random.randint(0, 15)
            defect_rate = random.uniform(0.01, 0.04)

            # Occasionally simulate a bad day that breaches the alert threshold
            if random.random() < 0.12:
                defect_rate = random.uniform(0.06, 0.12)

            defected = max(0, round(produced * defect_rate))

            database.upsert_daily_record(line["id"], date, daily_target, produced, defected)

    print(f"Seeded {days} days of history for {len(lines)} production lines.")


if __name__ == "__main__":
    database.init_db()
    seed_users()
    seed_history(days=45)
    print("\nDone. Run `streamlit run app.py` to explore the dashboard.")
