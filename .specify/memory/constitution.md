<!--
Sync Impact Report
- Version change: 0.0.0 (template) → 1.0.0
- Modified principles: none (initial adoption)
- Added sections:
  - I. On-Device First
  - II. Simplicity & Minimalism
  - III. User Sovereignty
  - IV. Audio Pipeline Integrity
  - V. Incremental Evolution
  - Technology Constraints
  - Development Workflow
  - Governance
- Removed sections: none
- Templates requiring updates:
  - .specify/templates/plan-template.md ✅ (Constitution Check gate compatible)
  - .specify/templates/spec-template.md ✅ (no mandatory section changes)
  - .specify/templates/tasks-template.md ✅ (no new principle-driven task types)
  - .opencode/command/speckit.constitution.md ✅ (no outdated agent references)
  - .opencode/command/speckit.plan.md ✅ (no outdated agent references)
  - .opencode/command/speckit.implement.md ✅ (no outdated agent references)
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
runtime (`voice_loop_mac.py`) unless a clear performance or maintenance
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
- **Target Platform**: macOS on Apple Silicon (M-series); Metal/MLX for
  LLM inference.
- **Audio Stack**: 16 kHz mono, 512-sample chunks (32 ms). `sounddevice`
  for I/O, `numpy` for signal manipulation.
- **Inference**: Moonshine (CPU, STT), Gemma 4 E4B (MLX/Metal, LLM),
  Kokoro (CPU, TTS), Silero VAD + Smart Turn v3 (endpoint detection),
  WebRTC AEC3 via LiveKit APM (echo cancellation).
- **Distribution**: Single-file script with `uv` dependency resolution.
  No build step, no container requirement.

## Development Workflow

1. **Implementation Style**: Edit `voice_loop_mac.py` directly. Extract
   modules only when a component becomes independently testable or is
   reused by another script.
2. **Validation Gate**: Every change MUST be validated by running the
   voice loop and confirming the audio pipeline completes a full
   turn without error.
3. **Configuration First**: Adjust `SOUL.md` or add CLI flags before
   changing hard-coded behavior.
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

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): original adoption date unknown | **Last Amended**: 2026-04-16
