---

description: "Task list for Linux (Arch Linux) Support feature"
---

# Tasks: Linux (Arch Linux) Support

**Input**: Design documents from `/specs/001-linux-support/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Rename script, update dependencies, create config file

- [x] T001 Rename `voice_loop_mac.py` to `voice_loop.py` at repo root
- [x] T002 Update `pyproject.toml` — add `llama-cpp-python>=0.3.0; sys_platform == 'linux'`, change `mlx-vlm>=0.4.3` to `mlx-vlm>=0.4.3; sys_platform == 'darwin'`, bump version from `0.1.0` to `1.0.0`
- [x] T003 Run `uv lock` to re-resolve lockfile after pyproject.toml changes
- [x] T004 [P] Create `config.yaml.example` at repo root with default model aliases (gemma-4-e4b, gemma-4-e2b) mapping to platform-specific HuggingFace repos per `specs/001-linux-support/research.md` R6
- [x] T005 [P] Add `config.yaml` to `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-platform infrastructure that MUST be in place before any user story work begins

- [ ] T006 Add platform detection (`sys.platform`) at top of `main()` in `voice_loop.py` — store result as `IS_DARWIN` / `IS_LINUX` constants
- [ ] T007 Add `config.yaml` loading in `voice_loop.py` — parse YAML with built-in defaults fallback; create `load_model_aliases(config_path)` that returns the alias map from `config.yaml` if present, else uses hardcoded defaults matching `config.yaml.example`
- [ ] T008 Add `resolve_model(alias, platform)` function in `voice_loop.py` — look up alias in config, return `(repo_id, filename_glob)` for current platform; if alias not found, treat as raw HuggingFace repo ID and pass through
- [ ] T009 Replace espeak-ng path detection in `voice_loop.py` — change lines 164-169 to use `ctypes.util.find_library("espeak-ng")` as primary detection, with Homebrew fallback on macOS only; remove hardcoded `.dylib` extension
- [ ] T010 Add system dependency check function in `voice_loop.py` — `check_linux_deps()` that verifies PortAudio (via `sounddevice` import attempt) and espeak-ng (via `ctypes.util.find_library`); on failure, print install command per `specs/001-linux-support/contracts/cli-schema.md` and `sys.exit(1)`; only runs on Linux

**Checkpoint**: Platform detection, config loading, model resolution, espeak-ng detection, and dep checking are all in place. No LLM backend changes yet.

---

## Phase 3: User Story 1 - Run Voice Loop on Arch Linux (Priority: P1)

**Goal**: A Linux user with CUDA GPU can run the full voice pipeline

**Independent Test**: On Arch Linux with NVIDIA GPU, `uv sync && uv run voice_loop.py` — speak a full turn, confirm STT → LLM → TTS completes with voice interrupt working

### Implementation for User Story 1

- [ ] T011 [US1] Add Linux LLM backend in `voice_loop.py` — create `load_llm_linux(model_alias, args)` function that imports `llama_cpp`, resolves the model alias to GGUF repo + filename, calls `Llama.from_pretrained()` with `n_gpu_layers=-1`, `n_ctx=4096`, `verbose=False`; handle first-run auto-download (same pattern as Kokoro/Moonshine in existing code)
- [ ] T012 [US1] Add `llm_generate_linux(llm, messages, max_tokens, temperature)` function in `voice_loop.py` — wraps `llm.create_chat_completion(messages=messages, max_tokens=max_tokens, temperature=temperature)` and returns the content string
- [ ] T013 [US1] Update `main()` in `voice_loop.py` — add platform-conditional LLM loading: on Linux call `load_llm_linux()`, on macOS keep existing `mlx_vlm.load()` / `generate()` flow; update `llm_generate` helper to dispatch to the correct backend based on `IS_LINUX` / `IS_DARWIN`
- [ ] T014 [US1] Update `--model` flag default in `voice_loop.py` argparse — change from `mlx-community/gemma-4-E4B-it-4bit` to `gemma-4-e4b` (generic alias); update `--model` help text to mention aliases and config.yaml
- [ ] T015 [US1] Guard `--audio-mode` flag in `voice_loop.py` — the mlx-vlm audio multimodal path has no Linux equivalent; on Linux, print error "Error: --audio-mode is not supported on Linux (requires MLX multimodal input)." and exit; on macOS keep existing behavior unchanged
- [ ] T016 [US1] Update greeting prompt in `voice_loop.py` — the existing greeting call at line 429-436 uses `llm_generate` which must work with both backends; verify it uses the same `messages` format both paths accept
- [ ] T017 [US1] Validate full pipeline on Linux — run `uv run voice_loop.py` on Arch Linux with CUDA GPU, complete a full voice turn (speak → STT → LLM → TTS); explicitly verify: (a) voice interrupt works via AEC [FR-005], (b) `--memory` flag reads/writes `MEMORY.md` correctly [FR-010], (c) `SOUL.md` persona is applied [FR-010]

**Checkpoint**: At this point, the voice loop runs end-to-end on Arch Linux with CUDA GPU. User Story 1 is complete.

---

## Phase 4: User Story 2 - Single Codebase, Dual Platform (Priority: P2)

**Goal**: Same `voice_loop.py` works on both macOS and Linux with zero macOS regressions

**Independent Test**: On macOS, run `uv run voice_loop.py` and confirm all existing behavior is unchanged

### Implementation for User Story 2

- [ ] T018 [US2] Verify macOS MLX path in `voice_loop.py` — confirm the `IS_DARWIN` branch still uses `mlx_vlm.load()` and `generate()` identically to the original `voice_loop_mac.py`; compare diff to ensure no accidental changes to the macOS code path
- [ ] T019 [US2] Update `README.md` — add Arch Linux setup section with system deps (`pacman -S portaudio espeak-ng cuda nvidia`), update all `voice_loop_mac.py` references to `voice_loop.py`, add Linux-specific troubleshooting, keep macOS instructions as-is
- [ ] T020 [P] [US2] Update `AGENTS.md` — change `voice_loop_mac.py` references to `voice_loop.py`, add Linux/CUDA platform notes, update system deps section to mention both platforms
- [ ] T021 [US2] Validate on macOS — run `uv run voice_loop.py` on macOS, complete a full voice turn, confirm zero regressions (same models, same CLI flags, same output, same latency)

**Checkpoint**: Both platforms run the same file. macOS has zero regressions. User Stories 1 and 2 both pass.

---

## Phase 5: User Story 3 - Graceful Failure Without GPU (Priority: P3)

**Goal**: Linux without CUDA gets a clear, actionable error message instead of a crash

**Independent Test**: On Linux without CUDA (or with `CUDA_VISIBLE_DEVICES=""`), run script and confirm clear error message

### Implementation for User Story 3

- [ ] T022 [US3] Add CUDA availability check in `voice_loop.py` — after importing `llama_cpp` on Linux, check if GPU offload is available; if not, print `Error: No CUDA-capable GPU detected. Voice Loop on Linux requires an NVIDIA GPU with CUDA support (VRAM >= 4 GB).` and `sys.exit(1)`
- [ ] T023 [US3] Add graceful handling for AMD/ROCm GPUs in `voice_loop.py` — if `llama_cpp` loads but CUDA init fails with a non-CUDA GPU present, print `Error: AMD/Intel GPUs are not yet supported. Voice Loop on Linux requires an NVIDIA GPU with CUDA.` and exit; do not crash with a traceback
- [ ] T024 [US3] Add `llama-cpp-python` import guard in `voice_loop.py` — wrap `from llama_cpp import Llama` in try/except; on `ImportError`, print `Error: llama-cpp-python not installed. Run: uv sync` and exit
- [ ] T025 [US3] Validate error paths on Linux — test: (a) no GPU → clear error, (b) no espeak-ng → clear error with pacman cmd, (c) no PortAudio → clear error with pacman cmd, (d) AMD GPU → unsupported message

**Checkpoint**: All error paths produce actionable messages. User Stories 1, 2, and 3 all pass independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T026 [P] Update docstring at top of `voice_loop.py` — remove "Mac M4 / Apple Silicon" specificity, update to mention both macOS and Linux
- [ ] T027 [P] Update argparse description in `voice_loop.py` — change `"Voice Loop — a minimal on-device voice agent (Mac)"` to `"Voice Loop — a minimal on-device voice agent"`
- [ ] T028 [P] Remove any remaining hardcoded macOS-only references in `voice_loop.py` comments (search for "Mac", "macOS", "M4", "Apple Silicon" in comments)
- [ ] T029 [P] Verify `config.yaml.example` is consistent with the built-in defaults in `voice_loop.py` — they MUST match so that deleting config.yaml produces identical behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 completion
- **US2 (Phase 4)**: Depends on Phase 3 completion (needs the Linux path to exist before verifying macOS isn't broken)
- **US3 (Phase 5)**: Depends on Phase 2 completion; can run in parallel with Phase 3/4 (error paths are independent of happy-path code)
- **Polish (Phase 6)**: Depends on all user stories being complete

### Within Each User Story

- Config/infra before backend
- Backend before integration
- Integration before validation
- Story complete before moving to next priority

### Parallel Opportunities

- T004 (config.yaml.example) and T005 (.gitignore) can run in parallel with T001-T003
- T020 (AGENTS.md) can run in parallel with T019 (README.md)
- Phase 5 (US3) can start after Phase 2, in parallel with Phases 3 and 4
- All Phase 6 tasks can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (rename, deps, config)
2. Complete Phase 2: Foundational (platform detection, config loading, dep checks)
3. Complete Phase 3: User Story 1 (Linux LLM backend, full pipeline)
4. **STOP and VALIDATE**: Run on Arch Linux, complete a full voice turn
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. Add User Story 1 → Linux works end-to-end (MVP!)
3. Add User Story 2 → macOS zero-regression verified
4. Add User Story 3 → Graceful error handling on Linux
5. Polish → Clean up, version bump, docs final

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- No automated tests — validation is manual (run the voice loop)
- The constitution requires MAJOR version bump (0.1 → 1.0) due to script rename
