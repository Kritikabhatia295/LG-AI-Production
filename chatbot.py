"""
chatbot.py
----------
A lightweight, rule-based "AI assistant" for the dashboard. It doesn't
call any external LLM - it matches the question against known patterns
(keywords + regex) and pulls the answer straight from the database.
This keeps the whole project self-contained and free to run.

(If you later want smarter natural-language understanding, you can
swap `answer()` to call the Anthropic API instead - the function
signature below already returns a plain string, so the rest of the
app doesn't need to change.)
"""

import re
from datetime import datetime

import config
import database


def _find_line(text: str):
    text = text.lower()
    # Check longer aliases first (e.g. "air conditioner" before "ac"), and use
    # word-boundary matching so short aliases like "ac" don't match inside
    # unrelated words (e.g. the "ac" inside "machine").
    for alias in sorted(config.LINE_ALIASES, key=len, reverse=True):
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, text):
            return config.LINE_ALIASES[alias]
    return None


def _find_days(text: str, default=7):
    match = re.search(r"last (\d+) day", text.lower())
    if match:
        return int(match.group(1))
    if "week" in text.lower():
        return 7
    if "month" in text.lower():
        return 30
    return default


def answer(query: str) -> str:
    text = query.lower().strip()
    today = datetime.now().date().isoformat()

    if not text:
        return "Ask me about targets, production, defects, or history for any line."

    # Greetings / help
    if any(w in text for w in ["hello", "hi ", "hey"]) or text in ("hi", "hello", "hey"):
        return (
            "Hello! I'm the LG Production Assistant. Try asking things like:\n"
            "- \"What's today's target for the AC line?\"\n"
            "- \"How many defects in refrigerator today?\"\n"
            "- \"Show me washing machine history for the last 7 days\"\n"
            "- \"Summary of all lines today\""
        )
    if "help" in text or "what can you do" in text:
        return (
            "I can tell you, for any line (Refrigerator / Air Conditioner / Washing Machine):\n"
            "- today's target, produced count, and defect count\n"
            "- today's defect rate\n"
            "- history over the last N days\n"
            "- a summary across all three lines"
        )

    line = _find_line(text)

    # Summary across all lines
    if ("summary" in text or "all lines" in text or "overview" in text) and not line:
        df = database.get_today_summary(today)
        lines_txt = []
        for _, r in df.iterrows():
            lines_txt.append(
                f"- {r['line']}: target {r['target']}, produced {r['produced']}, "
                f"defected {r['defected']} ({r['defect_rate_%']}% defect rate)"
            )
        return f"Today's summary ({today}):\n" + "\n".join(lines_txt)

    # History query
    if "history" in text or "past" in text or "trend" in text:
        days = _find_days(text)
        df = database.get_history(line_name=line, days=days)
        if df.empty:
            return f"No history found for the last {days} days" + (f" for {line}." if line else ".")
        if line:
            rows = "\n".join(
                f"- {r['date']}: target {r['target']}, produced {r['produced']}, defected {r['defected']}"
                for _, r in df.iterrows()
            )
            return f"{line} - last {days} days:\n{rows}"
        else:
            summary = df.groupby("line")[["target", "produced", "defected"]].sum()
            rows = "\n".join(
                f"- {ln}: total target {row['target']}, total produced {row['produced']}, "
                f"total defected {row['defected']}"
                for ln, row in summary.iterrows()
            )
            return f"Totals across all lines - last {days} days:\n{rows}"

    # Line-specific "today" queries
    if line:
        line_id = database.get_line_id_by_name(line)
        record = database.get_record(line_id, today)
        if not record:
            return f"No production data has been entered yet for {line} today ({today})."

        defect_rate = (
            round(record["defected"] / record["produced"] * 100, 2) if record["produced"] else 0.0
        )

        if "target" in text:
            return f"Today's target for {line} is {record['target']} units."
        if "defect" in text:
            return (
                f"{line} has {record['defected']} defected units today out of "
                f"{record['produced']} produced ({defect_rate}% defect rate)."
            )
        if "produc" in text:
            return f"{line} has produced {record['produced']} units today (target: {record['target']})."
        if "rate" in text:
            return f"{line}'s defect rate today is {defect_rate}%."

        # No specific metric asked -> give the full picture
        return (
            f"{line} today - Target: {record['target']}, Produced: {record['produced']}, "
            f"Defected: {record['defected']} ({defect_rate}% defect rate)."
        )

    return (
        "I didn't quite catch which line or metric you mean. Try naming a line "
        "(Refrigerator / Air Conditioner / Washing Machine) and a metric "
        "(target, produced, defects, history)."
    )
