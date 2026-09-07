# LLM Wiki Pattern Source

## Status

Source note for the external LLM Wiki idea requested by the user on
2026-06-15.

## Source

- Original URL:
  `https://gist.githubusercontent.com/karpathy/442a6bf555914893e9891c11519de94f/raw/ac46de1ad27f92b28ac95459c782c07f6b8c964a/llm-wiki.md`
- Author indicated by the gist path: Andrej Karpathy.
- Local handling: summarized as a source note instead of copying the full
  external document.

## Relevant Pattern

The source proposes a persistent Markdown wiki maintained by an LLM agent. Raw
sources remain stable, the wiki becomes the maintained synthesis layer, and a
schema file such as `AGENTS.md` teaches future agents how to update it.

For this repository, the pattern is instantiated as:

- raw/reference sources: repository docs, code, local SDK/reference checkouts,
  and real-scanner observations when available;
- wiki: `docs/wiki/` with `index.md`, `log.md`, topic pages, and source
  summaries;
- schema: `AGENTS.md` plus this `docs/wiki/README.md`;
- durable decisions: `docs/decisions/` and compact facts in `docs/context.md`.

## Adaptation Notes

- The wiki should compile protocol and architecture knowledge once, then keep
  it current as new observations, host behaviors, or implementation changes
  appear.
- `index.md` is content-oriented and should be read first.
- `log.md` is chronological and append-only.
- Useful answers can be filed back into the wiki when they create reusable
  synthesis.
- Lint passes should look for stale claims, contradictions, orphan pages, and
  missing cross-references.
