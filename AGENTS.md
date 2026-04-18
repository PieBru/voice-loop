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
- **Configuration**: `config.yaml` at project root for user-tunable settings (model aliases, language settings). Built-in defaults used when absent.
- **Multilanguage**: `--lang` flag sets language for the full pipeline (STT + LLM + TTS). `--stt` flag selects STT backend (`whisper` or `moonshine`; auto-selected if omitted). Default language is `en` (English).
- **TTS backend**: `--tts` flag selects TTS backend (`kokoro` for CPU ONNX, `qwen` for CUDA neural TTS, `qwen-cpp` for C++ subprocess, `voxcpm` for VoxCPM2 diffusion TTS). Default is `kokoro`. `--tts qwen` requires Linux with NVIDIA CUDA (≥8 GB VRAM for 1.7B model). `--tts qwen-cpp` works on all platforms (requires external `qwen3-tts-cli` binary). `--tts voxcpm` requires `uv add voxcpm` (30 languages, voice cloning, voice design). Kokoro uses sentence-by-sentence streaming TTS (asyncio Queue, GROUP=2). Neither QwenTTS nor VoxCPM backend supports streaming; audio plays after full synthesis.
- **Response handler**: `--handler` flag selects the response generation backend (`llm` for direct API call, `agentic` for external agent service). Default is `llm`. `--list-handlers` shows available handlers. Handler config in `config.yaml` → `handlers` section.

## How to Change Behavior

1. **Persona/style**: edit `SOUL.md` (live-reloaded every turn).
2. **Model aliases**: edit `config.yaml` (loaded at startup).
3. **Language/STT backend**: use `--lang` and `--stt` CLI flags; defaults preserve English-only behavior.
4. **Response handler**: use `--handler` CLI flag; default is `llm`. Configure agentic endpoint in `config.yaml` → `handlers`.
5. **TTS backend**: use `--tts` CLI flag; default is `kokoro`. Use `--tts qwen` for Qwen3-TTS on CUDA Linux. Use `--tts qwen-cpp` for C++ subprocess (all platforms). Use `--tts voxcpm` for VoxCPM2 diffusion TTS (install: `uv add voxcpm`).
6. **New capability**: add a CLI flag in `voice_loop.py` before hard-coding behavior. Every new feature MUST be disable-able at runtime.
7. **Memory**: enable with `--memory`; `MEMORY.md` is gitignored user-local state.

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

## Active Technologies
- Python 3.11+ (managed with `uv`) + faster-whisper 1.2.1, moonshine-voice, kokoro-onnx, qwen-tts (Linux only)
- File-based (HF cache for models, config.yaml for settings)
- Python 3.11+ managed with `uv` + stdlib `urllib.request`, `json`; no new cloud dependencies
- Python 3.11+ (managed with `uv`) + `asyncio`, `threading`, `queue`, `re`, `numpy`, `sounddevice` (all already in project) (008-streaming-tts)
- Python 3.11+ + stdlib `urllib.request`, `json` (already imported); `soundfile` (already transitive via qwen-cpp path) for WAV parsing in non-streaming mode; `numpy` + `sounddevice` (already imported) for playback (009-openai-tts)
- N/A (HTTP client — no local storage beyond config.yaml) (009-openai-tts)

## Recent Changes
- 008-streaming-tts: Ported upstream sentence-by-sentence streaming TTS architecture with `stream_sentences()`, `_collecting()`, `_split_sentences()`, asyncio Queue + GROUP=2 Kokoro synthesis, `pad_gap_and_check()` inter-sentence AEC, incremental response printing
- 007-voxcpm-tts: Added `--tts voxcpm` option, VoxCPM2 diffusion TTS backend (30 languages, voice cloning via ref_audio, voice design via desc), `_load_voxcpm_config()`, `_print_voxcpm_info()`
- 006-qwen-tts-cpp: Added `--tts qwen-cpp` option, subprocess integration with `qwen3-tts-cli`, config for binary path/model dir/ref audio, `_print_qwen_cpp_info()`, install instructions
- 005-qwen-tts: Added `--tts` flag (kokoro/qwen), Qwen3-TTS backend for CUDA Linux, `_QWEN_SPEAKER_MAP`, `_patch_qwen_tts_compat()` for transformers 5.x compat, `--list --tts qwen` speaker listing
- 004-zeroclaw-handler: Added ZeroClaw handler for `--handler zeroclaw`
- 003-pluggable-response-handler: Added `--handler`, `--list-handlers`, `--offline` flags, agentic handler, fallback logic
- 002-multilang-support: Added `--lang`, `--stt`, `--list`, `--whisper-device` flags, dual STT backend, language-aware TTS
