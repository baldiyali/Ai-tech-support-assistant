---
id: blue-screen-crash
title: Blue Screen (BSOD) and Unexpected Restarts
category: bsod
keywords: blue screen, bsod, crash, stop code, restarts, reboot loop, critical process died, kernel, memory management, irql, system crash, sad face
---
# Blue Screen (BSOD) and Unexpected Restarts

## Symptoms
- Blue screen with a sad face and a stop code (e.g., `CRITICAL_PROCESS_DIED`, `MEMORY_MANAGEMENT`)
- The computer restarts on its own or gets stuck in a restart loop

## Troubleshooting Steps
1. Write down or take a photo of the stop code shown on the blue screen. This is the most useful information for a technician.
2. Think about what changed recently (new device, driver, update, or software). Disconnect any newly added hardware.
3. Install all Windows updates and optional driver updates: Settings > Windows Update > Advanced options > Optional updates.
4. If the problem started after a recent update or program install, uninstall it (Settings > Apps, or Windows Update > Update history > Uninstall updates).
5. Run system file repair: open Command Prompt as administrator and run `sfc /scannow`, then `DISM /Online /Cleanup-Image /RestoreHealth`.
6. Run Windows Memory Diagnostic (search for it in Start) and let the computer restart to test RAM.
7. If Windows won't start normally, boot into Safe Mode (hold Shift while clicking Restart > Troubleshoot > Advanced options > Startup Settings) and remove the recent change.

## When to Escalate
- Blue screens keep happening after updates and repairs, or the memory test reports errors.
- The computer can't start Windows at all.

## Recommended Next Action
Analyse crash dumps (C:\Windows\Minidump) for the faulting driver, test RAM and disk, update BIOS/drivers, and reimage the device if needed. Back up the user's data first.
