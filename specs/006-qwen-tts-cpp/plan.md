# Implementation Plan: QwenTTS C++ Backend

**Branch**: `006-qwen-tts-cpp`
**Date**: 2026-04-17
**Spec**: `specs/006-qwen-tts-cpp/spec.md`

---

## Summary

Add `--tts qwen-cpp` as a third TTS backend option that calls `qwen3-tts-cli` (from qwen3-tts.cpp) as a subprocess. The C++ binary handles all model loading and inference — we only manage the subprocess lifecycle, temp files for WAV I/O, and config. No new Python dependencies. Works on macOS (Metal), Linux (CUDA/CPU), and ARM devices.

---

## Technical Context

| Item | Value |
|---|---|
| Language | Python 3.11+ (subprocess calls to C++ binary) |
| Primary deps | `subprocess`, `tempfile`, `soundfile` (all already in project) |
| External binary | `qwen3-tts-cli` from [qwen3-tts.cpp](https://github.com/predict-woo/qwen3-tts.cpp) |
| Storage | GGUF model files in configurable directory (~1.2GB for 0.6B F16) |
| Testing | Manual: `uv run voice_loop.py --tts qwen-cpp` + speak a turn |
| Target | All platforms: macOS (Metal/CoreML), Linux (CUDA/CPU), ARM (RPi) |
| Constraints | No streaming. Voice cloning via reference audio. No built-in speakers. |

---

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. On-Device First | PASS | qwen3-tts.cpp runs entirely locally. |
| II. Simplicity & Minimalism | PASS | Subprocess integration — no new Python deps, no model loading in Python. |
| III. User Sovereignty | PASS | User builds/installs the binary. Path configurable. |
| IV. Audio Pipeline Integrity | CONDITIONAL | Same non-streaming limitation as Python qwen-tts. 24kHz output resampled for playback. |
| V. Incremental Evolution | PASS | Additive. Adds `qwen-cpp` as a choice alongside existing `kokoro` and `qwen`. |

**Verdict**: CONDITIONAL — non-streaming is inherent to qwen3-tts.cpp, same as Python backend.

---

## Project Structure

### Documentation

```
specs/006-qwen-tts-cpp/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
```

### Source Code

```
voice_loop.py          # Add --tts qwen-cpp choice, subprocess TTS, _print_qwen_cpp_info()
config.yaml.example    # Add tts.qwen_cpp_model_dir, tts.qwen_cpp_ref_audio, tts.qwen_cpp_bin
README.md              # Add qwen3-tts.cpp install + usage docs
AGENTS.md              # Update with --tts qwen-cpp info
```

### Structure Decision

Single-file architecture preserved. Subprocess integration is ~50 lines of code.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Subprocess + temp file I/O | qwen3-tts.cpp has no Python bindings or library API | Rewriting TTS in Python would defeat the purpose of using C++ |
| External binary dependency | User must build and install qwen3-tts-cli separately | Bundling a C++ binary is out of scope; would violate constitution simplicity |
