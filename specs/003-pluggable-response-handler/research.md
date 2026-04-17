# Research: Pluggable Response Handler

**Feature**: 003-pluggable-response-handler
**Date**: 2026-04-17

## R1: Handler dispatch pattern

**Decision**: Use a simple dict mapping handler names to closure functions, created at startup in `main()`. No class hierarchy or plugin framework.

**Rationale**: Constitution Principle II (Simplicity & Minimalism) explicitly forbids abstraction layers in anticipation of future features. A dict dispatch is sufficient for 2 handlers, matches the existing pattern used for STT backend selection (`_stt_backend` + if/else in `transcribe()`), and can grow to 3-4 handlers without becoming unwieldy.

**Alternatives considered**:
- Abstract base class + registry: over-engineered for a single-file script with 2 handlers
- Strategy pattern with separate functions: essentially what the dict dispatch does, but with more indirection
- Config-only handler definitions: not feasible since handler logic differs (different endpoints, different timeouts, different error handling)

## R2: Reuse existing HTTP client vs new library

**Decision**: Reuse `urllib.request` + `json` (already imported in voice_loop.py) for the agentic handler's HTTP calls.

**Rationale**: The existing `llm_generate()` function already implements an OpenAI-compatible chat completion client using `urllib.request.Request` with JSON encoding. The agentic handler needs the exact same API call, just with a different endpoint URL and model name. Adding `httpx`, `requests`, or `aiohttp` would violate Principle II (no unnecessary dependencies).

**Alternatives considered**:
- `requests` library: not currently a dependency; would require adding it to pyproject.toml
- `httpx`: same issue, plus async support not needed since we wait for full response
- Shared helper function: extracting the HTTP call into a reusable function within voice_loop.py is acceptable and reduces duplication

## R3: Agentic handler configuration location

**Decision**: Add a `handlers` section to `config.yaml`, following the same pattern as the existing `models` section.

**Rationale**: Consistent with existing config patterns (`models` for aliases, `languages` for TTS). The `handlers` section maps handler names to their config (endpoint, model, timeout). Built-in defaults used when absent.

**Config structure**:
```yaml
handlers:
  agentic:
    api_base: http://localhost:8089/v1
    model: agent-model-name
    timeout: 60
```

**Alternatives considered**:
- Separate config file: violates constitution preference for `config.yaml` as single config point
- CLI flags only (`--agent-endpoint`): too many flags for a single handler; doesn't scale
- Environment variables: not the project's configuration pattern

## R4: Fallback mechanism implementation

**Decision**: On agentic handler failure (connection error, timeout, empty response), print a warning to stderr, set a `_handler_fallback` flag, and switch to the `llm` handler's dispatch for all subsequent calls in the session.

**Rationale**: Matches FR-008a (fall back to `llm` handler for remainder of session). The fallback is persistent within the session — once the agentic endpoint fails, we don't retry it (prevents repeated timeouts). The user is clearly informed via a warning message.

**Alternatives considered**:
- Retry with exponential backoff: adds complexity; the user is waiting in real-time for a voice response
- Per-request fallback (try agentic, fall back per-turn): confusing UX — user wouldn't know which handler responded
- Exit on failure: violates user sovereignty — the voice loop should keep working

## R5: Integration with greeting and memory

**Decision**: The greeting (line ~890 in voice_loop.py) and memory functions (`update_memory`, `consolidate_memory`) already call `llm_generate()`. Since the handler dispatch replaces `llm_generate()`, greeting automatically uses the selected handler. Memory functions also use the handler, which is correct — they need LLM inference to extract/consolidate facts.

**Rationale**: Minimal code change. The existing `llm_generate()` closure becomes the `llm` handler function. A new `agentic_generate()` closure is added. Both are stored in a `_handlers` dict. A wrapper `generate_response()` function dispatches to the active handler (with fallback logic).

**Alternatives considered**:
- Separate greeting handler config: over-complicated; greeting should use the same handler as the conversation
- Skip greeting for agentic handler: would break the UX flow; greeting is expected

## R6: Startup validation for agentic handler

**Decision**: When `--handler agentic` is selected, verify the endpoint is reachable at startup (same pattern as the existing LLM server check at line ~392). If unreachable, immediately fall back to `llm` with a warning (don't exit — the user may have the agentic service coming online shortly).

**Rationale**: Consistent with how the LLM server is checked. Early feedback lets the user know the agentic endpoint isn't available before they start speaking. Not exiting is important — the fallback keeps the loop functional.

**Alternatives considered**:
- Exit if agentic endpoint unreachable: too strict; the LLM fallback keeps the loop working
- Lazy check (only on first request): delays feedback; user speaks first, then gets a warning
- No check: user discovers failure only after speaking; poor UX
