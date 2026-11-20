"""Job Tracker MCP server (FastMCP).

Run directly:   python server/server.py          (stdio, used by the client)
HTTP mode:      python server/server.py --http   (http://127.0.0.1:8000/mcp)
Inspector UI:   fastmcp dev server/server.py
"""
from __future__ import annotations

import json
import sys

from fastmcp import FastMCP

import analyzer
import database as db

mcp = FastMCP(
    name="job-tracker",
    instructions=(
        "Tracks job applications, compares resumes to job descriptions and prepares "
        "tailoring / interview prompts. Statuses: " + ", ".join(db.STATUSES) + "."
    ),
)


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


# ================================================================= TOOLS
@mcp.tool()
def add_application(company: str, role: str, status: str = "applied",
                    link: str = "", notes: str = "") -> dict:
    """Log a new job application.

    Args:
        company: Company name, e.g. "Google".
        role: Job title, e.g. "Data Analyst".
        status: One of wishlist, applied, screening, interview, offer, rejected, withdrawn.
        link: URL of the job posting (optional).
        notes: Any note to remember (optional).
    """
    company, role, status = company.strip(), role.strip(), status.strip().lower()
    if not company or not role:
        return _err("Both company and role are required.")
    if status not in db.STATUSES:
        return _err(f"Status must be one of: {', '.join(db.STATUSES)}")
    return db.add_application(company, role, status, link.strip(), notes.strip())


@mcp.tool()
def update_status(app_id: int, status: str, note: str = "") -> dict:
    """Move an application to a new status (e.g. applied -> interview). Resets the follow-up clock."""
    status = status.strip().lower()
    if status not in db.STATUSES:
        return _err(f"Status must be one of: {', '.join(db.STATUSES)}")
    app = db.update_application(app_id, status=status, note=note.strip())
    return {"ok": True, "application": app} if app else _err(f"No application with id {app_id}.")


@mcp.tool()
def mark_followed_up(app_id: int, note: str = "Followed up") -> dict:
    """Record that you followed up on an application, so it stops showing as stale."""
    app = db.update_application(app_id, note=note.strip() or "Followed up")
    return {"ok": True, "application": app} if app else _err(f"No application with id {app_id}.")


@mcp.tool()
def list_applications(status: str = "") -> dict:
    """List applications, newest activity first. Optionally filter by status."""
    status = status.strip().lower()
    if status and status not in db.STATUSES:
        return _err(f"Status must be one of: {', '.join(db.STATUSES)}")
    apps = db.list_applications(status or None)
    return {"ok": True, "count": len(apps), "applications": apps}


@mcp.tool()
def compare_resume_to_jd(resume_path: str, jd_text: str) -> dict:
    """Compare a resume with a job description and report matched / missing keywords.

    Args:
        resume_path: Path to a .txt, .md, .pdf or .docx resume. Leave empty or use
            "master" to use the master profile.
        jd_text: The full text of the job description.
    """
    if not jd_text.strip():
        return _err("jd_text is empty. Paste the job description.")
    try:
        resume_text = analyzer.read_resume_text(resume_path, db.read_profile())
    except Exception as exc:  # file missing, bad type, missing library...
        return _err(str(exc))
    if not resume_text.strip():
        return _err("The resume looks empty (scanned PDFs have no extractable text).")
    source = "master profile" if not resume_path.strip() or resume_path.strip().lower() in {
        "master", "profile", "resume://master-profile"} else resume_path
    return {"ok": True, "resume_source": source, **analyzer.compare(resume_text, jd_text)}


@mcp.tool()
def list_stale_followups(days_inactive: int = 7) -> dict:
    """List active applications (applied / screening / interview) with no activity
    for at least `days_inactive` days, oldest first."""
    if days_inactive < 0:
        return _err("days_inactive must be 0 or more.")
    apps = db.stale_followups(days_inactive)
    return {"ok": True, "days_inactive": days_inactive, "count": len(apps), "applications": apps}


# ================================================================= RESOURCES
@mcp.resource("applications://pipeline", mime_type="application/json")
def pipeline() -> str:
    """Your full application pipeline with counts per status."""
    apps = db.list_applications()
    return json.dumps({"total": len(apps), "by_status": db.counts_by_status(),
                       "applications": apps}, indent=2)


@mcp.resource("resume://master-profile", mime_type="text/markdown")
def master_profile() -> str:
    """Your master resume profile (data/master_profile.md)."""
    return db.read_profile()


# ================================================================= PROMPTS
@mcp.prompt()
def tailor_bullet_points(job_description: str, role_focus: str = "") -> str:
    """Prompt that rewrites your master-profile bullets for a specific job description."""
    focus = f"\nExtra focus: emphasise {role_focus}.\n" if role_focus.strip() else ""
    return f"""You are an expert resume writer and ATS specialist.

## Job description
{job_description}

## My master profile
{db.read_profile()}
{focus}
## Task
1. Choose the 5-7 most relevant experiences/projects from my profile for this role.
2. Rewrite each as one strong bullet: action verb + what I did + measurable result.
3. Use keywords from the job description ONLY where my profile truthfully supports them.
4. Never invent experience, tools or numbers.
5. Output the tailored bullets, then a "Keywords used" list, then a "Gaps to address" list."""


@mcp.prompt()
def interview_prep_brief(company: str, role: str, job_description: str = "") -> str:
    """Prompt that builds an interview prep brief for a company and role."""
    app = db.find_application(company, role)
    notes = f"\n## My notes on this application\n{app['notes']}\n" if app and app["notes"] else ""
    jd = f"\n## Job description\n{job_description}\n" if job_description.strip() else ""
    return f"""You are a senior interviewer and career coach.

Prepare me for an interview for **{role}** at **{company}**.
{jd}{notes}
## My profile
{db.read_profile()}

## Produce
1. What to research about {company} (list items to verify yourself; do not invent facts).
2. 8 likely technical questions with short model answers.
3. 5 behavioural questions, each mapped to a STAR story from MY profile.
4. 5 smart questions I should ask the interviewer.
5. A 3-point "why me" pitch.
6. Weak spots in my profile for this role and how to address them."""


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="http", host="127.0.0.1", port=8000, show_banner=False)
    else:
        mcp.run(show_banner=False)