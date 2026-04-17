# Tasks: Pluggable Response Handler

**Input**: Design documents from `/specs/003-pluggable-response-handler/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Manual validation only — run `uv run voice_loop.py --handler <name>` and confirm full voice turn.

**Organization**: Tasks grouped by user story. US1 and US2 are both P1 and tightly coupled (US2 is the alternative to US1), so they share Phase 3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Add CLI flags and handler configuration infrastructure

- [ ] T001 Add `--handler` CLI flag to argparse in `voice_loop.py`: default `"llm"`, help text `"Response generation handler (default: llm)"`, no choices restriction (extensible via config)
- [ ] T002 Add `--list-handlers` CLI flag to argparse in `voice_loop.py`: action `"store_true"`, help text `"List available response handlers and exit"`. When set, print handler table and exit immediately (before loading models)
- [ ] T003 [P] Update `config.yaml.example` with a `handlers` section showing the agentic handler defaults (`api_base: http://localhost:8089/v1`, `model: agent-model-name`, `timeout: 60`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core handler infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Add `_HANDLER_DEFAULTS` dict constant to `voice_loop.py` near `_DEFAULT_ALIASES`, mapping built-in handler names to their descriptions and default configs. At minimum: `{"llm": {"description": "Direct LLM API call (default)"}, "agentic": {"description": "External agentic service (configurable endpoint)", "api_base": "http://localhost:8089/v1", "model": "agentic", "timeout": 60}}`
- [ ] T005 Add `load_handler_config()` function to `voice_loop.py` that reads handler settings from `config.yaml` → `handlers` section, merging with `_HANDLER_DEFAULTS` (same pattern as `load_model_aliases()`). Returns a dict mapping handler names to their resolved configs
- [ ] T006 Refactor `llm_generate()` in `voice_loop.py` into a handler dispatch pattern: rename the existing closure to `_llm_handler`, create a new `_agentic_handler` closure that sends the same OpenAI-compatible chat completion request to the agentic endpoint (using `urllib.request` with the configured `api_base`, `model`, and `timeout`). Store both in a `_handlers` dict. Create a wrapper `generate_response(messages, max_tokens, temperature)` that dispatches to `_handlers[_active_handler]` with fallback logic: on any exception from the agentic handler, print warning to stderr and permanently switch `_active_handler` to `"llm"` for the session

**Checkpoint**: Handler infrastructure ready — user story implementation can begin

---

## Phase 3: User Stories 1 & 2 — LLM Default + Agentic Handler (Priority: P1) 🎯 MVP

**Goal**: `--handler llm` preserves current behavior (zero regression); `--handler agentic` delegates to an external agentic service

**Independent Test**: `uv run voice_loop.py` (no change) and `uv run voice_loop.py --handler agentic` (agentic delegation)

### Implementation

- [ ] T007 [US1] After argparse in `voice_loop.py` main(), resolve handler config: load via `load_handler_config()`, validate `args.handler` is a known handler name (print error listing available handlers and exit if not). Set `_active_handler = args.handler`. Store the resolved handler config in `_handler_cfg`
- [ ] T008 [US1] Replace all calls to `llm_generate()` in `voice_loop.py` with `generate_response()`. This includes: the greeting call (~line 891), `process_utterance()` call, and the memory helper functions (`_run_memory()`). The `llm_generate` name can be kept as an alias for the `llm` handler closure internally
- [ ] T009 [US2] Add startup validation for the agentic handler in `voice_loop.py` main(): if `_active_handler == "agentic"`, try `urllib.request.urlopen(f"{_handler_cfg['api_base']}/models", timeout=5)`. If unreachable, print warning `"Warning: Agentic handler endpoint {_handler_cfg['api_base']} unreachable. Falling back to llm handler."` to stderr and set `_active_handler = "llm"`
- [ ] T010 [US2] Update the startup banner "Listening" line in `voice_loop.py` to include `handler: {_active_handler}` per the CLI schema contract
- [ ] T011 [US1] Validate English regression: run `uv run voice_loop.py` without `--handler`, confirm identical behavior to pre-feature version (same LLM endpoint, same response flow, no warnings)
- [ ] T012 [US2] Validate agentic handler: run `uv run voice_loop.py --handler agentic` with an agentic service running on port 8089, speak a question, confirm response comes from the agentic service and is spoken via TTS
- [ ] T013 [US2] Validate agentic fallback: run `uv run voice_loop.py --handler agentic` with NO agentic service running, confirm warning is printed at startup and the system falls back to the LLM handler. Also confirm that mid-session timeout and empty responses are handled gracefully (no crash, no TTS, continue listening)

**Checkpoint**: Both handlers work. `--handler llm` = zero regression. `--handler agentic` = delegates to agent service with fallback.

---

## Phase 4: User Story 3 — Discover Available Handlers (Priority: P2)

**Goal**: `--list-handlers` shows all registered handlers with descriptions

**Independent Test**: `uv run voice_loop.py --list-handlers` prints handler table

### Implementation

- [ ] T014 [US3] Implement `_print_handler_table()` function in `voice_loop.py`: load handler config, print a formatted table with columns `Handler` and `Description` (per CLI schema contract). Mark the default handler with ` (default)`
- [ ] T015 [US3] Validate: run `uv run voice_loop.py --list-handlers`, confirm output shows `llm` and `agentic` with descriptions, then exits without loading models

**Checkpoint**: Handler discoverability complete

---

## Phase 5: Polish & Cross-Cutting

**Purpose**: Documentation and consistency

- [ ] T016 [P] Update `README.md` with `--handler` and `--list-handlers` usage examples, and add a `handlers` section to config.yaml documentation
- [ ] T017 Update `AGENTS.md` to mention `--handler` flag and the `handlers` config section
- [ ] T018 Verify constitution v1.1.1 Technology Constraints still accurately describe the project (add response handler mention if needed)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1+US2 (Phase 3)**: Depends on Phase 2 — core implementation
- **US3 (Phase 4)**: Depends on Phase 2 (uses handler config infrastructure)
- **Polish (Phase 5)**: Depends on Phase 4

### User Story Dependencies

- **US1 + US2**: Can start after Phase 2 (tightly coupled — agentic is the alternative to LLM)
- **US3**: Can start after Phase 2 (only needs handler config, not the dispatch)

### Parallel Opportunities

- T001 + T002 + T003 can be done in parallel (T001/T002 same file argparse but independent flags; T003 different file)
- T011 + T012 + T013 can be done in parallel (independent validation runs)
- T016 is parallelizable with T017/T018 (different files)

---

## Parallel Example: Phase 3

```text
# Sequential core (same file, ordered):
T007 → T008 → T009 → T010

# Then parallel validation:
T011: Validate English regression
T012: Validate agentic handler
T013: Validate agentic fallback
```

---

## Implementation Strategy

### MVP (User Stories 1 & 2)

1. Complete Phase 1: Setup (add flags, config)
2. Complete Phase 2: Foundational (handler infrastructure)
3. Complete Phase 3: US1+US2 (LLM default + agentic handler)
4. **STOP and VALIDATE**: `--handler llm` = zero regression, `--handler agentic` = works or falls back
5. Commit and demo

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. Add US1+US2 → Test both handlers → **MVP!**
3. Add US3 → Handler listing → Polish
4. Polish → Docs updated

---

## Notes

- All code changes go into `voice_loop.py` (single-file architecture per constitution)
- No new dependencies — reuses `urllib.request` and `json` already in use
- The agentic handler uses the exact same HTTP request format as the LLM handler (OpenAI-compatible chat completions)
- Handler config defaults: `api_base: http://localhost:8089/v1`, `model: agentic`, `timeout: 60`
- Memory functions (`update_memory`, `consolidate_memory`) automatically use the active handler via `generate_response()` — no separate handling needed
- The `llm` handler's existing macOS path (mlx-vlm) and Linux path (HTTP API) are preserved unchanged inside `_llm_handler`
