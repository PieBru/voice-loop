# CLI Schema Changes: Streaming TTS

**Feature**: 008-streaming-tts | **Date**: 2026-04-17

## No new CLI flags

This feature modifies internal behavior only. No new flags are added.

## Behavioral changes to existing flags

| Flag | Before | After |
|---|---|---|
| *(default)* | Full response generated, printed, then TTS streams via `kokoro.create_stream()` | Sentences generated incrementally, printed one-by-one, Kokoro synthesizes pairs in background |
| `--no-tts` | Full response printed at once | Sentences printed incrementally (splitting still active) |
| `--tts qwen` | Full synthesis then play, printed at once | Sentences printed incrementally, full synthesis then play |
| `--tts qwen-cpp` | Same as qwen | Same as qwen |

## Internal function signature changes

### `play_tts_stream(source)` — modified

Before: `source: str` → splits to Kokoro async generator stream
After: `source: str | Iterator[str]` → if iterator, pulls sentences directly; if str, splits then iterates

### `process_utterance()` — modified

Before: `response = llm_generate(messages)` → `print(response)` → `play_tts_stream(response)`
After: `stream_sentences(messages)` → `_collecting()` tee → `play_tts_stream(sentence_iter)`

### New functions

| Function | Signature | Purpose |
|---|---|---|
| `_split_sentences(text)` | `str → list[str]` | Regex sentence splitter with 20-char minimum |
| `stream_sentences(messages, ...)` | `→ Generator[str]` | Background-thread LLM yielding sentences |
| `_collecting(gen)` | `Generator → Generator` | Tees sentences to print() and downstream |
| `pad_gap_and_check()` | `→ bool` | Inter-sentence AEC gap handler |
