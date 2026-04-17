# Data Model: Pluggable Response Handler

**Feature**: 003-pluggable-response-handler
**Date**: 2026-04-17

## Entities

### HandlerConfig

Configuration for a response handler, loaded from `config.yaml` → `handlers` section.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_base` | string | `"http://localhost:8089/v1"` | OpenAI-compatible API endpoint URL |
| `model` | string | Handler name | Model identifier sent to the API |
| `timeout` | int | `60` | Request timeout in seconds |

**Identity**: Handler name (string key in config dict, e.g. `"agentic"`).

**Lifecycle**: Loaded once at startup from `config.yaml`. Not modified at runtime.

**Validation**: `api_base` must be a valid URL. `timeout` must be positive integer.

### HandlerDispatch

Runtime dispatch table mapping handler names to callable functions.

| Field | Type | Description |
|-------|------|-------------|
| `"llm"` | callable | Existing `llm_generate()` logic (direct API call to configured LLM) |
| `"agentic"` | callable | HTTP call to agentic service endpoint |

**Identity**: Handler name string.

**Lifecycle**: Created at startup in `main()`. Active handler selected by `--handler` flag. Fallback switches active handler to `"llm"` on failure.

### ResponseContext (implicit, not persisted)

The data passed to every handler call.

| Field | Type | Description |
|-------|------|-------------|
| `messages` | list[dict] | Chat message array (system + history + user) |
| `max_tokens` | int | Maximum tokens in response |
| `temperature` | float | Sampling temperature |

## Relationships

```
config.yaml ──► HandlerConfig (loaded at startup)
                       │
                       ▼
CLI --handler ──► HandlerDispatch ──► active_handler (callable)
                       │
                       ▼
              ResponseContext ──► active_handler(messages, max_tokens, temperature)
                       │
                       ▼
                  response string ──► TTS
```

## State Transitions

```
[Startup] ──► load HandlerConfig from config.yaml
         ──► build HandlerDispatch dict
         ──► set active_handler based on --handler flag
         ──► (if agentic) validate endpoint reachability
              ├─ reachable ──► [Running: agentic]
              └─ unreachable ──► warn + fallback ──► [Running: llm]

[Running: agentic] ──► on request failure/timeout ──► warn + [Running: llm]
[Running: llm] ──► (no further fallback; this is the base)
```
