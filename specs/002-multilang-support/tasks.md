# Tasks: Multilanguage STT & TTS Support

**Input**: Design documents from `/specs/002-multilang-support/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Manual validation only — run `uv run voice_loop.py --lang <code>` and confirm full voice turn.

**Organization**: Tasks grouped by user story. US1 and US2 are both P1 and closely coupled (Italian IS a non-English language), so they share Phase 3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Add dependency and CLI flags

- [x] T001 Add `faster-whisper>=1.2` to dependencies in `pyproject.toml`
- [x] T002 Run `uv lock` to resolve the new dependency
- [x] T003 Add `--lang` CLI flag (default `"en"`, help lists built-in codes: en, es, ja, fr, it, pt, zh, de) and `--stt` CLI flag (default `None` for auto-select, choices: whisper, moonshine) to argparse in `voice_loop.py`. Change `--voice` default from `"af_heart"` to `None` so we can detect user override vs language-inferred default.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core language infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Add `_LANG_MAP` dict constant to `voice_loop.py` with 8 built-in language entries (en, es, ja, fr, it, pt, zh, de) mapping to tts_voice, tts_lang, llm_language, moonshine_supported — placed near `_DEFAULT_ALIASES`
- [x] T005 Add `MOONSHINE_LANGS` frozenset constant to `voice_loop.py`: `{en, ar, es, ja, ko, vi, uk, zh}`
- [x] T006 Add `resolve_language()` function to `voice_loop.py` that looks up `--lang` code in `_LANG_MAP`, returns the config dict or a synthesized default for unknown codes with a warning. If `config.yaml` exists and contains a `languages` section, merge user overrides into `_LANG_MAP` before lookup (same pattern as `load_model_aliases()`)
- [x] T007 Add STT backend auto-selection logic in `voice_loop.py` main(): if `args.stt` is set use it; else if `args.lang` in `MOONSHINE_LANGS` use moonshine; else use whisper. Store result in `_stt_backend` variable

**Checkpoint**: Language resolution and STT selection logic ready — user story implementation can begin

---

## Phase 3: User Stories 1 & 2 — Non-English + Italian End-to-End (Priority: P1) 🎯 MVP

**Goal**: Full voice loop works in any language (specifically Italian) with a single `--lang` flag

**Independent Test**: `uv run voice_loop.py --lang it` — speak Italian, confirm STT→LLM→TTS all in Italian

### Implementation

- [x] T008 [US1] Replace hardcoded `get_model_for_language("en")` with language-aware STT loading in `voice_loop.py`: if moonshine backend → `get_model_for_language(args.lang)`; if whisper backend → `from faster_whisper import WhisperModel` and load `WhisperModel("base", device="cpu", compute_type="int8")`
- [x] T009 [US1] Update startup print message in `voice_loop.py` to show which STT backend and model is loading (e.g., `"Loading Whisper base (transcription)..."` vs `"Loading Moonshine (transcription)..."`)
- [x] T010 [US1] Update `transcribe()` closure in `voice_loop.py` to dispatch based on `_stt_backend`: moonshine path uses existing `moonshine.transcribe_without_streaming()`, whisper path uses `WhisperModel.transcribe(audio, language=args.lang)` and joins segments
- [x] T011 [US1] Set default voice from language config: after argparse, if `args.voice is None` (user did NOT pass `--voice` since T003 changed default to `None`), set `args.voice` to the language's `tts_voice` from `_LANG_MAP`
- [x] T012 [US1] Append LLM language instruction to system prompt in `voice_loop.py`: when `args.lang != "en"`, append `"You MUST respond in {llm_language}. Never use English unless the user explicitly asks for it."` after loading SOUL.md — never modify SOUL.md itself
- [x] T013 [US1] Update greeting prompt language in `voice_loop.py`: when `args.lang != "en"`, append `"Respond in {llm_language}."` to the greeting user message
- [x] T014 [US1] Update startup banner "Listening" line in `voice_loop.py` to show language, STT backend, and TTS voice: `Listening (lang: {lang}, stt: {backend}, tts: {voice}, ...)`
- [ ] T015 [US2] Validate Italian end-to-end: run `uv run voice_loop.py --lang it` on Linux, confirm startup shows `stt: whisper, tts: if_sara`, speak Italian, confirm transcription in Italian, LLM responds in Italian, TTS speaks Italian
- [ ] T016 [US1] Validate English regression: run `uv run voice_loop.py` without `--lang`, confirm identical behavior to pre-feature version (Moonshine loads for English, voice is `af_heart`, no language instruction appended)

**Checkpoint**: At this point, `--lang it` and `--lang es` should work end-to-end. English unchanged.

---

## Phase 4: User Story 3 — Consistent Components & Error Handling (Priority: P2)

**Goal**: All components align on language; clear errors for invalid combinations

**Independent Test**: `--stt moonshine --lang it` produces a clear error. `--lang es` shows Moonshine for STT, Spanish voice, Spanish LLM instruction.

### Implementation

- [x] T017 [US3] Add validation in `voice_loop.py` main(): if `args.stt == "moonshine"` and `args.lang not in MOONSHINE_LANGS`, print error listing supported languages and exit with code 1
- [x] T018 [US3] Add validation in `voice_loop.py` main(): if `args.stt == "whisper"`, verify faster-whisper imports successfully; if not, print actionable error and exit
- [ ] T019 [US3] Verify startup banner clearly shows component alignment per SC-004: test with `--lang es` (shows Moonshine), `--lang it` (shows whisper), `--lang fr --stt whisper` (shows whisper explicitly forced)
- [ ] T020 [US3] Verify `--voice` override works with `--lang`: run `--lang it --voice im_nicola`, confirm male Italian voice is used

**Checkpoint**: All error paths validated, component consistency verified

---

## Phase 5: Polish & Cross-Cutting

**Purpose**: Documentation and config updates

- [x] T021 [P] Update `config.yaml.example` with a `languages` section showing how to override built-in language defaults
- [x] T022 [P] Update `README.md` with `--lang` and `--stt` usage examples and language table
- [x] T023 Verify `AGENTS.md` reflects multilanguage flags (already partially updated — verify completeness)
- [x] T024 Verify `.specify/memory/constitution.md` Technology Constraints mention both STT backends (already updated to v1.1.1 — verify accuracy)
- [ ] T025 Run `uv sync` on both platforms and confirm no dependency conflicts

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1+US2 (Phase 3)**: Depends on Phase 2 — core implementation
- **US3 (Phase 4)**: Depends on Phase 3 — error handling and validation on top of working implementation
- **Polish (Phase 5)**: Depends on Phase 4

### User Story Dependencies

- **US1 + US2**: Can start after Phase 2 (they're tightly coupled — Italian IS a non-English language)
- **US3**: Depends on US1+US2 being functionally complete (validates their behavior)

### Parallel Opportunities

- T001 + T003 can be done in parallel (different files: pyproject.toml vs voice_loop.py)
- T004 + T005 can be done in parallel (both constants, same file but independent)
- T021 + T022 can be done in parallel (different files)
- T015 + T016 can be done in parallel (independent validation runs)

---

## Parallel Example: Phase 3

```text
# Sequential core (same file, ordered):
T008 → T009 → T010 → T011 → T012 → T013 → T014

# Then parallel validation:
T015: Validate Italian end-to-end
T016: Validate English regression
```

---

## Implementation Strategy

### MVP (User Stories 1 & 2)

1. Complete Phase 1: Setup (add dep, add flags)
2. Complete Phase 2: Foundational (language map, STT dispatch)
3. Complete Phase 3: US1+US2 (whisper integration, voice/language wiring)
4. **STOP and VALIDATE**: `--lang it` works end-to-end, English unchanged
5. Commit and demo

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. Add US1+US2 → Test Italian end-to-end → **MVP!**
3. Add US3 → Error handling → Robust
4. Polish → Docs updated

---

## Notes

- All code changes go into `voice_loop.py` (single-file architecture per constitution)
- `faster-whisper` base model auto-downloads ~145MB on first use (HF cache)
- Moonshine non-English models print a license warning (non-commercial) — this is expected
- `--lang en` with no `--stt` MUST produce identical behavior to running without `--lang` at all
- The `_lang_from_voice()` function already handles Italian prefix `i` → `"it"` — no changes needed there
