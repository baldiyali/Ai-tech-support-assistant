"""Knowledge base loading and TF-IDF retrieval.

Each article is a markdown file with a small front-matter header
(id, title, category, keywords) and sections for symptoms, numbered
troubleshooting steps, escalation criteria and a recommended next action.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_DIR = Path(__file__).resolve().parent.parent / "kb"


@dataclass
class Article:
    id: str
    title: str
    category: str
    keywords: list[str]
    body: str
    steps: list[str] = field(default_factory=list)
    escalate_when: list[str] = field(default_factory=list)
    next_action: str = ""

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "category": self.category}


def _section(body: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def parse_article(text: str) -> Article:
    meta: dict[str, str] = {}
    body = text
    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if fm:
        for line in fm.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        body = fm.group(2)
    steps = [re.sub(r"^\d+\.\s*", "", s).strip()
             for s in re.findall(r"^\d+\.\s+.+$", _section(body, "Troubleshooting Steps"), re.M)]
    escalate = [s[2:].strip() for s in _section(body, "When to Escalate").splitlines() if s.startswith("- ")]
    return Article(
        id=meta.get("id", ""),
        title=meta.get("title", ""),
        category=meta.get("category", "other"),
        keywords=[k.strip() for k in meta.get("keywords", "").split(",") if k.strip()],
        body=body.strip(),
        steps=steps,
        escalate_when=escalate,
        next_action=_section(body, "Recommended Next Action"),
    )


class KnowledgeBase:
    """Loads markdown articles and ranks them against a query with TF-IDF."""

    def __init__(self, kb_dir: Path = KB_DIR):
        self.articles: list[Article] = [parse_article(p.read_text(encoding="utf-8"))
                                        for p in sorted(Path(kb_dir).glob("*.md"))]
        if not self.articles:
            raise RuntimeError(f"No knowledge base articles found in {kb_dir}")
        self.by_id = {a.id: a for a in self.articles}
        # Title and keywords are repeated so they weigh more than body text.
        corpus = [f"{a.title} {a.title} {' '.join(a.keywords) * 3} {a.body}" for a in self.articles]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, k: int = 3, min_score: float = 0.02) -> list[tuple[Article, float]]:
        if not query.strip():
            return []
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        ranked = sorted(zip(self.articles, scores), key=lambda x: x[1], reverse=True)
        return [(a, float(s)) for a, s in ranked[:k] if s >= min_score]

    def for_category(self, category: str) -> Article | None:
        return next((a for a in self.articles if a.category == category), None)
