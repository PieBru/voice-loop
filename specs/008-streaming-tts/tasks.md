# Tasks: Streaming TTS Port

**Input**: `specs/008-streaming-tts/spec.md`, `specs/008-streaming-tts/plan.md`, `specs/008-streaming-tts/research.md`, `specs/008-streaming-tts/contracts/cli-schema.md`
**Prerequisites**: `008-streaming-tts` branch checked out
**Test strategy**: Manual — `uv run voice_loop.py` + speak a multi-sentence turn + verify audio starts before full generation
**Organization**: Sequential phases. Phase 1 is setup, Phase 2–5 are user stories in priority order.

**Format**: `[ID] [P?] [Story] Description`

---

## Phase 1: Sentence Splitting Foundation

**Purpose**: Add the sentence boundary detector and constants.

- [ ] T001 Add `_SENT_END` regex and `_SENT_MIN_CHARS` constant at module level in `voice_loop.py`: `_SENT_END = re.compile(r'(?<=[.!?])\s+')` and `_SENT_MIN_CHARS = 20`. Place near other regex constants.
- [ ] T002 Add `_GAP_BLANK_SAMPLES` constant: `int(0.15 * 16000)` (150ms at 16kHz). Place near audio constants.
- [ ] T003 Add `_split_sentences(text: str) -> list[str]` function at module level in `voice_loop.py`: iterate `_SENT_END.split()`, accumulate fragments under `_SENT_MIN_CHARS` chars into next sentence, return list. Port directly from upstream.

**Checkpoint**: Call `_split_sentences("Hello world. This is a test. Short.")` returns correct list. Fragments under 20 chars merge forward.

---

## Phase 2: Stream Sentences Generator (US1, US2)

**Purpose**: Add the background-thread LLM-to-sentence generator.

- [ ] T004 [US1] Add `stream_sentences(messages, max_tokens=200, temperature=0.7)` function inside `main()` in `voice_loop.py`: creates `queue.Queue`, spawns daemon thread running `_worker()`, yields sentences from queue. On None sentinel, returns. On generator abandonment (barge-in), sets `cancel` event.
- [ ] T005 [US1] Inside `stream_sentences._worker()`: implement macOS MLX path — accumulate tokens in `token_buf`, apply `_SENT_END` regex incrementally, dispatch sentences ≥ `_SENT_MIN_CHARS` to queue. Flush remainder at end. Port from upstream.
- [ ] T006 [US1] Inside `stream_sentences._worker()`: implement Linux fallback path — call `llm_generate(messages, max_tokens, temperature)`, split result with `_split_sentences()`, put each sentence in queue. This is the non-streaming path.
- [ ] T007 [US2] Add `_collecting(gen)` wrapper function inside `main()`: wraps a sentence generator, calls `print(f"> {s}", flush=True)` for each sentence and yields it. This is the tee that provides incremental printing. Port from upstream's `_collecting()`.

**Checkpoint**: `stream_sentences()` yields sentences one at a time. `_collecting()` prints each and passes through.

---

## Phase 3: Streaming Kokoro Playback (US1, US3)

**Purpose**: Rewrite `play_tts_stream()` to use the asyncio Queue architecture with sentence groups.

- [ ] T008 [US1] Rewrite `play_tts_stream(sentence_source)` signature in `voice_loop.py`: accept `str | Iterator[str]`. If str, wrap with `iter(_split_sentences(source) or [source])`. If iterator, use directly.
- [ ] T009 [US1] Inside the rewritten `play_tts_stream()`, add `async def _play()` with `synth_q: asyncio.Queue(maxsize=1)`. Create inner `async def _synthesizer()` coroutine: groups sentences by GROUP=2, calls `kokoro.create()` via `loop.run_in_executor(None, lambda: kokoro.create(text, voice, speed, lang))`, puts `(samples, sr)` into `synth_q`, sends None sentinel at end. Port from upstream.
- [ ] T010 [US1] Inside `_play()`, add playback loop: pulls from `synth_q`, creates single `sd.OutputStream` on first item (kept alive across all sentences), writes audio in 4096-sample chunks, checks for keypress and `check_barge_in()` on each chunk. Port from upstream.
- [ ] T011 [US3] Add `pad_gap_and_check()` inner function inside `play_tts_stream()`: drains `audio_q`, blanks AEC reference for first `_GAP_BLANK_SAMPLES` samples (reverb tail), then resumes normal AEC with zero reference. Returns True if barge-in detected (5 consecutive speech frames). Port from upstream.
- [ ] T012 [US3] In playback loop, call `pad_gap_and_check()` between sentence groups (not on first sentence). Reset VAD states at each sentence boundary. Port from upstream.
- [ ] T013 [US1] Handle cancellation in `_play()` finally block: cancel `synth_task`, await with `CancelledError` suppression, stop/close `out_stream`. Call `drain_audio_q()` and `vad.reset_states()` after `asyncio.run(_play())` returns.

**Checkpoint**: `uv run voice_loop.py` with Kokoro default: speak a multi-sentence question, first audio starts within 2s, no gaps between sentences.

---

## Phase 4: process_utterance Refactor (US1, US2, US4)

**Purpose**: Replace the response generation flow with `stream_sentences()` + `_collecting()`.

- [ ] T014 [US1] Refactor `process_utterance()` in `voice_loop.py`: replace the `response = llm_generate(messages)` + `print(f"\n> {response}\n")` flow with `stream_sentences(messages)` + `_collecting()` wrapper. Collect response parts into a list for memory/history.
- [ ] T015 [US1] Wire `play_tts_stream()` call in the refactored `process_utterance()`: pass the collecting generator (not a string) to `play_tts_stream()`. The TTS pipeline consumes sentences as the LLM generates them.
- [ ] T016 [US4] Handle non-Kokoro backends in `process_utterance()`: when `kokoro` is None but `qwen_tts_model` or `_qwen_cpp_bin` or `voxcpm_model` is available, still use `stream_sentences()` + `_collecting()` for incremental printing, but collect full response before calling `speak_tts(full_response)`.
- [ ] T017 [US4] Handle `--no-tts` in `process_utterance()`: still use `stream_sentences()` + `_collecting()` for incremental printing even when TTS is disabled.
- [ ] T018 [US1] Handle greeting: keep `speak_tts(greeting)` for the greeting (single sentence, no streaming needed). No change to greeting flow.

**Checkpoint**: Multi-sentence responses print incrementally. Kokoro streams. Non-Kokoro backends print incrementally but synthesize after full response. `--no-tts` prints incrementally.

---

## Phase 5: Polish & Edge Cases

**Purpose**: Handle edge cases and verify regression.

- [ ] T019 Handle single-sentence responses: verify `_split_sentences()` returns single-element list, `play_tts_stream()` plays it correctly (no grouping issues). Test with a question that elicits a one-word answer.
- [ ] T020 Handle LLM errors: verify `stream_sentences._worker()` catches exceptions, prints `[LLM error: ...]` to stderr, sends None sentinel so TTS pipeline doesn't hang.
- [ ] T021 Verify `--no-aec` path: when AEC is disabled, `pad_gap_and_check()` should be a no-op. Keypress interrupt still works.
- [ ] T022 Verify regression: `uv run voice_loop.py --no-tts` prints sentences incrementally. `uv run voice_loop.py --tts qwen` prints incrementally + plays after synthesis. `uv run voice_loop.py` (Kokoro) streams correctly.

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 2 depends on Phase 1 (needs `_split_sentences`, constants)
- Phase 3 depends on Phase 1 (needs constants) and Phase 2 (needs `stream_sentences`)
- Phase 4 depends on Phase 3 (needs rewritten `play_tts_stream`)
- Phase 5 depends on Phase 4 (tests full flow)

### Parallel Opportunities
- T001, T002, T003 are independent within Phase 1
- T004–T007 are sequential (worker implementation builds up)
- T019–T022 can run in parallel within Phase 5

### Implementation Strategy (MVP)

1. Add sentence splitting constants + function (Phase 1)
2. Add `stream_sentences()` + `_collecting()` (Phase 2)
3. Rewrite `play_tts_stream()` with asyncio Queue (Phase 3)
4. Refactor `process_utterance()` to use streaming (Phase 4)
5. Test: speak a multi-sentence turn, verify streaming works
6. Test regression: `--no-tts`, `--tts qwen`, `--tts qwen-cpp`
7. Edge cases (Phase 5)

---

## Summary

| Metric | Value |
|---|---|
| Total tasks | 22 |
| Phase 1 (Setup) | 3 tasks |
| Phase 2 (US1, US2) | 4 tasks |
| Phase 3 (US1, US3) | 6 tasks |
| Phase 4 (US1, US2, US4) | 5 tasks |
| Phase 5 (Polish) | 4 tasks |
| Parallel opportunities | 6 task pairs |
| MVP scope | Phases 1–4 (US1 + US2) |
