"""Deterministic troubleshooting engine (conversation state machine).

Phases:
  start          -> user describes the problem; we diagnose/classify it
  clarify        -> category unclear; ask the user to pick one
  questions      -> guided follow-up questions (flow + device details + impact)
  steps          -> walk through KB troubleshooting steps, grounded with RAG sources
  device_details -> collect model / asset tag before opening a ticket
  resolved / escalated -> finished (a new message starts a new issue)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from . import llm
from .db import TicketStore
from .flows import (ASSET_QUESTION, BASE_PRIORITY, CATEGORY_KEYWORDS, CATEGORY_LABELS, ESCALATION,
                    DEVICE_QUESTIONS, detect_option, diagnose, max_priority, questions_for)
from .kb import Article, KnowledgeBase
from .rag import DocumentIndex

STEP_OPTIONS = ["✅ That fixed it", "❌ Still not working", "⏭ I can't do this step", "🧑‍🔧 Escalate to IT"]
ESCALATE_RE = re.compile(r"\b(escalate|human|technician|real person|open a ticket|create a ticket|"
                         r"talk to (it|someone|support)|give up)\b", re.I)
YES_RE = re.compile(r"(✅|\b(fixed|works|working now|resolved|solved|yes|yep|that did it|it worked)\b)", re.I)
NO_RE = re.compile(r"(❌|\b(no|nope|not|still|didn'?t|did not|doesn'?t|same)\b)", re.I)
SKIP_RE = re.compile(r"(⏭|\b(can'?t do|cannot do|skip|unable)\b)", re.I)
QUESTION_RE = re.compile(r"\?\s*$|^(how|what|where|why|which|when|can|could|should|is|does|do)\b", re.I)
UNKNOWN_RE = re.compile(r"^(i )?(don'?t|do not) know|^not sure|^no idea|^unknown|^n/?a$|^skip", re.I)
DEVICE_LABELS = {"device_type": "Device type", "os": "Operating system", "model_asset": "Model / asset tag"}


@dataclass
class Session:
    id: str
    user: str = "Anonymous"
    phase: str = "start"
    category: str | None = None
    description: str = ""
    q_index: int = 0
    answers: dict = field(default_factory=dict)
    symptoms: list = field(default_factory=list)
    priority_hints: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    impact: str | None = None
    device: dict = field(default_factory=lambda: {"device_type": None, "os": None, "model_asset": None})
    article_id: str | None = None
    step_index: int = 0
    steps_tried: list = field(default_factory=list)
    related: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    cited: dict = field(default_factory=dict)
    transcript: list = field(default_factory=list)
    pending: dict | None = None
    diagnosis: list = field(default_factory=list)
    skip_steps: set = field(default_factory=set)
    ticket: dict | None = None


class TroubleshootingEngine:
    def __init__(self, kb: KnowledgeBase, store: TicketStore, docs: DocumentIndex | None = None):
        self.kb = kb
        self.store = store
        self.docs = docs or DocumentIndex(kb)
        self.sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------ helpers
    def classify(self, text: str) -> tuple[str | None, list[tuple[Article, float]]]:
        """Natural-language diagnosis rules first, then keyword hits + TF-IDF similarity."""
        hits = self.kb.search(text, k=5)
        rule = diagnose(text)
        if rule:
            return rule, hits
        lowered = text.lower()
        scores: dict[str, float] = {}
        for cat, words in CATEGORY_KEYWORDS.items():
            n = sum(1 for w in words if w in lowered)
            if n:
                scores[cat] = scores.get(cat, 0) + n
        for article, sim in hits:
            scores[article.category] = scores.get(article.category, 0) + sim * 4
        if not scores:
            return None, hits
        best = max(scores, key=scores.get)
        return (best if scores[best] >= 0.5 else None), hits

    @staticmethod
    def _match_option(text: str, options: list[str]) -> str | None:
        t = text.strip().lower()
        for opt in options:
            if t == opt.lower():
                return opt
        for opt in options:  # loose match: answer contained in option or vice versa
            o = opt.lower()
            if len(t) >= 2 and (t in o or o in t):
                return opt
        return None

    def _priority(self, s: Session) -> str:
        if s.impact:
            return max_priority(s.impact, *s.priority_hints)
        return max_priority(BASE_PRIORITY.get(s.category or "", "medium"), *s.priority_hints)

    def _state(self, s: Session) -> dict:
        article = self.kb.by_id.get(s.article_id) if s.article_id else None
        return {
            "phase": s.phase,
            "category": s.category,
            "category_label": CATEGORY_LABELS.get(s.category or "", None),
            "priority": self._priority(s) if s.category else None,
            "step": s.step_index + 1 if s.phase == "steps" else None,
            "total_steps": len(article.steps) if article else None,
            "device": s.device,
        }

    def _reply(self, s: Session, user_msg: str, text: str, options: list[str] | None = None,
               polish: bool = True, sources: list | None = None) -> dict:
        if polish and not sources:  # never let the LLM rewrite cited, grounded text
            text = llm.polish(text, user_msg, context=f"category={s.category}, phase={s.phase}")
        s.sources = sources if sources is not None else []
        for src in s.sources:
            s.cited.setdefault(src["doc_id"], {"doc_id": src["doc_id"], "title": src["title"],
                                               "status": src["status"], "section": src["section"]})
        s.transcript.append({"role": "assistant", "text": text})
        return {
            "session_id": s.id,
            "reply": text,
            "options": options or [],
            "state": self._state(s),
            "articles": s.related,
            "sources": s.sources,
            "ticket": s.ticket,
            "llm": llm.llm_enabled(),
        }

    def _grounding(self, query: str, heading: str = "📚 **From your documentation:**") -> tuple[str, list]:
        rag = self.docs.answer(query, k=3)
        if not rag["answer"]:
            return "", rag["sources"]
        return f"{heading}\n{rag['answer']}\n\n", rag["sources"]

    def _query(self, s: Session, extra: str = "") -> str:
        return " ".join([CATEGORY_LABELS.get(s.category or "", ""), s.description, *s.symptoms, extra])

    # ------------------------------------------------------------------ main entry
    def handle(self, message: str, session_id: str | None = None, user: str | None = None) -> dict:
        s = self.sessions.get(session_id or "")
        if s is None:
            s = Session(id=session_id or uuid.uuid4().hex[:12])
            self.sessions[s.id] = s
        if user and user.strip():
            s.user = user.strip()[:80]
        message = (message or "").strip()[:2000]

        if s.phase in ("resolved", "escalated"):  # start a fresh issue, keep the user's name
            s = Session(id=s.id, user=s.user)
            self.sessions[s.id] = s
        s.transcript.append({"role": "user", "text": message})

        if not message:
            return self._reply(s, message, "Please describe the problem you're having.", polish=False)
        if s.phase not in ("start", "device_details") and ESCALATE_RE.search(message):
            return self._escalate(s, message, "No problem, I'll hand this over to a technician.",
                                  trigger="User requested a technician")
        return getattr(self, f"_phase_{s.phase}")(s, message)

    # ------------------------------------------------------------------ phases
    def _phase_start(self, s: Session, message: str) -> dict:
        s.description = message
        category, hits = self.classify(message)
        s.related = [{**a.summary(), "score": round(sc, 3)} for a, sc in hits[:3] if sc >= 0.08]
        if category is None:
            s.phase = "clarify"
            grounded, sources = self._grounding(message, "📚 **This might help, from your documentation:**")
            return self._reply(s, message, f"{grounded}To point you in the right direction, which area best "
                                           f"matches your problem?", list(CATEGORY_LABELS.values()),
                               sources=sources)
        return self._begin_category(s, message, category)

    def _phase_clarify(self, s: Session, message: str) -> dict:
        labels = {v: k for k, v in CATEGORY_LABELS.items()}
        chosen = self._match_option(message, list(labels))
        category = labels[chosen] if chosen else self.classify(s.description + " " + message)[0]
        if category is None:
            return self._reply(s, message, "Sorry, I couldn't tell which area that is. Please pick one of the "
                                           "options, or type \"escalate\" to open a ticket.",
                               list(CATEGORY_LABELS.values()) + ["🧑‍🔧 Escalate to IT"])
        if not chosen:
            s.description = f"{s.description} {message}".strip()
        return self._begin_category(s, message, category)

    def _begin_category(self, s: Session, message: str, category: str, intro: str | None = None) -> dict:
        s.category = category
        s.skip_steps = set()
        for q in DEVICE_QUESTIONS:  # capture device details mentioned up front, even if we escalate early
            found = detect_option(q, s.description)
            if found and not s.device.get(q["field"]):
                s.device[q["field"]] = found
        article = self.kb.for_category(category)
        s.article_id = article.id if article else None
        if article:
            s.related = [{**article.summary(), "score": None}] + [a for a in s.related if a["id"] != article.id][:2]
        s.phase = "questions"
        s.q_index = 0
        if intro is None:
            intro = (f"It sounds like a **{CATEGORY_LABELS[category]}** issue. I'll ask a few quick questions, "
                     f"then we'll try some fixes together.")
        return self._ask_next(s, message, intro)

    def _record_answer(self, s: Session, q: dict, chosen: str | None, raw: str) -> dict:
        effects = q["options"].get(chosen, {}) if chosen else {}
        value = chosen or raw
        s.answers[q["id"]] = value
        if q.get("field"):
            if not (chosen or "").lower().startswith(("not sure", "other")):
                s.device[q["field"]] = value
        elif effects.get("symptom"):
            s.symptoms.append(effects["symptom"])
        elif not chosen:
            s.symptoms.append(f"{q['text']} -> {raw}")
        if effects.get("priority"):
            if q["id"] == "impact":
                s.impact = effects["priority"]
            else:
                s.priority_hints.append(effects["priority"])
        if effects.get("hint"):
            s.hints.append(effects["hint"])
        if effects.get("diagnosis"):
            s.diagnosis.append(effects["diagnosis"])
        s.skip_steps.update(n - 1 for n in effects.get("skip_steps", []))
        return effects

    def _advance_past_skipped(self, s: Session, article: Article):
        while s.step_index < len(article.steps) and s.step_index in s.skip_steps:
            s.steps_tried.append(f"(covered during diagnosis) {article.steps[s.step_index]}")
            s.step_index += 1

    def _ask_next(self, s: Session, message: str, prefix: str = "") -> dict:
        """Ask the next unanswered question, auto-answering ones the description already covers."""
        questions = questions_for(s.category)
        noted = []
        while s.q_index < len(questions):
            q = questions[s.q_index]
            auto = detect_option(q, s.description)
            if not auto:
                break
            self._record_answer(s, q, auto, auto)
            noted.append(auto)
            s.q_index += 1
        if noted:
            prefix = f"{prefix}\n\n(Noted from your description: {', '.join(noted)}.)".strip()
        if s.q_index >= len(questions):
            return self._start_steps(s, message, prefix)
        q = questions[s.q_index]
        return self._reply(s, message, f"{prefix}\n\n{q['text']}".strip(), list(q["options"]))

    def _phase_questions(self, s: Session, message: str) -> dict:
        q = questions_for(s.category)[s.q_index]
        chosen = self._match_option(message, list(q["options"]))
        effects = self._record_answer(s, q, chosen, message)
        if effects.get("escalate"):
            return self._escalate(s, message, effects["escalate"], trigger=f"{q['text']} -> {chosen}",
                                  ask_asset=False)
        if effects.get("switch"):
            new = effects["switch"]
            return self._begin_category(s, message, new, intro=(
                f"Thanks, that narrows it down: the computer has power, so this is a "
                f"**{CATEGORY_LABELS[new]}** problem. A few targeted questions:"))
        s.q_index += 1
        return self._ask_next(s, message)

    def _start_steps(self, s: Session, message: str, prefix: str = "") -> dict:
        article = self.kb.by_id.get(s.article_id) if s.article_id else None
        if not article or not article.steps:
            return self._escalate(s, message, "I don't have guided steps for this one yet.",
                                  trigger="No guided troubleshooting available")
        s.phase = "steps"
        s.step_index = 0
        self._advance_past_skipped(s, article)
        if s.step_index >= len(article.steps):
            return self._escalate(s, message, "Your answers already cover the standard fixes.",
                                  trigger="Diagnosis covered all guided steps")
        grounded, sources = self._grounding(self._query(s))
        diagnosis = f"🔎 **Diagnosis:** {' '.join(s.diagnosis)}\n\n" if s.diagnosis else ""
        n = s.step_index
        text = (f"{prefix}\n\nThanks, that helps. {diagnosis}{grounded}Let's work through the "
                f"**{article.title}** guide one step at a time.\n\n**Step {n + 1} of {len(article.steps)}:** "
                f"{article.steps[n]}\n\nDid that fix it?").strip()
        return self._reply(s, message, text, STEP_OPTIONS, sources=sources)

    def _phase_steps(self, s: Session, message: str) -> dict:
        article = self.kb.by_id[s.article_id]
        current = article.steps[s.step_index]
        if YES_RE.search(message) and not NO_RE.search(message.replace("✅", "")):
            s.phase = "resolved"
            s.steps_tried.append(current)
            return self._reply(s, message, f"🎉 Great, glad that's fixed! It was resolved at step "
                                           f"{s.step_index + 1}: *{current}*\n\nIf anything else comes up, "
                                           f"just describe the new problem.")
        if SKIP_RE.search(message):
            s.steps_tried.append(f"(skipped - user couldn't perform) {current}")
        elif NO_RE.search(message) and not QUESTION_RE.search(message):
            s.steps_tried.append(current)
        elif QUESTION_RE.search(message):  # free-form question -> answer from the documents (RAG)
            grounded, sources = self._grounding(f"{message} {CATEGORY_LABELS.get(s.category, '')}",
                                                "📚 **Here's what the documentation says:**")
            text = grounded or "I couldn't find that in the documentation. "
            return self._reply(s, message, f"{text}Back to **step {s.step_index + 1}:** {current}\n\n"
                                           f"Did that fix it?", STEP_OPTIONS, sources=sources)
        else:
            return self._reply(s, message, "Sorry, I didn't catch that. Did this step fix the problem?",
                               STEP_OPTIONS, polish=False)

        s.step_index += 1
        self._advance_past_skipped(s, article)
        if s.step_index >= len(article.steps):
            return self._escalate(s, message, "We've tried all the standard fixes and it's still not working, "
                                              "so this needs a technician.",
                                  trigger=f"All {len(article.steps)} guided troubleshooting steps attempted "
                                          f"without success")
        n, total = s.step_index + 1, len(article.steps)
        return self._reply(s, message, f"OK, let's try the next one.\n\n**Step {n} of {total}:** "
                                       f"{article.steps[s.step_index]}\n\nDid that fix it?", STEP_OPTIONS)

    def _phase_device_details(self, s: Session, message: str) -> dict:
        if not UNKNOWN_RE.search(message):
            s.device["model_asset"] = message[:120]
        pending, s.pending = s.pending, None
        return self._create_ticket(s, message, "Thanks, I've added that to the ticket.", pending["trigger"])

    # ------------------------------------------------------------------ escalation
    def recommend_escalation(self, s: Session, trigger: str) -> dict:
        level, why = ESCALATION.get(s.category or "", ("Tier 1 - Help desk", "needs triage by a technician"))
        priority = self._priority(s)
        if s.category == "network" and "Office-wide internet outage" in s.symptoms:
            level, why = "Tier 3 - Network administrator / ISP", "office-wide outage affecting all users"
        elif s.category == "black_screen" and "hardware" in s.hints:
            why = "diagnosis points to a hardware fault (" + "; ".join(
                sym for sym in s.symptoms if "External monitor works" in sym or "POST" in sym) + ")"
        elif s.category == "power" and priority == "urgent":
            level, why = "Tier 2 - Hardware technician (safety)", "possible electrical/physical damage reported"
        return {"level": level, "reason": f"{trigger}; {why}.", "trigger": trigger}

    def build_ticket(self, s: Session, trigger: str = "Escalated") -> dict:
        article = self.kb.by_id.get(s.article_id) if s.article_id else None
        label = CATEGORY_LABELS.get(s.category or "", "General IT issue")
        desc = s.description or "(no description)"
        short = desc if len(desc) <= 80 else desc[:77] + "..."
        return {
            "user": s.user,
            "category": s.category or "other",
            "priority": self._priority(s),
            "summary": f"{label}: {short}",
            "description": desc,
            "device": {k: (v or "Unknown") for k, v in s.device.items()},
            "symptoms": s.symptoms,
            "steps_tried": s.steps_tried,
            "escalation": self.recommend_escalation(s, trigger),
            "recommended_next_action": (article.next_action if article else
                                        "Technician to contact the user and triage the issue."),
            "kb_articles": [{"id": a["id"], "title": a["title"]} for a in s.related],
            "sources": list(s.cited.values()),
            "transcript": s.transcript,
        }

    def _escalate(self, s: Session, message: str, reason: str, trigger: str, ask_asset: bool = True) -> dict:
        if ask_asset and not s.device.get("model_asset"):
            s.phase = "device_details"
            s.pending = {"reason": reason, "trigger": trigger}
            return self._reply(s, message, f"{reason}\n\n{ASSET_QUESTION}", ["I don't know"], polish=False)
        return self._create_ticket(s, message, reason, trigger)

    def _create_ticket(self, s: Session, message: str, reason: str, trigger: str) -> dict:
        s.phase = "escalated"
        s.ticket = self.store.create(self.build_ticket(s, trigger))
        t = s.ticket
        text = (f"{reason}\n\n📋 I've created support ticket **{t['id']}** (priority: **{t['priority']}**, "
                f"routed to **{t['escalation']['level']}**). A technician will follow up with you. You can view "
                f"it on the Tickets page.")
        return self._reply(s, message, text, [], polish=False)
