from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Callable, List, Optional

from .api import EmulatorConfig, EmulatorEvent, EmulatorLogRecord, EmulatorSnapshot


class _EventLoggingHandler(logging.Handler):
    def __init__(self, sink: Callable[[EmulatorEvent], None]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = record.msg if isinstance(record.msg, str) else repr(record.msg)
        self._sink(
            EmulatorEvent.log_event(
                EmulatorLogRecord.create(
                    created_ts=record.created,
                    level_name=record.levelname,
                    logger_name=record.name,
                    message=message,
                )
            )
        )


class ScannerEmulatorController:
    def __init__(self, *, emit_events: bool = True) -> None:
        self._emit_events = emit_events
        self._events: queue.Queue[EmulatorEvent] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._emulator = None
        self._last_snapshot: Optional[EmulatorSnapshot] = None
        self._logger_handler: Optional[_EventLoggingHandler] = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self, config: EmulatorConfig, timeout: float = 15.0) -> EmulatorSnapshot:
        with self._lock:
            if self.is_running:
                raise RuntimeError("Emulator backend is already running")
            ready_queue: queue.Queue[object] = queue.Queue(maxsize=1)
            thread = threading.Thread(
                target=self._thread_entry,
                args=(config, ready_queue),
                name="scanner-emu-backend",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        try:
            result = ready_queue.get(timeout=timeout)
        except queue.Empty as error:
            raise TimeoutError("Timed out while starting emulator backend") from error

        if isinstance(result, Exception):
            self.stop(timeout=1.0)
            raise result

        snapshot = self.get_state()
        if snapshot is None:
            raise RuntimeError("Emulator backend started without a snapshot")
        return snapshot

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            loop = self._loop
            stop_event = self._stop_event
            thread = self._thread

        if loop is None or stop_event is None or thread is None:
            return

        loop.call_soon_threadsafe(stop_event.set)
        thread.join(timeout)
        if thread.is_alive():
            raise TimeoutError("Timed out while stopping emulator backend")

    def get_state(self) -> Optional[EmulatorSnapshot]:
        with self._lock:
            return self._last_snapshot

    def drain_events(self) -> List[EmulatorEvent]:
        events: List[EmulatorEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def disconnect(self) -> str:
        return self._invoke_command("disconnect")

    def set_connectable(self, enabled: bool) -> str:
        return self._invoke_command("set_connectable", enabled)

    def set_model(self, model) -> str:
        return self._invoke_command("set_model", model)

    def set_battery(self, percent: int) -> str:
        return self._invoke_command("set_battery", percent)

    def set_firmware(self, app_version: str, bootloader_version: str) -> str:
        return self._invoke_command("set_firmware", app_version, bootloader_version)

    def set_tx_level(self, tx_level: int) -> str:
        return self._invoke_command("set_tx_level", tx_level)

    def send_trigger(self, pressed: bool) -> str:
        return self._invoke_command("send_trigger", pressed)

    def queue_rfid(self, epc_hex: str, rssi: int, antenna_id: int) -> str:
        return self._invoke_command("queue_rfid", epc_hex, rssi, antenna_id)

    def flush_rfid(self) -> str:
        return self._invoke_command("flush_rfid")

    def start_inventory(self) -> str:
        return self._invoke_command("start_inventory")

    def stop_inventory(self) -> str:
        return self._invoke_command("stop_inventory")

    def emit_barcode(self, code: str) -> str:
        return self._invoke_command("emit_barcode", code)

    def start_feed(self, feed_config) -> str:
        return self._invoke_command("start_feed", feed_config)

    def stop_feed(self) -> str:
        return self._invoke_command("stop_feed")

    def get_feed_status(self) -> str:
        return self._invoke_command("get_feed_status")

    def describe_state(self) -> str:
        snapshot = self.get_state()
        if snapshot is None:
            raise RuntimeError("Emulator backend is not running")
        return snapshot.describe()

    def _invoke_command(self, method_name: str, *args) -> str:
        loop, emulator = self._require_backend()
        future = asyncio.run_coroutine_threadsafe(
            getattr(emulator, method_name)(*args),
            loop,
        )
        result = future.result(timeout=10.0)
        self._emit_event(EmulatorEvent.action_result(result))
        return result

    def _require_backend(self):
        with self._lock:
            loop = self._loop
            emulator = self._emulator
        if loop is None or emulator is None or not self.is_running:
            raise RuntimeError("Emulator backend is not running")
        return loop, emulator

    def _thread_entry(
        self,
        config: EmulatorConfig,
        ready_queue: "queue.Queue[object]",
    ) -> None:
        asyncio.run(self._backend_main(config, ready_queue))

    async def _backend_main(
        self,
        config: EmulatorConfig,
        ready_queue: "queue.Queue[object]",
    ) -> None:
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        emulator = None
        ready_sent = False
        logger = logging.getLogger("scanner_emu")
        handler = _EventLoggingHandler(self._emit_event)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, config.normalized_log_level()))

        with self._lock:
            self._loop = loop
            self._stop_event = stop_event
            self._logger_handler = handler

        try:
            try:
                from .emulator import ScannerEmulator
            except ImportError as error:
                if error.name and error.name.startswith("bumble"):
                    raise RuntimeError(
                        "Bumble is not installed. Install it with "
                        "`python3 -m pip install bumble`."
                    ) from error
                raise

            emulator = ScannerEmulator(
                config.transport_spec,
                config.build_state(),
                logger=logger,
                on_state_changed=self._record_state_change,
            )
            with self._lock:
                self._emulator = emulator

            await emulator.start()
            self._record_state_change()
            ready_queue.put(True)
            ready_sent = True
            snapshot = self.get_state()
            if snapshot is not None:
                self._emit_event(EmulatorEvent.backend_started(snapshot))
            await stop_event.wait()
        except Exception as error:
            snapshot = self.get_state()
            if not ready_sent:
                ready_queue.put(error)
                ready_sent = True
            self._emit_event(EmulatorEvent.error(str(error), snapshot))
        finally:
            if emulator is not None:
                try:
                    await emulator.stop()
                except Exception as error:
                    self._emit_event(
                        EmulatorEvent.error(str(error), self.get_state())
                    )
                self._record_state_change()

            stopped_snapshot = self.get_state()
            if ready_sent:
                self._emit_event(EmulatorEvent.backend_stopped(stopped_snapshot))

            logger.removeHandler(handler)
            handler.close()

            with self._lock:
                self._loop = None
                self._stop_event = None
                self._emulator = None
                self._thread = None
                self._logger_handler = None

    def _record_state_change(self) -> None:
        emulator = None
        with self._lock:
            emulator = self._emulator
        if emulator is None:
            return
        snapshot = emulator.snapshot()
        with self._lock:
            self._last_snapshot = snapshot
        self._emit_event(EmulatorEvent.state_changed(snapshot))

    def _emit_event(self, event: EmulatorEvent) -> None:
        if not self._emit_events:
            return
        self._events.put(event)
