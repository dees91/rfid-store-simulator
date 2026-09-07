from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .epc import SERIAL_MAX, ean13_to_sgtin96
from .product_catalog import ProductCatalog, load_catalog

DEFAULT_SEED_MAX = (1 << 63) - 1


@dataclass(frozen=True)
class TagDistributionBucket:
    name: str
    weight: float
    min_tags: int
    max_tags: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Distribution bucket name must not be empty")
        if self.weight <= 0:
            raise ValueError("Distribution bucket weight must be positive")
        if self.min_tags < 1:
            raise ValueError("Distribution bucket min_tags must be at least 1")
        if self.max_tags < self.min_tags:
            raise ValueError("Distribution bucket max_tags must be >= min_tags")

    @property
    def is_single_tag(self) -> bool:
        return self.min_tags == 1 and self.max_tags == 1

    @property
    def is_multi_tag(self) -> bool:
        return self.max_tags > 1

    def summary(self) -> dict[str, object]:
        return {
            "name": self.name,
            "weight": self.weight,
            "min_tags": self.min_tags,
            "max_tags": self.max_tags,
        }


DEFAULT_DISTRIBUTION: Tuple[TagDistributionBucket, ...] = (
    TagDistributionBucket("single", 0.30, 1, 1),
    TagDistributionBucket("standard", 0.50, 2, 16),
    TagDistributionBucket("dense", 0.20, 20, 40),
)


@dataclass(frozen=True)
class Store3DConfig:
    shelf_count: int = 32
    shelf_levels: int = 4
    slots_per_level: int = 12
    seed: Optional[int] = None
    distribution: Sequence[TagDistributionBucket] = field(
        default_factory=lambda: DEFAULT_DISTRIBUTION
    )
    serial_start: int = 1

    def __post_init__(self) -> None:
        if self.shelf_count < 1:
            raise ValueError("shelf_count must be positive")
        if self.shelf_levels < 1:
            raise ValueError("shelf_levels must be positive")
        if self.slots_per_level < 1:
            raise ValueError("slots_per_level must be positive")
        if self.seed is not None and self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.serial_start < 0 or self.serial_start > SERIAL_MAX:
            raise ValueError("serial_start must be in range 0..%s" % SERIAL_MAX)
        distribution = tuple(self.distribution)
        object.__setattr__(self, "distribution", distribution)
        _validate_distribution(distribution)

    @property
    def slot_capacity(self) -> int:
        return self.shelf_count * self.shelf_levels * self.slots_per_level

    def summary(self) -> dict[str, object]:
        return {
            "shelf_count": self.shelf_count,
            "shelf_levels": self.shelf_levels,
            "slots_per_level": self.slots_per_level,
            "serial_start": self.serial_start,
            "distribution": [bucket.summary() for bucket in self.distribution],
        }


@dataclass(frozen=True)
class StoreSlotLocation:
    shelf_index: int
    level_index: int
    slot_index: int

    @property
    def group_id(self) -> str:
        return "shelf-%03d-level-%02d-slot-%02d" % (
            self.shelf_index,
            self.level_index,
            self.slot_index,
        )


@dataclass(frozen=True)
class StoreRenderGroup:
    group_id: str
    shelf_index: int
    level_index: int
    slot_index: int
    ean: str
    category: str
    tag_count: int
    bucket_name: str

    def summary(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "shelf_index": self.shelf_index,
            "level_index": self.level_index,
            "slot_index": self.slot_index,
            "ean": self.ean,
            "category": self.category,
            "tag_count": self.tag_count,
            "bucket_name": self.bucket_name,
        }


@dataclass(frozen=True)
class StoreTag:
    epc_hex: str
    group_id: str
    ean: str
    serial: int
    product_index: int


@dataclass(frozen=True)
class ProductGroupPlan:
    product_index: int
    buckets: Tuple[TagDistributionBucket, ...]
    tag_counts: Tuple[int, ...]


@dataclass(frozen=True)
class GroupAllocation:
    bucket: TagDistributionBucket
    tag_count: int
    product_index: int


@dataclass(frozen=True)
class StoreSession:
    config: Store3DConfig
    seed: int
    render_groups: Tuple[StoreRenderGroup, ...]
    scan_groups: Tuple[Tuple[str, Tuple[StoreTag, ...]], ...]
    total_epc_count: int
    catalog_product_count: int
    placed_product_count: int
    category_tag_counts: Dict[str, int] = field(default_factory=dict)

    def tags_for_group(self, group_id: str) -> Tuple[StoreTag, ...]:
        for candidate_group_id, tags in self.scan_groups:
            if candidate_group_id == group_id:
                return tags
        return ()

    def all_epcs(self) -> Tuple[str, ...]:
        return tuple(
            tag.epc_hex
            for group in self.render_groups
            for tag in self.tags_for_group(group.group_id)
        )

    def summary(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "total_epc_count": self.total_epc_count,
            "render_group_count": len(self.render_groups),
            "catalog_product_count": self.catalog_product_count,
            "placed_product_count": self.placed_product_count,
            "category_tag_counts": dict(self.category_tag_counts),
            "config": self.config.summary(),
            "groups_by_bucket": self.groups_by_bucket(),
        }

    def groups_by_bucket(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for group in self.render_groups:
            counts[group.bucket_name] = counts.get(group.bucket_name, 0) + 1
        return counts


def load_store_session(
    catalog_path: str, config: Optional[Store3DConfig] = None
) -> StoreSession:
    if not Path(catalog_path).exists():
        raise FileNotFoundError(catalog_path)
    try:
        catalog = load_catalog(catalog_path)
    except ValueError as error:
        raise ValueError(
            "Store session requires a CSV catalog with valid EAN-13 "
            "products: %s" % error
        ) from error
    if len(catalog) == 0:
        raise ValueError(
            "Store session requires a CSV catalog with valid EAN-13 products: "
            "no valid products in %s" % catalog_path
        )
    return generate_store_session(catalog, config)


def generate_store_session(
    catalog: ProductCatalog, config: Optional[Store3DConfig] = None
) -> StoreSession:
    resolved_config = config or Store3DConfig()
    targets = {
        index: product.quantity
        for index, product in enumerate(catalog.products)
        if product.quantity > 0
    }
    if not targets:
        raise ValueError(
            "Store session requires a catalog with at least one product "
            "with quantity greater than 0"
        )

    seed = _resolve_seed(resolved_config.seed)
    rng = random.Random(seed)
    locations = _build_locations(resolved_config)
    rng.shuffle(locations)
    product_group_plans = _build_product_group_plans(
        rng,
        resolved_config,
        targets,
    )
    group_allocations: List[GroupAllocation] = []
    for plan in product_group_plans:
        for bucket, tag_count in zip(plan.buckets, plan.tag_counts):
            group_allocations.append(
                GroupAllocation(
                    bucket=bucket,
                    tag_count=tag_count,
                    product_index=plan.product_index,
                )
            )
    # Shuffle display order so the seed varies group placement and the
    # order in which groups claim global serials (products would otherwise
    # always serialize in catalog order).
    rng.shuffle(group_allocations)

    render_groups = []
    tags_by_group: Dict[str, Tuple[StoreTag, ...]] = {}
    next_serial = resolved_config.serial_start
    seen_epcs: set[str] = set()

    for index, allocation in enumerate(group_allocations):
        location = locations[index]
        product_index = allocation.product_index
        product = catalog.products[product_index]
        tag_count = allocation.tag_count
        group_id = location.group_id

        group_tags = []
        for _ in range(tag_count):
            serial = next_serial
            if serial > SERIAL_MAX:
                raise ValueError("Unable to assign unique EPC serials within range")
            next_serial += 1
            epc_hex = ean13_to_sgtin96(product.ean, serial)
            if epc_hex in seen_epcs:
                raise ValueError("Unable to assign unique EPC values")
            seen_epcs.add(epc_hex)
            group_tags.append(
                StoreTag(
                    epc_hex=epc_hex,
                    group_id=group_id,
                    ean=product.ean,
                    serial=serial,
                    product_index=product_index,
                )
            )

        render_groups.append(
            StoreRenderGroup(
                group_id=group_id,
                shelf_index=location.shelf_index,
                level_index=location.level_index,
                slot_index=location.slot_index,
                ean=product.ean,
                category=product.category,
                tag_count=tag_count,
                bucket_name=allocation.bucket.name,
            )
        )
        tags_by_group[group_id] = tuple(group_tags)

    category_tag_counts: Dict[str, int] = {}
    for index in sorted(targets):
        label = catalog.products[index].category
        category_tag_counts[label] = (
            category_tag_counts.get(label, 0) + targets[index]
        )

    return StoreSession(
        config=resolved_config,
        seed=seed,
        render_groups=tuple(render_groups),
        scan_groups=tuple(
            (group.group_id, tags_by_group[group.group_id])
            for group in render_groups
        ),
        total_epc_count=len(seen_epcs),
        catalog_product_count=len(catalog),
        placed_product_count=len(targets),
        category_tag_counts=category_tag_counts,
    )


def minimum_shelf_count(
    catalog: ProductCatalog,
    shelf_levels: int,
    slots_per_level: int,
    distribution: Sequence[TagDistributionBucket],
) -> int:
    """Return the smallest shelf count that fits the catalog quantities."""
    targets = {
        index: product.quantity
        for index, product in enumerate(catalog.products)
        if product.quantity > 0
    }
    if not targets:
        raise ValueError(
            "Store session requires a catalog with at least one product "
            "with quantity greater than 0"
        )
    if shelf_levels < 1 or slots_per_level < 1:
        raise ValueError("shelf_levels and slots_per_level must be positive")
    distribution_tuple = tuple(distribution)
    _validate_distribution(distribution_tuple)
    return _minimum_shelves_for_targets(
        targets, shelf_levels, slots_per_level, distribution_tuple
    )


def _minimum_shelves_for_targets(
    targets: Dict[int, int],
    shelf_levels: int,
    slots_per_level: int,
    distribution: Tuple[TagDistributionBucket, ...],
) -> int:
    total = sum(targets.values())
    minimum_groups = 0
    for index in sorted(targets):
        feasible = _feasible_group_counts(distribution, targets[index], total)
        if not feasible:
            raise ValueError(
                "Store target %s tags cannot be reached with configured "
                "distribution" % total
            )
        minimum_groups += feasible[0]
    return _ceil_div(minimum_groups, shelf_levels * slots_per_level)


def _unreachable_error(
    targets: Dict[int, int], config: Store3DConfig
) -> ValueError:
    total = sum(targets.values())
    try:
        minimum = _minimum_shelves_for_targets(
            targets,
            config.shelf_levels,
            config.slots_per_level,
            config.distribution,
        )
    except ValueError:
        return ValueError(
            "Store target %s tags cannot be reached with configured "
            "distribution" % total
        )
    return ValueError(
        "Store target %s tags cannot be reached with %s slots; "
        "minimum shelf count for this catalog and distribution is %s"
        % (total, config.slot_capacity, minimum)
    )


def _build_product_group_plans(
    rng: random.Random,
    config: Store3DConfig,
    targets: Dict[int, int],
) -> Tuple[ProductGroupPlan, ...]:
    product_items = sorted(targets.items(), key=lambda item: (-item[1], item[0]))
    slot_capacity = config.slot_capacity
    feasible_counts = {
        product_index: _feasible_group_counts(
            config.distribution,
            target,
            slot_capacity,
        )
        for product_index, target in product_items
    }
    group_counts: Optional[Dict[int, int]] = None
    if all(feasible_counts.values()):
        group_counts = _select_group_counts(
            product_items=product_items,
            feasible_counts=feasible_counts,
            slot_capacity=slot_capacity,
        )
    if group_counts is None:
        raise _unreachable_error(targets, config)

    plans = []
    for product_index, target in product_items:
        group_count = group_counts[product_index]
        preferred = _weighted_buckets(rng, config.distribution, group_count)
        _force_required_bucket_shapes(
            rng,
            preferred,
            config.distribution,
            target,
        )
        desired_counts = _desired_bucket_counts(
            config.distribution,
            preferred,
            group_count,
        )
        counts = _find_feasible_bucket_counts(
            config.distribution,
            group_count,
            target,
            desired_counts,
        )
        if counts is None:
            raise _unreachable_error(targets, config)
        buckets: list[TagDistributionBucket] = []
        for bucket, count in zip(config.distribution, counts):
            buckets.extend([bucket] * count)
        rng.shuffle(buckets)
        plans.append(
            ProductGroupPlan(
                product_index=product_index,
                buckets=tuple(buckets),
                tag_counts=_allocate_tag_counts(rng, tuple(buckets), target),
            )
        )
    return tuple(plans)


def _feasible_group_counts(
    distribution: Tuple[TagDistributionBucket, ...],
    target: int,
    slot_capacity: int,
) -> Tuple[int, ...]:
    max_bucket_tags = max(bucket.max_tags for bucket in distribution)
    min_group_count = _ceil_div(target, max_bucket_tags)
    max_group_count = min(slot_capacity, target)
    feasible = []
    for group_count in range(min_group_count, max_group_count + 1):
        desired_counts = _desired_bucket_counts(distribution, (), group_count)
        counts = _find_feasible_bucket_counts(
            distribution,
            group_count,
            target,
            desired_counts,
        )
        if counts is not None:
            feasible.append(group_count)
    return tuple(feasible)


def _select_group_counts(
    product_items: list[tuple[int, int]],
    feasible_counts: Dict[int, Tuple[int, ...]],
    slot_capacity: int,
) -> Optional[Dict[int, int]]:
    selected = {
        product_index: counts[0]
        for product_index, counts in feasible_counts.items()
    }
    min_total = sum(selected.values())
    if min_total > slot_capacity:
        return None

    max_total = sum(counts[-1] for counts in feasible_counts.values())
    desired_total = min(slot_capacity, max_total)
    total_target = sum(target for _, target in product_items)
    desired_by_product = {
        product_index: max(
            selected[product_index],
            int(round(target / total_target * desired_total)),
        )
        for product_index, target in product_items
    }

    for product_index, counts in feasible_counts.items():
        desired = min(desired_by_product[product_index], counts[-1])
        selected[product_index] = max(
            count for count in counts if count <= desired
        )

    while sum(selected.values()) > desired_total:
        candidates = [
            product_index
            for product_index, counts in feasible_counts.items()
            if selected[product_index] > counts[0]
        ]
        if not candidates:
            break
        product_index = max(
            candidates,
            key=lambda candidate: (
                selected[candidate] - desired_by_product[candidate],
                candidate,
            ),
        )
        lower_counts = [
            count
            for count in feasible_counts[product_index]
            if count < selected[product_index]
        ]
        selected[product_index] = lower_counts[-1]

    while sum(selected.values()) < desired_total:
        candidates = []
        for product_index, counts in feasible_counts.items():
            higher_counts = [
                count
                for count in counts
                if count > selected[product_index]
            ]
            if higher_counts and sum(selected.values()) - selected[product_index] + higher_counts[0] <= desired_total:
                candidates.append((product_index, higher_counts[0]))
        if not candidates:
            break
        product_index, next_count = max(
            candidates,
            key=lambda item: (
                desired_by_product[item[0]] - selected[item[0]],
                -item[1],
                item[0],
            ),
        )
        selected[product_index] = next_count

    if sum(selected.values()) > slot_capacity:
        return None
    return selected


def _validate_distribution(distribution: Sequence[TagDistributionBucket]) -> None:
    if not distribution:
        raise ValueError("distribution must contain at least one bucket")
    if not any(bucket.is_single_tag for bucket in distribution):
        raise ValueError("distribution must include an exact single-tag bucket")
    if not any(bucket.is_multi_tag for bucket in distribution):
        raise ValueError("distribution must include at least one multi-tag bucket")


def _resolve_seed(seed: Optional[int]) -> int:
    if seed is not None:
        return seed
    return random.SystemRandom().randint(0, DEFAULT_SEED_MAX)


def _build_locations(config: Store3DConfig) -> list[StoreSlotLocation]:
    return [
        StoreSlotLocation(shelf_index=shelf, level_index=level, slot_index=slot)
        for shelf in range(config.shelf_count)
        for level in range(config.shelf_levels)
        for slot in range(config.slots_per_level)
    ]


def _weighted_buckets(
    rng: random.Random,
    distribution: Tuple[TagDistributionBucket, ...],
    count: int,
) -> list[TagDistributionBucket]:
    return rng.choices(
        list(distribution),
        weights=[bucket.weight for bucket in distribution],
        k=count,
    )


def _force_required_bucket_shapes(
    rng: random.Random,
    buckets: list[TagDistributionBucket],
    distribution: Tuple[TagDistributionBucket, ...],
    target: int,
) -> None:
    single = next(bucket for bucket in distribution if bucket.is_single_tag)
    multi_candidates = [bucket for bucket in distribution if bucket.is_multi_tag]
    multi = min(multi_candidates, key=lambda bucket: bucket.min_tags)

    if not buckets:
        return
    if not any(bucket.is_single_tag for bucket in buckets):
        buckets[0] = single

    can_force_multi = (
        len(buckets) >= 2
        and target >= single.min_tags + multi.min_tags
        and not any(bucket.is_multi_tag for bucket in buckets)
    )
    if can_force_multi:
        index = 1 if buckets[0].is_single_tag else 0
        buckets[index] = multi

    if (
        len(buckets) >= 2
        and target >= single.min_tags + multi.min_tags
        and not any(bucket.is_single_tag for bucket in buckets)
    ):
        buckets[rng.randrange(len(buckets))] = single


def _bucket_counts(
    distribution: Tuple[TagDistributionBucket, ...],
    buckets: Sequence[TagDistributionBucket],
) -> Tuple[int, ...]:
    return tuple(sum(1 for bucket in buckets if bucket == candidate) for candidate in distribution)


def _desired_bucket_counts(
    distribution: Tuple[TagDistributionBucket, ...],
    preferred_buckets: Sequence[TagDistributionBucket],
    group_count: int,
) -> Tuple[int, ...]:
    counts = list(_bucket_counts(distribution, preferred_buckets))
    while sum(counts) > group_count:
        index = max(range(len(counts)), key=lambda candidate: counts[candidate])
        counts[index] -= 1
    while sum(counts) < group_count:
        if preferred_buckets:
            candidate = preferred_buckets[sum(counts) % len(preferred_buckets)]
            index = distribution.index(candidate)
        else:
            index = 0
        counts[index] += 1
    return tuple(counts)


def _find_feasible_bucket_counts(
    distribution: Tuple[TagDistributionBucket, ...],
    group_count: int,
    target: int,
    desired_counts: Tuple[int, ...],
) -> Optional[Tuple[int, ...]]:
    min_suffix = _suffix_values(distribution, "min_tags", min)
    max_suffix = _suffix_values(distribution, "max_tags", max)

    def search(
        index: int,
        groups_left: int,
        min_total: int,
        max_total: int,
    ) -> Optional[Tuple[int, ...]]:
        if index == len(distribution) - 1:
            bucket = distribution[index]
            final_min = min_total + groups_left * bucket.min_tags
            final_max = max_total + groups_left * bucket.max_tags
            if final_min <= target <= final_max:
                return (groups_left,)
            return None

        for count in _ordered_counts(groups_left, desired_counts[index]):
            bucket = distribution[index]
            next_groups = groups_left - count
            next_min = min_total + count * bucket.min_tags
            next_max = max_total + count * bucket.max_tags

            if next_min + next_groups * min_suffix[index + 1] > target:
                continue
            if next_max + next_groups * max_suffix[index + 1] < target:
                continue

            result = search(index + 1, next_groups, next_min, next_max)
            if result is not None:
                return (count,) + result
        return None

    return search(0, group_count, 0, 0)


def _suffix_values(
    distribution: Tuple[TagDistributionBucket, ...],
    attribute: str,
    selector,
) -> Tuple[int, ...]:
    values = [0] * len(distribution)
    running = getattr(distribution[-1], attribute)
    for index in range(len(distribution) - 1, -1, -1):
        running = selector(running, getattr(distribution[index], attribute))
        values[index] = running
    return tuple(values)


def _ordered_counts(max_count: int, preferred: int):
    preferred = max(0, min(max_count, preferred))
    yield preferred
    for distance in range(1, max_count + 1):
        lower = preferred - distance
        upper = preferred + distance
        if lower >= 0:
            yield lower
        if upper <= max_count:
            yield upper


def _allocate_tag_counts(
    rng: random.Random,
    buckets: Tuple[TagDistributionBucket, ...],
    target: int,
) -> Tuple[int, ...]:
    counts = [bucket.min_tags for bucket in buckets]
    remaining = target - sum(counts)
    capacities = [bucket.max_tags - bucket.min_tags for bucket in buckets]

    while remaining > 0:
        candidates = [index for index, capacity in enumerate(capacities) if capacity > 0]
        if not candidates:
            raise ValueError(
                "Store target %s EPCs cannot be allocated to distribution" % target
            )
        index = rng.choice(candidates)
        add_count = rng.randint(1, min(capacities[index], remaining))
        counts[index] += add_count
        capacities[index] -= add_count
        remaining -= add_count

    return tuple(counts)


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)
