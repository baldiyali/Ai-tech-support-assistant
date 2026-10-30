"""Optional LLM polish layer.

If OPENAI_API_KEY is set, assistant replies are rephrased by an
OpenAI-compatible chat completions endpoint (configurable via
OPENAI_BASE_URL and LLM_MODEL). The deterministic engine always decides
*what* to say (questions, steps, escalation); the LLM only rewrites *how*
it's said, and any failure silently falls back to the original text.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a friendly IT help desk assistant for a small company. Rewrite the draft reply below so it "
    "sounds natural and empathetic, in at most 4 short sentences. Keep every technical instruction, command, "
    "menu path, ticket ID and question exactly as given. Don't add new troubleshooting steps or facts."
)


def llm_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _chat(messages: list[dict], temperature: float = 0.3) -> str:
    resp = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": os.environ.get("LLM_MODEL", "gpt-4o-mini"), "temperature": temperature,
              "messages": messages},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


GROUNDED_PROMPT = (
    "You are an IT help desk assistant. Answer the user's problem using ONLY the numbered sources. "
    "Give at most 3 short bullet points starting with '• ', and end each bullet with the citation(s) "
    "it came from, like [1] or [2]. If the sources don't contain the answer, reply exactly: NO_ANSWER"
)


def generate_grounded(query: str, chunks: list[dict]) -> str | None:
    """LLM answer grounded in retrieved chunks; None if disabled, failed or unanswerable."""
    if not llm_enabled() or not chunks:
        return None
    context = "\n\n".join(f"[{i}] {c['title']} ({c.get('section') or 'general'}):\n{c['text']}"
                           for i, c in enumerate(chunks, 1))
    try:
        text = _chat([{"role": "system", "content": GROUNDED_PROMPT},
                      {"role": "user", "content": f"Sources:\n{context}\n\nProblem: {query}"}], 0.1)
    except Exception as exc:
        log.warning("LLM grounded generation failed, using extractive answer: %s", exc)
        return None
    return None if not text or "NO_ANSWER" in text else text


def polish(draft: str, user_message: str, context: str = "") -> str:
    if not llm_enabled() or not draft:
        return draft
    try:
        resp = httpx.post(
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={
                "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Context: {context}\nUser said: {user_message}\n\nDraft reply:\n{draft}"},
                ],
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return text or draft
    except Exception as exc:  # network errors, bad key, quota... never break the chat
        log.warning("LLM polish failed, using deterministic reply: %s", exc)
        return draft
