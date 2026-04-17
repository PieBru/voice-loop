# Research: VoxCPM TTS Backend

**Feature**: 007-voxcpm-tts | **Date**: 2026-04-17

## Decision 1: Integration approach — Python import vs subprocess

**Chosen**: Python import via `voxcpm` pip package.
**Rationale**: VoxCPM has a proper pip package (`voxcpm>=2.0.2`) with a clean API (`VoxCPM.from_pretrained()`, `model.generate()`). Unlike qwen3-tts.cpp, there's no C++ binary to manage.
**Alternatives considered**: Subprocess (like qwen-cpp) — rejected because the Python package exists and provides streaming API.

## Decision 2: Streaming vs full synthesis

**Chosen**: Full synthesis with sentence splitting for first iteration.
**Rationale**: VoxCPM has `generate_streaming()` but bidirectional streaming is not supported. The spec 008 (streaming TTS) will handle the sentence-by-sentence architecture that could leverage this in the future. For now, split into sentences, synthesize each, concatenate, play — matching the QwenTTS pattern.
**Alternatives considered**: Use `generate_streaming()` per sentence — deferred to spec 008 integration.

## Decision 3: Model variant

**Chosen**: VoxCPM2 (2B parameters).
**Rationale**: Latest and best quality. 30 languages. 48kHz output. ~8GB VRAM on CUDA. The 0.8B and 0.6B variants exist but are not in initial scope.
**Alternatives considered**: VoxCPM1.5 (0.8B, lower VRAM) — not in scope for initial implementation.

## Decision 4: Device selection

**Chosen**: Auto-detect: CUDA on Linux, MPS on macOS, CPU fallback. Configurable via `tts.voxcpm_device`.
**Rationale**: VoxCPM supports all three. `device="auto"` in the VoxCPM API handles this.
**Alternatives considered**: CUDA-only — rejected because VoxCPM explicitly supports CPU and MPS.

## Decision 5: optimize flag

**Chosen**: `optimize=False`.
**Rationale**: `torch.compile` (enabled by `optimize=True`) uses CUDA Graphs which are incompatible with multi-threading. Our voice_loop uses threading for audio callbacks. Setting `optimize=False` avoids crashes.
**Alternatives considered**: `optimize=True` with single-threaded audio — too risky, may cause audio glitches.

## Decision 6: Dependency compatibility

**Finding**: `voxcpm>=2.0.2` requires `torch>=2.5.0`. Our project already has PyTorch. The `voxcpm` package may have its own `transformers` pin. Need to verify with `uv add voxcpm` whether version conflicts arise (similar to the `qwen-tts` transformers conflict). If conflicts occur, use platform marker `sys_platform == 'linux'` or `override-dependencies`.
**Action**: Test `uv add voxcpm` during implementation. Use override if needed.

## Decision 7: Long text handling

**Chosen**: Split into sentences before synthesis, concatenate audio.
**Rationale**: VoxCPM documentation warns that long text causes instability (speed-up, buzzing, OOM). Splitting into ~3-sentence chunks avoids this.
**Alternatives considered**: Max-length truncation — rejected, loses content.
