from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from .breaker import CircuitBreaker, CircuitOpenError


class LLMCallError(Exception):
    """Normalized error for provider-backed LLM calls."""


class LLMCircuitOpenError(CircuitOpenError, LLMCallError):
    """Raised when the LLM circuit breaker rejects a call."""


@runtime_checkable
class LLMClient(Protocol):
    """Structural protocol for all LLM provider clients.

    Any object that implements ``chat`` and ``is_available`` satisfies this
    protocol and can be wrapped by ``CircuitBreakerLLMClient``.
    """

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request. Returns the assistant message text."""
        ...

    def is_available(self) -> bool:
        """Return True if the underlying provider appears reachable."""
        ...


class CircuitBreakerLLMClient:
    """``LLMClient`` adapter that guards all calls with a circuit breaker.

    Wraps any object satisfying the ``LLMClient`` protocol.  On
    ``CircuitOpenError`` the exception is re-raised as ``LLMCircuitOpenError``
    so callers can distinguish circuit rejection from provider errors.

    Args:
        client: Any ``LLMClient``-compliant provider client.
        provider: Human-readable provider name (used in logs and the breaker).
        breaker: Optional pre-configured ``CircuitBreaker``.  A default
            breaker (failure_threshold=5, recovery_timeout=60s) is created
            when not supplied.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        provider: str,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        if not isinstance(client, LLMClient):
            raise TypeError(
                f"client must satisfy LLMClient protocol, got {type(client)!r}"
            )
        self._client = client
        self._provider = provider
        self._breaker = breaker or CircuitBreaker(
            name=provider,
            failure_threshold=5,
            recovery_timeout_secs=60,
        )

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def _call_with_breaker(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._breaker.call(func, *args, **kwargs)
        except CircuitOpenError as exc:
            logging.warning("[LLM:%s] circuit open; rejecting call", self._provider)
            raise LLMCircuitOpenError(str(exc)) from exc
        except LLMCallError:
            raise
        except Exception as exc:  # pragma: no cover
            raise LLMCallError(f"{self._provider} call failed") from exc

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        return self._call_with_breaker(
            self._client.chat,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def call_method(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Call an arbitrary method on the wrapped client through the breaker."""
        method = getattr(self._client, method_name)
        return self._call_with_breaker(method, *args, **kwargs)

    def is_available(self) -> bool:
        return self._client.is_available()
