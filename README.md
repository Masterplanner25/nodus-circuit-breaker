# nodus-circuit-breaker

**Three-state circuit breaker (closed → open → half-open) with async support
and an optional LLM provider adapter.**

Zero required dependencies — pure Python standard library. Optional
Prometheus metrics via the `[metrics]` extra.

> **Status:** v0.1.0 — published on [PyPI](https://pypi.org/project/nodus-circuit-breaker/).

---

## Install

```bash
pip install nodus-circuit-breaker

# With optional Prometheus metrics:
pip install "nodus-circuit-breaker[metrics]"
```

---

## What it provides

| Component | Purpose |
|---|---|
| `CircuitBreaker` | Three-state machine with sync and async call wrappers |
| `CircuitState` | `CLOSED` / `OPEN` / `HALF_OPEN` enum |
| `CircuitOpenError` | Raised when the circuit rejects a call |
| `LLMClient` | Structural protocol for LLM provider clients |
| `CircuitBreakerLLMClient` | Wraps any `LLMClient` with a `CircuitBreaker` |
| `LLMCallError` / `LLMCircuitOpenError` | Normalized LLM error types |

---

## Basic usage

```python
from nodus_circuit_breaker import CircuitBreaker, CircuitOpenError

cb = CircuitBreaker(
    "my-service",
    failure_threshold=3,      # open after 3 consecutive failures
    recovery_timeout_secs=60, # wait 60s before trying half-open
)

try:
    result = cb.call(my_function, arg1, arg2)
except CircuitOpenError:
    result = fallback_value
```

### Async

```python
result = await cb.async_call(my_async_function, arg1, arg2)
```

---

## State machine

```
CLOSED ──(failures ≥ threshold)──► OPEN
OPEN   ──(timeout elapsed)───────► HALF_OPEN
HALF_OPEN ──(success)────────────► CLOSED
HALF_OPEN ──(failure)────────────► OPEN
```

- **CLOSED** — normal operation; failures are counted.
- **OPEN** — all calls immediately raise `CircuitOpenError`; no upstream calls made.
- **HALF_OPEN** — one probe call allowed; success closes, failure reopens.

---

## State change callback

```python
def on_change(name: str, previous: str, new: str) -> None:
    print(f"{name}: {previous} → {new}")

cb = CircuitBreaker("svc", on_state_change=on_change)
```

### Prometheus integration via callback

```python
from prometheus_client import CollectorRegistry, Gauge

registry = CollectorRegistry()
cb_gauge = Gauge("cb_state", "Circuit breaker state", ["name"], registry=registry)

def prometheus_hook(name: str, prev: str, new: str) -> None:
    value = {"closed": 0, "half_open": 1, "open": 2}.get(new, -1)
    cb_gauge.labels(name=name).set(value)

cb = CircuitBreaker("my-service", on_state_change=prometheus_hook)
```

Requires `pip install "nodus-circuit-breaker[metrics]"`.

---

## LLM provider adapter

```python
from nodus_circuit_breaker import CircuitBreakerLLMClient, LLMCircuitOpenError

# Wrap any LLMClient-compliant provider (OpenAI, Anthropic, etc.)
client = CircuitBreakerLLMClient(my_provider_client, provider="openai")

try:
    reply = client.chat([{"role": "user", "content": "hello"}])
except LLMCircuitOpenError:
    reply = "Service temporarily unavailable."
```

`LLMClient` is a structural protocol — any object with `chat(messages, **kwargs)` satisfies it.

---

## Inspecting state

```python
cb.state          # CircuitState.CLOSED / OPEN / HALF_OPEN
cb.failure_count  # int
cb.name           # str
cb.reset()        # force-close the circuit
```

---

## Design

- **No required dependencies.** Core breaker and LLM adapter are pure stdlib.
  Prometheus integration is opt-in via `[metrics]` extra.
- **Thread-safe.** State transitions use `threading.Lock`.
- **Callback-driven observability.** `on_state_change` decouples metrics from
  the breaker itself.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

---

## License

MIT — see [LICENSE](LICENSE).
