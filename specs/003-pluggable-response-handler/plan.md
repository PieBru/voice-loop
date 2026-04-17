# Implementation Plan: Pluggable Response Handler

**Branch**: `003-pluggable-response-handler` | **Date**: 2026-04-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-pluggable-response-handler/spec.md`

## Summary

Add a `--handler` CLI flag (default: `llm`) that selects the response generation backend. The `llm` handler preserves current behavior. The `agentic` handler delegates to an external agent service via OpenAI-compatible API at a configurable endpoint. Agentic responses are delivered in full (no streaming), with existing chime/ticks providing audible feedback during processing. On timeout or unreachable endpoint, the system falls back to the `llm` handler with a warning.

## Technical Context

**Language/Version**: Python 3.11+ managed with `uv`
**Primary Dependencies**: stdlib `urllib.request`, `json` (already in use); no new dependencies
**Storage**: `config.yaml` for handler configuration (existing pattern)
**Testing**: Manual validation only — run `uv run voice_loop.py --handler agentic` and confirm full voice turn
**Target Platform**: macOS Apple Silicon + Arch Linux NVIDIA CUDA (same as existing)
**Project Type**: Single-file CLI script
**Performance Goals**: Agentic handler response within 60 seconds (timeout); zero overhead for `llm` handler
**Constraints**: Single-file architecture (`voice_loop.py`); on-device only; no new dependencies
**Scale/Scope**: 2 built-in handlers (`llm`, `agentic`); extensible via config.yaml

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. On-Device First | PASS | Agentic service runs locally (localhost:8089). No cloud APIs. |
| II. Simplicity & Minimalism | PASS | No new dependencies. Single-file. Reuses existing `urllib` + `json` HTTP client. No abstract handler framework — just a dispatch dict. |
| III. User Sovereignty | PASS | Handler is a CLI flag (`--handler`). SOUL.md and MEMORY.md work unchanged. |
| IV. Audio Pipeline Integrity | PASS | Handler only replaces the LLM→response step. Mic→VAD→STT and TTS→Speakers paths untouched. No audio callback changes. |
| V. Incremental Evolution | PASS | Default is `llm` (zero regression). New capability is disable-able (just don't use `--handler agentic`). Existing flags unchanged. |

**Result**: PASS — all 5 principles satisfied. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/003-pluggable-response-handler/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-schema.md
└── tasks.md              # Created by /speckit.tasks
```

### Source Code (repository root)

```text
voice_loop.py             # All code changes (single-file)
config.yaml.example       # Updated with handlers section
pyproject.toml            # No changes (no new dependencies)
```

**Structure Decision**: Single-file script per constitution. All handler logic lives in `voice_loop.py`. Handler configuration in `config.yaml`.

## Complexity Tracking

No constitution violations — table not applicable.

### Post-Design Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. On-Device First | PASS | Agentic endpoint is localhost. Config.yaml allows any local URL. No cloud. |
| II. Simplicity & Minimalism | PASS | No new deps. No abstract classes. Dict dispatch. Shared HTTP helper reuses existing code. |
| III. User Sovereignty | PASS | `--handler` is a CLI flag. `--list-handlers` for discoverability. SOUL.md/MEMORY.md untouched. |
| IV. Audio Pipeline Integrity | PASS | Handler is synchronous (blocks until response). No audio path changes. Chime fills the gap. |
| V. Incremental Evolution | PASS | Default `llm` = zero regression. `--handler agentic` is opt-in. `config.yaml` extension is additive. |

**Result**: PASS — design confirms compliance with all principles.
