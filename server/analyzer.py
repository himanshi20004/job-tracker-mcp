"""Resume <-> job description keyword matching (pure Python, no paid APIs)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

# canonical skill -> spellings that count as the same skill
SKILL_BANK: dict[str, tuple[str, ...]] = {
    # languages
    "python": ("python",), "java": ("java",), "javascript": ("javascript", "ecmascript"),
    "typescript": ("typescript",), "c++": ("c++",), "c#": ("c#",), "golang": ("golang",),
    "rust": ("rust",), "kotlin": ("kotlin",), "swift": ("swift",), "php": ("php",),
    "ruby": ("ruby",), "scala": ("scala",), "bash": ("bash", "shell scripting"),
    # data / databases
    "sql": ("sql",), "nosql": ("nosql",), "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",), "mongodb": ("mongodb", "mongo"), "redis": ("redis",),
    "pandas": ("pandas",), "numpy": ("numpy",), "spark": ("spark", "pyspark"),
    "hadoop": ("hadoop",), "kafka": ("kafka",), "airflow": ("airflow",), "etl": ("etl",),
    "data analysis": ("data analysis", "data analytics"),
    "data visualization": ("data visualization", "data visualisation", "dashboards"),
    "tableau": ("tableau",), "power bi": ("power bi", "powerbi"), "excel": ("excel",),
    "statistics": ("statistics", "statistical"), "a/b testing": ("a/b testing", "ab testing"),
    # web / backend
    "html": ("html", "html5"), "css": ("css", "css3"), "react": ("react", "reactjs", "react.js"),
    "angular": ("angular",), "vue": ("vue", "vue.js"), "next.js": ("next.js", "nextjs"),
    "node.js": ("node.js", "nodejs"), "express": ("express", "express.js"),
    "django": ("django",), "flask": ("flask",), "fastapi": ("fastapi",),
    "spring boot": ("spring boot", "springboot"),
    "rest api": ("rest", "restful", "rest api", "rest apis"), "graphql": ("graphql",),
    "api": ("api", "apis"), "microservices": ("microservices", "microservice"),
    # devops / cloud
    "docker": ("docker", "containerization", "containerisation"),
    "kubernetes": ("kubernetes", "k8s"), "aws": ("aws", "amazon web services"),
    "azure": ("azure",), "gcp": ("gcp", "google cloud"), "terraform": ("terraform",),
    "ci/cd": ("ci/cd", "cicd", "continuous integration"), "jenkins": ("jenkins",),
    "github actions": ("github actions",), "git": ("git", "github", "gitlab"),
    "linux": ("linux",),
    # AI / ML
    "machine learning": ("machine learning", "ml"), "deep learning": ("deep learning",),
    "nlp": ("nlp", "natural language processing"), "computer vision": ("computer vision",),
    "pytorch": ("pytorch",), "tensorflow": ("tensorflow",),
    "scikit-learn": ("scikit-learn", "sklearn"), "opencv": ("opencv",),
    "llm": ("llm", "llms", "large language model", "large language models"),
    "generative ai": ("generative ai", "genai", "gen ai"), "langchain": ("langchain",),
    "langgraph": ("langgraph",), "rag": ("rag", "retrieval augmented generation",
                                         "retrieval-augmented generation"),
    "prompt engineering": ("prompt engineering",),
    "mcp": ("mcp", "model context protocol"),
    # engineering practice
    "testing": ("unit testing", "pytest", "junit", "test automation", "tdd"),
    "system design": ("system design",), "oop": ("oop", "object-oriented", "object oriented"),
    "data structures": ("data structures",), "algorithms": ("algorithms",),
    "agile": ("agile",), "scrum": ("scrum",), "jira": ("jira",),
    # soft skills
    "communication": ("communication", "communicate"),
    "teamwork": ("teamwork", "collaboration", "collaborate", "team player"),
    "problem solving": ("problem solving", "problem-solving"),
    "leadership": ("leadership", "led a team", "team lead"),
    "project management": ("project management",),
    "stakeholder management": ("stakeholder", "stakeholders"),
    "mentoring": ("mentoring", "mentored", "mentor"),
}

STOPWORDS = set("""
about above across after also always another any are around ability able and applicants
apply based become been being best both build building but can candidate candidates
company could day days deliver does done drive each end ensure environment equal
etc every excellent experience familiar familiarity find first for from get give good
great have help high highly how including into job join just keep knowledge know
like look looking make many may more most must need needs new nice not offer one only
opportunity other our out over own part plus position preferred prefer required
requirements responsibilities responsible role skills small solid some strong such
take team teams than that the their them then there these they this those through
time to together understanding use using very want was way well were what when where
which while will with within without work working would year years you your
""".split())

_ALL_VARIANT_WORDS = {w for variants in SKILL_BANK.values() for v in variants
                      for w in re.split(r"[^a-z0-9]+", v) if w}


def _pattern(term: str) -> re.Pattern:
    # match whole terms only ("java" must not match "javascript", "sql" not "nosql")
    return re.compile(rf"(?<![a-z0-9+#]){re.escape(term)}(?![a-z0-9+#])")


_COMPILED = {skill: [_pattern(v) for v in variants] for skill, variants in SKILL_BANK.items()}


def skill_counts(text: str) -> Counter:
    """How many times each known skill appears in `text`."""
    t = text.lower()
    counts: Counter = Counter()
    for skill, patterns in _COMPILED.items():
        n = sum(len(p.findall(t)) for p in patterns)
        if n:
            counts[skill] = n
    return counts


def frequent_terms(text: str, limit: int = 10, min_count: int = 2) -> list[str]:
    """Repeated words in the JD that are not in the skill bank (e.g. domain words)."""
    words = [w.strip("-") for w in re.findall(r"[a-z][a-z0-9+#\-]{3,}", text.lower())]
    words = [w for w in words if w not in STOPWORDS and w not in _ALL_VARIANT_WORDS]
    return [w for w, n in Counter(words).most_common(limit * 2) if n >= min_count][:limit]


def _verdict(score: int) -> str:
    if score >= 75:
        return "Strong match. Polish a few bullets and apply."
    if score >= 50:
        return "Decent match. Add the missing keywords where you honestly have the experience."
    return "Weak match. Tailor your resume heavily, or consider if this role fits."


def compare(resume_text: str, jd_text: str) -> dict:
    jd_counts = skill_counts(jd_text)
    resume_skills = set(skill_counts(resume_text))
    jd_skills = sorted(jd_counts, key=lambda s: (-jd_counts[s], s))

    matched = [s for s in jd_skills if s in resume_skills]
    missing = [s for s in jd_skills if s not in resume_skills]

    resume_lower = resume_text.lower()
    other = frequent_terms(jd_text)
    other_matched = [w for w in other if _pattern(w).search(resume_lower)]
    other_missing = [w for w in other if w not in other_matched]

    if jd_skills:
        basis, score = "skills", round(100 * len(matched) / len(jd_skills))
    elif other:
        basis, score = "terms", round(100 * len(other_matched) / len(other))
    else:
        basis, score = "none", 0

    suggestions = [f"Add '{s}' to your resume if you genuinely have this experience." for s in missing[:5]]
    if basis == "none":
        suggestions = ["No recognisable keywords found. Is the job description pasted correctly?"]

    return {
        "score": score, "basis": basis, "verdict": _verdict(score),
        "matched": matched, "missing": missing,
        "other_terms_matched": other_matched, "other_terms_missing": other_missing,
        "suggestions": suggestions,
    }


def read_resume_text(path: str, master_text: str) -> str:
    """Read a resume from .txt/.md/.pdf/.docx. Empty path or 'master' uses the master profile."""
    if not path or path.strip().lower() in {"master", "profile", "resume://master-profile"}:
        return master_text
    p = Path(path.strip().strip('"')).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"Resume file not found: {path}")
    suffix = p.suffix.lower()
    if suffix in {".txt", ".md", ""}:
        return p.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("PDF support needs: pip install pypdf") from e
        return "\n".join((page.extract_text() or "") for page in PdfReader(str(p)).pages)
    if suffix == ".docx":
        try:
            import docx
        except ImportError as e:
            raise RuntimeError("DOCX support needs: pip install python-docx") from e
        return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    raise ValueError(f"Unsupported file type '{suffix}'. Use .txt, .md, .pdf or .docx")