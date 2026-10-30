---
id: black-screen-powers-on
title: Computer Turns On but Screen Stays Black
category: black_screen
keywords: black screen, blank screen, screen stays black, turns on but no display, no picture, power light on, fans spinning, no image, dark screen, backlight, laptop screen black, no post
---
# Computer Turns On but Screen Stays Black

## Symptoms
- The power light and fans come on, but the screen shows nothing
- The laptop screen is black but may show a very faint image under a flashlight
- The computer beeps or the lights blink in a pattern at startup

## Diagnosis Guide
- **External monitor works, built-in screen black:** the laptop's display panel, backlight, or display cable has likely failed (hardware).
- **Faint image visible with a flashlight:** the backlight has failed or brightness is at zero.
- **No logo at all and beeps / blinking lights:** the computer is failing its power-on self-test (often RAM or motherboard). Count the beeps/blinks for the technician.
- **Logo appears, then black:** Windows or the graphics driver is the problem, not the hardware.

## Troubleshooting Steps
1. Press the brightness-up key several times (often Fn + F-key with a sun icon), and press Win+Ctrl+Shift+B to restart the graphics driver.
2. Close and reopen the laptop lid, or press Win+P twice and Enter to cycle display modes in case output is going to a disconnected monitor.
3. Connect an external monitor or TV with HDMI/USB-C. If the external screen works, note that the built-in screen is the problem.
4. Do a hard reset: hold the power button for 15 seconds until it turns off, disconnect the charger and all accessories, wait 30 seconds, then power on with only the charger connected.
5. Shine a flashlight at an angle on the screen. If you can faintly see the desktop, the backlight has failed: stop here and escalate.
6. If the manufacturer logo appears but Windows goes black, force-restart three times during startup to open Windows Recovery, then choose Troubleshoot > Advanced options > Startup Settings > Safe Mode.
7. In Safe Mode, roll back or uninstall the display driver (Device Manager > Display adapters > Properties > Driver > Roll Back Driver), then restart normally.

## When to Escalate
- An external monitor works but the built-in screen doesn't (panel, cable, or backlight repair).
- Beep codes or blinking light patterns at startup with no logo (RAM/motherboard).
- The screen is physically damaged.

## Recommended Next Action
Tier 2 hardware diagnosis: test with an external display, check the display cable/backlight, reseat or test RAM, and arrange screen repair or warranty service. Provide a loaner if the user can't work.
