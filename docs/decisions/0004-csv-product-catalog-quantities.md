# ADR 0004: CSV Product Catalog With Per-Product Quantities

## Status

Accepted on 2026-09-07.

## Context

The 3D store generator needs a stock plan: how many physical product
instances (RFID tags) to place per product. An external application-shaped
relational database with per-store category counts was evaluated for this,
but it ties the emulator's data model to one specific external schema
(stores, category IDs, exclusion flags) and forces the generator to invent
per-product splits from category-level numbers.

## Decision

- The product catalog input is a CSV table with `ean,category,quantity`
  columns (utf-8-sig, case/space-tolerant headers).
- `ean` is required and validated as EAN-13; bad rows are skipped with a
  warning. Empty categories fall back to `Uncategorized`; empty quantities
  default to 1. Duplicate EANs merge by summing quantities.
- `quantity` is the per-product unit count placed on the shelves. The
  quantity sum is the generated tag count (`total_epc_count`).
- 3D store planning works per product index with quantity targets, reusing
  the existing bucket machinery (single/standard/dense shapes, incremental
  group-count selection). Products with quantity 0 are not placed;
  generation fails when no product has a quantity greater than 0 or when
  quantities exceed the shelf slots (reporting the minimum fitting
  `--shelf-count`).
- `Product`, `ProductCatalog`, and `load_catalog()` expose only this model;
  no relational-database, store-count, or exclusion-flag concepts remain in
  the catalog layer.

## Alternatives Considered

- Application-shaped relational database with per-store category counts:
  rejected, it encodes one external schema into the emulator and cannot
  express exact per-product quantities.
- Category-level counts with invented per-product splits: rejected, the
  generator would invent precision the input does not provide.
- Fixed demo tag target: rejected, totals should follow the catalog.

## Consequences

- Operators describe the store with a plain CSV file; demo catalogs are
  generated into `/tmp` and never committed.
- Session summaries report per-label tag counts (`category_tag_counts`)
  without EAN lists.
- `scanner-emu-3d --shelf-count` defaults to the larger of 32 and the
  minimum fitting shelf count.

## Related

- `src/scanner_emu/product_catalog.py`
- `src/scanner_emu/store_3d.py`
- `src/scanner_emu/three_d.py`
- [3D store simulator](../usage.md#3d-store-simulator)
