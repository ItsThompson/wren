"""Small in-process rate limiter for operational reporting.

The limiter is intentionally local to one process. It prevents a hot exception
from filling an error-reporting queue while leaving the request path free to
raise the original exception.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
from time import monotonic


class EventLimiter:
    """Allow a bounded number of events per key during a rolling time window."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, key: str) -> bool:
        """Return whether the next event for ``key`` is within the limit."""
        now = self._clock()
        cutoff = now - self._window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self._limit:
                return False
            events.append(now)
            return True

    def reset(self) -> None:
        """Drop all recorded events."""
        with self._lock:
            self._events.clear()


# The longer name reads better at Sentry call sites and keeps the implementation
# reusable for any bounded reporting sink.
ReportLimiter = EventLimiter
