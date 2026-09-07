from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from .epc import SERIAL_MAX, ean13_to_sgtin96
from .nur_session import QueueTagResult
from .product_catalog import ProductCatalog
from .state import NurState

TICK_INTERVAL = 0.05  # 50 ms


@dataclass
class ConstantRate:
    tps: float = 50.0

    def tags_per_second(self, elapsed: float) -> float:
        return self.tps

    def describe(self) -> str:
        return "constant(%.1f/s)" % self.tps


@dataclass
class WaveRate:
    base: float = 50.0
    amplitude: float = 40.0
    period: float = 30.0

    def tags_per_second(self, elapsed: float) -> float:
        return max(0.0, self.base + self.amplitude * math.sin(
            2.0 * math.pi * elapsed / self.period
        ))

    def describe(self) -> str:
        return "wave(base=%.1f amp=%.1f period=%.1fs)" % (
            self.base, self.amplitude, self.period
        )


@dataclass
class BurstRate:
    high: float = 200.0
    low: float = 5.0
    burst_duration: float = 3.0
    pause_duration: float = 5.0

    def tags_per_second(self, elapsed: float) -> float:
        cycle = self.burst_duration + self.pause_duration
        phase = elapsed % cycle
        return self.high if phase < self.burst_duration else self.low

    def describe(self) -> str:
        return "burst(high=%.1f low=%.1f burst=%.1fs pause=%.1fs)" % (
            self.high, self.low, self.burst_duration, self.pause_duration
        )


@dataclass(frozen=True)
class FeedConfig:
    catalog: ProductCatalog
    rate: object = field(default_factory=ConstantRate)
    rssi_range: Tuple[int, int] = (-65, -30)
    antenna_ids: Tuple[int, ...] = (0, 1)
    category_weights: Optional[Dict[str, float]] = None
    serial_start: int = 1


@dataclass
class FeedStats:
    total_tags_fed: int = 0
    elapsed_seconds: float = 0.0
    current_rate: float = 0.0
    is_active: bool = False


class TagFeed:
    def __init__(
        self,
        queue_fn: Callable[[str, int, int], Awaitable[QueueTagResult]],
        state: NurState,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._queue_fn = queue_fn
        self._state = state
        self._logger = logger or logging.getLogger("scanner_emu.feed")
        self._task: Optional[asyncio.Task] = None
        self._config: Optional[FeedConfig] = None
        self._stats = FeedStats()
        self._serial_counter = 1

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def stats(self) -> FeedStats:
        return self._stats

    async def start(self, config: FeedConfig) -> None:
        if self.is_running:
            await self.stop()
        self._config = config
        self._serial_counter = config.serial_start
        self._stats = FeedStats()
        self._task = asyncio.ensure_future(self._feed_loop(config))
        self._logger.info(
            "Tag feed started: %s products, rate=%s",
            len(config.catalog),
            config.rate.describe() if hasattr(config.rate, "describe") else "custom",
        )

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._stats.is_active = False
        self._logger.info(
            "Tag feed stopped: %s tags fed", self._stats.total_tags_fed
        )

    async def _feed_loop(self, config: FeedConfig) -> None:
        accumulator = 0.0
        start_time = time.monotonic()
        self._stats.is_active = True

        try:
            while True:
                elapsed = time.monotonic() - start_time
                self._stats.elapsed_seconds = elapsed

                rate = config.rate.tags_per_second(elapsed)
                self._stats.current_rate = rate

                if not self._state.inventory_running or rate <= 0:
                    self._stats.is_active = self._state.inventory_running
                    await asyncio.sleep(0.2)
                    continue

                self._stats.is_active = True
                accumulator += rate * TICK_INTERVAL
                tags_this_tick = int(accumulator)

                if tags_this_tick > 0:
                    accumulator -= tags_this_tick
                    await self._emit_tags(config, tags_this_tick)

                await asyncio.sleep(TICK_INTERVAL)

        except asyncio.CancelledError:
            raise

    async def _emit_tags(self, config: FeedConfig, count: int) -> None:
        products = config.catalog.sample(count, config.category_weights)
        for product in products:
            serial = self._serial_counter
            self._serial_counter += 1
            if self._serial_counter > SERIAL_MAX:
                self._serial_counter = 1

            try:
                epc_hex = ean13_to_sgtin96(product.ean, serial)
            except ValueError:
                continue

            rssi = random.randint(config.rssi_range[0], config.rssi_range[1])
            antenna = random.choice(config.antenna_ids)

            try:
                result = await self._queue_fn(epc_hex, rssi, antenna)
                if result.accepted:
                    self._stats.total_tags_fed += 1
            except Exception:
                self._logger.debug("Failed to queue tag", exc_info=True)
