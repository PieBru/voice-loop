# Quickstart: Pluggable Response Handler

**Feature**: 003-pluggable-response-handler
**Date**: 2026-04-17

## Default (no change)

```bash
uv run voice_loop.py
# Uses the direct LLM handler — identical to previous behavior
```

## Use agentic handler

```bash
# Start your agentic service on port 8089 first, e.g.:
# llama-server -m agent-model.gguf --port 8089

uv run voice_loop.py --handler agentic
```

## Configure agentic endpoint

Edit `config.yaml`:

```yaml
handlers:
  agentic:
    api_base: http://localhost:8089/v1
    model: my-agent-model
    timeout: 90
```

## List available handlers

```bash
uv run voice_loop.py --list-handlers
```

## Combine with other flags

```bash
# Italian with agentic handler
uv run voice_loop.py --lang it --handler agentic

# Explicit default (same as no flag)
uv run voice_loop.py --handler llm
```
