"""SQLite persistence for support tickets."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "tickets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    pk INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE,
    created_at TEXT NOT NULL,
    user TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    summary TEXT NOT NULL,
    description TEXT NOT NULL,
    symptoms TEXT NOT NULL,
    steps_tried TEXT NOT NULL,
    device TEXT NOT NULL DEFAULT '{}',
    escalation TEXT NOT NULL DEFAULT '{}',
    recommended_next_action TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    kb_articles TEXT NOT NULL,
    transcript TEXT NOT NULL
);
"""
JSON_FIELDS = ("symptoms", "steps_tried", "kb_articles", "transcript", "device", "escalation", "sources")
STATUSES = ("open", "in_progress", "resolved", "closed")


class TicketStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = str(path or os.environ.get("TICKETS_DB", DEFAULT_DB))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def create(self, ticket: dict) -> dict:
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cols = ["created_at", "user", "category", "priority", "summary", "description", "symptoms",
                "steps_tried", "recommended_next_action", "kb_articles", "transcript", "device", "escalation",
                "sources"]
        ticket = {"device": {}, "escalation": {}, "sources": [], **ticket}
        row = {k: (json.dumps(v) if k in JSON_FIELDS else v) for k, v in ticket.items()}
        row["created_at"] = created
        cur = self.conn.execute(
            f"INSERT INTO tickets ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [row[c] for c in cols])
        ticket_id = f"TKT-{cur.lastrowid:05d}"
        self.conn.execute("UPDATE tickets SET id = ? WHERE pk = ?", (ticket_id, cur.lastrowid))
        self.conn.commit()
        return self.get(ticket_id)

    def _to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d.pop("pk", None)
        for k in JSON_FIELDS:
            d[k] = json.loads(d[k])
        return d

    def get(self, ticket_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return self._to_dict(row) if row else None

    def list(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.conn.execute("SELECT * FROM tickets WHERE status = ? ORDER BY pk DESC", (status,))
        else:
            rows = self.conn.execute("SELECT * FROM tickets ORDER BY pk DESC")
        return [self._to_dict(r) for r in rows.fetchall()]

    def update_status(self, ticket_id: str, status: str) -> dict | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        self.conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        self.conn.commit()
        return self.get(ticket_id)


def ticket_to_text(t: dict) -> str:
    """Human-readable plain-text rendering of a ticket (for email/IT handoff)."""
    lines = [
        f"Support Ticket {t['id']}  [{t['priority'].upper()}]  status: {t['status']}",
        f"Created: {t['created_at']}   User: {t['user']}   Category: {t['category']}",
        "", f"Summary: {t['summary']}", "", f"Description: {t['description']}", "", "Device:",
        *[f"  - {k.replace('_', ' ').title()}: {v}" for k, v in t["device"].items()], "", "Symptoms:",
        *([f"  - {s}" for s in t["symptoms"]] or ["  (none)"]), "", "Steps already tried:",
        *([f"  {i}. {s}" for i, s in enumerate(t["steps_tried"], 1)] or ["  (none)"]), "",
        f"Recommended escalation: {t['escalation'].get('level', '-')}",
        f"  Reason: {t['escalation'].get('reason', '-')}",
        f"Recommended next action: {t['recommended_next_action']}",
        "", "Related KB articles: " + ", ".join(a["title"] for a in t["kb_articles"]),
        "Documentation cited: " + (", ".join(f"{d['title']} ({d['status']})" for d in t["sources"]) or "none"),
    ]
    return "\n".join(lines)
