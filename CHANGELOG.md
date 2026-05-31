# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-05-30

Initial release — prepared, not yet published.

### Added

- **`CircuitBreaker`** — three-state machine (`CLOSED → OPEN → HALF_OPEN`).
  Constructor: `name`, `failure_threshold` (default 3),
  `recovery_timeout_secs` (default 60), `on_state_change` callback.
  `call(fn, *args, **kwargs)` — sync call with state enforcement.
  `async_call(fn, *args, **kwargs)` — async variant.
  `reset()` — force-close the circuit.
  `state`, `failure_count`, `name` properties.

- **`CircuitState`** — `CLOSED`, `OPEN`, `HALF_OPEN` enum values.

- **`CircuitOpenError`** — raised when a call is rejected because the
  circuit is open. Carries `name` (breaker name) and `state`.

- **`LLMClient`** — structural protocol: any object with
  `chat(messages, **kwargs) -> str` satisfies it.

- **`CircuitBreakerLLMClient`** — wraps any `LLMClient` with a
  `CircuitBreaker`. Constructor: `client`, `provider` (name string),
  optional `breaker` (uses default settings if omitted).
  `chat(messages, **kwargs)` — delegates to client; raises
  `LLMCircuitOpenError` when the circuit is open.

- **`LLMCallError`** — normalized provider error. Fields: `provider`,
  `message`, `original`.

- **`LLMCircuitOpenError`** — subclass of `LLMCallError` raised when
  the circuit rejects the call.

- **24 tests** across two test files (breaker, llm_adapter).

- **No required dependencies** — pure stdlib. Optional `[metrics]` extra
  for `prometheus-client`.

[0.1.0]: https://github.com/Masterplanner25/nodus-circuit-breaker/releases/tag/v0.1.0
