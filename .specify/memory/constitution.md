<!--
Sync Impact Report
- Version change: 1.1.0 → 1.1.1
- Modified principles: none
- Modified sections:
  - Technology Constraints (updated STT to include faster-whisper + pluggable backend; added language config)
- Added sections: none
- Removed sections: none
- Changes driven by: feature 002-multilang-support introduces faster-whisper as
  STT backend alongside Moonshine; STT is now pluggable via --stt flag;
  --lang flag enables multilanguage pipeline; config.yaml supports language
  settings.
- Bump rationale: PATCH — Technology Constraints updated to reflect current
  STT architecture; no principles removed or redefined.
- Templates requiring updates:
  - .specify/templates/plan-template.md ✅ (Constitution Check gate compatible)
  - .specify/templates/spec-template.md ✅ (no mandatory section changes)
  - AGENTS.md ✅ (already updated by agent context script)
- Follow-up TODOs: RATIFICATION_DATE (original adoption date unknown)
-->

# Voice Loop Constitution

## Core Principles

### I. On-Device First

All inference and audio processing MUST run locally on the target machine.
No cloud API keys, no network calls for core functionality, no external
service dependencies in the hot path. Local execution preserves user
privacy, eliminates latency from round-trips, and guarantees the agent
works offline.

### II. Simplicity & Minimalism

The project SHALL prioritize a single-file architecture for the core
runtime (`voice_loop.py`) unless a clear performance or maintenance
benefit justifies extraction. Every new dependency MUST be essential;
prefer standard-library or already-transitive solutions. YAGNI applies:
do not add abstraction layers in anticipation of future features.

### III. User Sovereignty

Users MUST retain full control over agent behavior and data:

- `SOUL.md` controls persona and is live-reloaded every turn.
- `MEMORY.md` stores durable facts and is only active when explicitly
  requested (`--memory`).
- Both voice and keypress interruption MUST remain available.

No hidden state, no opaque training, no lock-in.

### IV. Audio Pipeline Integrity

The real-time signal path (Mic → VAD → Smart Turn → STT → LLM → TTS →
Speakers) MUST maintain low latency and clean synchronization:

- Audio callbacks SHALL NOT block.
- TTS output MUST align with AEC reference timing to prevent echo
  misalignment.
- Buffer sizes and sample rates are fixed constants; changing them
  requires end-to-end validation.

### V. Incremental Evolution

New features SHALL be additive and backward-compatible. Existing CLI
flags and default behaviors MUST NOT change without a MAJOR version
bump of the project. Configuration changes are preferred over code
changes when possible. Every new capability MUST include a way to
disable it at runtime.

## Technology Constraints

- **Language/Runtime**: Python 3.11+ managed with `uv`.
- **Target Platforms**:
  - macOS on Apple Silicon (M-series): Metal/MLX for LLM inference.
  - Arch Linux x86_64 with NVIDIA CUDA GPU (compute capability ≥ 7.0,
    VRAM ≥ 4 GB): llama.cpp/CUDA for LLM inference.
- **Audio Stack**: 16 kHz mono, 512-sample chunks (32 ms). `sounddevice`
  for I/O, `numpy` for signal manipulation.
- **Inference**: Moonshine (CPU, STT for 8 languages) or faster-whisper
  (CPU/CUDA, STT for 99+ languages; auto-selected for unsupported languages),
  Gemma 4 E4B (MLX/Metal on macOS or llama.cpp server on Linux for LLM),
  Kokoro (CPU, TTS, 10 languages), Silero VAD + Smart Turn v3 (endpoint
  detection), WebRTC AEC3 via LiveKit APM (echo cancellation).
- **Configuration**: `config.yaml` at project root for user-tunable settings
  (model aliases, language settings). Built-in defaults used when absent.
- **Distribution**: Single-file script with `uv` dependency resolution.
  Platform-specific deps use PEP 508 environment markers in
  `pyproject.toml`. No build step, no container requirement.

## Development Workflow

1. **Implementation Style**: Edit `voice_loop.py` directly. Extract
   modules only when a component becomes independently testable or is
   reused by another script.
2. **Validation Gate**: Every change MUST be validated by running the
   voice loop and confirming the audio pipeline completes a full
   turn without error on each target platform.
3. **Configuration First**: Adjust `SOUL.md`, `config.yaml`, or add
   CLI flags before changing hard-coded behavior.
4. **Versioning**: Project version follows SemVer in `pyproject.toml`.
   Constitution version follows its own SemVer track.

## Governance

This constitution supersedes all ad-hoc development decisions.

- **Amendments**: Require a documented rationale, a Sync Impact Report,
  and a version bump (MAJOR for breaking principle redefinitions,
  MINOR for new principles or sections, PATCH for clarifications).
- **Compliance Review**: The `/speckit.plan` Constitution Check gate
  MUST verify that every feature spec aligns with the active
  constitution.
- **Guidance**: Use `.specify/templates/agent-file-template.md` for
  runtime development guidance; keep it synchronized when technology
  constraints change.

**Version**: 1.1.1 | **Ratified**: TODO(RATIFICATION_DATE): original adoption date unknown | **Last Amended**: 2026-04-16
