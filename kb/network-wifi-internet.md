---
id: network-wifi-internet
title: No Internet or Wi-Fi Connection
category: network
keywords: internet, wifi, wi-fi, wireless, network, ethernet, connection, offline, no internet, router, dns, slow internet, disconnects
---
# No Internet or Wi-Fi Connection

## Symptoms
- "No internet" or "Connected, no internet" message
- Web pages won't load but Wi-Fi shows as connected
- Connection drops repeatedly

## Troubleshooting Steps
1. Check whether other people or devices (e.g., your phone on office Wi-Fi) have internet. If nobody does, skip to escalation; it's an office-wide outage.
2. Make sure Wi-Fi is turned on and Airplane mode is off (click the network icon in the taskbar). For wired connections, check the Ethernet cable is clicked in at both ends and the port light is blinking.
3. Disconnect from the Wi-Fi network and reconnect. If prompted, re-enter the office Wi-Fi password.
4. Restart your computer. This resets the network adapter and clears many temporary issues.
5. Run the built-in troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Network and Internet.
6. Reset the network stack: open Command Prompt as administrator and run `ipconfig /release`, `ipconfig /renew`, and `ipconfig /flushdns`.
7. Forget the Wi-Fi network (Settings > Network & internet > Wi-Fi > Manage known networks), then reconnect.

## When to Escalate
- Nobody in the office has internet (router/modem or ISP outage).
- Only your device fails after all steps (possible network adapter/driver fault).

## Recommended Next Action
Check the router/modem and ISP status; power-cycle network equipment; if only one device is affected, update or reinstall the network adapter driver.
