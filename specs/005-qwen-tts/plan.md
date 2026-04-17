# Implementation Plan: QwenTTS Backend

**Branch**: `005-qwen-tts`
**Date**: 2026-04-17
**Spec**: `specs/005-qwen-tts/spec.md`

---

## Summary

Add a `--tts` CLI flag (`kokoro` | `qwen`, default `kokoro`) to select the TTS backend. When `qwen` is selected, load Qwen3-TTS CustomVoice model on CUDA and use non-streaming synthesis (`sd.play()`) for audio output. Extend `_LANG_MAP` with QwenTTS speaker defaults, add a `_QWEN_SPEAKER_MAP`, and refactor `speak_tts()` / `play_tts_stream()` to dispatch by backend. Kokoro path is untouched.

---

## Technical Context

| Item | Value |
|---|---|
| Language | Python 3.11+ |
| Primary deps | `qwen-tts>=0.1`, `torch>=2.0` (already present), `transformers` |
| Storage | HF cache for Qwen3-TTS model (~3.4GB), config.yaml for overrides |
| Testing | Manual: `uv run voice_loop.py --tts qwen` + speak a turn |
| Target | Linux NVIDIA CUDA (≥4GB VRAM). macOS rejected at startup. |
| Project type | Single-file (`voice_loop.py`) |
| Constraints | No streaming API in qwen-tts package. AEC barge-in not available during QwenTTS synthesis (no reference signal). |

---

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. On-Device First | PASS | Qwen3-TTS runs locally on CUDA. No cloud API. |
| II. Simplicity & Minimalism | PASS | `--tts` flag mirrors existing `--stt` flag pattern. Kokoro default unchanged. |
| III. User Sovereignty | PASS | User explicitly opts in via `--tts qwen`. Can always go back to `--tts kokoro`. |
| IV. Audio Pipeline Integrity | CONDITIONAL | QwenTTS outputs 24kHz → resampled to 16kHz for AEC ref. No streaming = no voice barge-in during synthesis. Keypress interrupt works during playback. |
| V. Incremental Evolution | PASS | Additive change. No existing codepaths modified for Kokoro path. |

**Verdict**: CONDITIONAL — AEC limitation is inherent to QwenTTS non-streaming architecture, not a design flaw. Document it clearly.

---

## Project Structure

### Documentation

```
specs/005-qwen-tts/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
```

### Source Code

```
voice_loop.py          # Add --tts flag, _QWEN_SPEAKER_MAP, QwenTTS loading, speak_qwen(), dispatch logic
pyproject.toml         # Add qwen-tts dependency
config.yaml.example    # Add tts section
README.md              # Add QwenTTS docs
AGENTS.md              # Update with --tts flag info
```

### Structure Decision

Single-file architecture preserved. All QwenTTS code in `voice_loop.py`, gated behind `--tts qwen` flag.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Non-streaming playback for QwenTTS | qwen-tts package has no streaming API | Streaming would require patching qwen-tts internals or using vLLM-Omni (too complex) |
| Platform restriction (no macOS) | QwenTTS requires CUDA | CPU inference is too slow for real-time voice agent |
