# Demo video agent brief

This directory holds the reproducible Remotion source for the README demo
GIF and the GitHub social preview.

## Source precedence

1. The current user's request.
2. `STORYBOARD.md`, the human-readable story and review contract.
3. `src/storyboard.ts`, the executable timing, copy, and asset list.
4. Scene and component implementation.

Keep `STORYBOARD.md` and `src/storyboard.ts` aligned; copy and timings
belong there, not scattered through scene code.

## Privacy and accuracy

- Only synthetic data: the catalog from `scripts/media/make_demo_catalog.py`,
  the virtual controller peer, invented EANs under the GS1 documentation
  prefix. Never capture a real catalog, BLE address, or store.
- Show only shipped behavior. Do not stage UI that does not exist.

## Output contract

- Master: 1920x1080, 30 fps, 660 frames, no audio, `out/demo-master.mp4`
  (ignored by Git).
- README GIF: `out/demo.gif`, infinite loop, at most 10 MiB. It is not
  tracked; upload it (and `docs/media/3d-store-demo.mp4`) as assets of the
  release the README links to, then update the README GIF link if the release
  tag changed. The walkthrough watch link uses a repository-scoped GitHub
  attachment for browser playback; see `../scripts/media/README.md`.
- Social preview: `../.github/assets/social-preview.png`, 1280x640 PNG, at
  most 1 MiB.
- The GIF script may lower frame rate, palette, or resolution in that
  order; it must not shorten the story without user approval.

## Update workflow

1. Recapture assets with `scripts/media/` if the UI changed.
2. Update `STORYBOARD.md` (bump the revision) and `src/storyboard.ts`.
3. `npm ci && npm run check && npm run render`.
4. `npm run social-preview && npm run gif && npm run verify`.
5. Inspect the GIF at README size and the social preview at card size.
6. Upload `out/demo.gif` and `docs/media/3d-store-demo.mp4` to the current
   GitHub release and update the README GIF link to that tag. When the
   walkthrough changes, also update its playback attachment and watch link
   using the instructions in `../scripts/media/README.md`.
7. Update the README when the product story changes.
