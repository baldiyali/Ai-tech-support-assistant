"""Drive the running app in headless Chromium: verify the main flows and save screenshots.

Usage:  uvicorn app.main:app --port 8000   (in another terminal)
        python scripts/e2e_screenshots.py [base_url]
"""
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
MANUAL = Path(__file__).resolve().parent.parent / "docs" / "sample-manuals" / "acme-laserpro-400-manual.pdf"
OUT.mkdir(parents=True, exist_ok=True)


def say(page, text):
    """Click a quick-reply button if one matches, otherwise type the message."""
    n = page.locator(".msg.bot").count()
    btn = page.locator("#options button", has_text=text)
    if btn.count():
        btn.first.click()
    else:
        page.fill("#input", text)
        page.press("#input", "Enter")
    expect(page.locator(".msg.bot")).to_have_count(n + 1)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)

    # 1) Upload a vendor manual on the Knowledge page and ask it a question (RAG with citations)
    page.goto(f"{BASE}/knowledge")
    page.set_input_files("#file", str(MANUAL))
    page.fill("#title", "Acme LaserPro 400 manual")
    page.click("#upload button[type=submit]")
    expect(page.locator("#up-msg")).to_contain_text("Indexed")
    page.fill("#q", "The printer shows error E-49, what should I do?")
    page.click("#ask button")
    expect(page.locator("#answer .source").first).to_be_visible()
    expect(page.locator("#answer")).to_contain_text("fuser")
    page.screenshot(path=OUT / "knowledge-rag.png", full_page=True)
    print("✔ upload + ask-the-docs")

    # 2) Printer issue diagnosed to resolution
    page.goto(BASE)
    page.fill("#user", "Alex (Finance)")
    page.dispatch_event("#user", "change")
    say(page, "The printer isn't printing my documents")
    for a in ["Only me", "Looks normal / Ready", "Job is stuck in the queue", "Desktop", "Windows 11",
              "I can work around it"]:
        say(page, a)
    expect(page.locator(".sources").last).to_be_visible()
    say(page, "What does error E-49 mean?")
    expect(page.locator(".msg.bot").last).to_contain_text("fuser")
    page.screenshot(path=OUT / "chat-rag-citations.png")
    say(page, "Still not working")
    say(page, "Still not working")
    say(page, "That fixed it")
    expect(page.locator("#s-phase")).to_contain_text("resolved")
    page.screenshot(path=OUT / "chat-printer-resolved.png")
    print("✔ printer issue resolved at step 3")

    # 3) Natural-language diagnosis: laptop on, black screen -> targeted questions -> ticket
    page.click("#new")
    say(page, "My laptop turns on, but the screen stays black")
    expect(page.locator(".msg.bot").last).to_contain_text("external monitor")
    say(page, "Yes, the external monitor works")
    expect(page.locator(".msg.bot").last).to_contain_text("chime")
    say(page, "Lights and fan, but no chime")
    say(page, "No, never")
    say(page, "Windows 11")
    say(page, "I can't work at all")
    expect(page.locator(".msg.bot").last).to_contain_text("Diagnosis")
    page.screenshot(path=OUT / "chat-black-screen-diagnosis.png")
    print("✔ black-screen targeted diagnosis")

    # 4) 'PC won't turn on' escalated to a ticket after all steps fail
    page.click("#new")
    say(page, "My PC won't turn on")
    for a in ["Nothing at all (no lights, no fans)", "No", "Desktop", "Windows 10", "I can't work at all"]:
        say(page, a)
    while page.locator("#s-phase").inner_text() == "troubleshooting":
        say(page, "Still not working")
    expect(page.locator(".msg.bot").last).to_contain_text("asset tag")
    say(page, "HP EliteDesk 800 G6 / ASSET-0042")
    expect(page.locator(".ticket-card")).to_be_visible()
    expect(page.locator(".ticket-card")).to_contain_text("Tier 2 - Hardware technician")
    page.locator(".ticket-card").scroll_into_view_if_needed()
    page.screenshot(path=OUT / "chat-ticket-escalation.png")
    ticket_id = page.locator(".ticket-card h4").inner_text().split()[1]
    print(f"✔ PC-won't-turn-on escalated to {ticket_id}")

    # 5) Tickets list + detail
    page.goto(f"{BASE}/tickets")
    expect(page.locator("tr.row").first).to_contain_text(ticket_id)
    page.screenshot(path=OUT / "tickets-list.png")
    page.locator("tr.row").first.click()
    expect(page.locator("#modal .ticket-card")).to_be_visible()
    page.screenshot(path=OUT / "ticket-detail.png")
    print("✔ tickets page")
    browser.close()
print(f"Screenshots saved to {OUT}")
