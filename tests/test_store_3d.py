from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scanner_emu.epc import SERIAL_MAX
from scanner_emu.product_catalog import Product, ProductCatalog, load_catalog
from scanner_emu.store_3d import (
    DEFAULT_DISTRIBUTION,
    Store3DConfig,
    StoreSession,
    TagDistributionBucket,
    generate_store_session,
    load_store_session,
    minimum_shelf_count,
)


VALID_PRODUCTS = (
    Product("4006381333931", "books", 45),
    Product("4012345358216", "kitchen", 17),
    Product("5901234123457", "garden", 8),
    Product("1234567890128", "tools", 5),
    Product("2109876543210", "lighting", 3),
)
VALID_TOTAL = 78

SMALL_DISTRIBUTION = (
    TagDistributionBucket("single", 0.35, 1, 1),
    TagDistributionBucket("normal", 0.45, 2, 8),
    TagDistributionBucket("dense", 0.20, 9, 16),
)


class Store3DTests(unittest.TestCase):
    def test_header_only_csv_loads_empty_catalog(self) -> None:
        catalog = csv_catalog("ean,category,quantity\n")

        self.assertEqual(len(catalog), 0)
        self.assertEqual(catalog.total_quantity, 0)

    def test_csv_without_ean_column_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(catalog_path, "code,category,quantity\n4006381333931,books,1\n")

            with self.assertRaisesRegex(ValueError, "'ean'"):
                load_catalog(catalog_path.as_posix())

    def test_csv_applies_category_and_quantity_defaults(self) -> None:
        catalog = csv_catalog(
            "ean,category,quantity\n"
            "4006381333931,,\n"
            "4012345358216,kitchen,\n"
            "5901234123457,,\n"
        )

        self.assertEqual(
            [(product.ean, product.category, product.quantity) for product in catalog.products],
            [
                ("4006381333931", "Uncategorized", 1),
                ("4012345358216", "kitchen", 1),
                ("5901234123457", "Uncategorized", 1),
            ],
        )

    def test_csv_headers_are_case_space_and_bom_tolerant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            catalog_path.write_bytes(
                " EAN , Category , Quantity \n4006381333931,books,2\n".encode(
                    "utf-8-sig"
                )
            )

            catalog = load_catalog(catalog_path.as_posix())

        self.assertEqual(
            [(product.ean, product.category, product.quantity) for product in catalog.products],
            [("4006381333931", "books", 2)],
        )

    def test_csv_skips_rows_without_valid_ean(self) -> None:
        catalog = csv_catalog(
            "ean,category,quantity\n"
            ",books,1\n"
            "not-an-ean,books,1\n"
            "4006381333931,books,2\n"
        )

        self.assertEqual(
            [(product.ean, product.quantity) for product in catalog.products],
            [("4006381333931", 2)],
        )

    def test_load_catalog_rejects_non_csv_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("catalog.sqlite", "catalog.txt"):
                catalog_path = Path(tmp) / name
                catalog_path.write_text("ean,category,quantity\n", encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "CSV"):
                    load_catalog(catalog_path.as_posix())

    def test_csv_duplicate_eans_are_merged(self) -> None:
        catalog = csv_catalog(
            "ean,category,quantity\n"
            "4006381333931,books,3\n"
            "4006381333931,books,2\n"
            "4012345358216,kitchen,4\n"
        )

        self.assertEqual(
            [(product.ean, product.category, product.quantity) for product in catalog.products],
            [
                ("4006381333931", "books", 5),
                ("4012345358216", "kitchen", 4),
            ],
        )
        self.assertEqual(catalog.total_quantity, 9)

    def test_csv_negative_and_non_numeric_quantities_fail_with_row_number(self) -> None:
        for bad_quantity in ("-1", "abc"):
            with self.subTest(quantity=bad_quantity):
                with tempfile.TemporaryDirectory() as tmp:
                    catalog_path = Path(tmp) / "catalog.csv"
                    write_csv(
                        catalog_path,
                        "ean,category,quantity\n4006381333931,books,%s\n" % bad_quantity,
                    )

                    with self.assertRaisesRegex(ValueError, "row 2"):
                        load_catalog(catalog_path.as_posix())

    def test_csv_zero_quantity_is_kept(self) -> None:
        catalog = csv_catalog("ean,category,quantity\n4006381333931,books,0\n")

        self.assertEqual(catalog.products[0].quantity, 0)
        self.assertEqual(catalog.total_quantity, 0)

    def test_missing_csv_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "missing.csv"

            with self.assertRaises(FileNotFoundError):
                load_catalog(catalog_path.as_posix())

            self.assertFalse(catalog_path.exists())

    def test_sample_uses_category_weights(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))

        self.assertEqual(len(catalog.sample(10)), 10)
        weighted = catalog.sample(
            20,
            {
                "books": 1.0,
                "kitchen": 0.0,
                "garden": 0.0,
                "tools": 0.0,
                "lighting": 0.0,
            },
        )
        self.assertTrue(all(product.category == "books" for product in weighted))

    def test_generation_total_matches_quantity_sum(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))

        session = generate_store_session(catalog, small_config(7))

        self.assertEqual(session.total_epc_count, VALID_TOTAL)
        self.assertEqual(session.total_epc_count, catalog.total_quantity)
        self.assertEqual(session.catalog_product_count, len(VALID_PRODUCTS))
        self.assertEqual(session.placed_product_count, len(VALID_PRODUCTS))

    def test_generation_matches_per_ean_quantities(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))

        session = generate_store_session(catalog, small_config(7))

        sums: dict[str, int] = {}
        for group in session.render_groups:
            sums[group.ean] = sums.get(group.ean, 0) + group.tag_count
        self.assertEqual(
            sums,
            {
                "4006381333931": 45,
                "4012345358216": 17,
                "5901234123457": 8,
                "1234567890128": 5,
                "2109876543210": 3,
            },
        )

    def test_zero_quantity_products_are_not_placed(self) -> None:
        catalog = ProductCatalog(
            products=[
                Product("4006381333931", "books", 0),
                Product("4012345358216", "kitchen", 6),
            ]
        )

        session = generate_store_session(catalog, small_config(7))

        self.assertEqual(session.total_epc_count, 6)
        self.assertEqual(session.placed_product_count, 1)
        self.assertEqual(
            {group.ean for group in session.render_groups}, {"4012345358216"}
        )

    def test_generation_without_positive_quantities_fails(self) -> None:
        for products in ([], [Product("4006381333931", "books", 0)]):
            with self.subTest(products=products):
                with self.assertRaises(ValueError):
                    generate_store_session(
                        ProductCatalog(products=list(products)), small_config(7)
                    )

    def test_single_product_catalog_yields_unique_epcs(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 80)]
        )

        session = generate_store_session(catalog, small_config(11))

        self.assertEqual(session.total_epc_count, 80)
        self.assertEqual(len(set(session.all_epcs())), 80)
        self.assertEqual(
            {tag.ean for _, tags in session.scan_groups for tag in tags},
            {"4006381333931"},
        )

    def test_serials_are_global_within_store_session(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))

        session = generate_store_session(catalog, small_config(80))
        serials = [tag.serial for _, tags in session.scan_groups for tag in tags]

        self.assertEqual(len(serials), session.total_epc_count)
        self.assertEqual(len(set(serials)), session.total_epc_count)
        self.assertEqual(min(serials), session.config.serial_start)

    def test_small_capacity_creates_single_and_multi_tag_groups(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 45)]
        )
        config = Store3DConfig(
            shelf_count=1,
            shelf_levels=2,
            slots_per_level=4,
            seed=1,
        )

        session = generate_store_session(catalog, config)

        self.assertEqual(session.total_epc_count, 45)
        tag_counts = [group.tag_count for group in session.render_groups]
        self.assertIn(1, tag_counts)
        self.assertTrue(any(count > 1 for count in tag_counts))

    def test_products_do_not_starve_each_other(self) -> None:
        catalog = ProductCatalog(
            products=[
                Product("4006381333931", "books", 45),
                Product("4012345358216", "kitchen", 17),
            ]
        )

        session = generate_store_session(catalog, small_config(3))

        sums: dict[str, int] = {}
        for group in session.render_groups:
            sums[group.ean] = sums.get(group.ean, 0) + group.tag_count
        self.assertEqual(sums, {"4006381333931": 45, "4012345358216": 17})

    def test_summary_reports_label_counts_without_eans(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))
        session = generate_store_session(catalog, small_config(9))

        summary = session.summary()
        self.assertEqual(
            summary["category_tag_counts"],
            {
                "books": 45,
                "kitchen": 17,
                "garden": 8,
                "tools": 5,
                "lighting": 3,
            },
        )
        summary_text = repr(summary)
        self.assertIn("total_epc_count", summary_text)
        self.assertNotIn(session.all_epcs()[0], summary_text)
        self.assertNotIn("4006381333931", summary_text)

    def test_same_seed_reproduces_layout_and_epc_assignment(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))
        config = small_config(123)

        first = generate_store_session(catalog, config)
        second = generate_store_session(catalog, config)

        self.assertEqual(render_signature(first), render_signature(second))
        self.assertEqual(first.all_epcs(), second.all_epcs())
        self.assertEqual(first.seed, second.seed)

    def test_different_seeds_can_change_layout_or_assignment(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))

        first = generate_store_session(catalog, small_config(1))
        second = generate_store_session(catalog, small_config(2))

        self.assertNotEqual(render_signature(first), render_signature(second))
        self.assertNotEqual(first.all_epcs(), second.all_epcs())

    def test_render_metadata_is_grouped_and_scan_metadata_keeps_epcs(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))
        session = generate_store_session(catalog, small_config(44))

        self.assertLess(len(session.render_groups), session.total_epc_count)
        group = next(item for item in session.render_groups if item.tag_count > 1)
        tags = session.tags_for_group(group.group_id)

        self.assertEqual(len(tags), group.tag_count)
        self.assertFalse(hasattr(group, "epc_hex"))
        self.assertFalse(hasattr(group, "epcs"))
        self.assertTrue(all(tag.group_id == group.group_id for tag in tags))
        with self.assertRaises(AttributeError):
            session.scan_groups.append((group.group_id, ()))
        copied = copy.deepcopy(session)
        self.assertEqual(copied.all_epcs(), session.all_epcs())

    def test_invalid_config_values_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "shelf_count"):
            Store3DConfig(shelf_count=0)
        with self.assertRaisesRegex(ValueError, "distribution"):
            Store3DConfig(distribution=())
        with self.assertRaisesRegex(ValueError, "single-tag"):
            Store3DConfig(distribution=(TagDistributionBucket("multi", 1, 2, 3),))
        with self.assertRaisesRegex(ValueError, "multi-tag"):
            Store3DConfig(distribution=(TagDistributionBucket("single", 1, 1, 1),))
        with self.assertRaisesRegex(ValueError, "weight"):
            TagDistributionBucket("bad", 0, 1, 1)

    def test_unreachable_target_fails(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 5)]
        )
        distribution = (
            TagDistributionBucket("single", 1, 1, 1),
            TagDistributionBucket("double", 1, 2, 2),
        )
        config = Store3DConfig(
            shelf_count=1,
            shelf_levels=1,
            slots_per_level=1,
            seed=3,
            distribution=distribution,
        )

        with self.assertRaisesRegex(ValueError, "cannot be reached"):
            generate_store_session(catalog, config)

    def test_too_few_slots_error_names_minimum_shelf_count(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 17)]
        )
        config = Store3DConfig(
            shelf_count=1,
            shelf_levels=1,
            slots_per_level=1,
            seed=1,
        )

        with self.assertRaisesRegex(ValueError, "cannot be reached") as raised:
            generate_store_session(catalog, config)
        self.assertIn("minimum shelf count", str(raised.exception))
        self.assertIn("is 2", str(raised.exception))

    def test_minimum_shelf_count_fits_seventeen_tags_in_two_groups(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 17)]
        )

        self.assertEqual(
            minimum_shelf_count(catalog, 4, 12, DEFAULT_DISTRIBUTION), 1
        )
        session = generate_store_session(
            catalog,
            Store3DConfig(
                shelf_count=1, shelf_levels=1, slots_per_level=2, seed=2
            ),
        )
        self.assertEqual(len(session.render_groups), 2)
        self.assertEqual(
            sorted(group.tag_count for group in session.render_groups), [1, 16]
        )

    def test_minimum_shelf_count_scales_with_quantities(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 100)]
        )

        self.assertEqual(
            minimum_shelf_count(catalog, 1, 2, DEFAULT_DISTRIBUTION), 2
        )
        session = generate_store_session(
            catalog,
            Store3DConfig(
                shelf_count=2, shelf_levels=1, slots_per_level=2, seed=2
            ),
        )
        self.assertEqual(session.total_epc_count, 100)
        with self.assertRaisesRegex(ValueError, "cannot be reached"):
            generate_store_session(
                catalog,
                Store3DConfig(
                    shelf_count=1, shelf_levels=1, slots_per_level=2, seed=2
                ),
            )

    def test_minimum_shelf_count_without_positive_quantities_fails(self) -> None:
        catalog = ProductCatalog(products=[Product("4006381333931", "books", 0)])

        with self.assertRaises(ValueError):
            minimum_shelf_count(catalog, 4, 12, DEFAULT_DISTRIBUTION)

    def test_compact_reachable_target_uses_non_largest_multi_bucket(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 2)]
        )
        config = Store3DConfig(
            shelf_count=1,
            shelf_levels=1,
            slots_per_level=1,
            seed=13,
        )

        session = generate_store_session(catalog, config)

        self.assertEqual(session.total_epc_count, 2)
        self.assertEqual(len(session.render_groups), 1)
        self.assertEqual(session.render_groups[0].bucket_name, "standard")

    def test_high_density_reachable_target_repairs_to_dense_buckets(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 400)]
        )
        config = Store3DConfig(
            shelf_count=10,
            shelf_levels=1,
            slots_per_level=1,
            seed=5,
        )

        session = generate_store_session(catalog, config)

        self.assertEqual(session.total_epc_count, 400)
        self.assertEqual(len(session.render_groups), 10)
        self.assertTrue(all(group.bucket_name == "dense" for group in session.render_groups))

    def test_custom_distribution_uses_global_feasible_bucket_counts(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 15)]
        )
        distribution = (
            TagDistributionBucket("single", 1, 1, 1),
            TagDistributionBucket("small", 1, 2, 3),
            TagDistributionBucket("dense", 1, 7, 8),
        )
        config = Store3DConfig(
            shelf_count=3,
            shelf_levels=1,
            slots_per_level=1,
            seed=3,
            distribution=distribution,
        )

        session = generate_store_session(catalog, config)

        self.assertEqual(session.total_epc_count, 15)
        self.assertEqual(session.groups_by_bucket(), {"single": 1, "dense": 2})

    def test_feasible_generation_can_use_fewer_than_preferred_groups(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 9)]
        )
        distribution = (
            TagDistributionBucket("single", 1, 1, 1),
            TagDistributionBucket("quad", 1, 4, 4),
        )
        config = Store3DConfig(
            shelf_count=5,
            shelf_levels=1,
            slots_per_level=1,
            seed=17,
            distribution=distribution,
        )

        session = generate_store_session(catalog, config)

        self.assertEqual(session.total_epc_count, 9)
        self.assertEqual(len(session.render_groups), 3)
        self.assertEqual(session.groups_by_bucket(), {"single": 1, "quad": 2})

    def test_serial_exhaustion_fails_without_wrapping(self) -> None:
        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 2)]
        )
        distribution = (
            TagDistributionBucket("single", 1, 1, 1),
            TagDistributionBucket("double", 1, 2, 2),
        )
        config = Store3DConfig(
            shelf_count=1,
            shelf_levels=1,
            slots_per_level=1,
            seed=5,
            distribution=distribution,
            serial_start=SERIAL_MAX,
        )

        with self.assertRaisesRegex(ValueError, "serials"):
            generate_store_session(catalog, config)

    def test_seed_is_recorded_when_config_seed_is_omitted(self) -> None:
        catalog = ProductCatalog(products=list(VALID_PRODUCTS))
        session = generate_store_session(
            catalog,
            Store3DConfig(
                shelf_count=2,
                shelf_levels=2,
                slots_per_level=3,
                distribution=SMALL_DISTRIBUTION,
            ),
        )

        self.assertIsInstance(session.seed, int)
        self.assertGreaterEqual(session.seed, 0)

    def test_config_distribution_is_not_mutated_after_session_generation(self) -> None:
        distribution = [
            TagDistributionBucket("single", 1, 1, 1),
            TagDistributionBucket("normal", 1, 2, 4),
        ]
        config = Store3DConfig(
            shelf_count=2,
            shelf_levels=1,
            slots_per_level=2,
            seed=21,
            distribution=distribution,
        )

        catalog = ProductCatalog(
            products=[Product("4006381333931", "books", 8)]
        )
        session = generate_store_session(catalog, config)
        distribution.append(TagDistributionBucket("late", 1, 5, 8))

        self.assertEqual(len(session.config.distribution), 2)
        self.assertEqual([bucket.name for bucket in session.config.distribution], ["single", "normal"])

    def test_empty_or_invalid_csv_fails_with_valid_ean_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "invalid.csv"
            write_csv(catalog_path, "ean,category,quantity\nnot-an-ean,books,1\n")

            with self.assertRaisesRegex(ValueError, "valid EAN-13 products"):
                load_store_session(catalog_path.as_posix(), small_config(5))

    def test_blank_csv_fails_with_valid_ean_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "blank.csv"
            write_csv(catalog_path, "")

            with self.assertRaisesRegex(ValueError, "valid EAN-13 products"):
                load_store_session(catalog_path.as_posix(), small_config(5))

    def test_missing_csv_path_raises_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "missing.csv"

            with self.assertRaises(FileNotFoundError):
                load_store_session(catalog_path.as_posix(), small_config(5))

            self.assertFalse(catalog_path.exists())

    def test_load_store_session_generates_before_controller_matters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.csv"
            write_csv(
                catalog_path,
                "ean,category,quantity\n"
                "4006381333931,books,45\n"
                "4012345358216,kitchen,17\n",
            )

            session = load_store_session(catalog_path.as_posix(), small_config(5))

        self.assertEqual(session.total_epc_count, 62)
        self.assertEqual(session.placed_product_count, 2)


def small_config(seed: int) -> Store3DConfig:
    return Store3DConfig(
        shelf_count=4,
        shelf_levels=2,
        slots_per_level=5,
        seed=seed,
        distribution=SMALL_DISTRIBUTION,
    )


def write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def csv_catalog(text: str) -> ProductCatalog:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "catalog.csv"
        write_csv(path, text)
        return load_catalog(path.as_posix())


def render_signature(session: StoreSession):
    return tuple(
        (
            group.group_id,
            group.ean,
            group.tag_count,
            group.bucket_name,
        )
        for group in session.render_groups
    )
