# Tasks: VoxCPM TTS Backend

**Input**: `specs/007-voxcpm-tts/spec.md`, `specs/007-voxcpm-tts/plan.md`, `specs/007-voxcpm-tts/research.md`
**Prerequisites**: `007-voxcpm-tts` branch checked out
**Test strategy**: Manual validation — `uv run voice_loop.py --tts voxcpm` and speak a full turn
**Organization**: Sequential phases. Phase 1 is setup, Phase 2–5 are user stories in priority order.

**Format**: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup & CLI Flag

**Purpose**: Add the `--tts voxcpm` choice, dependency, and platform guard.

- [ ] T001 [US1] Add `voxcpm` to `--tts` choices in `voice_loop.py` argparse section: `choices=["kokoro", "qwen", "qwen-cpp", "voxcpm"]`. Update help text.
- [ ] T002 [US1] Add `import` guard in `voice_loop.py` TTS loading section: when `args.tts == "voxcpm"`, try `from voxcpm import VoxCPM`. If ImportError, print `"Error: voxcpm not installed. Run: uv add voxcpm"` and exit.
- [ ] T003 [P] [US1] Add `voxcpm` dependency to `pyproject.toml`. Test with `uv sync`. If version conflicts arise (like qwen-tts transformers pin), use `[tool.uv] override-dependencies` or platform marker.
- [ ] T004 [P] [US1] Add `_load_voxcpm_config()` function in `voice_loop.py` near other config loaders: reads `tts.voxcpm_ref_audio`, `tts.voxcpm_voice_desc`, `tts.voxcpm_device` from config.yaml. Defaults: all None, device="auto".
- [ ] T005 [P] [US1] Add `_print_voxcpm_info()` function in `voice_loop.py` near other print functions: prints 30 supported languages (inline list), current config (ref_audio, voice_desc, device), and install instructions (`uv add voxcpm`).

**Checkpoint**: `uv run voice_loop.py --tts voxcpm` exits with "not installed" if voxcpm missing. `--list --tts voxcpm` shows capabilities.

---

## Phase 2: Model Loading (US1)

**Purpose**: Load VoxCPM2 model when `--tts voxcpm` is selected.

- [ ] T006 [US1] Add VoxCPM model loading in `voice_loop.py` TTS loading section (after Kokoro/QwenTTS blocks): when `args.tts == "voxcpm" and args.tts_enabled`, call `VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device=device)` where device comes from config or auto-detect (CUDA on Linux, MPS on macOS, CPU fallback). Store as `voxcpm_model`. Print loading message with model size (~8GB on first run).
- [ ] T007 [US1] Add `voxcpm_sr` variable: read `voxcpm_model.tts_model.sample_rate` after loading (should be 48000). Print sample rate info.
- [ ] T008 [US1] Wire `--list --tts voxcpm` to call `_print_voxcpm_info()` in the `args.list` dispatch block.

**Checkpoint**: `uv run voice_loop.py --tts voxcpm --lang en` loads model without error.

---

## Phase 3: Voice Cloning & Design (US1, US2, US3)

**Purpose**: Implement synthesis with voice cloning and voice design support.

- [ ] T009 [US2] Add `speak_voxcpm(text)` branch inside `speak_tts()` in `voice_loop.py`: when `voxcpm_model` is available, split text into sentences (reuse `_split_sentences` or simple regex), synthesize each sentence via `voxcpm_model.generate()`, concatenate audio arrays, play via `sd.play(samples, voxcpm_sr)` + `sd.wait()`.
- [ ] T010 [US2] In `speak_voxcpm`, handle voice cloning: if `_voxcpm_cfg["ref_audio"]` is set, pass `reference_wav_path=ref_audio` to `generate()`. Log a warning if file is < 5 seconds or missing.
- [ ] T011 [US3] In `speak_voxcpm`, handle voice design: if no ref_audio but `_voxcpm_cfg["voice_desc"]` is set, prepend description in parentheses to text: `f"({desc}){text}"`. This uses VoxCPM's built-in voice design.
- [ ] T012 [US1] In `speak_voxcpm`, handle AEC reference resampling: if AEC is enabled (`make_aec_processor`), resample 48kHz audio to 16kHz using `np.interp` for the `tts_16k_buf`. Play at native 48kHz via OutputStream.
- [ ] T013 [US2] Implement FR-012: when both ref_audio and voice_desc are configured, ref_audio takes precedence. Log which mode is active at startup.

**Checkpoint**: `uv run voice_loop.py --tts voxcpm --lang it` produces Italian audio. With ref_audio configured, voice is cloned.

---

## Phase 4: Integration & Dispatch (US1)

**Purpose**: Wire VoxCPM into all TTS dispatch points.

- [ ] T014 [US1] Wire `voxcpm_model` into `speak_tts()` dispatcher in `voice_loop.py`: add `elif voxcpm_model:` branch calling the VoxCPM synthesis path.
- [ ] T015 [US1] Wire into `process_utterance()` response playback: add `elif voxcpm_model:` branch (same pattern as `qwen_tts_model` — full synthesis then playback).
- [ ] T016 [US1] Wire into greeting playback: update `if kokoro or qwen_tts_model or _qwen_cpp_bin:` to include `or voxcpm_model`.
- [ ] T017 [US1] Update banner line to show `tts: voxcpm` when selected.

**Checkpoint**: Full turn works: `uv run voice_loop.py --tts voxcpm` → speak → get audio response.

---

## Phase 5: Polish & Documentation

**Purpose**: Config, docs, and edge cases.

- [ ] T018 [P] Update `config.yaml.example`: add `tts` section with `voxcpm_ref_audio`, `voxcpm_voice_desc`, `voxcpm_device` fields.
- [ ] T019 [P] Update `README.md`: add VoxCPM section with supported languages, voice cloning, voice design, install, and usage.
- [ ] T020 [P] Update `AGENTS.md`: add `--tts voxcpm` to TTS backend documentation and Recent Changes.
- [ ] T021 Verify regression: `uv run voice_loop.py` (no `--tts`) works identically. `uv run voice_loop.py --tts kokoro` works. `uv run voice_loop.py --tts qwen` works.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 2 depends on Phase 1 (needs flag + config)
- Phase 3 depends on Phase 2 (needs loaded model)
- Phase 4 depends on Phase 3 (needs working synthesis)
- Phase 5 depends on Phase 4 (docs reflect working implementation)

### Parallel Opportunities
- T003, T004, T005 can run in parallel within Phase 1
- T018, T019, T020 can run in parallel within Phase 5

### Implementation Strategy (MVP)

1. Add `--tts voxcpm` flag + import guard + config (Phase 1)
2. Add model loading (Phase 2)
3. Add synthesis with cloning/design (Phase 3)
4. Wire into dispatch (Phase 4)
5. Test: `uv run voice_loop.py --tts voxcpm --lang it`
6. Test regression: `uv run voice_loop.py` (no `--tts`)
7. Docs (Phase 5)
