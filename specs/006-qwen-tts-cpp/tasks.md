# Tasks: QwenTTS C++ Backend

**Input**: `specs/006-qwen-tts-cpp/spec.md`, `specs/006-qwen-tts-cpp/plan.md`
**Prerequisites**: `006-qwen-tts-cpp` branch checked out
**Test strategy**: Manual — `uv run voice_loop.py --tts qwen-cpp` and speak a full turn
**Organization**: Sequential phases. Phase 1 is foundation, Phase 2 is core, Phase 3 is polish.

**Format**: `[ID] [P?] [Story] Description`

---

## Phase 1: CLI Flag & Config

**Purpose**: Add the flag choice and configuration.

- [ ] T001 [US-1] Add `qwen-cpp` to `--tts` choices: `choices=["kokoro", "qwen", "qwen-cpp"]`. Update help text.
- [ ] T002 [US-1] Remove the macOS rejection for `qwen-cpp`: update the platform check at ~line 513 to only reject `qwen` on macOS (not `qwen-cpp`). `qwen-cpp` works everywhere.
- [ ] T003 [US-3] Add config reading for `tts.qwen_cpp_model_dir`, `tts.qwen_cpp_ref_audio`, `tts.qwen_cpp_bin` from config.yaml. Store as `_qwen_cpp_cfg` dict. Defaults:
  - `bin`: `"qwen3-tts-cli"` (assumes on PATH)
  - `model_dir`: `"models"` (relative to qwen3-tts.cpp clone, or absolute path)
  - `ref_audio`: `None`
- [ ] T004 [US-3] Update `config.yaml.example` with `tts` section additions for qwen-cpp.

**Checkpoint**: `uv run voice_loop.py --tts qwen-cpp --help` parses without error.

---

## Phase 2: Subprocess Integration

**Purpose**: Implement the subprocess TTS path.

- [ ] T005 [US-1] Add `_find_qwen_cpp_bin()` function: checks `config.yaml` path first, then PATH. Runs `qwen3-tts-cli --help` (or `-h`) to verify it works. Returns path or None.
- [ ] T006 [US-1] Add startup validation in `main()`: if `args.tts == "qwen-cpp"` and `args.tts_enabled`, call `_find_qwen_cpp_bin()`. If not found, print install instructions and exit.
- [ ] T007 [US-1,US-2] Add `speak_qwen_cpp(text)` function inside `main()`:
  1. Create temp WAV file via `tempfile.NamedTemporaryFile(suffix=".wav", delete=False)`
  2. Build command: `[bin_path, "-m", model_dir, "-t", text, "-o", wav_path]`
  3. If ref_audio configured: append `["-r", ref_audio]`
  4. Run `subprocess.run(cmd, capture_output=True, timeout=120)`
  5. Read WAV with `soundfile.read(wav_path)`
  6. `sd.play(samples, sr)` + `sd.wait()`
  7. Clean up temp file
- [ ] T008 [US-1] Wire `speak_qwen_cpp` into `speak_tts()` dispatcher: add `elif _qwen_cpp_bin:` branch.
- [ ] T009 [US-1] Wire into `process_utterance()` response playback: add `elif _qwen_cpp_bin:` branch (same pattern as `qwen_tts_model`).
- [ ] T010 [US-1] Wire into greeting playback: `if kokoro or qwen_tts_model or _qwen_cpp_bin: speak_tts(greeting)`.

**Checkpoint**: `uv run voice_loop.py --tts qwen-cpp --lang en` produces spoken output (requires qwen3-tts-cli installed).

---

## Phase 3: Listing & Documentation

**Purpose**: Discoverability and docs.

- [ ] T011 [US-4] Add `_print_qwen_cpp_info()` function: prints config path, model dir, reference audio, install instructions (clone/build/convert steps from qwen3-tts.cpp README).
- [ ] T012 [US-4] Wire `--list --tts qwen-cpp` to call `_print_qwen_cpp_info()`.
- [ ] T013 Update `README.md`: add qwen3-tts.cpp section with install steps, model setup, usage.
- [ ] T014 Update `AGENTS.md`: add `--tts qwen-cpp` documentation.
- [ ] T015 Update banner: show `tts: qwen-cpp` in startup message.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 2 depends on Phase 1 (needs flag + config)
- Phase 3 depends on Phase 2 (docs reflect working implementation)

### Parallel Opportunities
- T001, T003 can be done in parallel within Phase 1
- T011, T013, T014 can be done in parallel within Phase 3

---

## Implementation Strategy (MVP)

1. Add `qwen-cpp` to `--tts` choices + config reading (Phase 1)
2. Add `_find_qwen_cpp_bin()` + startup validation
3. Add `speak_qwen_cpp()` + wire into dispatch (Phase 2)
4. Test: `uv run voice_loop.py --tts qwen-cpp --lang en`
5. Test: `uv run voice_loop.py` (regression, no `--tts`)
6. Test: `uv run voice_loop.py --tts qwen` (Python backend regression)
7. Listing + docs (Phase 3)
