# Feature Specification: Linux (Arch Linux) Support

**Feature Branch**: `001-linux-support`
**Created**: 2026-04-16
**Status**: Draft
**Input**: User description: "Deeply analyze and adapt this project to work also in Arch Linux instead of only MLX (Mackintosh metal)."

## Clarifications

### Session 2026-04-16

- Q: Should the Linux port support CPU-only LLM inference (no GPU present), or require CUDA and error out gracefully? → A: Require CUDA GPU — print clear error and exit if absent. No CPU fallback.
- Q: What should the script be renamed to? → A: `voice_loop.py` — simple, matches project name, no platform qualifier.
- Q: How should the `--model` flag work across platforms? → A: Generic aliases — user passes a short name (e.g., `gemma-4-e4b`) and the system resolves to the correct model format per platform automatically.
- Remediation I1: FR-003 `--audio-mode` exception — macOS-only, errors on Linux.
- Remediation I2: Added FR-012 for `config.yaml` model alias loading with built-in defaults fallback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Voice Loop on Arch Linux (Priority: P1)

A user on an Arch Linux machine with a CUDA-capable GPU wants to clone
the repository, install dependencies with `uv sync`, and run the voice
agent — getting the same real-time voice interaction experience that
macOS users have today.

**Why this priority**: This is the core value — without it, Linux users
cannot use the project at all. It is the minimum viable port.

**Independent Test**: Boot an Arch Linux machine with an NVIDIA GPU,
install system deps, run `uv sync && uv run voice_loop.py`, speak a
full turn, and confirm the audio pipeline (mic → STT → LLM → TTS →
speakers) completes without error and with interruption working.

**Acceptance Scenarios**:

1. **Given** a clean Arch Linux install with CUDA GPU and system deps
   installed, **When** the user runs `uv sync`, **Then** all Python
   dependencies resolve without errors (no macOS-only packages block
   install).
2. **Given** dependencies are installed, **When** the user runs the
   voice loop script, **Then** the agent loads all models, listens to
   the microphone, transcribes speech, generates a response, and speaks
   it back — completing a full turn.
3. **Given** the agent is speaking via TTS, **When** the user speaks
   over the agent, **Then** voice interrupt triggers via AEC (same as
   macOS).

---

### User Story 2 - Single Codebase, Dual Platform (Priority: P2)

A developer wants to maintain a single script that works on both macOS
(Apple Silicon) and Arch Linux (CUDA) without forking the codebase or
maintaining separate branches.

**Why this priority**: Long-term maintainability. Two divergent scripts
would double the maintenance burden and drift apart quickly.

**Independent Test**: On macOS, the existing behavior is unchanged
(zero regressions). On Linux, User Story 1 passes. Both platforms run
the same file.

**Acceptance Scenarios**:

1. **Given** the shared script is run on macOS, **When** the user
   completes a full turn, **Then** behavior is identical to the
   current macOS-only version (same models, same CLI flags, same
   output).
2. **Given** the shared script is run on Arch Linux, **When** the
   user completes a full turn, **Then** behavior is functionally
   equivalent (same audio pipeline stages, same CLI flags, same
   persona/memory system).

---

### User Story 3 - Graceful Failure Without GPU (Priority: P3)

A user on a Linux machine without a CUDA GPU (or without NVIDIA drivers)
runs the voice loop and receives a clear, actionable error message
rather than a cryptic import crash or silent failure.

**Why this priority**: Developer experience and debugging time. A
clear error message saves the user from digging through stack traces.

**Independent Test**: On a Linux machine without CUDA, run the script
and confirm it prints a human-readable message explaining what is
missing and how to fix it.

**Acceptance Scenarios**:

1. **Given** a Linux machine without CUDA or without the GPU
   runtime installed, **When** the user runs the voice loop, **Then**
   the script prints a clear error identifying the missing requirement
   and exits gracefully (no Python traceback for the common case).

---

### Edge Cases

- What happens when the LLM backend model file is not yet downloaded on
  first Linux run? (Should auto-download, same as macOS first-run
  behavior.)
- What happens when espeak-ng is not installed on Linux? (Should error
  with a clear message: install via `pacman -S espeak-ng`.)
- What happens when PortAudio is not installed on Linux? (Should error
  with a clear message: install via `pacman -S portaudio`.)
- What happens on a Linux machine with AMD GPU (ROCm) instead of
  NVIDIA? (Out of scope for initial port, but should not crash —
  should fall back gracefully or report unsupported GPU.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST install and run on Arch Linux with a
  CUDA-capable NVIDIA GPU (VRAM ≥ 4 GB) using the same `uv sync && uv
  run` workflow as macOS. CPU-only inference is not supported on Linux.
- **FR-002**: The LLM inference backend MUST be automatically selected
  at runtime based on the detected platform (MLX on macOS, CUDA-based
  inference on Linux).
- **FR-003**: All existing CLI flags MUST work identically on both
  platforms (`--tts`, `--no-tts`, `--smart-turn`, `--aec`, `--chime`,
  `--memory`, `--model`, `--silence-ms`, `--record`, `--voice`).
  Exception: `--audio-mode` is macOS-only (requires MLX multimodal
  input); on Linux, the flag MUST print a clear error explaining it
  is not supported and exit.
- **FR-004**: The espeak-ng phonemizer library path MUST be detected
  correctly on both macOS (via Homebrew) and Linux (via system library
  paths).
- **FR-005**: The voice interrupt system (WebRTC AEC3 via LiveKit APM)
  MUST work on Linux the same way it does on macOS.
- **FR-006**: The `--model` flag MUST accept generic model aliases
  (e.g., `gemma-4-e4b`) that resolve to the correct format per platform
  (MLX-quantized on macOS, GGUF or equivalent on Linux). Passing a
  platform-inappropriate model identifier MUST produce a clear error.
  The default alias maps to Gemma 4 E4B on both platforms.
- **FR-007**: First-run model downloads MUST work on Linux, caching
  models locally the same way they are cached on macOS.
- **FR-008**: The script MUST detect the platform at startup and skip
  importing platform-specific backends that are unavailable, rather
  than crashing on import.
- **FR-009**: The script MUST print a clear, actionable error message
  when a required system dependency (PortAudio, espeak-ng, CUDA
  runtime) is missing on Linux, or when no CUDA-capable GPU is
  detected, and then exit.
- **FR-010**: The `SOUL.md` and `MEMORY.md` persona and memory systems
  MUST work identically on Linux.
- **FR-011**: The script MUST be renamed from `voice_loop_mac.py` to
  `voice_loop.py` to reflect cross-platform support. All documentation
  and CLI examples MUST reference the new name.
- **FR-012**: Model aliases MUST be loaded from `config.yaml` at project
  root when present. If the file is absent or malformed, built-in
  defaults MUST be used (matching `config.yaml.example`). A sample
  `config.yaml.example` MUST be provided in the repository.

### Key Entities

- **Platform**: Detected at runtime (macOS vs Linux); determines which
  LLM backend, model format, and system library paths to use.
- **LLM Backend**: An abstraction over the inference engine — one
  implementation per platform, sharing the same chat-completion
  interface (messages in, text out).
- **Model Identifier**: A string that resolves to a downloadable model;
  format varies by platform but the CLI interface (`--model`) is
  uniform.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user on Arch Linux with an NVIDIA GPU (VRAM ≥ 4 GB)
  can go from `git clone` to a completed voice turn in under 15
  minutes (excluding model download time).
- **SC-002**: End-to-end latency (end of user speech to start of TTS
  output) on Linux with a CUDA GPU (reference: RTX 3060 12 GB or
  equivalent) is under 6 seconds, which is within 2× of the
  macOS/Apple Silicon baseline.
- **SC-003**: Zero regression in macOS behavior — every existing CLI
  flag and default produces identical results on macOS after the
  changes.
- **SC-004**: A missing system dependency on Linux produces an error
  message containing the exact `pacman` command needed to install it.

## Assumptions

- Target Linux distribution is Arch Linux (rolling release, latest
  packages). Other distros may work but are not explicitly tested.
- The Linux machine has an NVIDIA GPU with CUDA support (compute
  capability 7.0+) and the NVIDIA driver installed. AMD/Intel GPU
  support is out of scope for this initial port.
- The user has `uv` installed on Linux (same as macOS requirement).
- System dependencies (PortAudio, espeak-ng) are installed via
  `pacman` on Arch Linux.
- The voice loop remains a single-file script as per the project
  constitution. Platform abstraction happens within the file, not
  via module extraction.
- Model download sizes and memory usage on Linux will be comparable
  to macOS (~3-4 GB total).
- `moonshine-voice`, `silero-vad`, `kokoro-onnx`, and `livekit` all
  have functional Linux wheels, which has been verified in the
  project's lock file.
