---
id: vpn-remote-access
title: VPN Won't Connect
category: vpn
keywords: vpn, remote, remote access, work from home, tunnel, anyconnect, forticlient, globalprotect, wireguard, can't connect to office, shared drive from home
---
# VPN Won't Connect

## Symptoms
- The VPN client fails to connect or keeps disconnecting
- Connected to the VPN but company resources (shared drives, intranet) don't load
- Authentication or certificate errors

## Troubleshooting Steps
1. Confirm your regular internet works without the VPN (open a public website). If not, fix your internet connection first.
2. Double-check your username and password, and approve any MFA prompt on your phone promptly.
3. Fully quit the VPN client (including from the system tray) and open it again, then reconnect.
4. Restart your computer to clear stale network adapters created by the VPN.
5. If you're on public/hotel/guest Wi-Fi, try a different network or a phone hotspot; some networks block VPN traffic.
6. Make sure your computer's date and time are correct (Settings > Time & language). Incorrect time causes certificate errors.
7. Check for an update to the VPN client or reinstall it from the company software portal.

## When to Escalate
- You get a certificate, license, or "account not authorized" error.
- Several remote employees can't connect at the same time (VPN server issue).

## Recommended Next Action
Check the VPN server status and user's VPN group/licence; verify certificates and push a fresh VPN client profile.
