from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from nodus_circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def _failing():
    raise RuntimeError("boom")


def _succeeding():
    return "ok"


# ── Basic state transitions ───────────────────────────────────────────────────

def test_initial_state_is_closed():
    cb = CircuitBreaker("test", failure_threshold=2)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_closed_on_success():
    cb = CircuitBreaker("test", failure_threshold=2)
    result = cb.call(_succeeding)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=2)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_failing)
    assert cb.state == CircuitState.OPEN


def test_open_rejects_immediately():
    cb = CircuitBreaker("test", failure_threshold=1)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.call(_succeeding)


def test_reset_closes_circuit():
    cb = CircuitBreaker("test", failure_threshold=1)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# ── Half-open probe ───────────────────────────────────────────────────────────

def test_half_open_probe_success_closes():
    cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=0)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN
    # recovery_timeout=0 means next call enters half-open immediately
    result = cb.call(_succeeding)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


def test_half_open_probe_failure_reopens():
    cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=0)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN


# ── on_state_change callback ──────────────────────────────────────────────────

def test_on_state_change_called_on_open():
    hook = MagicMock()
    cb = CircuitBreaker("svc", failure_threshold=1, on_state_change=hook)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    hook.assert_called_once_with("svc", "closed", "open")


def test_on_state_change_called_on_close():
    hook = MagicMock()
    cb = CircuitBreaker("svc", failure_threshold=1, recovery_timeout_secs=0, on_state_change=hook)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    cb.call(_succeeding)
    # calls: closed->open, open->half_open (implicit in _enter_call), half_open->closed
    states = [(c.args[1], c.args[2]) for c in hook.call_args_list]
    assert ("closed", "open") in states
    assert ("half_open", "closed") in states


def test_on_state_change_exception_does_not_break_breaker():
    def bad_hook(name, prev, new):
        raise ValueError("hook crash")

    cb = CircuitBreaker("svc", failure_threshold=1, on_state_change=bad_hook)
    # Should not raise — hook exception is swallowed
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.state == CircuitState.OPEN


# ── Async call ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_call_success():
    cb = CircuitBreaker("async-test", failure_threshold=2)

    async def good():
        return "async-ok"

    result = await cb.async_call(good)
    assert result == "async-ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_async_call_opens_on_threshold():
    cb = CircuitBreaker("async-test", failure_threshold=2)

    async def bad():
        raise RuntimeError("async boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.async_call(bad)
    assert cb.state == CircuitState.OPEN


# ── Properties ────────────────────────────────────────────────────────────────

def test_opened_at_set_on_open():
    cb = CircuitBreaker("test", failure_threshold=1)
    assert cb.opened_at is None
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    assert cb.opened_at is not None


def test_opened_at_cleared_on_close():
    cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=0)
    with pytest.raises(RuntimeError):
        cb.call(_failing)
    cb.call(_succeeding)
    assert cb.opened_at is None
