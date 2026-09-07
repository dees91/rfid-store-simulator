# ADR 0001: LLM Wiki Knowledge Layer

## Status

Accepted on 2026-06-15.

## Context

The project already has implementation docs, protocol notes, local SDK
reference material, and compatibility assumptions spread across `README.md`,
`AGENTS.md`, `docs/nur-protocol.md`, `docs/emulator.md`, and code. Future
agents need a persistent synthesis layer so they do not have to re-derive the
same relationships from scratch in every session.

The user requested an LLM Wiki-style knowledge layer based on Andrej
Karpathy's LLM Wiki pattern and similar to the local Deesoft wiki structure.

## Decision

Use `docs/wiki/` as the persistent LLM-maintained knowledge layer for Scanner
Emulator.

The wiki includes:

- `docs/wiki/README.md` for rules and workflows;
- `docs/wiki/index.md` as the content index;
- `docs/wiki/log.md` as an append-only maintenance log;
- topic pages under `docs/wiki/topics/`;
- source summaries under `docs/wiki/sources/`.

Future agents should update the wiki when a source is ingested, reusable
analysis is produced, protocol knowledge changes, an ADR is accepted, or a lint
pass finds stale or missing knowledge.

The wiki is not a decision authority. Claims must be labeled or written so that
their status is clear: accepted, inferred, rejected, deferred, or open.
Accepted durable decisions still require explicit user acceptance and should be
recorded in ADRs or `docs/context.md`.

## Alternatives Considered

### Keep Only Existing Docs

- Pros: less documentation surface.
- Cons: reusable synthesis and open questions stay scattered across chat
  history and implementation docs.
- Rejected because future agents need a maintained intermediate layer.

### Put All Synthesis In `docs/context.md`

- Pros: one compact onboarding file.
- Cons: context would grow too large and mix accepted facts with exploratory
  synthesis.
- Rejected because `docs/context.md` should stay compact and current.

## Consequences

- `AGENTS.md` must route agents through the wiki and require wiki maintenance.
- `docs/context.md` stays compact and accepted-fact oriented.
- Protocol and workflow synthesis can grow without turning every note into an
  ADR.
- Periodic wiki linting becomes part of repository maintenance.

## Related

- `docs/wiki/README.md`
- `docs/wiki/sources/original/llm-wiki.md`
- `docs/context.md`
