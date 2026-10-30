"""Guided follow-up question flows for each problem category.

Each question has quick-reply options. An option can carry *effects*:
  - priority: raises the ticket priority (low < medium < high < urgent)
  - symptom:  adds a line to the ticket's symptom list
  - escalate: skip troubleshooting and escalate immediately (with a message)
  - diagnosis: an explanation shown before troubleshooting starts
  - skip_steps: KB step numbers already covered by the answer (not repeated)
  - switch:   jump to a more specific flow (e.g. power -> black_screen)
  - detect:   regex; if it matches the user's description the question is
              answered automatically (so we never ask what the user already said)
"""
from __future__ import annotations

import re

PRIORITIES = ["low", "medium", "high", "urgent"]

CATEGORY_LABELS = {
    "power": "Computer won't turn on",
    "black_screen": "Turns on, but screen stays black",
    "printer": "Printer",
    "network": "Internet / Wi-Fi",
    "slow_pc": "Slow or freezing computer",
    "email": "Email / Outlook",
    "vpn": "VPN / remote access",
    "display": "Monitor / display",
    "peripherals": "Keyboard / mouse",
    "account": "Password / account lockout",
    "bsod": "Blue screen / crashes",
    "audio": "Sound / headset / mic",
    "software": "Software install / app errors",
    "security": "Phishing / virus / security",
}

# Keyword hints used together with TF-IDF to classify the first message.
CATEGORY_KEYWORDS = {
    "black_screen": ["black screen", "blank screen", "screen stays black", "screen is black", "no picture",
                     "no image", "screen goes black"],
    "power": ["won't turn on", "wont turn on", "not turning on", "doesn't turn on", "dead", "no power",
              "power button", "won't boot", "wont start", "won't start", "battery", "charger", "no lights"],
    "printer": ["printer", "print", "printing", "paper jam", "toner", "ink", "spooler", "scanner"],
    "network": ["internet", "wifi", "wi-fi", "wireless", "network", "ethernet", "router", "no connection",
                "disconnect", "websites won't load"],
    "slow_pc": ["slow", "sluggish", "freez", "lag", "not responding", "takes forever", "hangs"],
    "email": ["email", "e-mail", "outlook", "inbox", "mailbox", "outbox"],
    "vpn": ["vpn", "remote access", "work from home", "anyconnect", "forticlient", "globalprotect"],
    "display": ["monitor", "screen", "display", "no signal", "flicker", "hdmi", "resolution"],
    "peripherals": ["keyboard", "mouse", "trackpad", "touchpad", "cursor", "keys"],
    "account": ["password", "locked out", "lockout", "locked", "log in", "login", "sign in", "mfa",
                "authenticator", "two-factor"],
    "bsod": ["blue screen", "bsod", "stop code", "crash", "restarts", "reboot loop"],
    "audio": ["sound", "audio", "headset", "headphone", "microphone", "mic", "speaker", "can't hear"],
    "software": ["install", "software", "application", "program", "update", "license", "activation",
                 "excel", "word", "adobe", "won't open"],
    "security": ["phishing", "suspicious", "scam", "virus", "malware", "ransom", "hacked", "clicked a link",
                 "pop-up", "popup", "compromised"],
}

# Base priority used when the user's answers don't say otherwise.
BASE_PRIORITY = {
    "power": "high", "black_screen": "high", "network": "high", "security": "high", "account": "high", "bsod": "medium",
}

IMPACT_QUESTION = {
    "id": "impact",
    "text": "How much is this affecting your work right now?",
    "options": {
        "I can't work at all": {"priority": "high", "symptom": "User is unable to work"},
        "I can work around it": {"priority": "medium"},
        "Minor inconvenience": {"priority": "low"},
    },
}

FLOWS: dict[str, list[dict]] = {
    "black_screen": [
        {"id": "external", "text": "Does an external monitor or TV show a picture when you connect it "
                                   "(HDMI / USB-C)?",
         "options": {
             "Yes, the external monitor works": {
                 "symptom": "External monitor works - built-in display/backlight likely faulty", "hint": "hardware",
                 "skip_steps": [3],
                 "diagnosis": "Because an external monitor works, the computer itself is running. The built-in "
                              "screen, its cable, or its backlight is the most likely culprit."},
             "No, it's black too": {"symptom": "External monitor also black - not just the built-in screen"},
             "No external monitor to test": {"symptom": "External monitor test not performed"}}},
        {"id": "indicators", "text": "When you press power, which startup signs do you notice: power or keyboard "
                                     "lights, fan noise, or a startup chime?",
         "options": {
             "Lights and fan, but no chime": {"symptom": "Power/keyboard lights and fan on, no startup chime"},
             "Startup chime or sound plays": {"symptom": "Startup chime plays (system is booting)"},
             "Beeps or blinking light pattern": {"priority": "high", "hint": "hardware",
                                                 "diagnosis": "Beeps or blinking lights usually mean the computer "
                                                              "failed its power-on self-test (often memory). Count "
                                                              "the pattern for the technician.",
                                                 "symptom": "Beep codes / blinking light pattern at startup "
                                                            "(possible POST failure)"},
             "Lights only, no fan sound": {"symptom": "Lights on but no fan noise"}}},
        {"id": "logo", "text": "Do you see the manufacturer logo (Dell, HP, Lenovo...) at all, even briefly?",
         "options": {"Yes, then it goes black": {"symptom": "Logo appears then screen goes black (OS/driver)",
                                                "diagnosis": "Since the logo appears, the hardware starts fine; "
                                                             "Windows or the display driver is the likely cause, "
                                                             "so the Safe Mode steps matter most."},
                     "No, never": {"symptom": "No manufacturer logo at any point"}}},
    ],
    "power": [
        {"id": "signs", "text": "When you press the power button, what happens?",
         "options": {
             "Nothing at all (no lights, no fans)": {"symptom": "No lights or fans when power button pressed"},
             "Lights/fans come on but screen stays black": {"symptom": "Powers on but no display",
                                                            "switch": "black_screen"},
             "It starts, then shuts off": {"symptom": "Starts briefly then shuts off"}}},
        {"id": "safety", "text": "Do you notice any burning smell, smoke, sparks, or liquid damage?",
         "options": {
             "Yes": {"priority": "urgent", "symptom": "Burning smell / smoke / liquid damage reported",
                     "escalate": "⚠️ For your safety, unplug the computer now and don't try to turn it on again. "
                                 "I'm creating an urgent ticket for a technician."},
             "No": {}}},
    ],
    "printer": [
        {"id": "scope", "text": "Is the problem only on your computer, or can nobody print to this printer?",
         "options": {"Only me": {"symptom": "Only this user affected"},
                     "Nobody can print": {"priority": "high", "symptom": "Printer fails for all users"},
                     "Not sure": {}}},
        {"id": "panel", "text": "What does the printer's display or lights show?",
         "options": {"Paper jam / out of paper": {"symptom": "Printer reports paper jam or no paper"},
                     "An error code or warning light": {"symptom": "Printer shows an error code/warning light"},
                     "Looks normal / Ready": {"symptom": "Printer panel shows Ready"},
                     "It's off / no display": {"symptom": "Printer appears powered off"}}},
        {"id": "symptom", "text": "What happens when you print?",
         "options": {"Nothing prints at all": {"symptom": "Jobs sent but nothing prints"},
                     "Job is stuck in the queue": {"symptom": "Print job stuck in queue"},
                     "Prints but looks wrong (faded/streaky)": {"symptom": "Poor print quality"}}},
    ],
    "network": [
        {"id": "scope", "text": "Do other people or devices in the office have internet right now?",
         "options": {"Yes, it's just me": {"symptom": "Only this device affected"},
                     "No, nobody has internet": {"priority": "urgent", "symptom": "Office-wide internet outage",
                                                 "escalate": "Since nobody in the office has internet, this is "
                                                             "most likely a router or provider outage, not your "
                                                             "computer. I'm escalating it right away."},
                     "Not sure": {}}},
        {"id": "conn", "text": "How is your computer connected?",
         "options": {"Wi-Fi": {"symptom": "Connection: Wi-Fi"}, "Cable (Ethernet)": {"symptom": "Connection: Ethernet"}}},
        {"id": "behavior", "text": "Which best describes it?",
         "options": {"No connection at all": {"symptom": "No connection"},
                     "Connected, but no internet": {"symptom": "Connected but no internet access"},
                     "Keeps dropping / very slow": {"symptom": "Intermittent or slow connection"}}},
    ],
    "slow_pc": [
        {"id": "when", "text": "When did the slowness start?",
         "options": {"Suddenly, today or this week": {"symptom": "Sudden slowdown"},
                     "Gradually over time": {"symptom": "Gradual slowdown"}}},
        {"id": "where", "text": "Is it slow everywhere, or in one specific program?",
         "options": {"Everywhere": {"symptom": "Whole system slow"},
                     "One program": {"symptom": "Slowness limited to one application"}}},
        {"id": "restart", "text": "When did you last fully restart the computer?",
         "options": {"Today": {"symptom": "Restarted today"},
                     "More than a few days ago": {"symptom": "Not restarted for several days"},
                     "I don't remember": {}}},
    ],
    "email": [
        {"id": "issue", "text": "What's the email problem?",
         "options": {"Can't send": {"symptom": "Cannot send email"},
                     "Not receiving email": {"symptom": "Not receiving email"},
                     "Outlook won't open / crashes": {"symptom": "Outlook won't open or crashes"},
                     "Keeps asking for password": {"symptom": "Repeated password prompts"}}},
        {"id": "webmail", "text": "Does your email work in the browser (webmail)?",
         "options": {"Yes": {"symptom": "Webmail works (client-side issue)"},
                     "No": {"priority": "high", "symptom": "Webmail also fails (account/server issue)"},
                     "Haven't tried": {}}},
    ],
    "vpn": [
        {"id": "internet", "text": "Does your normal internet work when the VPN is off?",
         "options": {"Yes": {"symptom": "Internet works without VPN"},
                     "No": {"symptom": "No internet even without VPN"}}},
        {"id": "error", "text": "What do you see?",
         "options": {"Login / password / MFA error": {"symptom": "VPN authentication error"},
                     "Certificate or license error": {"symptom": "VPN certificate/license error"},
                     "Connects, but can't reach files": {"symptom": "VPN connected but resources unreachable"},
                     "It just times out": {"symptom": "VPN connection times out"}}},
    ],
    "display": [
        {"id": "which", "text": "Which screen has the problem?",
         "options": {"External monitor": {"symptom": "External monitor affected"},
                     "Built-in laptop screen": {"symptom": "Built-in laptop screen affected"},
                     "Second monitor not detected": {"symptom": "Second monitor not detected"}}},
        {"id": "what", "text": "What does it show?",
         "options": {"'No signal' / black": {"symptom": "No signal / black screen"},
                     "Flickering or lines": {"symptom": "Flickering or lines on screen"},
                     "Wrong size / blurry": {"symptom": "Wrong resolution or blurry"}}},
    ],
    "peripherals": [
        {"id": "device", "text": "Which device isn't working?",
         "options": {"Keyboard": {"symptom": "Keyboard affected"}, "Mouse": {"symptom": "Mouse affected"},
                     "Laptop touchpad": {"symptom": "Touchpad affected"}}},
        {"id": "type", "text": "Is it wired or wireless?",
         "options": {"Wired (USB)": {"symptom": "Wired USB device"},
                     "Wireless / Bluetooth": {"symptom": "Wireless/Bluetooth device"},
                     "Built into the laptop": {"symptom": "Built-in device"}}},
    ],
    "account": [
        {"id": "what", "text": "What's happening when you try to sign in?",
         "options": {"Account is locked": {"symptom": "Account locked"},
                     "Forgot / expired password": {"symptom": "Forgotten or expired password"},
                     "MFA / authenticator problem": {"symptom": "MFA problem"}}},
        {"id": "self", "text": "Did you cause the lockout yourself (e.g., mistyped password)?",
         "options": {"Yes, probably": {},
                     "No, it happened unexpectedly": {"priority": "high",
                                                      "symptom": "Unexpected lockout - possible unauthorized attempts"}}},
    ],
    "bsod": [
        {"id": "freq", "text": "How often does the blue screen or crash happen?",
         "options": {"Once": {"symptom": "Single crash"},
                     "Several times a day/week": {"priority": "high", "symptom": "Recurring crashes"},
                     "Stuck in a restart loop": {"priority": "high", "symptom": "Restart loop - cannot reach desktop"}}},
        {"id": "change", "text": "Did anything change recently (new hardware, driver, update, or program)?",
         "options": {"Yes": {"symptom": "Recent change before crashes"}, "No / not sure": {}}},
    ],
    "audio": [
        {"id": "what", "text": "What's the audio problem?",
         "options": {"I can't hear anything": {"symptom": "No audio output"},
                     "Others can't hear me": {"symptom": "Microphone not working"},
                     "Echo / crackling": {"symptom": "Audio quality issues"}}},
        {"id": "where", "text": "Is it in every app or only in meetings (Teams/Zoom)?",
         "options": {"Every app": {"symptom": "Affects all apps"},
                     "Only meetings": {"symptom": "Only in meeting apps"}}},
    ],
    "software": [
        {"id": "what", "text": "What are you trying to do?",
         "options": {"Install new software": {"symptom": "Software installation"},
                     "Open an app that won't start": {"symptom": "Application won't start"},
                     "App crashes or shows an error": {"symptom": "Application crashes / error"},
                     "License / activation message": {"symptom": "Licensing/activation problem"}}},
        {"id": "admin", "text": "Are you being asked for an administrator password?",
         "options": {"Yes": {"symptom": "Admin rights required",
                             "escalate": "Installing that needs administrator rights, which only IT can grant. "
                                         "I'll create a ticket so a technician can install it for you."},
                     "No": {}}},
    ],
    "security": [
        {"id": "what", "text": "What happened?",
         "options": {"I received a suspicious email": {"symptom": "Suspicious email received"},
                     "I clicked a link / opened an attachment": {"priority": "high",
                                                                 "symptom": "User clicked link/opened attachment"},
                     "Pop-ups or antivirus alerts": {"priority": "high", "symptom": "Pop-ups / antivirus alerts"},
                     "Files are encrypted / ransom note": {
                         "priority": "urgent", "symptom": "Ransomware symptoms",
                         "escalate": "🚨 Disconnect from the network now (turn off Wi-Fi / unplug the cable) but "
                                     "leave the computer on. I'm creating an urgent security ticket."}}},
        {"id": "password", "text": "Did you enter your password or any personal details?",
         "options": {"Yes": {"priority": "urgent", "symptom": "Credentials may be compromised"},
                     "No": {}}},
    ],
}


# Device details asked in every flow (auto-filled when the description already says it).
DEVICE_QUESTIONS = [
    {"id": "device_type", "field": "device_type", "text": "What kind of computer is this on?",
     "options": {"Laptop": {"detect": r"\b(laptop|notebook|macbook|surface|thinkpad|chromebook)\b"},
                 "Desktop": {"detect": r"\b(desktop|tower|workstation|imac|all-in-one)\b"},
                 "Other / not sure": {}}},
    {"id": "os", "field": "os", "text": "Which operating system does it run?",
     "options": {"Windows 11": {"detect": r"\b(windows|win) ?11\b"},
                 "Windows 10": {"detect": r"\b(windows|win) ?10\b"},
                 "macOS": {"detect": r"\b(macos|mac os|os x|macbook|imac)\b"},
                 "Linux": {"detect": r"\b(linux|ubuntu|fedora|debian)\b"},
                 "Not sure": {}}},
]

ASSET_QUESTION = ("Before I create the ticket: what's the computer's **model or asset tag**? It's usually on a "
                  "sticker underneath or on the back (e.g. \"Dell Latitude 5420\" or \"ASSET-0142\").")

# Natural-language diagnosis rules, checked before keyword/TF-IDF scoring so that
# specific phrasings ("turns on but the screen stays black") route to the right flow.
DIAGNOSIS_RULES: list[tuple[str, str]] = [
    (r"(turns?|turning|powers?|boots?|starts?|switch(es)?) on\b.*\b(screen|display|monitor)\b.*"
     r"\b(black|blank|dark|nothing|stays off)\b", "black_screen"),
    (r"\b(black|blank|dark) (screen|display)\b|\b(screen|display) (stays|is|goes|went|remains) "
     r"(black|blank|dark)\b|\bno (picture|image)\b", "black_screen"),
    (r"\b(won'?t|doesn'?t|does not|will not|not|can'?t) (turn|power|switch|boot)(ing)? ?(it )?on\b|"
     r"\bcompletely dead\b|\bno power\b", "power"),
    (r"\bclicked (a|on|the|an)\b.*\b(link|attachment)\b|\bphish", "security"),
    (r"\blocked out\b|\baccount (is |was |got )?locked\b", "account"),
]

# Recommended escalation level and reason per category.
ESCALATION = {
    "power": ("Tier 2 - Hardware technician", "no power after power-source checks; likely charger, PSU, battery "
                                              "or motherboard fault"),
    "black_screen": ("Tier 2 - Hardware technician", "device powers on but shows no picture; needs display, "
                                                     "backlight, RAM or GPU diagnosis"),
    "printer": ("Tier 2 - Desktop support", "printer hardware, driver or print-server configuration issue"),
    "network": ("Tier 2 - Network administrator", "network adapter, router or ISP issue beyond user-level fixes"),
    "slow_pc": ("Tier 2 - Desktop support", "needs disk/RAM health checks, malware scan or reimage"),
    "email": ("Tier 2 - Microsoft 365 / email admin", "mailbox, licence or Outlook profile issue"),
    "vpn": ("Tier 2 - Network administrator", "VPN server, certificate or user VPN-group configuration"),
    "display": ("Tier 2 - Hardware technician", "monitor, cable, dock or graphics hardware fault"),
    "peripherals": ("Tier 1 - Help desk", "likely faulty device; swap from spare stock"),
    "account": ("Tier 1 - Help desk (admin)", "requires identity verification and an admin unlock/reset"),
    "bsod": ("Tier 2 - Desktop support", "needs crash-dump analysis, driver/RAM testing or reimage"),
    "audio": ("Tier 1 - Help desk", "audio driver or headset replacement"),
    "software": ("Tier 1 - Help desk (admin rights)", "install/repair requires admin rights or a licence"),
    "security": ("Tier 3 - Security incident response", "possible compromise; credentials and device must be "
                                                        "secured"),
}


def diagnose(text: str) -> str | None:
    for pattern, category in DIAGNOSIS_RULES:
        if re.search(pattern, text, re.I):
            return category
    return None


def detect_option(question: dict, text: str) -> str | None:
    for option, effects in question["options"].items():
        if effects.get("detect") and re.search(effects["detect"], text, re.I):
            return option
    return None


def questions_for(category: str) -> list[dict]:
    return FLOWS.get(category, []) + DEVICE_QUESTIONS + [IMPACT_QUESTION]


def max_priority(*levels: str | None) -> str:
    valid = [p for p in levels if p in PRIORITIES]
    return max(valid, key=PRIORITIES.index) if valid else "medium"
