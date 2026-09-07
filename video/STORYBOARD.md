# RFID Store Simulator README demo storyboard

Revision: 3

Format: 22 seconds, 1920x1080, 30 fps, silent, light canvas matching the 3D
UI's HUD palette. Must stay readable with no sound at 960x540 in a GitHub
README.

Audience: developers of RFID inventory software and anyone
evaluating whether the emulator replaces a physical Nordic ID EXA scanner for
testing.

## Social preview

Static PNG, 1280x640. Product label `RFID Store Simulator`, headline `The RFID
scanner, without the scanner.`, two supporting lines naming the hardware
emulated and the surfaces, and a tilted frame of the aisle screenshot
(`ui/3d-store-final.png`).

## Timeline

1. **Problem** (frames 0–84). Eyebrow `RFID HANDHELD SCANNERS · BLE`,
   headline `Testing an RFID app without the scanner in your hand?`, chips
   for EXA51, EXA81, BLE, NUR protocol.
2. **Emulator** (78–186). Eyebrow `BUILT ON SCANNER-EMU`, headline `A Nordic ID EXA scanner, emulated in
   Python.` and a two-node diagram: `Your app` (any BLE host) linked to
   `scanner-emu on macOS` over `BLE · Nordic UART · NUR`, with the radio
   options under the host node.
3. **Store** (180–318). Browser frame with the aisle screenshot, then the
   scan-start screenshot. Callout `Walk a store generated from your product
   catalog.`
4. **Scan** (312–492). Browser frame playing `ui/scan-clip.mp4`, a 6 s cut
   from the second pass of the captured walkthrough where shelves turn
   green. Callouts `Aim at a shelf. Tags flow to your app over BLE.` then
   `Every shelf turns green as the inventory fills.`
5. **CLI** (486–576). Headline `Or drive it from the REPL.` beside a
   terminal panel typing `scanner-emu run --transport usb:0 --model exa51`
   and three REPL commands. Deliberately secondary: no screenshots, one
   panel.
6. **Closing** (570–660). Aisle screenshot, product label, headline `The
   RFID scanner, without the scanner.`, footer `Python 3.10+ · MIT ·
   github.com/dees91/rfid-store-simulator`.

Scenes overlap by six frames for cross-fades. Copy and timings are the
values in `src/storyboard.ts`; update both together and bump the revision.
