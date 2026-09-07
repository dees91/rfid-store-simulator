# RFID Store Simulator LLM Wiki

This directory is the persistent LLM-maintained knowledge layer for Scanner
Emulator. It sits between raw/reference sources and durable accepted decisions.

The wiki exists so future agents do not have to re-synthesize every protocol
note, implementation detail, observation, and planning decision from
scratch.

## Layers

`Raw and reference sources`

- Stable or source-like materials such as `README.md`, `AGENTS.md`,
  `docs/nur-protocol.md`, `docs/emulator.md`, real-scanner observations when
  a task provides them, and the upstream NUR SDK and Bumble repositories.
- Agents may read and summarize them, but should not rewrite source exports or
  vendored reference material casually.

`Wiki`

- LLM-maintained synthesis under `docs/wiki/`.
- Topic pages, source summaries, cross-links, open questions, contradictions,
  and current working summaries live here.
- Wiki pages can contain `accepted`, `inferred`, `rejected`, `deferred`, and
  `open` claims, but must label them clearly.

`Accepted decisions`

- Durable accepted decisions live in `docs/decisions/` as ADRs and in
  `docs/context.md` when they are important onboarding facts.
- Wiki synthesis does not become a decision until the user explicitly accepts
  the relevant conclusion.

## Required Files

- `index.md` is the content index. Update it whenever pages are added, removed,
  renamed, or materially repurposed.
- `log.md` is append-only. Add an entry for every source ingest, reusable query
  result saved to the wiki, ADR synchronization, and lint pass.

Use this log heading format:

```text
## [YYYY-MM-DD] type | Short title
```

Known `type` values: `setup`, `ingest`, `query`, `decision`, `lint`,
`maintenance`.

## Workflows

### Ingest

When a new source is added or approved for use:

1. Read the source and identify whether it is raw input, reference material,
   accepted decision, rejected material, or research.
2. Update or create one source page under `sources/`.
3. Update relevant topic pages under `topics/`.
4. Record contradictions, stale claims, and open questions.
5. Update `index.md`.
6. Append to `log.md`.

### Query

When answering a reusable question:

1. Read `index.md` first.
2. Read the relevant topic/source pages.
3. Answer with links to wiki pages and source files.
4. If the answer creates useful synthesis, file it back into the wiki after
   user approval for edits or when the task explicitly asks for maintained
   context.

### Lint

Periodically check the wiki for:

- contradictions between topic pages, ADRs, and current code;
- claims that are not labeled by status;
- important concepts without pages;
- orphan pages missing from `index.md`;
- stale references to missing observations or moved files;
- external or source-like data copied where only summaries should exist.

## Safety

- Do not copy external app data, real inventory exports,
  barcode/RFID captures, or scanner logs into the wiki.
- Prefer summaries, aggregate facts, links, and source references.
- Do not vendor the Nordic ID NUR SDK; it carries no license.
- Keep accepted decisions separate from inferred protocol synthesis.
