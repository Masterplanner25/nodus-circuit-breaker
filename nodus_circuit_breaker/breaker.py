from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""


class CircuitBreaker:
    """Three-state (closed/open/half-open) circuit breaker.

    Protects a downstream dependency from cascade failures.  When the failure
    threshold is reached the circuit opens and all calls are rejected
    immediately (``CircuitOpenError``).  After ``recovery_timeout_secs`` one
    probe call is allowed through (half-open); on success the circuit closes,
    on failure it re-opens and resets the recovery timer.

    Thread-safe via an internal ``threading.Lock``.  Async callers should use
    ``async_call``; sync callers use ``call``.

    Args:
        name: Human-readable name used in log messages and the
            ``on_state_change`` callback.
        failure_threshold: Consecutive failures required to open the circuit.
        recovery_timeout_secs: Seconds to wait before allowing a probe call.
        on_state_change: Optional callback fired on every state transition.
            Signature: ``fn(name: str, previous: str, new: str) -> None``.
            Exceptions raised by the callback are swallowed — the hook must
            never break the breaker.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_secs: int = 60,
        on_state_change: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout_secs = int(recovery_timeout_secs)
        self._on_state_change = on_state_change
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: datetime | None = None
        self._half_open_in_flight = False
        self._lock = Lock()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _transition_to(self, new_state: CircuitState, *, now: datetime) -> None:
        previous_state = self._state
        if previous_state != new_state:
            logger.warning(
                "[CircuitBreaker:%s] %s -> %s",
                self.name,
                previous_state.value,
                new_state.value,
            )
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_in_flight = False
        elif new_state == CircuitState.OPEN:
            self._opened_at = now
            self._half_open_in_flight = False
        if self._on_state_change is not None:
            try:
                self._on_state_change(self.name, previous_state.value, new_state.value)
            except Exception:
                pass  # hook must never break the breaker

    def _enter_call(self) -> str:
        with self._lock:
            now = self._now()
            if self._state == CircuitState.CLOSED:
                return "closed"

            if self._state == CircuitState.OPEN:
                if self._opened_at is not None:
                    elapsed = (now - self._opened_at).total_seconds()
                    if elapsed >= self.recovery_timeout_secs:
                        self._transition_to(CircuitState.HALF_OPEN, now=now)
                        self._half_open_in_flight = True
                        return "half_open"
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is open; rejecting call"
                )

            if self._half_open_in_flight:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is half-open; probe already in flight"
                )

            self._half_open_in_flight = True
            return "half_open"

    def _record_success(self, phase: str) -> None:
        with self._lock:
            if phase == "half_open" or self._state != CircuitState.CLOSED:
                self._transition_to(CircuitState.CLOSED, now=self._now())
            else:
                self._failure_count = 0

    def _record_failure(self, phase: str) -> None:
        with self._lock:
            now = self._now()
            if phase == "half_open" or self._state == CircuitState.HALF_OPEN:
                self._failure_count = self.failure_threshold
                self._transition_to(CircuitState.OPEN, now=now)
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN, now=now)

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func(*args, **kwargs)`` with circuit breaker protection.

        - CLOSED: call normally, track failures.
        - OPEN (timeout not elapsed): raise ``CircuitOpenError`` immediately.
        - OPEN (timeout elapsed): transition to HALF_OPEN, try once.
        - HALF_OPEN success: transition to CLOSED.
        - HALF_OPEN failure: transition back to OPEN, reset timer.
        """
        phase = self._enter_call()
        try:
            result = func(*args, **kwargs)
        except Exception:
            self._record_failure(phase)
            raise
        self._record_success(phase)
        return result

    async def async_call(
        self,
        coro_func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Async version of ``call()`` for coroutine-based clients."""
        phase = self._enter_call()
        try:
            result = await coro_func(*args, **kwargs)
        except Exception:
            self._record_failure(phase)
            raise
        self._record_success(phase)
        return result

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def opened_at(self) -> datetime | None:
        with self._lock:
            return self._opened_at

    def reset(self) -> None:
        """Force the circuit back to CLOSED regardless of current state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED, now=self._now())
