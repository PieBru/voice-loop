# Tasks: QwenTTS Backend

**Input**: `specs/005-qwen-tts/spec.md`, `specs/005-qwen-tts/plan.md`
**Prerequisites**: `005-qwen-tts` branch checked out
**Test strategy**: Manual validation — `uv run voice_loop.py --tts qwen` and speak a full turn
**Organization**: Sequential phases. Phase 1–2 are foundation, Phase 3 is core, Phase 4–5 are polish.

**Format**: `[ID] [P?] [Story] Description`

---

## Phase 1: CLI Flag & Constants

**Purpose**: Add the `--tts` flag and speaker mapping constants.

- [ ] T001 [US-1] Add `--tts` argument to argparse: choices `["kokoro", "qwen"]`, default `"kokoro"`, help `"TTS backend (default: kokoro)"`. Place after `--stt` flag for logical grouping.
- [ ] T002 [US-3] Add `_QWEN_SPEAKER_MAP` dict at module level, mapping language codes to default QwenTTS speakers and language names:

```python
_QWEN_SPEAKER_MAP = {
    "en": {"speaker": "Ryan", "language": "English"},
    "zh": {"speaker": "Vivian", "language": "Chinese"},
    "ja": {"speaker": "Ono_Anna", "language": "Japanese"},
    "ko": {"speaker": "Sohee", "language": "Korean"},
    "es": {"speaker": "Ryan", "language": "Spanish"},
    "fr": {"speaker": "Ryan", "language": "French"},
    "it": {"speaker": "Ryan", "language": "Italian"},
    "pt": {"speaker": "Ryan", "language": "Portuguese"},
    "de": {"speaker": "Ryan", "language": "German"},
    "ru": {"speaker": "Ryan", "language": "Russian"},
}
```

Note: QwenTTS has no native speakers for es/fr/it/pt/de/ru — Ryan (multilingual English) is used as fallback. Users can override with `--voice`.

- [ ] T003 [US-1] Add platform check in `main()`: if `args.tts == "qwen"` and `IS_DARWIN`, print error and `sys.exit(1)`.

**Checkpoint**: `uv run voice_loop.py --tts qwen` on macOS should error. `uv run voice_loop.py --tts kokoro` should parse without error.

---

## Phase 2: QwenTTS Model Loading

**Purpose**: Load Qwen3-TTS model when `--tts qwen` is selected.

- [ ] T004 [US-1] In the TTS loading section (after line 616), add QwenTTS loading path. When `args.tts == "qwen"`: lazy-import `qwen_tts`, load `Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", device_map="cuda:0", dtype=torch.bfloat16)` and `Qwen3TTSTokenizer.from_pretrained(...)`. Store in a `qwen_tts_model` variable (parallel to `kokoro`).
- [ ] T005 [US-1] When `args.tts == "kokoro"`: existing Kokoro loading code unchanged.
- [ ] T006 [US-1] Refactor the loading guard: change `if args.tts:` to dispatch by `args.tts` value. Both paths set their model variable. The `tts_enabled` flag is True when either model loads.

**Checkpoint**: `uv run voice_loop.py --tts qwen` should start loading Qwen3-TTS model (will download ~3.4GB on first run).

---

## Phase 3: Synthesis & Playback

**Purpose**: Wire QwenTTS into the speak/play paths.

- [ ] T007 [US-1] Add `speak_qwen(text)` function inside `main()` (parallel to `speak_tts`). Uses `qwen_tts_model.generate_custom_voice(text=text, language=..., speaker=args.voice, non_streaming_mode=True)`. Returns `(wavs, sr)`. Play via `sd.play(wavs[0], sr)` then `sd.wait()`.
- [ ] T008 [US-5] Add `play_qwen_tts(response)` function: synthesizes full text via QwenTTS, then plays via `sd.play()`. Since there's no streaming, AEC barge-in is not possible during synthesis. After playback starts, keypress interrupt still works via stdin select (but simpler than Kokoro's streaming approach — just `sd.stop()` on keypress).
- [ ] T009 [US-1] Refactor `speak_tts()` to `speak_tts_or_qwen()`: dispatch by `args.tts` value. Similarly refactor greeting and response playback to use the correct backend.
- [ ] T010 [US-1] Update `process_utterance()` at line 1023: change `if kokoro and response:` to check the active TTS backend. If `qwen`, call `play_qwen_tts(response)`. If `kokoro`, call `play_tts_stream(response)`.

**Checkpoint**: `uv run voice_loop.py --tts qwen --lang en` should produce spoken output.

---

## Phase 4: Voice Resolution & Listing

**Purpose**: Handle `--voice` for QwenTTS and extend `--list`.

- [ ] T011 [US-2,US-3] Update voice resolution logic (lines 500-501): when `args.tts == "qwen"` and `args.voice is None`, look up `_QWEN_SPEAKER_MAP[args.lang]["speaker"]` instead of `_lang_cfg["tts_voice"]`. Warn if language not in `_QWEN_SPEAKER_MAP`.
- [ ] T012 [US-4] Update `_print_language_table()` (or add `_print_qwen_speaker_table()`): when `--tts qwen` is active, list QwenTTS built-in speakers instead of Kokoro voices. Call `model.get_supported_speakers()` if model is loaded, otherwise print from `_QWEN_SPEAKER_MAP`.
- [ ] T013 [US-4] Wire `--list --tts qwen` to call the QwenTTS listing function.

**Checkpoint**: `uv run voice_loop.py --list --tts qwen` shows QwenTTS speakers.

---

## Phase 5: Configuration & Documentation

**Purpose**: Config file support and docs.

- [ ] T014 [FR-010] Add `tts` section to `config.yaml.example` with QwenTTS settings (model variant, device). Read in `main()` and merge with defaults.
- [ ] T015 Update `README.md`: add QwenTTS section with usage, supported languages, VRAM requirements.
- [ ] T016 Update `AGENTS.md`: add `--tts` flag documentation.
- [ ] T017 Update banner line (line 1053): show `tts: qwen` or `tts: kokoro` in the startup message.
- [ ] T018 Add `qwen-tts` to `pyproject.toml` dependencies.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 2 depends on Phase 1 (needs `args.tts` flag)
- Phase 3 depends on Phase 2 (needs loaded model)
- Phase 4 depends on Phase 1 (needs `args.tts` flag) and Phase 2 (needs model for listing)
- Phase 5 depends on Phase 3 (docs reflect working implementation)

### Parallel Opportunities
- T001, T002, T003 are independent within Phase 1
- T015, T016, T018 are independent within Phase 5

---

## Implementation Strategy (MVP)

1. Add `--tts` flag + platform check + `_QWEN_SPEAKER_MAP` (Phase 1)
2. Add QwenTTS model loading (Phase 2)
3. Add `speak_qwen()` + `play_qwen_tts()` + dispatch (Phase 3)
4. Add `qwen-tts` to pyproject.toml (T018)
5. Test: `uv run voice_loop.py --tts qwen --lang en`
6. Test: `uv run voice_loop.py` (regression, no `--tts`)
7. Voice resolution + listing (Phase 4)
8. Config + docs (Phase 5)
