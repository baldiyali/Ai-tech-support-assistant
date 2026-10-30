import pytest

from app.db import TicketStore, ticket_to_text
from app.engine import TroubleshootingEngine
from app.kb import KnowledgeBase


@pytest.fixture
def engine():
    return TroubleshootingEngine(KnowledgeBase(), TicketStore(":memory:"))


@pytest.mark.parametrize("text,expected", [
    ("My computer won't turn on", "power"),
    ("The printer is not printing anything", "printer"),
    ("No internet on my laptop", "network"),
    ("My PC is super slow and freezing", "slow_pc"),
    ("Outlook keeps crashing", "email"),
    ("Second monitor says no signal", "display"),
    ("My wireless mouse stopped working", "peripherals"),
    ("I'm locked out, forgot my password", "account"),
    ("Got a blue screen with a stop code", "bsod"),
    ("My laptop turns on, but the screen stays black", "black_screen"),
    ("The PC powers on and fans spin but the display shows nothing", "black_screen"),
    ("People can't hear me on Teams, microphone issue", "audio"),
    ("I clicked a link in a suspicious email", "security"),
])
def test_classification(engine, text, expected):
    assert engine.classify(text)[0] == expected


def test_unclear_message_asks_to_clarify(engine):
    r = engine.handle("help me please")
    assert r["state"]["phase"] == "clarify"
    assert "Printer" in r["options"]
    r = engine.handle("Printer", r["session_id"])
    assert r["state"]["category"] == "printer" and r["state"]["phase"] == "questions"


def test_unrecognised_step_answer_reprompts(engine):
    sid = engine.handle("printer broken")["session_id"]
    for answer in ["Only me", "Looks normal / Ready", "Nothing prints at all", "Desktop", "Windows 10",
                   "Minor inconvenience"]:
        engine.handle(answer, sid)
    s = engine.sessions[sid]
    assert s.phase == "steps"
    r = engine.handle("banana", sid)
    assert "didn't catch" in r["reply"] and s.step_index == 0


def test_free_text_answer_is_recorded_as_symptom(engine):
    sid = engine.handle("printer broken")["session_id"]
    engine.handle("it is making a weird beeping noise", sid)
    assert any("beeping" in sym for sym in engine.sessions[sid].symptoms)


def test_priority_from_impact_and_flags(engine):
    r = engine.handle("nobody can print to the office printer")
    sid = r["session_id"]
    engine.handle("Nobody can print", sid)               # high hint
    engine.handle("Looks normal / Ready", sid)
    engine.handle("Nothing prints at all", sid)
    engine.handle("Desktop", sid)
    engine.handle("Windows 11", sid)
    r = engine.handle("Minor inconvenience", sid)        # impact low, but hint keeps it high
    assert r["state"]["priority"] == "high"


def test_ticket_text_rendering(engine):
    sid = engine.handle("my laptop is dead and won't turn on", user="Sam")["session_id"]
    engine.handle("escalate", sid)
    r = engine.handle("ASSET-0099", sid)
    text = ticket_to_text(r["ticket"])
    assert r["ticket"]["id"] in text and "Sam" in text and "Recommended next action" in text


def test_device_details_auto_detected_from_description(engine):
    r = engine.handle("Outlook keeps crashing on my Windows 11 laptop")
    sid = r["session_id"]
    engine.handle("Outlook won't open / crashes", sid)
    r = engine.handle("Yes", sid)
    assert "Noted from your description: Laptop, Windows 11" in r["reply"]
    assert engine.sessions[sid].device["device_type"] == "Laptop"
    assert engine.sessions[sid].device["os"] == "Windows 11"


def test_ticket_contains_required_fields(engine):
    sid = engine.handle("I'm locked out of my account", user="Priya")["session_id"]
    engine.handle("Account is locked", sid)
    engine.handle("No, it happened unexpectedly", sid)
    engine.handle("escalate", sid)
    t = engine.handle("Dell OptiPlex 7090 / ASSET-0007", sid)["ticket"]
    for key in ("id", "user", "category", "priority", "summary", "description", "device", "symptoms",
                "steps_tried", "escalation", "recommended_next_action", "kb_articles", "sources", "status"):
        assert key in t, key
    assert t["priority"] == "high" and t["category"] == "account"
    assert "Unexpected lockout - possible unauthorized attempts" in t["symptoms"]
    assert set(t["device"]) == {"device_type", "os", "model_asset"}
    assert t["device"]["model_asset"] == "Dell OptiPlex 7090 / ASSET-0007"
    assert t["escalation"]["level"] == "Tier 1 - Help desk (admin)" and t["escalation"]["reason"]
