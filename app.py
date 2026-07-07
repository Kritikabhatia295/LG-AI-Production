"""
app.py
------
LG Electronics Production Dashboard & AI Assistant.

Run with:
    streamlit run app.py
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import config
import database
import chatbot
import email_alert

st.set_page_config(page_title="LG Production Dashboard", page_icon="🏭", layout="wide")
database.init_db()


# ============================================================
# AUTH
# ============================================================
def login_page():
    st.title("🏭 LG Electronics — Production Dashboard")
    st.subheader("Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        user = database.verify_user(username, password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.caption(
        f"First time running this project? Default admin login is "
        f"**{config.DEFAULT_ADMIN_USERNAME} / {config.DEFAULT_ADMIN_PASSWORD}** "
        f"— change it after logging in."
    )


def logout_button():
    with st.sidebar:
        st.markdown(f"**Logged in as:** {st.session_state['user']['username']}")
        st.markdown(f"**Role:** {st.session_state['user']['role']}")
        if st.button("Log out"):
            del st.session_state["user"]
            st.rerun()


# ============================================================
# DASHBOARD
# ============================================================
def dashboard_page():
    st.header("📊 Today's Production Dashboard")
    today = datetime.now().date().isoformat()
    df = database.get_today_summary(today)

    cols = st.columns(3)
    for i, row in df.iterrows():
        with cols[i]:
            st.markdown(f"### {row['line']}")
            st.metric("Target", int(row["target"]))
            st.metric("Produced", int(row["produced"]))
            defect_rate = row["defect_rate_%"]
            delta_color = "inverse" if defect_rate >= config.DEFECT_RATE_THRESHOLD else "normal"
            st.metric(
                "Defected",
                int(row["defected"]),
                delta=f"{defect_rate}% defect rate",
                delta_color=delta_color,
            )
            if row["produced"] == 0:
                st.info("No data entered for today yet.")
            elif defect_rate >= config.DEFECT_RATE_THRESHOLD or row["defected"] >= config.DEFECT_COUNT_THRESHOLD:
                st.error("⚠️ Defect threshold breached — an alert should have been sent.")
            else:
                st.success("Within acceptable defect range.")

    st.divider()
    st.subheader("Target vs Produced vs Defected — Today")
    if df["produced"].sum() > 0:
        chart_df = df.set_index("line")[["target", "produced", "defected"]]
        st.bar_chart(chart_df)
    else:
        st.caption("Enter today's data to see the chart.")


# ============================================================
# ADD / UPDATE DATA
# ============================================================
def add_data_page():
    st.header("➕ Add / Update Today's Production Data")
    lines = database.get_lines()
    line_names = [l["name"] for l in lines]

    with st.form("data_entry_form"):
        line_name = st.selectbox("Production Line", line_names)
        date = st.date_input("Date", value=datetime.now().date())
        target = st.number_input("Target (units)", min_value=0, step=1)
        produced = st.number_input("Produced (units)", min_value=0, step=1)
        defected = st.number_input("Defected (units)", min_value=0, step=1)
        submitted = st.form_submit_button("Save entry")

    if submitted:
        line_id = database.get_line_id_by_name(line_name)
        date_str = date.isoformat()
        database.upsert_daily_record(line_id, date_str, target, produced, defected)
        st.success(f"Saved {line_name} data for {date_str}.")

        status = email_alert.check_and_alert(line_id, line_name, date_str, target, produced, defected)
        if status:
            if status.startswith("SENT"):
                st.warning("Defect threshold breached — alert email sent to production/branch head.")
            else:
                st.warning(f"Defect threshold breached, but the alert email failed: {status}")
        else:
            st.info("Defect levels are within the normal range — no alert triggered.")


# ============================================================
# HISTORY
# ============================================================
def history_page():
    st.header("📅 Production History")
    lines = database.get_lines()
    line_names = ["All lines"] + [l["name"] for l in lines]

    col1, col2 = st.columns(2)
    with col1:
        selected_line = st.selectbox("Line", line_names)
    with col2:
        days = st.slider("Number of past days", min_value=7, max_value=90, value=30, step=1)

    line_filter = None if selected_line == "All lines" else selected_line
    df = database.get_history(line_name=line_filter, days=days)

    if df.empty:
        st.info("No historical data found for this selection.")
        return

    st.dataframe(df, use_container_width=True)

    if line_filter:
        st.subheader(f"{line_filter} — Trend")
        chart_df = df.set_index("date")[["target", "produced", "defected"]]
        st.line_chart(chart_df)
    else:
        st.subheader("Total produced per line (selected period)")
        totals = df.groupby("line")[["target", "produced", "defected"]].sum()
        st.bar_chart(totals)


# ============================================================
# CHATBOT
# ============================================================
def chatbot_page():
    st.header("💬 AI Production Assistant")
    st.caption(
        "Ask about targets, production counts, defects, or history — e.g. "
        "\"How many defects in AC line today?\" or \"Show refrigerator history for last 14 days\"."
    )

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for role, msg in st.session_state["chat_history"]:
        with st.chat_message(role):
            st.markdown(msg)

    user_msg = st.chat_input("Type your question...")
    if user_msg:
        st.session_state["chat_history"].append(("user", user_msg))
        with st.chat_message("user"):
            st.markdown(user_msg)

        reply = chatbot.answer(user_msg)
        st.session_state["chat_history"].append(("assistant", reply))
        with st.chat_message("assistant"):
            st.markdown(reply)


# ============================================================
# ALERTS LOG
# ============================================================
def alerts_page():
    st.header("🚨 Alerts Log")
    df = database.get_alerts()
    if df.empty:
        st.info("No alerts have been triggered yet.")
    else:
        st.dataframe(df, use_container_width=True)


# ============================================================
# MANAGE USERS (admin only)
# ============================================================
def manage_users_page():
    st.header("👤 Manage Users")
    lines = database.get_lines()
    line_options = {l["name"]: l["id"] for l in lines}

    with st.form("add_user_form"):
        st.subheader("Add a new user")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["operator", "production_head", "branch_head", "admin"])
        email = st.text_input("Email (used for alerts if role is production_head / branch_head)")
        assigned_line = None
        if role == "production_head":
            assigned_line_name = st.selectbox("Assigned line", list(line_options.keys()))
            assigned_line = line_options[assigned_line_name]
        submitted = st.form_submit_button("Create user")

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        else:
            ok, msg = database.create_user(username, password, role, email, assigned_line)
            st.success(msg) if ok else st.error(msg)

    st.subheader("Existing users")
    st.dataframe(database.get_all_users(), use_container_width=True)


# ============================================================
# MAIN ROUTING
# ============================================================
def main():
    if "user" not in st.session_state:
        login_page()
        return

    logout_button()
    role = st.session_state["user"]["role"]

    pages = {
        "Dashboard": dashboard_page,
        "Chatbot Assistant": chatbot_page,
        "History & Trends": history_page,
        "Alerts Log": alerts_page,
    }
    if role in ("admin", "operator"):
        pages["Add Production Data"] = add_data_page
    if role == "admin":
        pages["Manage Users"] = manage_users_page

    with st.sidebar:
        choice = st.radio("Navigate", list(pages.keys()))

    pages[choice]()


if __name__ == "__main__":
    main()
