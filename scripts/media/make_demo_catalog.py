"""Generate a synthetic CSV product catalog for screenshots and demos.

Everything here is invented: category names, EAN-13 values under the GS1
documentation prefix 4012345, and per-product quantities. Nothing is derived
from a real store.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

CATEGORIES = [
    ("Kitchen", 320),
    ("Textiles", 260),
    ("Lighting", 140),
    ("Books", 410),
    ("Games", 180),
    ("Stationery", 300),
    ("Garden", 220),
    ("Tools", 170),
]


def ean13(prefix: str, item_ref: int) -> str:
    body = "%s%05d" % (prefix, item_ref)
    weighted = sum((3 if index % 2 else 1) * int(d) for index, d in enumerate(body))
    return body + str((10 - weighted % 10) % 10)


def build(path: Path, products_per_category: int, seed: int) -> None:
    rng = random.Random(seed)
    rows = []
    item_ref = 10000
    for label, total in CATEGORIES:
        per_product, remainder = divmod(total, products_per_category)
        for position in range(products_per_category):
            item_ref += rng.randint(1, 9)
            quantity = per_product + (1 if position < remainder else 0)
            rows.append((ean13("4012345", item_ref), label, quantity))
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ean", "category", "quantity"])
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--products-per-category", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    build(args.output, args.products_per_category, args.seed)
    print("wrote %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
