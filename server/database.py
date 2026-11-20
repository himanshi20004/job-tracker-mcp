"""SQLite storage layer for the Job Tracker (standard library only)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("JOB_TRACKER_DATA_DIR", ROOT / "data"))

STATUSES = ("wishlist", "applied", "screening", "interview", "offer", "rejected", "withdrawn")
# Statuses where a follow-up still makes sense
ACTIVE_STATUSES = ("applied", "screening", "interview")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company       TEXT NOT NULL,
    role          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'applied',
    link          TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    applied_at    TEXT NOT NULL,
    last_activity TEXT NOT NULL
)
"""

DEFAULT_PROFILE = """# Master Profile
> Replace everything below with your own details. Keep it long and honest:
> this is the source of truth the tailoring prompts pull from.

## Summary
Final-year engineering student interested in AI and backend development.

## Skills
Python, SQL, FastAPI, Git, Docker, machine learning, PyTorch, pandas, numpy,
REST APIs, problem solving, communication, teamwork

## Projects
- **Sentiment Analyzer**: Built an NLP classifier in Python (scikit-learn) with 91% accuracy on 20k reviews.
- **Expense API**: Designed a REST API with FastAPI and PostgreSQL; containerised with Docker.
- **Portfolio Bot**: Created a chatbot using LangChain and an LLM for answering recruiter questions.

## Experience
- **Software Intern, Example Corp** (Jun-Aug 2026): Automated weekly reports with Python and SQL, saving 5 hours/week.

## Education
B.Tech in Computer Science, Example University (2023-2027)
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@contextmanager
def connect():
    """Open the database (creating it on first use) and commit/rollback automatically."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA_DIR / "jobs.db")
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    last = datetime.fromisoformat(d["last_activity"])
    d["days_since_activity"] = max((_now() - last).days, 0)
    return d


def add_application(company: str, role: str, status: str = "applied",
                    link: str = "", notes: str = "") -> dict:
    with connect() as conn:
        dup = conn.execute(
            "SELECT id FROM applications WHERE lower(company)=lower(?) AND lower(role)=lower(?) "
            "AND status NOT IN ('rejected','withdrawn')",
            (company, role),
        ).fetchone()
        if dup:
            return {"ok": False, "error": f"Already tracking {company} - {role} as #{dup['id']}."}
        now = _iso(_now())
        cur = conn.execute(
            "INSERT INTO applications (company, role, status, link, notes, applied_at, last_activity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (company, role, status, link, notes, now, now),
        )
        row = conn.execute("SELECT * FROM applications WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"ok": True, "application": _to_dict(row)}


def list_applications(status: str | None = None) -> list[dict]:
    query, params = "SELECT * FROM applications", ()
    if status:
        query, params = query + " WHERE status = ?", (status,)
    query += " ORDER BY last_activity DESC"
    with connect() as conn:
        return [_to_dict(r) for r in conn.execute(query, params)]


def update_application(app_id: int, status: str | None = None, note: str = "") -> dict | None:
    """Change status and/or add a note. Always resets the follow-up clock."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        if row is None:
            return None
        notes = row["notes"]
        if note:
            notes = f"{notes}\n[{_now():%Y-%m-%d}] {note}".strip()
        conn.execute(
            "UPDATE applications SET status=?, notes=?, last_activity=? WHERE id=?",
            (status or row["status"], notes, _iso(_now()), app_id),
        )
        row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    return _to_dict(row)


def stale_followups(days_inactive: int) -> list[dict]:
    """Active applications with no activity for at least `days_inactive` days (oldest first)."""
    cutoff = _iso(_now() - timedelta(days=days_inactive))
    marks = ",".join("?" * len(ACTIVE_STATUSES))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM applications WHERE status IN ({marks}) AND last_activity <= ? "
            "ORDER BY last_activity ASC",
            (*ACTIVE_STATUSES, cutoff),
        ).fetchall()
    return [_to_dict(r) for r in rows]


def counts_by_status() -> dict[str, int]:
    with connect() as conn:
        found = {r["status"]: r["n"] for r in
                 conn.execute("SELECT status, COUNT(*) AS n FROM applications GROUP BY status")}
    return {s: found.get(s, 0) for s in STATUSES}


def find_application(company: str, role: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE lower(company)=lower(?) AND lower(role)=lower(?) "
            "ORDER BY id DESC LIMIT 1", (company, role)).fetchone()
    return _to_dict(row) if row else None


def read_profile() -> str:
    """Return the master profile, creating a starter template on first use."""
    path = DATA_DIR / "master_profile.md"
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_PROFILE, encoding="utf-8")
    return path.read_text(encoding="utf-8")