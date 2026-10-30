"""End-to-end API tests for the main user journeys."""
import re


def run(chat, messages, **kw):
    r = None
    for m in messages:
        r = chat(m, **kw)
    return r


def test_health_and_kb(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["articles"] >= 10 and h["llm_enabled"] is False
    assert client.get("/api/kb/search", params={"q": "printer jam"}).json()[0]["category"] == "printer"
    assert "Troubleshooting Steps" in client.get("/api/kb/printer-not-printing").json()["body"]
    assert client.get("/api/kb/nope").status_code == 404


def test_pages_served(client):
    assert "AI Tech Support" in client.get("/").text
    assert "Support tickets" in client.get("/tickets").text
    assert "Upload a troubleshooting manual" in client.get("/knowledge").text


def test_printer_issue_resolved_without_ticket(client, chat):
    r = chat("The printer isn't printing my documents")
    assert r["state"]["category"] == "printer" and r["state"]["phase"] == "questions"
    assert r["articles"][0]["id"] == "printer-not-printing"
    r = run(chat, ["Only me", "Looks normal / Ready", "Job is stuck in the queue", "Desktop", "Windows 10",
                   "I can work around it"])
    assert r["state"]["phase"] == "steps" and "Step 1 of" in r["reply"]
    # step reply is grounded in retrieved documentation, with citations
    assert r["sources"] and r["sources"][0]["status"] == "approved"
    assert re.search(r"\[\d\]", r["reply"])
    r = run(chat, ["❌ Still not working", "❌ Still not working"])
    assert r["state"]["step"] == 3 and "print queue" in r["reply"].lower()
    r = chat("✅ That fixed it")
    assert r["state"]["phase"] == "resolved" and r["ticket"] is None
    assert client.get("/api/tickets").json() == []


def test_pc_wont_turn_on_escalates_to_ticket(client, chat):
    r = chat("My PC won't turn on at all", user="Jordan (Sales)")
    assert r["state"]["category"] == "power"
    r = run(chat, ["Nothing at all (no lights, no fans)", "No", "Desktop", "Windows 11", "I can't work at all"])
    total = r["state"]["total_steps"]
    for _ in range(total - 1):
        r = chat("❌ Still not working")
        assert r["state"]["phase"] == "steps"
    r = chat("⏭ I can't do this step")
    assert r["state"]["phase"] == "device_details" and "asset tag" in r["reply"]
    r = chat("HP EliteDesk 800 G6, ASSET-0042")
    assert r["state"]["phase"] == "escalated"
    t = r["ticket"]
    assert t["id"].startswith("TKT-") and t["priority"] == "high" and t["status"] == "open"
    assert t["user"] == "Jordan (Sales)" and t["category"] == "power"
    assert t["device"] == {"device_type": "Desktop", "os": "Windows 11", "model_asset": "HP EliteDesk 800 G6, ASSET-0042"}
    assert "No lights or fans when power button pressed" in t["symptoms"]
    assert len(t["steps_tried"]) == total and t["steps_tried"][-1].startswith("(skipped")
    assert t["escalation"]["level"] == "Tier 2 - Hardware technician"
    assert f"All {total} guided troubleshooting steps attempted" in t["escalation"]["reason"]
    assert "power supply" in t["recommended_next_action"].lower()
    # persisted and retrievable
    assert client.get(f"/api/tickets/{t['id']}").json()["device"]["model_asset"].endswith("ASSET-0042")
    assert client.get("/api/tickets").json()[0]["id"] == t["id"]
    text = client.get(f"/api/tickets/{t['id']}/text").text
    assert t["id"] in text and "Recommended escalation: Tier 2" in text and "Model Asset: HP EliteDesk" in text


def test_black_screen_natural_language_diagnosis_end_to_end(client, chat):
    r = chat("My laptop turns on, but the screen stays black")
    assert r["state"]["category"] == "black_screen"
    assert "external monitor" in r["reply"].lower()            # targeted question 1
    r = chat("Yes, the external monitor works")
    assert "startup" in r["reply"].lower() and "chime" in r["reply"].lower()   # targeted question 2
    assert "Beeps or blinking light pattern" in r["options"]
    r = chat("Lights and fan, but no chime")
    assert "logo" in r["reply"].lower()
    r = chat("No, never")
    # "laptop" was in the description, so device type is filled in, not asked
    assert "Noted from your description: Laptop" in r["reply"] and "operating system" in r["reply"]
    r = run(chat, ["Windows 11", "I can't work at all"])
    assert r["state"]["phase"] == "steps"
    assert "Diagnosis:" in r["reply"] and "external monitor works" in r["reply"].lower()
    assert r["sources"] and any(s["title"].startswith("Computer Turns On but Screen") for s in r["sources"])
    total = r["state"]["total_steps"]
    while r["state"]["phase"] == "steps":
        r = chat("❌ Still not working")
    r = chat("I don't know")
    t = r["ticket"]
    assert t["category"] == "black_screen" and t["priority"] == "high"
    assert t["device"] == {"device_type": "Laptop", "os": "Windows 11", "model_asset": "Unknown"}
    assert "External monitor works - built-in display/backlight likely faulty" in t["symptoms"]
    # the external-monitor step was already covered during diagnosis, not repeated
    assert len(t["steps_tried"]) == total
    assert any(s.startswith("(covered during diagnosis) Connect an external monitor") for s in t["steps_tried"])
    assert t["escalation"]["level"] == "Tier 2 - Hardware technician"
    assert "hardware fault" in t["escalation"]["reason"]
    assert any(src["status"] == "approved" for src in t["sources"])


def test_power_flow_switches_to_black_screen(chat):
    chat("my computer won't turn on")
    r = chat("Lights/fans come on but screen stays black")
    assert r["state"]["category"] == "black_screen" and "external monitor" in r["reply"].lower()


def test_safety_answer_escalates_immediately_as_urgent(chat):
    r = run(chat, ["laptop won't turn on", "It starts, then shuts off", "Yes"])
    assert r["state"]["phase"] == "escalated" and r["ticket"]["priority"] == "urgent"
    assert "unplug" in r["reply"].lower()
    assert r["ticket"]["escalation"]["level"] == "Tier 2 - Hardware technician (safety)"
    assert r["ticket"]["device"]["device_type"] == "Laptop"


def test_office_wide_outage_routes_to_tier3(chat):
    r = run(chat, ["the internet is down", "No, nobody has internet"])
    t = r["ticket"]
    assert t["priority"] == "urgent" and t["escalation"]["level"].startswith("Tier 3")


def test_user_can_escalate_any_time(chat):
    chat("Outlook won't open")
    r = chat("please escalate to a technician")
    assert r["state"]["phase"] == "device_details"
    r = chat("Lenovo ThinkPad T14")
    assert r["state"]["phase"] == "escalated" and r["ticket"]["category"] == "email"
    assert r["ticket"]["escalation"]["reason"].startswith("User requested a technician")


def test_new_message_after_escalation_starts_new_issue(chat):
    run(chat, ["vpn not connecting", "escalate", "I don't know"])
    r = chat("my monitor is flickering")
    assert r["state"]["category"] == "display" and r["state"]["phase"] == "questions"


def test_ticket_status_update(client, chat):
    tid = run(chat, ["blue screen crash", "escalate", "I don't know"])["ticket"]["id"]
    assert client.patch(f"/api/tickets/{tid}", json={"status": "in_progress"}).json()["status"] == "in_progress"
    assert client.patch(f"/api/tickets/{tid}", json={"status": "bogus"}).status_code == 422
    assert client.patch("/api/tickets/TKT-99999", json={"status": "open"}).status_code == 404
    assert [t["id"] for t in client.get("/api/tickets", params={"status": "in_progress"}).json()] == [tid]


def test_llm_failure_falls_back(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9")  # nothing listening
    r = client.post("/api/chat", json={"message": "printer jam"}).json()
    assert r["llm"] is True and "Printer" in r["reply"]
    a = client.post("/api/ask", json={"question": "how do I clear a paper jam"}).json()
    assert a["mode"] == "extractive" and a["sources"]
