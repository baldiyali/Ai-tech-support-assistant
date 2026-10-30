---
id: email-outlook
title: Email / Outlook Problems
category: email
keywords: email, outlook, mail, inbox, send, receive, sync, mailbox full, attachments, calendar, exchange, gmail, not receiving
---
# Email / Outlook Problems

## Symptoms
- Emails stuck in the Outbox or not arriving
- Outlook won't open, crashes, or keeps asking for a password
- "Mailbox full" warning

## Troubleshooting Steps
1. Check if webmail works (e.g., outlook.office.com) in your browser. If webmail works, the problem is with the Outlook app on your computer, not your account.
2. Make sure Outlook isn't in Offline mode: Send/Receive tab > "Work Offline" should not be highlighted. Then click "Send/Receive All Folders".
3. Check the Outbox for a large attachment stuck there; delete it or re-send with a smaller file or a OneDrive/SharePoint link.
4. Close Outlook completely (check Task Manager for OUTLOOK.EXE) and reopen it.
5. If you see a "Mailbox full" warning, empty Deleted Items and Junk, and archive or delete large old emails (sort by size).
6. Start Outlook in Safe Mode (Win+R, type `outlook.exe /safe`). If it works, disable add-ins under File > Options > Add-ins.
7. Repair the Office installation: Settings > Apps > Installed apps > Microsoft 365 > Modify > Quick Repair.

## When to Escalate
- Webmail also fails, or you can't sign in (account/server issue).
- You suspect someone else has access to your mailbox (treat as a security incident).

## Recommended Next Action
Check the user's mailbox status, licensing and quota in the email admin console; rebuild the Outlook profile if the app is corrupted.
