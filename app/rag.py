"""Retrieval-augmented generation over approved KB articles and uploaded manuals.

* Approved (seeded) KB articles from ``kb/`` are always indexed.
* Users/admins can upload troubleshooting manuals (.md, .txt, .pdf). Text is
  extracted (pypdf for PDFs, page numbers kept for citations), split into
  overlapping chunks, stored in SQLite and indexed with TF-IDF.
* ``answer()`` retrieves the top chunks and grounds a reply in them with
  numbered citations. With an LLM key the answer is generated from the chunks;
  without one an extractive answer is composed from the best-matching sentences.
"""
from __future__ import annotations

import io
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import llm
from .kb import KnowledgeBase

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 500
CHUNK_OVERLAP = 120
CODE_BOOST = 0.25  # bonus per exact error-code match (hybrid lexical + TF-IDF scoring)
CODE_RE = re.compile(r"\b(?:[a-z]{1,4}-?\d{2,}|0x[0-9a-f]{4,})\b", re.I)
UNAPPROVED_WEIGHT = 0.9  # approved content wins ties against unreviewed uploads

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, n_chunks INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    pk INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL, ord INTEGER NOT NULL,
    section TEXT, text TEXT NOT NULL
);
"""


class UploadError(ValueError):
    pass


# ---------------------------------------------------------------- extraction & chunking
def extract_text(filename: str, data: bytes) -> list[tuple[str, str | None]]:
    """Return a list of (text, location) segments. PDFs yield one segment per page."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError(f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("File is larger than 10 MB.")
    if ext == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "", f"p. {i}") for i, page in enumerate(reader.pages, 1)]
        except Exception as exc:
            raise UploadError(f"Could not read PDF: {exc}") from exc
        pages = [(t, loc) for t, loc in pages if t.strip()]
        if not pages:
            raise UploadError("No extractable text found in the PDF (scanned images aren't supported).")
        return pages
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, flags=re.S)  # drop front matter
    if not text.strip():
        raise UploadError("The file has no text.")
    return [(text, None)]


def chunk_text(text: str, location: str | None = None, size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[tuple[str, str | None]]:
    """Split text into ~size-char chunks on paragraph boundaries, tracking markdown headings.

    Returns (chunk_text, section_label) pairs. The label combines the page (for PDFs)
    and the most recent heading so citations can point at a specific place.
    """
    chunks: list[tuple[str, str | None]] = []
    heading: str | None = None
    buf: list[str] = []

    def label() -> str | None:
        parts = [p for p in (location, heading) if p]
        return " · ".join(parts) or None

    def flush():
        if buf:
            body = "\n".join(buf).strip()
            if body:
                chunks.append((body, label()))
            buf.clear()

    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        para = para.strip()
        if not para:
            continue
        m = re.match(r"^#{1,6}\s+(.+)$", para.splitlines()[0])
        if m:
            flush()
            heading = m.group(1).strip()
            rest = "\n".join(para.splitlines()[1:]).strip()
            if not rest:
                continue
            para = rest
        if len(para) > size:  # long block (e.g. PDF page text): pack whole lines, overlap by a line
            flush()
            lines: list[str] = []
            for line in para.splitlines():
                while len(line) > size:  # pathological long line: hard window
                    lines.append(line[:size])
                    line = line[size - overlap:]
                lines.append(line)
            cur: list[str] = []
            for line in lines:
                if cur and sum(len(x) + 1 for x in cur) + len(line) > size:
                    chunks.append(("\n".join(cur).strip(), label()))
                    cur = [cur[-1]] if len(cur[-1]) <= overlap else []
                cur.append(line)
            if cur:
                chunks.append(("\n".join(cur).strip(), label()))
            continue
        if sum(len(b) for b in buf) + len(para) > size:
            prev_tail = buf[-1] if buf and len(buf[-1]) <= overlap * 2 else None
            flush()
            if prev_tail:  # carry a short trailing paragraph forward for context
                buf.append(prev_tail)
        buf.append(para)
    flush()
    return chunks


def _unwrap(text: str) -> list[tuple[str, bool]]:
    """Re-join lines that PDF extraction wrapped mid-sentence. Returns (line, is_list_item)."""
    out: list[list] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_item = bool(re.match(r"^(?:[-*]|\d+\.)\s+", line))
        if out and not is_item and not out[-1][0].rstrip().endswith((".", "!", "?", ":")) and (
                len(out[-1][0]) > 60 or line[:1].islower()):
            out[-1][0] += " " + line
        else:
            out.append([line, is_item])
    return [(l, i) for l, i in out]


def _sentences(text: str) -> list[str]:
    out = []
    for line, is_item in _unwrap(text):
        line = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip()
        if line.startswith("#") or (not is_item and len(line) < 60 and not re.search(r"[.!?]", line)):
            continue  # headings / titles are not answers
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line):
            sent = sent.strip()
            if len(sent) >= 25:
                out.append(sent)
    return out


# ---------------------------------------------------------------- index
class DocumentIndex:
    def __init__(self, kb: KnowledgeBase, db_path: str = ":memory:"):
        self.kb = kb
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._rebuild()

    # -- documents
    def _seed_docs(self) -> list[dict]:
        return [{"id": f"kb:{a.id}", "title": a.title, "filename": f"{a.id}.md", "status": "approved",
                 "origin": "seed", "created_at": None, "chunks": chunk_text(a.body)} for a in self.kb.articles]

    def list_documents(self) -> list[dict]:
        seeded = [{k: v for k, v in d.items() if k != "chunks"} | {"n_chunks": len(d["chunks"])}
                  for d in self._seed_docs()]
        uploaded = [dict(r) | {"origin": "upload"} for r in
                    self.conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()]
        return uploaded + seeded

    def add_document(self, filename: str, data: bytes, title: str | None = None,
                     approved: bool = False) -> dict:
        filename = Path(filename or "document.txt").name[:200]
        segments = extract_text(filename, data)
        chunks = [c for text, loc in segments for c in chunk_text(text, loc)]
        if not chunks:
            raise UploadError("No text could be extracted from the file.")
        doc_id = "up:" + uuid.uuid4().hex[:10]
        title = (title or "").strip()[:200] or Path(filename).stem.replace("-", " ").replace("_", " ").title()
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = "approved" if approved else "uploaded"
        self.conn.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                          (doc_id, title, filename, status, created, len(chunks)))
        self.conn.executemany("INSERT INTO chunks (doc_id, ord, section, text) VALUES (?, ?, ?, ?)",
                              [(doc_id, i, sec, txt) for i, (txt, sec) in enumerate(chunks)])
        self.conn.commit()
        self._rebuild()
        return self.get_document(doc_id)

    def get_document(self, doc_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) | {"origin": "upload"} if row else None

    def set_status(self, doc_id: str, status: str) -> dict | None:
        if status not in ("approved", "uploaded"):
            raise ValueError("status must be 'approved' or 'uploaded'")
        self.conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
        self.conn.commit()
        self._rebuild()
        return self.get_document(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.commit()
        self._rebuild()
        return cur.rowcount > 0

    # -- index
    def _rebuild(self):
        self.chunks: list[dict] = []
        for d in self._seed_docs():
            for i, (text, sec) in enumerate(d["chunks"]):
                self.chunks.append({"doc_id": d["id"], "title": d["title"], "status": "approved",
                                    "origin": "seed", "section": sec, "text": text, "ord": i})
        rows = self.conn.execute(
            "SELECT c.doc_id, c.ord, c.section, c.text, d.title, d.status FROM chunks c "
            "JOIN documents d ON d.id = c.doc_id ORDER BY c.doc_id, c.ord").fetchall()
        for r in rows:
            self.chunks.append({"doc_id": r["doc_id"], "title": r["title"], "status": r["status"],
                                "origin": "upload", "section": r["section"], "text": r["text"], "ord": r["ord"]})
        corpus = [f"{c['title']} {c['section'] or ''} {c['text']}" for c in self.chunks]
        # Token pattern keeps error codes like "E-49" or "0x0000007E" as single terms.
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
                                          token_pattern=r"(?u)\b(?:[a-z]+-\d+|\w\w+)\b")
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, k: int = 4, min_score: float = 0.05) -> list[dict]:
        if not query or not query.strip():
            return []
        sims = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        codes = {c.lower() for c in CODE_RE.findall(query)}
        scored = []
        for chunk, sim in zip(self.chunks, sims):
            score = float(sim)
            if codes and score > 0:  # exact error codes ("E-49", "0x0000007E") are very strong signals
                text = chunk["text"].lower()
                score += CODE_BOOST * sum(1 for c in codes if c in text)
            score *= 1.0 if chunk["status"] == "approved" else UNAPPROVED_WEIGHT
            if score >= min_score:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c | {"score": round(s, 3)} for s, c in scored[:k]]

    def answer(self, query: str, k: int = 3, max_points: int = 3) -> dict:
        """Retrieve top chunks and compose a grounded, cited answer."""
        hits = self.search(query, k=k)
        sources = [{"n": i, "doc_id": h["doc_id"], "title": h["title"], "status": h["status"],
                    "origin": h["origin"], "section": h["section"], "score": h["score"],
                    "snippet": h["text"][:400]} for i, h in enumerate(hits, 1)]
        if not hits:
            return {"answer": "", "sources": [], "mode": "none"}
        generated = llm.generate_grounded(query, hits)
        if generated:
            return {"answer": generated, "sources": sources, "mode": "llm"}
        # Extractive: score each sentence of the retrieved chunks against the query.
        qv = self.vectorizer.transform([query])
        candidates = [(n, s) for n, h in enumerate(hits, 1) for s in _sentences(h["text"])]
        if not candidates:
            return {"answer": "", "sources": sources, "mode": "extractive"}
        sims = cosine_similarity(qv, self.vectorizer.transform([s for _, s in candidates]))[0]
        codes = {c.lower() for c in CODE_RE.findall(query)}
        adjusted = []
        for sim, (n, sent) in zip(sims, candidates):
            sim = float(sim) + CODE_BOOST * sum(1 for c in codes if c in sent.lower())
            if "symptom" in (hits[n - 1]["section"] or "").lower():
                sim *= 0.5  # symptom lists restate the problem; prefer actionable sentences
            adjusted.append((sim, (n, sent)))
        ranked = sorted(adjusted, key=lambda x: x[0], reverse=True)
        points, seen = [], set()
        for sim, (n, sent) in ranked:
            key = sent.lower()[:60]
            if key in seen or sim <= 0:
                continue
            seen.add(key)
            points.append(f"• {sent} [{n}]")
            if len(points) >= max_points:
                break
        return {"answer": "\n".join(points), "sources": sources, "mode": "extractive"}
