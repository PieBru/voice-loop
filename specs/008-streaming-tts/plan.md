# Implementation Plan: Streaming TTS Port

**Branch**: `008-streaming-tts` | **Date**: 2026-04-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/008-streaming-tts/spec.md`

## Summary

Port the upstream's sentence-by-sentence TTS architecture into our `voice_loop.py`. Replace the current `play_tts_stream()` (Kokoro async generator) with the upstream's `stream_sentences()` + `_synthesizer()` + `asyncio.Queue(maxsize=1)` pipeline. LLM runs in a background thread yielding sentences; Kokoro synthesizes sentence pairs (GROUP=2) while the previous pair plays. Non-Kokoro backends get incremental sentence printing but full-response synthesis. Inter-sentence gap uses 150ms reverb blanking for cleaner AEC barge-in.

## Technical Context

**Language/Version**: Python 3.11+ (managed with `uv`)
**Primary Dependencies**: `asyncio`, `threading`, `queue`, `re`, `numpy`, `sounddevice` (all already in project)
**Storage**: N/A
**Testing**: Manual — `uv run voice_loop.py` + speak a multi-sentence turn + verify audio starts before full generation
**Target Platform**: macOS Apple Silicon (MLX streaming) and Linux (full-generation-then-split)
**Project Type**: Single-file script (`voice_loop.py`)
**Performance Goals**: First audio within 2s of LLM start for 5-sentence responses (SC-001)
**Constraints**: Linux llama.cpp server does not support token-by-token streaming; GROUP=2 minimum for Kokoro prosody; 150ms reverb blanking between sentences
**Scale/Scope**: All Kokoro TTS playback paths (greeting + process_utterance response)

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. On-Device First | PASS | No external services. |
| II. Simplicity & Minimalism | PASS | Uses stdlib asyncio/threading/queue. No new dependencies. |
| III. User Sovereignty | PASS | User can `--no-tts` or `--no-aec`. Streaming is transparent. |
| IV. Audio Pipeline Integrity | PASS | Maintains 16kHz AEC reference. Single OutputStream for gapless playback. Reverb blanking improves AEC accuracy. |
| V. Incremental Evolution | PASS | Existing `play_tts_stream()` replaced with streaming version. Behavior is backward-compatible for single-sentence responses. |

**Verdict**: PASS — All principles satisfied. No violations.

## Project Structure

### Documentation

```
specs/008-streaming-tts/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
```

### Source Code

```
voice_loop.py          # Rewrite play_tts_stream(), add _split_sentences(), stream_sentences(), pad_gap_and_check()
```

**Structure Decision**: Single-file architecture preserved. Changes confined to TTS playback section of `voice_loop.py`.

## Complexity Tracking

No violations — all principles pass.
