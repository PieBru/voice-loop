# Implementation Plan: Multilanguage STT & TTS Support

**Branch**: `002-multilang-support` | **Date**: 2026-04-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-multilang-support/spec.md`

## Summary

Add multilanguage support to Voice Loop via a `--lang` flag (default `en`) that configures STT, LLM, and TTS for the selected language. Introduce `faster-whisper` as a new STT backend (auto-selected for languages Moonshine doesn't support, e.g., Italian). Make STT backend configurable via `--stt` flag. Test end-to-end with Italian.

## Technical Context

**Language/Version**: Python 3.11+ (managed with `uv`)
**Primary Dependencies**: faster-whisper 1.2.1 (new), moonshine-voice (existing), kokoro-onnx (existing)
**Storage**: File-based (HF cache for models, config.yaml for settings)
**Testing**: Manual validation — run voice loop and confirm full turn in target language
**Target Platform**: macOS Apple Silicon + Arch Linux NVIDIA CUDA (existing dual-platform)
**Project Type**: Single-file CLI voice agent
**Performance Goals**: Real-time transcription latency comparable to existing Moonshine (<2s for a 5s utterance)
**Constraints**: Single-file architecture (`voice_loop.py`), no cloud APIs, on-device inference
**Scale/Scope**: ~10 language codes in built-in map; 99+ languages via faster-whisper

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. On-Device First | ✅ PASS | faster-whisper runs locally (CTranslate2), Moonshine runs locally. No cloud calls. |
| II. Simplicity & Minimalism | ⚠️ CONDITIONAL | Adding `faster-whisper` dependency (~70 MB install). Justified: essential for multilanguage STT; Moonshine only supports 8 languages. No new transitive deps (ctranslate2, av are the only new packages). Single-file architecture preserved. |
| III. User Sovereignty | ✅ PASS | SOUL.md unchanged; language instruction appended to system prompt at runtime, not written to SOUL.md. `--voice` override preserved. |
| IV. Audio Pipeline Integrity | ✅ PASS | STT replacement doesn't change audio pipeline (VAD → chunks → STT → text). Same 16kHz/512-sample audio path. |
| V. Incremental Evolution | ✅ PASS | `--lang en` (default) = existing behavior unchanged. `--stt` flag is additive. All new features disable-able at runtime. |

**Verdict**: PASS with conditional justification for faster-whisper dependency (Principle II).

## Project Structure

### Documentation (this feature)

```text
specs/002-multilang-support/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-schema.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
voice_loop.py          # Single-file runtime (modified)
config.yaml.example    # Updated with language map example
pyproject.toml         # Add faster-whisper dependency
```

**Structure Decision**: Single-file architecture preserved per constitution. All STT backend logic, language map, and transcribe dispatch live inside `voice_loop.py`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| faster-whisper dependency (~70 MB) | Only way to support 99+ languages for STT | Moonshine only supports 8 languages; openai-whisper is heavier (requires PyTorch explicitly); no stdlib solution exists for STT |
