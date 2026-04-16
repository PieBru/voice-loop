# Agent Guidance: Voice Loop

## Environment & Commands

- **Package manager**: `uv` only. Use `uv sync`, `uv run`, `uv add`. Do not use `pip` or manual `venv`.
- **Run the agent**: `uv run voice_loop.py`
- **System deps** (macOS): `brew install portaudio espeak-ng uv`
- **System deps** (Arch Linux): `pacman -S portaudio espeak-ng cuda nvidia uv`
- **First run**: downloads ~3.5 GB of models (Gemma 4 E4B, Moonshine, Kokoro). This is automatic but slow.

## Architecture & Constraints

- **Target platforms**: macOS Apple Silicon (MLX/Metal) and Arch Linux with NVIDIA CUDA GPU (VRAM ≥ 4 GB).
- **Single-file core**: `voice_loop.py` is the intentional main runtime. The constitution prefers keeping it single-file unless there is a clear performance or maintenance reason to extract.
- **On-device first**: No cloud API keys, no network calls in the hot path. All inference is local.
- **Sacred audio constants**: 16 kHz mono, 512-sample chunks (32 ms). Do not change sample rates or buffer sizes without end-to-end validation.
- **Configuration**: `config.yaml` at project root for user-tunable settings (model aliases). Built-in defaults used when absent.

## How to Change Behavior

1. **Persona/style**: edit `SOUL.md` (live-reloaded every turn).
2. **Model aliases**: edit `config.yaml` (loaded at startup).
3. **New capability**: add a CLI flag in `voice_loop.py` before hard-coding behavior. Every new feature MUST be disable-able at runtime.
4. **Memory**: enable with `--memory`; `MEMORY.md` is gitignored user-local state.

## Validation

- There is **no test suite, lint, or typecheck command** in this repo.
- The required validation gate is: run `uv run voice_loop.py`, speak a full turn, and confirm the audio pipeline completes without error.

## Feature Workflow (Speckit)

This repo uses the `.specify` framework for structured feature work. If adding a major feature, follow the speckit workflow:

1. `/speckit.git.feature <name>` — create a feature branch
2. `/speckit.specify`, `/speckit.plan`, `/speckit.tasks` — generate docs
3. `/speckit.implement` — execute tasks
4. Align with `.specify/memory/constitution.md` (principles are non-negotiable).

## What NOT to Do

- Do not add dependencies unless essential.
- Do not extract modules from `voice_loop.py` "for cleanliness".
- Do not introduce cloud APIs or external services in the core loop.
- Do not change existing CLI flag defaults without a MAJOR version bump.
