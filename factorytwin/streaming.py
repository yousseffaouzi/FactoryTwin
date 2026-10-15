"""Bounded Server-Sent Events transport for local FactoryTwin snapshots."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from threading import Condition
import time

STREAM_BUFFER_SIZE = 64
STREAM_WAIT_SECONDS = 15.0


@dataclass(frozen=True)
class StreamFrame:
    id: int
    event: str
    data: dict


class SnapshotStreamHub:
    """Non-blocking publisher with bounded replay for reconnecting SSE clients."""

    def __init__(self, capacity: int = STREAM_BUFFER_SIZE):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("stream capacity must be positive")
        self.capacity = capacity
        self._frames: deque[StreamFrame] = deque(maxlen=capacity)
        self._next_id = 1
        self._condition = Condition()

    @property
    def latest_id(self) -> int:
        with self._condition:
            return self._next_id - 1

    def publish(self, snapshot: dict) -> StreamFrame:
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be an object")
        with self._condition:
            frame = StreamFrame(self._next_id, "snapshot", deepcopy(snapshot))
            self._next_id += 1
            self._frames.append(frame)
            self._condition.notify_all()
            return frame

    def reconnect(self, last_event_id: int | None, current_snapshot: dict) -> list[StreamFrame]:
        """Replay missed frames, or return one resync frame when history is unavailable."""
        if last_event_id is not None and (type(last_event_id) is not int or last_event_id < 0):
            raise ValueError("invalid Last-Event-ID")
        with self._condition:
            if last_event_id is not None and self._frames:
                oldest = self._frames[0].id
                latest = self._frames[-1].id
                if oldest - 1 <= last_event_id <= latest:
                    return [deepcopy(frame) for frame in self._frames if frame.id > last_event_id]
                if last_event_id == latest:
                    return []
            # A fresh connection, future ID, or an ID older than retained history
            # gets an explicit full-state resync without advancing simulation time.
            return [StreamFrame(self._next_id - 1, "resync", deepcopy(current_snapshot))]

    def wait_after(self, last_event_id: int, timeout: float = STREAM_WAIT_SECONDS) -> list[StreamFrame]:
        if type(last_event_id) is not int or last_event_id < 0:
            raise ValueError("invalid stream event id")
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._next_id - 1 <= last_event_id:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)
            if not self._frames or last_event_id < self._frames[0].id - 1:
                return []  # caller must send a fresh resync snapshot
            return [deepcopy(frame) for frame in self._frames if frame.id > last_event_id]
