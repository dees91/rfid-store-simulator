# README demo video

Remotion source for the animation embedded in the repository README and for
the GitHub social preview. Everything shown is captured from the 3D store
simulator running against a virtual controller with a synthetic catalog
(`scripts/media/`), so no real hardware or catalog is involved.

## Outputs

| File | Contract |
| --- | --- |
| `out/demo-master.mp4` | 1920x1080, 30 fps, 660 frames (22 s), silent, ignored by Git |
| `out/demo.gif` | 960x540, infinite loop, at most 10 MiB; uploaded as a release asset, not tracked |
| `../.github/assets/social-preview.png` | 1280x640 PNG, at most 1 MiB |

## Regenerate

Requires Node 22+, ffmpeg, and the captured assets in `public/ui/`
(see `../scripts/media/README.md` for how those are produced).

```bash
npm ci
npm run check
npm run render
npm run social-preview
npm run gif
npm run verify
```

`npm run studio` opens Remotion Studio for editing. Scene timing and copy
live in `src/storyboard.ts`; `STORYBOARD.md` is the human-readable version
and must be kept in step with it.
