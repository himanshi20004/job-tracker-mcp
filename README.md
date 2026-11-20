# Job Tracker MCP

Track job applications, compare your resume to a job description, and never miss a follow-up.
Built with **FastMCP** (server) and a **conversational CLI** client. 100% free: no API keys, no paid services.

## Features
| MCP piece | Name | What it does |
|---|---|---|
| Tool | `add_application` | Log a company, role, status and link |
| Tool | `compare_resume_to_jd` | Matched vs missing keywords + match score (txt/md/pdf/docx) |
| Tool | `list_stale_followups` | Active applications with no activity for N days |
| Tool | `update_status`, `mark_followed_up`, `list_applications` | Keep the pipeline current |
| Resource | `applications://pipeline` | Full pipeline as JSON |
| Resource | `resume://master-profile` | Your master resume (markdown) |
| Prompt | `tailor_bullet_points` | Rewrites your bullets for a job description |
| Prompt | `interview_prep_brief` | Interview prep brief for a company/role |

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python client/cli.py
```
Try it: `add Google, Data Analyst` · `list` · `compare` (use `data/sample_jd.txt`) · `stale 3`

Edit `data/master_profile.md` with your real resume details (it is git-ignored).

## Project layout
```
server/   FastMCP server (server.py), SQLite layer (database.py), keyword engine (analyzer.py)
client/   CLI (cli.py) and MCP client wrapper (mcp_client.py)
tests/    pytest tests
data/     master_profile.md, jobs.db (created on first run), sample_jd.txt
```

## Other ways to run
- Tests: `pytest`
- Inspector UI: `fastmcp dev server/server.py`
- HTTP transport: `python server/server.py --http`
- Plug the server into Claude Desktop or any MCP client via stdio: `python /full/path/server/server.py`
