# Research: Streaming TTS Port

**Feature**: 008-streaming-tts | **Date**: 2026-04-17

## Decision 1: Architecture — asyncio Queue vs simpler threading approach

**Chosen**: asyncio Queue (matching upstream).
**Rationale**: The upstream uses `asyncio.Queue(maxsize=1)` with `_synthesizer()` and `_play()` coroutines inside `play_tts_stream()`. This is already battle-tested. The `maxsize=1` ensures exactly one pre-synthesized group is buffered, preventing memory bloat while maintaining gapless playback.
**Alternatives considered**: Simple threading with `queue.Queue` — rejected because asyncio provides cleaner cancellation via `task.cancel()` and integrates with the existing `asyncio.run()` pattern already in our `play_tts_stream()`.

## Decision 2: Kokoro API — create() vs create_stream()

**Chosen**: `kokoro.create()` (non-streaming) per sentence group.
**Rationale**: The upstream switched from `create_stream()` to `create()` with GROUP=2 because synthesizing sentence pairs gives better prosody across sentence boundaries. The per-group synthesis runs in a thread executor so it doesn't block playback.
**Alternatives considered**: Keep `create_stream()` — rejected because upstream explicitly found that grouped synthesis produces better quality.

## Decision 3: Sentence boundary detection

**Chosen**: Regex `(?<=[.!?])\s+` with 20-char minimum fragment size.
**Rationale**: Matches upstream. The 20-char minimum prevents tiny fragments like "Mr." from being dispatched as standalone sentences. Accumulated fragments merge into the next sentence.
**Alternatives considered**: NLP-based sentence splitter (nltk, spacy) — rejected, adds dependencies for marginal improvement.

## Decision 4: Linux LLM streaming

**Chosen**: Full generation then split (fallback path).
**Rationale**: The llama.cpp OpenAI-compatible server at `localhost:8088/v1` does support streaming (`stream: true` in the API), but our `llm_generate()` function currently waits for the full response. The upstream's macOS MLX path has `_mlx_stream_generate` for token-by-token streaming. For Linux, we use the same fallback as upstream: generate full response, then split into sentences. Incremental printing still works.
**Alternatives considered**: Add streaming API support for llama.cpp server — deferred, adds complexity and this spec focuses on TTS streaming, not LLM streaming.

## Decision 5: Inter-sentence gap handling

**Chosen**: 150ms reverb blanking (`_GAP_BLANK_SAMPLES`).
**Rationale**: After a sentence ends, speaker reverb tails can cause false AEC speech detection. Blanking the reference signal for 150ms lets the reverb decay, then AEC resumes with zero reference. This is upstream-proven.
**Alternatives considered**: No blanking — rejected, causes false barge-in triggers between sentences.

## Decision 6: process_utterance refactor scope

**Chosen**: Replace the entire response generation + TTS playback flow in `process_utterance()`.
**Rationale**: The current flow is: generate full response → print → play TTS. The new flow is: `stream_sentences()` → `_collecting()` (prints each sentence) → `play_tts_stream()` (streams sentence groups). This requires restructuring the response generation path, not just the TTS playback path.
**Alternatives considered**: Minimal change (only modify `play_tts_stream()`) — rejected because the sentence-by-sentence architecture requires the LLM to yield sentences incrementally, which means `process_utterance()` must use `stream_sentences()` instead of `llm_generate()`.

## Decision 7: Non-Kokoro backend handling

**Chosen**: Sentence splitting + incremental printing, but full synthesis before playback.
**Rationale**: Non-Kokoro backends (qwen, qwen-cpp, voxcpm) don't benefit from the asyncio synthesis queue because they can't overlap synthesis and playback. However, they still get the UX benefit of incremental sentence printing via `_collecting()`. The implementation: collect all sentences first, then call `speak_tts(full_response)`.
**Alternatives considered**: Synthesize per-sentence for all backends — rejected because it adds complexity for minimal gain (non-streaming backends would have long gaps between sentences anyway).
