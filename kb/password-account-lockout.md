---
id: password-account-lockout
title: Password Reset and Account Lockout
category: account
keywords: password, locked out, lockout, account locked, forgot password, reset password, login, sign in, can't log in, mfa, two-factor, authenticator, expired password
---
# Password Reset and Account Lockout

## Symptoms
- "Your account has been locked" or "incorrect password" messages
- Password expired and can't be changed
- Not receiving MFA / two-factor prompts

## Troubleshooting Steps
1. Check Caps Lock and the keyboard language (e.g., ENG vs another layout in the taskbar), then carefully retype your password.
2. If you just changed your password, use the new one everywhere; old saved passwords on your phone (email app) can lock your account repeatedly. Update or remove them.
3. Wait 15 minutes. Most accounts automatically unlock after a short lockout period, then try once more.
4. Use the self-service password reset page (e.g., aka.ms/sspr for Microsoft 365) from another device to reset your password.
5. For MFA issues, make sure your phone has the correct time and a connection, open the authenticator app manually, and check for pending approvals.

## When to Escalate
- Self-service reset isn't set up or doesn't work.
- You got a new phone and lost access to your authenticator app.
- You didn't trigger the lockout yourself (possible attack: report it).

## Recommended Next Action
Verify the user's identity, unlock the account and/or issue a temporary password in the admin console, and re-register MFA methods if needed. Review sign-in logs for suspicious activity.
