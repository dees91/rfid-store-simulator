# Media capture

Reproducible pipeline for the screenshots in `docs/media/`, the walkthrough
MP4 and README GIF published as release assets, and
the assets the Remotion project in `video/` consumes. Nothing here needs
Bluetooth hardware; everything is synthetic.

| Script | Purpose |
| --- | --- |
| `make_demo_catalog.py` | Writes a CSV product catalog (`ean,category,quantity`) with invented categories and EAN-13 values under the GS1 documentation prefix `4012345`. |
| `virtual_controller.py` | Serves a Bumble virtual controller over TCP. With `--peer` it also runs a fake BLE central that scans for `EXA`, connects, and subscribes to the NUR TX characteristic so the emulator has a peer. |
| `capture_3d.mjs` | Drives the 3D UI with Playwright along a fixed aisle tour, saves screenshots, and records a 1920x1080 video. |

## Run

Playwright is not a project dependency; install it once somewhere and point
`NODE_PATH` at it.

```bash
mkdir -p /tmp/pw && (cd /tmp/pw && npm init -y >/dev/null && npm i playwright && npx playwright install chromium)

.venv/bin/python scripts/media/make_demo_catalog.py /tmp/demo.csv
.venv/bin/python scripts/media/virtual_controller.py --port 9100 --peer &
.venv/bin/scanner-emu-3d --transport tcp-client:127.0.0.1:9100 --model exa51 \
  --catalog /tmp/demo.csv --shelf-count 10 \
  --standalone-inventory --port 8777 &

NODE_PATH=/tmp/pw/node_modules SCANNER_EMU_3D_URL=http://127.0.0.1:8777 \
  node scripts/media/capture_3d.mjs /tmp/raw
```

`/tmp/raw/stills/*.png` are the screenshots; `/tmp/raw/video3d/3d-store.webm`
is the recording. The tour is: spawn, walk to the first aisle, turn to the
left shelf, start scanning, walk the aisle, turn, raise scanner power to 5,
walk back scanning the right shelf, look down the aisle, stop.

## Publish

```bash
# trim the page-load lead-in and encode the walkthrough (release asset, gitignored)
ffmpeg -y -ss 1.0 -i /tmp/raw/video3d/3d-store.webm \
  -vf "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p" \
  -c:v libx264 -crf 22 -preset slow -movflags +faststart -an docs/media/3d-store-demo.mp4

# 6.2 s cut from the second pass for the Remotion scan scene
ffmpeg -y -ss 20 -t 6.2 -i /tmp/raw/video3d/3d-store.webm \
  -vf "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p" \
  -c:v libx264 -crf 18 -preset slow -movflags +faststart -an video/public/ui/scan-clip.mp4

cp /tmp/raw/stills/*.png docs/media/
cp /tmp/raw/stills/*.png video/public/ui/
```

The `-ss` offsets depend on how long the headless browser took to load; check
a contact sheet (`ffmpeg -i in.webm -vf "fps=0.5,scale=320:-1,tile=7x4" -frames:v 1 sheet.png`)
before trusting them. Then follow `video/README.md` to re-render the GIF and
social preview.
