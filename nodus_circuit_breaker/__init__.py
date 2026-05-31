"""nodus-circuit-breaker — three-state circuit breaker with optional LLM adapter.

Core:
    CircuitBreaker       — closed/open/half-open state machine (sync + async)
    CircuitState         — enum of the three states
    CircuitOpenError     — raised when the circuit rejects a call

LLM adapter (optional — requires no extra dependencies):
    LLMClient            — structural protocol any LLM provider must satisfy
    LLMCallError         — normalized provider error
    LLMCircuitOpenError  — circuit rejection wrapped as an LLM error
    CircuitBreakerLLMClient — wraps any LLMClient with a CircuitBreaker
"""
from .breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .llm import (
    CircuitBreakerLLMClient,
    LLMCallError,
    LLMCircuitOpenError,
    LLMClient,
)

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "CircuitBreakerLLMClient",
    "LLMCallError",
    "LLMCircuitOpenError",
    "LLMClient",
]
