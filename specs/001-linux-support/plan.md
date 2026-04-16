# Implementation Plan: Linux (Arch Linux) Support

**Branch**: `001-linux-support` | **Date**: 2026-04-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-linux-support/spec.md`

## Summary

Port Voice Loop from macOS-only (MLX/Metal) to also run on Arch Linux with
NVIDIA CUDA GPUs. The core runtime (`voice_loop_mac.py`) is renamed to
`voice_loop.py` and gains platform detection that selects MLX on macOS and
llama.cpp with CUDA on Linux for LLM inference. All other pipeline stages
(VAD, STT, TTS, AEC) already have cross-platform wheels and require no
changes beyond espeak-ng path detection.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: sounddevice, numpy, silero-vad, onnxruntime,
moonshine-voice, livekit, transformers, torch, kokoro-onnx, soundfile +
platform-conditional: mlx-vlm (macOS) | llama-cpp-python (Linux)
**Storage**: File-based — `SOUL.md`, `MEMORY.md`, temp dir for downloaded
models, `pyproject.toml` for project metadata.
**Testing**: No automated test suite. Validation gate: run the voice loop
and confirm a full audio turn completes without error.
**Target Platform**: macOS Apple Silicon (M-series, Metal/MLX) + Arch
Linux x86_64 with NVIDIA CUDA GPU (compute capability ≥ 7.0, VRAM ≥ 4 GB).
**Project Type**: CLI application — single-file script run via `uv run`.
**Performance Goals**: End-to-end voice turn latency on Linux within 2× of
macOS baseline (target: <6 seconds from end of speech to TTS start).
**Constraints**: On-device only, no cloud APIs, single-file architecture,
16 kHz mono / 512-sample audio constants, every new feature disable-able.
**Scale/Scope**: Single-user local application. No concurrent users,
no server component.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. On-Device First | ✅ PASS | All inference remains local. CUDA backend runs on-device, no cloud. |
| II. Simplicity & Minimalism | ⚠️ CONDITIONAL | Adding `llama-cpp-python` as a new dependency is justified: it is essential (MLX is macOS-only, Linux cannot function without a GPU inference backend). Single-file architecture preserved — platform branching stays inside `voice_loop.py`, no module extraction. |
| III. User Sovereignty | ✅ PASS | SOUL.md, MEMORY.md, voice/keypress interrupt all unchanged on both platforms. |
| IV. Audio Pipeline Integrity | ✅ PASS | Same audio stack (sounddevice, 16kHz, 512-sample chunks). No changes to sample rates or buffer sizes. |
| V. Incremental Evolution | ⚠️ CONDITIONAL | Renaming `voice_loop_mac.py` → `voice_loop.py` breaks the existing command. Justified: the current name is platform-specific and prevents Linux adoption. Will require a MAJOR version bump (0.1 → 1.0) per constitution. All existing CLI flags and defaults are preserved. |

**Violations requiring justification**: See Complexity Tracking below.

## Project Structure

### Documentation (this feature)

```text
specs/001-linux-support/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-schema.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit.tasks (NOT this command)
```

### Source Code (repository root)

```text
voice_loop.py           # Renamed from voice_loop_mac.py (single-file runtime)
config.yaml.example     # Default model aliases (sample config)
pyproject.toml           # Updated deps with platform markers
uv.lock                  # Re-resolved after pyproject.toml changes
SOUL.md                  # Unchanged
MEMORY.md.example        # Unchanged
README.md                # Updated: new script name, Linux setup instructions
AGENTS.md                # Updated: new commands, platform notes
```

**Structure Decision**: Single-file script architecture preserved per
constitution Principle II. No `src/` or `tests/` directories introduced.
The only file changes are renaming the main script and updating
`pyproject.toml` with platform-conditional dependencies.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| V: Rename `voice_loop_mac.py` → `voice_loop.py` | Current name is macOS-specific and contradicts cross-platform scope | Keeping the old name would confuse Linux users; having two filenames doubles maintenance |
| II: Add `llama-cpp-python` dependency | MLX is macOS-only; Linux requires a CUDA-capable LLM backend | No cross-platform inference library exists that covers both Metal and CUDA in a single package |
| V: MAJOR version bump (0.1 → 1.0) | Script rename is a breaking change for existing `uv run voice_loop_mac.py` users | Constitution requires MAJOR bump when existing commands change |
