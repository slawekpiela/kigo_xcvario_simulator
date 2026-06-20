"""Telemetry clock and publish cadence for the simulator runtime."""

from __future__ import annotations

import time
from threading import Event, Lock, Thread
from typing import Protocol, Sequence

from .contracts import SimulationSnapshot


class SnapshotPublisher(Protocol):
    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        ...


class TelemetryScheduler:
    def __init__(
        self,
        *,
        orchestrator,
        ownship_publishers: Sequence[SnapshotPublisher] = (),
        traffic_publishers: Sequence[SnapshotPublisher] = (),
        tick_hz: int,
        ownship_hz: int,
        traffic_hz: int,
        time_module=time,
    ) -> None:
        self._orchestrator = orchestrator
        self._ownship_publishers = tuple(ownship_publishers)
        self._traffic_publishers = tuple(traffic_publishers)
        self._time = time_module
        self._tick_interval_s = 1.0 / max(1, int(tick_hz))
        self._ownship_every_ticks = max(1, round(max(1, int(tick_hz)) / max(1, int(ownship_hz))))
        self._traffic_every_ticks = max(1, round(max(1, int(tick_hz)) / max(1, int(traffic_hz))))
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._listener_lock = Lock()
        self._snapshot_listeners: list = []
        self._tick_count = 0
        self._last_tick_started_s: float | None = None
        self._last_jitter_s = 0.0
        self._error_count = 0
        self._last_error = ""
        self._latest_snapshot = self._orchestrator.get_snapshot()

    @property
    def latest_snapshot(self) -> SimulationSnapshot:
        return self._latest_snapshot

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def last_jitter_s(self) -> float:
        return self._last_jitter_s

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def last_error(self) -> str:
        return self._last_error

    def add_snapshot_listener(self, listener) -> None:
        with self._listener_lock:
            self._snapshot_listeners.append(listener)

    def remove_snapshot_listener(self, listener) -> None:
        with self._listener_lock:
            self._snapshot_listeners = [item for item in self._snapshot_listeners if item is not listener]

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run_loop, name="sim-telemetry-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def run_tick(self) -> SimulationSnapshot:
        now_s = self._time.monotonic()
        if self._last_tick_started_s is not None:
            self._last_jitter_s = now_s - self._last_tick_started_s - self._tick_interval_s
        self._last_tick_started_s = now_s

        snapshot = self._orchestrator.tick(self._tick_interval_s)
        self._tick_count += 1
        self._latest_snapshot = snapshot

        if self._tick_count % self._ownship_every_ticks == 0:
            for publisher in self._ownship_publishers:
                self._publish_safely(publisher, snapshot)

        if self._tick_count % self._traffic_every_ticks == 0:
            for publisher in self._traffic_publishers:
                self._publish_safely(publisher, snapshot)

        with self._listener_lock:
            listeners = tuple(self._snapshot_listeners)
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception as exc:
                self._record_error(exc)

        return snapshot

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started_s = self._time.monotonic()
            try:
                self.run_tick()
            except Exception as exc:
                self._record_error(exc)
            elapsed_s = self._time.monotonic() - started_s
            sleep_s = max(0.0, self._tick_interval_s - elapsed_s)
            if sleep_s > 0.0:
                self._time.sleep(sleep_s)

    def _publish_safely(self, publisher: SnapshotPublisher, snapshot: SimulationSnapshot) -> None:
        try:
            publisher.publish_snapshot(snapshot)
        except Exception as exc:
            self._record_error(exc)

    def _record_error(self, exc: Exception) -> None:
        self._error_count += 1
        self._last_error = f"{type(exc).__name__}: {exc}"
