# Implementation Plan: OpenAI-Compatible TTS Endpoint Backend

**Branch**: `009-openai-tts` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-openai-tts/spec.md`

## Summary

Add `--tts openai` backend to `voice_loop.py` that sends TTS requests to an OpenAI-compatible `/v1/audio/speech` HTTP endpoint using stdlib `urllib.request`. No new dependencies. Supports configurable endpoint URL, model, voice, streaming mode, and sample rate via CLI flags and `config.yaml`. Follows the same integration pattern as `qwen-cpp` (config loader, print-info function, speak_tts branch).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: stdlib `urllib.request`, `json` (already imported); `soundfile` (already transitive via qwen-cpp path) for WAV parsing in non-streaming mode; `numpy` + `sounddevice` (already imported) for playback
**Storage**: N/A (HTTP client — no local storage beyond config.yaml)
**Testing**: No test suite. Validation: run voice_loop with `--tts openai` and a running TTS server, confirm audio pipeline completes a turn.
**Target Platform**: macOS + Linux (HTTP client is platform-agnostic — works everywhere)
**Project Type**: CLI tool (single-file script)
**Performance Goals**: HTTP round-trip + synthesis latency (server-dependent); voice_loop adds ~0 overhead vs other backends
**Constraints**: No new pip dependencies (FR-014); must not block audio callbacks (constitution IV); must fail-fast on server error (FR-007)
**Scale/Scope**: Single user, single TTS server endpoint

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. On-Device First | **PASS** | `--tts openai` is opt-in (default remains Kokoro). Typically used with localhost server (same machine, just separate process). No cloud API keys required. Constitution says "no network calls for core functionality" — TTS via external HTTP is not "core" when opt-in and default Kokoro remains untouched. |
| II. Simplicity & Minimalism | **PASS** | Single-file (`voice_loop.py`). No new dependencies (stdlib `urllib.request`). No abstraction layer — direct elif branch in `speak_tts()`. Pattern matches existing `qwen-cpp` backend exactly. |
| III. User Sovereignty | **PASS** | All params configurable via CLI flags and config.yaml. Feature is disable-able via `--no-tts`. Default behavior unchanged. |
| IV. Audio Pipeline Integrity | **PASS** | HTTP call is in main thread (same as qwen-cpp subprocess). `drain_audio_q()` + `vad.reset_states()` at end of `speak_tts()` already handles post-playback cleanup. AEC reference alignment works via `_append_ref()` in `play_tts_stream()` if streaming is used. |
| V. Incremental Evolution | **PASS** | Additive only. New CLI flag `--tts openai` added to choices. No existing defaults changed. No existing flags modified. |

**Gate Result**: PASS — no violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/009-openai-tts/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli-schema.md    # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
voice_loop.py          # All implementation (single file)
config.yaml.example    # Updated with openai_* keys under tts:
AGENTS.md              # Updated by agent context script
README.md              # No changes needed (already mentions --tts flag)
```

**Structure Decision**: Single-file script (Option 1). All code in `voice_loop.py`. Config keys added to `config.yaml.example`.

## Implementation Approach

### New module-level functions (pattern: `_load_qwen_cpp_config`, `_print_qwen_cpp_info`)

1. **`_load_openai_tts_config()`** — loads `config.yaml` → `tts.openai_*` keys, returns dict with defaults
2. **`_print_openai_tts_info()`** — prints endpoint, model, voice, streaming, sample rate, config example for `--list --tts openai`

### Modified sections in `voice_loop.py`

1. **`--tts` argparse choices** — add `"openai"` to choices list
2. **New CLI flags** — `--tts-openai-endpoint`, `--tts-openai-model`, `--tts-openai-stream`, `--tts-openai-sr`
3. **`--list` dispatch** — add `elif args.tts == "openai": _print_openai_tts_info()`
4. **Config loading** — `_openai_cfg = _load_openai_tts_config() if args.tts == "openai" else None`
5. **`speak_tts()` elif branch** — new `elif args.tts == "openai":` branch with HTTP request, WAV decode, playback
6. **Streaming support in `play_tts_stream()`** — Kokoro-specific async synth replaced with HTTP streaming PCM for openai backend
7. **`process_utterance()` dispatch** — add `openai` to the non-Kokoro backend check for `speak_tts()` path
8. **config.yaml.example** — add `openai_*` keys under `tts:` section

### HTTP request details

Non-streaming:
```python
POST {endpoint}/v1/audio/speech
Content-Type: application/json
{"model": "...", "voice": "...", "input": "text", "response_format": "wav"}
→ returns WAV binary
```

Streaming:
```python
POST {endpoint}/v1/audio/speech
Content-Type: application/json
{"model": "...", "voice": "...", "input": "text", "response_format": "pcm", "stream": true}
→ returns chunked PCM float32 data
```

### Non-streaming speak_tts flow

1. `drain_audio_q()`
2. Split text into sentences via `_split_sentences(text)`
3. For each sentence:
   - `urllib.request.urlopen(req, timeout=timeout)` → read full response
   - Parse WAV via `soundfile.read()` (or `io.BytesIO` + `wave` module for stdlib-only path)
   - `sd.play(samples, sr)` + `sd.wait()`
4. `drain_audio_q()` + `vad.reset_states()`

### Streaming flow (P2 — sentence-level buffering)

1. Same as non-streaming but request `response_format=pcm`, `stream=true`
2. Read chunked response into buffer per sentence
3. Convert float32 PCM to numpy array at configured sample rate
4. `sd.play()` + `sd.wait()` per sentence

## Complexity Tracking

> No violations — table not needed.
