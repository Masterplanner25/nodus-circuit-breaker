from __future__ import annotations

import pytest

from nodus_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerLLMClient,
    CircuitOpenError,
    LLMCallError,
    LLMCircuitOpenError,
    LLMClient,
)


# ── Minimal stub satisfying LLMClient protocol ────────────────────────────────

class StubClient:
    def __init__(self, *, response: str = "reply", raises: Exception | None = None):
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    def chat(self, messages, model=None, temperature=0.7, max_tokens=None) -> str:
        self.calls.append({"messages": messages, "model": model})
        if self._raises:
            raise self._raises
        return self._response

    def is_available(self) -> bool:
        return self._raises is None


# ── Protocol conformance ──────────────────────────────────────────────────────

def test_stub_satisfies_llm_client_protocol():
    stub = StubClient()
    assert isinstance(stub, LLMClient)


def test_circuit_breaker_llm_client_satisfies_protocol():
    wrapped = CircuitBreakerLLMClient(StubClient(), provider="test")
    assert isinstance(wrapped, LLMClient)


def test_rejects_non_protocol_client():
    with pytest.raises(TypeError):
        CircuitBreakerLLMClient("not-a-client", provider="test")  # type: ignore[arg-type]


# ── Normal operation ──────────────────────────────────────────────────────────

def test_chat_returns_response():
    stub = StubClient(response="hello")
    client = CircuitBreakerLLMClient(stub, provider="test")
    result = client.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"


def test_is_available_delegates():
    stub = StubClient()
    client = CircuitBreakerLLMClient(stub, provider="test")
    assert client.is_available() is True


def test_call_method_delegates():
    stub = StubClient(response="via-method")
    client = CircuitBreakerLLMClient(stub, provider="test")
    result = client.call_method("chat", [{"role": "user", "content": "hi"}])
    assert result == "via-method"


# ── Circuit breaker integration ───────────────────────────────────────────────

def test_circuit_opens_and_raises_llm_circuit_open_error():
    stub = StubClient(raises=RuntimeError("provider down"))
    cb = CircuitBreaker("test-llm", failure_threshold=2)
    client = CircuitBreakerLLMClient(stub, provider="test-llm", breaker=cb)

    # Provider errors are wrapped as LLMCallError by _call_with_breaker
    for _ in range(2):
        with pytest.raises(LLMCallError):
            client.chat([])

    # Circuit is now open — next call raises LLMCircuitOpenError
    with pytest.raises(LLMCircuitOpenError):
        client.chat([])


def test_llm_circuit_open_error_is_also_circuit_open_error():
    stub = StubClient(raises=RuntimeError("down"))
    cb = CircuitBreaker("test-llm", failure_threshold=1)
    client = CircuitBreakerLLMClient(stub, provider="test-llm", breaker=cb)

    # Provider error wrapped as LLMCallError
    with pytest.raises(LLMCallError):
        client.chat([])

    exc = None
    try:
        client.chat([])
    except LLMCircuitOpenError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc, CircuitOpenError)
    assert isinstance(exc, LLMCallError)


def test_breaker_property_returns_circuit_breaker():
    cb = CircuitBreaker("test-llm", failure_threshold=3)
    client = CircuitBreakerLLMClient(StubClient(), provider="test-llm", breaker=cb)
    assert client.breaker is cb


def test_default_breaker_created_when_not_supplied():
    client = CircuitBreakerLLMClient(StubClient(), provider="auto-breaker")
    assert client.breaker.name == "auto-breaker"
    assert client.breaker.failure_threshold == 5
