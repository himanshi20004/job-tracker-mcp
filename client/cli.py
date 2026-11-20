"""Conversational CLI for the Job Tracker MCP server.

Run from the project root:  python client/cli.py
Type commands ("add", "list", "stale", "compare"...) or just chat ("show my pipeline").
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from mcp_client import ROOT, JobTrackerClient

console = Console()

STATUSES = ("wishlist", "applied", "screening", "interview", "offer", "rejected", "withdrawn")
STATUS_STYLE = {
    "wishlist": "magenta", "applied": "cyan", "screening": "yellow", "interview": "bright_blue",
    "offer": "bold green", "rejected": "red", "withdrawn": "grey50",
}

HELP = [
    ("add", "Log a new application  (or: add Google, Data Analyst)"),
    ("list [status]", "Show your pipeline  (e.g. list interview)"),
    ("status <id> <new status>", "Move an application  (e.g. status 3 interview)"),
    ("followed <id>", "Mark that you followed up"),
    ("stale [days]", "Applications with no follow-up  (default 7 days)"),
    ("compare", "Resume vs job description: matched & missing keywords"),
    ("tailor", "Build an AI prompt that tailors your bullets to a job"),
    ("prep", "Build an interview-prep prompt for a company/role"),
    ("profile", "View your master profile"),
    ("help / exit", "Show this list / quit"),
]


# ------------------------------------------------------------------ helpers
def ago(days: int) -> str:
    return "today" if days <= 0 else f"{days}d ago"


def apps_table(apps: list[dict], title: str) -> Table:
    table = Table(title=title, box=box.ROUNDED, header_style="bold cyan",
                  title_style="bold", title_justify="left")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Company", style="bold")
    table.add_column("Role")
    table.add_column("Status")
    table.add_column("Last activity", justify="right")
    table.add_column("Link", justify="center")
    for a in apps:
        style = STATUS_STYLE.get(a["status"], "white")
        link = f"[link={a['link']}]open[/link]" if a.get("link") else "[dim]-[/dim]"
        table.add_row(str(a["id"]), escape(a["company"]), escape(a["role"]),
                      f"[{style}]{a['status']}[/{style}]", ago(a["days_since_activity"]), link)
    return table


def ok_panel(message: str) -> None:
    console.print(Panel(message, border_style="green", box=box.ROUNDED, expand=False))


def fail(message: str) -> None:
    console.print(Panel(escape(message), border_style="red", title="Oops", box=box.ROUNDED, expand=False))


def read_multiline(label: str, optional: bool = False) -> str:
    """Read pasted text until a line that says END. Also accepts @path/to/file.txt."""
    console.print(f"[bold]{label}[/bold] [dim](type END on its own line when done, or use @path/to/file.txt)[/dim]")
    lines: list[str] = []
    while True:
        try:
            line = console.input("[dim]|[/dim] ")
        except EOFError:
            break
        stripped = line.strip()
        if not lines:
            if stripped.startswith("@"):
                path = Path(stripped[1:].strip().strip('"')).expanduser()
                if path.is_file():
                    return path.read_text(encoding="utf-8", errors="ignore")
                console.print(f"[red]File not found: {escape(str(path))}[/red]")
                continue
            if not stripped and optional:
                return ""
        if stripped.upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def ask_int(label: str) -> int | None:
    raw = Prompt.ask(label)
    return int(raw) if raw.strip().isdigit() else None


def ask_status() -> str:
    return Prompt.ask("Status", choices=list(STATUSES), default="applied")


# ------------------------------------------------------------------ commands
async def dashboard(api: JobTrackerClient) -> None:
    data = await api.pipeline()  # MCP resource: applications://pipeline
    stale = await api.call("list_stale_followups", days_inactive=7)
    counts = data["by_status"]
    parts = [f"[{STATUS_STYLE[s]}]{counts[s]} {s}[/]" for s in STATUSES if counts.get(s)]
    summary = "  |  ".join(parts) if parts else "[dim]No applications yet. Type [bold]add[/bold] to log your first one.[/dim]"
    console.print(Panel(f"[bold]{data['total']}[/bold] applications tracked\n{summary}",
                        title="Your pipeline", border_style="cyan", box=box.ROUNDED))
    if stale.get("count"):
        top = ", ".join(f"{escape(a['company'])} ({a['days_since_activity']}d)" for a in stale["applications"][:3])
        console.print(Panel(f"[yellow]{stale['count']} application(s) have had no activity for 7+ days:[/yellow] {top}\n"
                            "[dim]Type [bold]stale[/bold] to see them all.[/dim]",
                           title="Follow-up reminder", border_style="yellow", box=box.ROUNDED))


async def cmd_list(api: JobTrackerClient, status: str | None = None) -> None:
    data = await api.pipeline()
    apps = [a for a in data["applications"] if not status or a["status"] == status]
    if not apps:
        console.print("[dim]Nothing here yet. Type [bold]add[/bold] to log an application.[/dim]")
        return
    console.print(apps_table(apps, f"Applications ({status or 'all'})"))


async def cmd_add(api: JobTrackerClient, company: str = "", role: str = "") -> None:
    company = company or Prompt.ask("Company")
    role = role or Prompt.ask("Role")
    status = ask_status()
    link = Prompt.ask("Job link [dim](optional)[/dim]", default="", show_default=False)
    notes = Prompt.ask("Notes [dim](optional)[/dim]", default="", show_default=False)
    res = await api.call("add_application", company=company, role=role, status=status, link=link, notes=notes)
    if res.get("ok"):
        a = res["application"]
        ok_panel(f"Added [bold]#{a['id']}[/bold]  {escape(a['company'])} - {escape(a['role'])}  [dim]({a['status']})[/dim]")
    else:
        fail(res.get("error", "Could not add application."))


async def cmd_status(api: JobTrackerClient, app_id: int | None, status: str | None) -> None:
    if app_id is None:
        app_id = ask_int("Application ID")
    if app_id is None:
        return fail("That is not a valid ID. Use 'list' to see IDs.")
    status = status or ask_status()
    note = Prompt.ask("Note [dim](optional)[/dim]", default="", show_default=False)
    res = await api.call("update_status", app_id=app_id, status=status, note=note)
    if res.get("ok"):
        a = res["application"]
        ok_panel(f"#{a['id']} {escape(a['company'])} is now [bold]{a['status']}[/bold]")
    else:
        fail(res.get("error", "Update failed."))


async def cmd_followed(api: JobTrackerClient, app_id: int | None) -> None:
    if app_id is None:
        app_id = ask_int("Application ID")
    if app_id is None:
        return fail("That is not a valid ID. Use 'stale' or 'list' to see IDs.")
    res = await api.call("mark_followed_up", app_id=app_id)
    if res.get("ok"):
        ok_panel(f"Logged follow-up for #{app_id} {escape(res['application']['company'])}. Clock reset.")
    else:
        fail(res.get("error", "Update failed."))


async def cmd_stale(api: JobTrackerClient, days: int = 7) -> None:
    res = await api.call("list_stale_followups", days_inactive=days)
    if not res.get("ok"):
        return fail(res.get("error", "Could not fetch follow-ups."))
    if not res["count"]:
        return ok_panel(f"All caught up. Nothing has been quiet for {days}+ days.")
    console.print(apps_table(res["applications"], f"Needs a follow-up ({days}+ days quiet)"))
    console.print("[dim]After you follow up, run [bold]followed <id>[/bold].[/dim]")


async def cmd_compare(api: JobTrackerClient) -> None:
    path = Prompt.ask("Resume file [dim](.pdf .docx .txt .md; Enter = master profile)[/dim]",
                      default="", show_default=False)
    jd = read_multiline("Paste the job description")
    if not jd:
        return fail("No job description given.")
    with console.status("Comparing keywords..."):
        res = await api.call("compare_resume_to_jd", resume_path=path, jd_text=jd)
    if not res.get("ok"):
        return fail(res.get("error", "Comparison failed."))

    score = res["score"]
    color = "green" if score >= 75 else "yellow" if score >= 50 else "red"
    filled = score // 5
    bar = Text.assemble((f"{score}%  ", f"bold {color}"), ("█" * filled, color),
                        ("░" * (20 - filled), "grey37"), (f"   {res['verdict']}", "white"))
    console.print(Panel(bar, title=f"Match: {escape(res['resume_source'])}", border_style=color, box=box.ROUNDED))

    matched = "\n".join(f"[green]✔[/green] {escape(s)}" for s in res["matched"]) or "[dim]none[/dim]"
    missing = "\n".join(f"[red]✘[/red] {escape(s)}" for s in res["missing"]) or "[dim]none, great![/dim]"
    console.print(Columns([
        Panel(matched, title=f"In your resume ({len(res['matched'])})", border_style="green", box=box.ROUNDED),
        Panel(missing, title=f"Missing ({len(res['missing'])})", border_style="red", box=box.ROUNDED),
    ], equal=True, expand=True))

    if res["other_terms_missing"]:
        console.print("[bold]Other repeated words not in your resume:[/bold] "
                      + ", ".join(escape(w) for w in res["other_terms_missing"]))
    for tip in res["suggestions"]:
        console.print(f"[dim]-[/dim] {escape(tip)}")
    console.print("[dim]Next: run [bold]tailor[/bold] to generate an AI prompt that rewrites your bullets.[/dim]")


async def show_generated_prompt(text: str, name: str, title: str) -> None:
    out_dir = ROOT / "exports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text(text, encoding="utf-8")
    console.print(Panel(Text(text), title=title, border_style="cyan", box=box.ROUNDED, padding=(1, 2)))
    ok_panel(f"Saved to [bold]{out.relative_to(ROOT)}[/bold]\n"
             "Paste it into any free AI chat (ChatGPT, Gemini, Claude, or local Ollama).")


async def cmd_tailor(api: JobTrackerClient) -> None:
    jd = read_multiline("Paste the job description")
    if not jd:
        return fail("No job description given.")
    focus = Prompt.ask("Any focus? [dim](e.g. backend, Enter to skip)[/dim]", default="", show_default=False)
    text = await api.prompt("tailor_bullet_points", job_description=jd, role_focus=focus)
    await show_generated_prompt(text, "tailor_bullet_points", "Tailor-my-bullets prompt")


async def cmd_prep(api: JobTrackerClient) -> None:
    company = Prompt.ask("Company")
    role = Prompt.ask("Role")
    jd = read_multiline("Job description (optional, press Enter to skip)", optional=True)
    text = await api.prompt("interview_prep_brief", company=company, role=role, job_description=jd)
    await show_generated_prompt(text, "interview_prep", f"Interview prep: {company}")


async def cmd_profile(api: JobTrackerClient) -> None:
    text = await api.master_profile()  # MCP resource: resume://master-profile
    console.print(Panel(Markdown(text), title="Master profile", border_style="cyan", box=box.ROUNDED, padding=(1, 2)))
    console.print("[dim]Edit it any time in [bold]data/master_profile.md[/bold].[/dim]")


def show_help() -> None:
    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", title="What you can do", title_justify="left")
    table.add_column("Command", style="bold")
    table.add_column("What it does")
    for cmd, desc in HELP:
        table.add_row(cmd, desc)
    console.print(table)
    console.print('[dim]You can also just chat: "show my pipeline", "which applications need a follow-up?", '
                  '"move 3 to interview".[/dim]')


# ------------------------------------------------------------------ understanding what you typed
def parse(raw: str) -> tuple[str, dict]:
    t = raw.strip().lower().lstrip("/")
    nums = [int(n) for n in re.findall(r"\d+", t)]
    status_word = next((s for s in STATUSES if re.search(rf"\b{s}\b", t)), None)

    if re.match(r"(exit|quit|q|bye|goodbye)\b", t):
        return "exit", {}
    if t in {"?", "h"} or re.search(r"\b(help|commands)\b", t):
        return "help", {}
    if re.match(r"(add|log|new)\b", t) or "applied to" in t:
        m = re.match(r"\s*/?(?:add|log|new)\s+(.+?)\s*(?:,|;|\s[-–—]\s)\s*(.+)$", raw.strip(), re.I)
        return "add", ({"company": m.group(1).strip(), "role": m.group(2).strip()} if m else {})
    if re.match(r"(followed|mark|done)\b", t) or (nums and re.search(r"\bfollowed\b", t)):
        return "followed", {"app_id": nums[0] if nums else None}
    if re.search(r"stale|follow|remind|inactive|overdue|no (reply|response)|haven'?t|nudge", t):
        return "stale", {"days": nums[0] if nums else 7}
    if re.match(r"(status|move|update|set)\b", t) and nums:
        return "status", {"app_id": nums[0], "status": status_word}
    if re.search(r"compare|match|keyword|missing|\bgap|\bats\b|score", t):
        return "compare", {}
    if re.search(r"tailor|bullet|rewrite", t):
        return "tailor", {}
    if re.search(r"\bprep\b|prepare|\bbrief\b", t):
        return "prep", {}
    if re.search(r"profile|master|resume", t):
        return "profile", {}
    if re.search(r"list|show|pipeline|\ball\b|applications|dashboard|overview|tracker", t) or status_word:
        return "list", {"status": status_word}
    return "unknown", {}


async def handle(api: JobTrackerClient, raw: str) -> bool:
    """Run one command. Returns False when the user wants to quit."""
    intent, args = parse(raw)
    if intent == "exit":
        return False
    if intent == "help":
        show_help()
    elif intent == "add":
        await cmd_add(api, **args)
    elif intent == "list":
        await cmd_list(api, **args)
    elif intent == "status":
        await cmd_status(api, **args)
    elif intent == "followed":
        await cmd_followed(api, **args)
    elif intent == "stale":
        await cmd_stale(api, **args)
    elif intent == "compare":
        await cmd_compare(api)
    elif intent == "tailor":
        await cmd_tailor(api)
    elif intent == "prep":
        await cmd_prep(api)
    elif intent == "profile":
        await cmd_profile(api)
    else:
        console.print("[dim]I did not catch that. Try [bold]help[/bold] to see what I can do.[/dim]")
    return True


# ------------------------------------------------------------------ main loop
async def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]Job Tracker[/bold cyan]  [dim]powered by MCP + FastMCP[/dim]\n"
        "[dim]Track applications. Match your resume. Never miss a follow-up.[/dim]",
        border_style="cyan", box=box.ROUNDED))
    try:
        async with JobTrackerClient() as api:
            caps = await api.capabilities()
            console.print(f"[dim]Connected to server: {caps['tools']} tools, "
                          f"{caps['resources']} resources, {caps['prompts']} prompts[/dim]\n")
            await dashboard(api)
            console.print('\n[dim]Type [bold]help[/bold] for commands, or just tell me what you need.[/dim]')
            while True:
                try:
                    raw = console.input("\n[bold cyan]you ›[/bold cyan] ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not raw:
                    continue
                try:
                    if not await handle(api, raw):
                        break
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Cancelled.[/dim]")
                except Exception as exc:  # keep the chat alive on unexpected errors
                    fail(f"Something went wrong: {exc}")
    except Exception as exc:
        fail(f"Could not start the MCP server: {exc}")
        return
    console.print("\n[dim]Good luck with the applications![/dim]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Bye![/dim]")