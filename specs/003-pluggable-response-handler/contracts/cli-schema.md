# CLI Schema: Pluggable Response Handler

**Feature**: 003-pluggable-response-handler
**Date**: 2026-04-17

## New CLI Flag

### `--handler`

| Attribute | Value |
|-----------|-------|
| Name | `--handler` |
| Type | string |
| Default | `llm` |
| Choices | Any registered handler name (built-in: `llm`, `agentic`) |
| Help text | "Response generation handler (default: llm)" |

**Behavior**:
- `llm`: Direct LLM API call to the configured model endpoint (existing behavior). Zero regression.
- `agentic`: Delegate to an external agentic service at the configured endpoint. Full response (no streaming). 60-second timeout with fallback to `llm`.

### `--list-handlers`

| Attribute | Value |
|-----------|-------|
| Name | `--list-handlers` |
| Type | boolean flag |
| Default | off |
| Help text | "List available response handlers and exit" |

**Output format**:
```
Handler       Description
--------------------------------------
llm           Direct LLM API call (default)
agentic       External agentic service (configurable endpoint)
```

## config.yaml Extension

New `handlers` section:

```yaml
handlers:
  agentic:
    api_base: http://localhost:8089/v1
    model: agent-model-name
    timeout: 60
```

All fields optional — built-in defaults used when absent.

## Startup Banner Extension

The "Listening" line gains a `handler:` field:

```
Listening (lang: en, stt: moonshine, tts: af_heart, handler: llm, mode: text, silence: 700ms, smart-turn: True)
```

## Error Messages

| Condition | Message |
|-----------|---------|
| Invalid handler name | `Error: Unknown handler 'foo'. Available: llm, agentic.` |
| Agentic endpoint unreachable at startup | `Warning: Agentic handler endpoint http://localhost:8089/v1 unreachable. Falling back to llm handler.` |
| Agentic timeout during request | `Warning: Agentic handler timed out (60s). Falling back to llm handler for this session.` |
| Agentic returns empty response | (no message; treated as empty transcription — no TTS output) |
