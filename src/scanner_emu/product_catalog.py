"""CSV product catalog with per-product quantities.

Catalog file format is a CSV table with columns ``ean,category,quantity``:

- ``ean`` (required): EAN-13 product code, validated and normalized.
- ``category`` (optional): shelf label; empty values fall back to
  ``"Uncategorized"``.
- ``quantity`` (optional): units of this product placed on the shelves;
  empty values default to 1. The sum of all quantities equals the number
  of RFID tags generated for the store.
"""

from __future__ import annotations

import csv
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .epc import normalize_ean13

logger = logging.getLogger("scanner_emu.catalog")

DEFAULT_CATEGORY = "Uncategorized"


@dataclass(frozen=True)
class Product:
    ean: str
    category: str = DEFAULT_CATEGORY
    quantity: int = 1


@dataclass
class ProductCatalog:
    products: List[Product] = field(default_factory=list)
    categories: Dict[str, List[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.categories:
            for idx, product in enumerate(self.products):
                self.categories.setdefault(product.category, []).append(idx)

    def __len__(self) -> int:
        return len(self.products)

    @property
    def total_quantity(self) -> int:
        return sum(product.quantity for product in self.products)

    @classmethod
    def from_csv(cls, path: str) -> "ProductCatalog":
        """Load a catalog from a CSV file with ean,category,quantity columns."""
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            normalized_fieldnames = _normalize_headers(reader.fieldnames)
            if normalized_fieldnames is None or "ean" not in normalized_fieldnames:
                raise ValueError(
                    "CSV product catalog %s is missing the required 'ean' column "
                    "(expected columns: ean,category,quantity)" % path
                )
            reader.fieldnames = normalized_fieldnames
            rows = list(reader)
            line_numbers = list(range(2, 2 + len(rows)))
        return cls.from_rows(rows, source=path, line_numbers=line_numbers)

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Mapping[str, Any]],
        source: str = "<rows>",
        line_numbers: Optional[List[int]] = None,
    ) -> "ProductCatalog":
        """Build a catalog from row mappings with ean/category/quantity keys."""
        merged: Dict[str, Product] = {}
        order: List[str] = []
        skipped = 0
        processed = 0
        for position, raw_row in enumerate(rows):
            processed += 1
            lineno = (
                line_numbers[position]
                if line_numbers is not None and position < len(line_numbers)
                else position + 1
            )
            row = {
                str(key).strip().lower(): value for key, value in dict(raw_row).items()
            }
            ean_raw = row.get("ean")
            if ean_raw is None or str(ean_raw).strip() == "":
                logger.warning("%s row %d: skipped row without EAN", source, lineno)
                skipped += 1
                continue
            try:
                ean = normalize_ean13(str(ean_raw).strip())
            except ValueError:
                logger.warning(
                    "%s row %d: skipped invalid EAN %r", source, lineno, ean_raw
                )
                skipped += 1
                continue
            category_raw = row.get("category")
            category = (
                str(category_raw).strip()
                if category_raw is not None and str(category_raw).strip()
                else DEFAULT_CATEGORY
            )
            quantity = _parse_quantity(row.get("quantity"), source, lineno)
            if ean in merged:
                existing = merged[ean]
                merged[ean] = Product(
                    ean=ean,
                    category=existing.category,
                    quantity=existing.quantity + quantity,
                )
                logger.warning(
                    "%s row %d: duplicate EAN %s merged (quantities summed)",
                    source,
                    lineno,
                    ean,
                )
            else:
                merged[ean] = Product(ean=ean, category=category, quantity=quantity)
                order.append(ean)

        catalog = cls()
        for ean in order:
            idx = len(catalog.products)
            product = merged[ean]
            catalog.products.append(product)
            catalog.categories.setdefault(product.category, []).append(idx)
        logger.info(
            "Loaded %s products from CSV "
            "(%s rows scanned, %s skipped invalid, %s categories, %s tags total)",
            len(catalog.products),
            processed,
            skipped,
            len(catalog.categories),
            catalog.total_quantity,
        )
        return catalog

    def sample(
        self,
        count: int,
        category_weights: Optional[Dict[str, float]] = None,
    ) -> List[Product]:
        if not self.products:
            return []
        if category_weights and self.categories:
            return self._weighted_sample(count, category_weights)
        return random.choices(self.products, k=count)

    def _weighted_sample(
        self, count: int, category_weights: Dict[str, float]
    ) -> List[Product]:
        cats = list(self.categories.keys())
        weights = [category_weights.get(c, 1.0) for c in cats]
        result: List[Product] = []
        for _ in range(count):
            chosen_cat = random.choices(cats, weights=weights, k=1)[0]
            indices = self.categories[chosen_cat]
            result.append(self.products[random.choice(indices)])
        return result


def load_catalog(path: str) -> ProductCatalog:
    """Load a CSV product catalog (ean,category,quantity columns)."""
    if path.lower().endswith(".csv"):
        return ProductCatalog.from_csv(path)
    suffix = Path(path).suffix or "file"
    raise ValueError(
        "Product catalog must be a CSV file with ean,category,quantity columns; "
        "%s input is not supported" % suffix
    )


def _normalize_headers(fieldnames: Optional[List[str]]) -> Optional[List[str]]:
    if fieldnames is None:
        return None
    return [str(name).strip().lower() for name in fieldnames]


def _parse_quantity(value: Any, source: str, lineno: int) -> int:
    if value is None or str(value).strip() == "":
        return 1
    try:
        quantity = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(
            "%s row %d: quantity %r is not a valid integer" % (source, lineno, value)
        )
    if quantity < 0:
        raise ValueError(
            "%s row %d: quantity %r must not be negative" % (source, lineno, value)
        )
    return quantity
