import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import analyzer  # noqa: E402
import database  # noqa: E402


def test_compare_matched_and_missing():
    jd = "We need Python, SQL and Docker experience. Docker and Kubernetes are a plus."
    resume = "Built apps in Python with SQL."
    r = analyzer.compare(resume, jd)
    assert set(r["matched"]) == {"python", "sql"}
    assert set(r["missing"]) == {"docker", "kubernetes"}
    assert r["score"] == 50


def test_whole_word_matching():
    assert "java" not in analyzer.skill_counts("I love JavaScript")
    assert "sql" not in analyzer.skill_counts("MongoDB is NoSQL")
    assert "node.js" in analyzer.skill_counts("Experience with Node.js")
    assert "c++" in analyzer.skill_counts("Skilled in C++ and C#")


def test_database_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    first = database.add_application("Acme", "Data Analyst", "applied", "http://x.y", "")
    assert first["ok"]
    assert not database.add_application("acme", "data analyst")["ok"]  # duplicate

    app_id = first["application"]["id"]
    assert database.stale_followups(7) == []

    with database.connect() as conn:  # pretend it happened long ago
        conn.execute("UPDATE applications SET last_activity='2020-01-01T00:00:00+00:00'")
    assert len(database.stale_followups(7)) == 1

    database.update_application(app_id, note="Emailed recruiter")
    assert database.stale_followups(7) == []
    assert database.counts_by_status()["applied"] == 1
