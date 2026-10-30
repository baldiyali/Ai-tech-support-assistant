---
id: printer-not-printing
title: Printer Not Printing or Jammed
category: printer
keywords: printer, print, printing, paper jam, jammed, toner, ink, queue, spooler, offline, scanner, copier
---
# Printer Not Printing or Jammed

## Symptoms
- Documents are sent but nothing prints
- Printer shows as "Offline" or jobs are stuck in the queue
- Paper jam, faded prints, or error lights on the printer

## Troubleshooting Steps
1. Check the printer's display panel for an error message (paper jam, out of paper, low toner, door open). Clear any jammed paper gently in the direction of the paper path and close all doors.
2. Make sure the printer is powered on, has paper in the correct tray, and is connected to the network (network light on, or Wi-Fi icon on the panel).
3. On your computer, open Settings > Bluetooth & devices > Printers & scanners, select the printer, and choose "Open print queue". Cancel all stuck jobs.
4. Set the correct printer as default and make sure "Use Printer Offline" is unchecked in the print queue's Printer menu.
5. Restart the printer: turn it off, wait 30 seconds, and turn it back on. Wait until it shows "Ready" before printing again.
6. Restart the Print Spooler service: press Win+R, type `services.msc`, find "Print Spooler", right-click and choose Restart. Then print a test page.
7. Remove the printer from Printers & scanners and add it again ("Add device"), which reinstalls the driver.

## When to Escalate
- The printer shows a hardware error code, makes grinding noises, or jams repeatedly.
- The printer doesn't print for anyone in the office (likely a printer/network issue, not your PC).

## Recommended Next Action
Technician to check the printer hardware/error code, update or reinstall the printer driver on the print server, and verify the printer's IP address/network configuration.
