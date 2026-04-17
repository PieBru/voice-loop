# Feature Specification: Streaming TTS Port

**Feature Branch**: `008-streaming-tts`
**Created**: 2026-04-17
**Status**: Draft
**Input**: Port upstream's streaming TTS into our voice_loop.py — the sentence-by-sentence background synthesis didn't auto-merge since our TTS section diverged

## User Scenarios & Testing

### User Story 1 - Gapless sentence-by-sentence TTS (Priority: P1)

As a user, I want TTS to start speaking the first sentence while the LLM is still generating the rest, so I hear the response sooner instead of waiting for the entire response to complete before any audio plays.

**Why this priority**: This is the core latency improvement. Currently, the full LLM response is generated first, then TTS synthesis begins. The upstream architecture overlaps LLM generation with TTS synthesis for near-zero delay between thinking and speaking.

**Independent Test**: Run `uv run voice_loop.py`, speak a turn that produces a multi-sentence response. The first sentence should begin speaking before the last sentence is generated.

**Acceptance Scenarios**:

1. **Given** a multi-sentence LLM response, **When** Kokoro TTS is active, **Then** audio begins playing after the first 1-2 sentences are synthesized, while subsequent sentences are still being generated.
2. **Given** a single-sentence response, **When** TTS plays, **Then** behavior is identical to today (full synthesis then playback).
3. **Given** `--no-tts`, **When** a response is generated, **Then** text prints normally with no TTS (regression).

### User Story 2 - Printed sentences during playback (Priority: P1)

As a user, I want each sentence printed to the terminal as it is generated (not all at once after full generation), so I can read along while the voice speaks.

**Why this priority**: The upstream's `_collecting()` pattern tees each sentence to both `print()` and TTS playback simultaneously. This is a UX improvement tied to the streaming architecture.

**Independent Test**: Run voice_loop, speak a turn, observe that `> ` prefixed sentences appear one at a time during TTS playback, not all at once.

**Acceptance Scenarios**:

1. **Given** a multi-sentence response, **When** streaming is active, **Then** each sentence is printed immediately as the LLM generates it.
2. **Given** `--no-tts`, **When** streaming is active, **Then** sentences still print incrementally.

### User Story 3 - Voice interrupt between sentences (Priority: P2)

As a user, I want the inter-sentence gap to be used for reliable voice interrupt detection, so I can interrupt the agent between sentences with less false-positive risk.

**Why this priority**: The upstream's `pad_gap_and_check()` uses a 150ms reverb-blanking window between sentences for cleaner AEC. This is a refinement over the current continuous AEC approach.

**Independent Test**: Run with AEC enabled, let TTS play 2+ sentences, speak during the gap between sentences — interrupt should trigger.

**Acceptance Scenarios**:

1. **Given** AEC is enabled and TTS is playing multi-sentence response, **When** user speaks during an inter-sentence gap, **Then** the agent interrupts within 1 second.
2. **Given** AEC is enabled, **When** TTS is mid-sentence, **Then** barge-in still works as before (regression).

### User Story 4 - Streaming works with all TTS backends (Priority: P2)

As a user, I want the sentence-by-sentence streaming to work not just with Kokoro but also with the non-streaming backends (QwenTTS, qwen-cpp), so I get incremental printing even when audio can't be streamed.

**Why this priority**: Consistency — even if a backend can't synthesize incrementally, the sentence splitting and incremental printing still benefit the user.

**Independent Test**: Run `--tts qwen-cpp`, speak a turn, confirm sentences print incrementally even though audio plays after full synthesis.

**Acceptance Scenarios**:

1. **Given** `--tts kokoro`, **When** streaming is active, **Then** audio streams sentence-by-sentence with overlapping synthesis.
2. **Given** `--tts qwen` or `--tts qwen-cpp`, **When** streaming is active, **Then** sentences print incrementally but audio plays after full response synthesis.

### Edge Cases

- Very short responses (1 sentence) should degrade gracefully to current behavior.
- LLM errors mid-generation should not leave TTS in a broken state — the worker thread's `finally` block sends a None sentinel.
- Barge-in during synthesis should cancel the background synthesizer coroutine.
- The macOS MLX path supports true token-by-token streaming; the Linux llama.cpp path generates the full response first then splits into sentences. Both paths must work.
- Thread safety: the synthesis queue must handle cancellation correctly when the user interrupts.
- Sentence fragments under 20 characters are accumulated into the next sentence to avoid weak TTS on tiny inputs.
- The inter-sentence gap blanking (150ms) must not interfere with AEC state for the next sentence.

## Clarifications

### 2026-04-17 Session

- **Q: Port only Kokoro streaming or all backends?** A: Port the sentence-by-sentence architecture for all backends. Kokoro gets true overlapping synthesis. Other backends get incremental printing but play after full synthesis.
- **Q: Sentence grouping size?** A: Use GROUP=2 like upstream (pairs of sentences synthesized together for better Kokoro prosody). Single sentences at the end are synthesized alone.
- **Q: Linux LLM streaming?** A: Linux (llama.cpp server) does not support token-by-token streaming. Use the fallback path: full generation, then sentence splitting. Only macOS MLX gets true incremental sentence dispatch.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST split LLM output into sentences using a regex-based sentence boundary detector with a minimum fragment size of 20 characters.
- **FR-002**: The system MUST run LLM generation in a background thread (macOS MLX) or as a full-generation-then-split step (Linux), yielding sentences one at a time to the TTS pipeline.
- **FR-003**: When Kokoro TTS is active, the system MUST synthesize sentences in pairs (GROUP=2) in a background thread while the previous pair plays, using an asyncio.Queue with maxsize=1 for pre-buffering.
- **FR-004**: Each sentence MUST be printed to the terminal as it is yielded, not after full generation completes.
- **FR-005**: The system MUST maintain a single sd.OutputStream across all sentences (not open/close per sentence) for gapless playback.
- **FR-006**: Between sentences, the system MUST apply a 150ms reverb-blanking window where AEC reference is silenced before resuming normal barge-in detection.
- **FR-007**: The system MUST reset VAD state at each sentence boundary to avoid carry-over from the previous sentence's audio.
- **FR-008**: When interrupted (barge-in or keypress), the system MUST cancel the background synthesizer coroutine and stop the output stream immediately.
- **FR-009**: For non-Kokoro TTS backends (qwen, qwen-cpp), the system MUST still use sentence splitting for incremental printing but synthesize the full response before playback.
- **FR-010**: The `process_utterance()` function MUST use a collecting wrapper that tees sentences to both `print()` and the TTS playback pipeline.
- **FR-011**: The current non-streaming `play_tts_stream()` behavior MUST be preserved as fallback when sentence streaming is unavailable.

### Key Entities

- **Sentence Iterator**: A generator that yields complete sentences from the LLM output, either incrementally (macOS MLX) or after full generation (Linux).
- **Synthesis Queue**: An asyncio.Queue(maxsize=1) that buffers one pre-synthesized sentence group while the current group plays.
- **Sentence Group**: A pair of consecutive sentences synthesized together by Kokoro for better prosody (GROUP=2).
- **Gap Handler**: Inter-sentence logic that blanks AEC reference for 150ms (reverb tail) then resumes normal barge-in detection.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For a 5-sentence response with Kokoro TTS, audio begins playing within 2 seconds of LLM starting generation (vs. waiting for full generation today).
- **SC-002**: Each sentence is printed to terminal within 500ms of the LLM generating it.
- **SC-003**: No audible gap between consecutive sentences during Kokoro TTS playback.
- **SC-004**: Voice interrupt (AEC barge-in) works both mid-sentence and between sentences.
- **SC-005**: `--tts qwen` and `--tts qwen-cpp` show incremental sentence printing even though audio plays after full synthesis.
- **SC-006**: `uv run voice_loop.py --no-tts` works identically to before (regression).
- **SC-007**: `uv run voice_loop.py` with Kokoro default produces correct audio with no regression in quality.

## Assumptions

- Kokoro's `create()` method (non-streaming, synchronous) is used for sentence-group synthesis instead of `create_stream()`. This gives better prosody across sentence boundaries.
- The sentence boundary regex `(?<=[.!?])\s+` is sufficient for English and most languages. Languages without explicit sentence-ending punctuation may not split correctly — this is an acceptable limitation.
- The macOS MLX streaming path uses the existing `_mlx_stream_generate` or equivalent token-by-token generator.
- The Linux llama.cpp server does not support streaming completions — the fallback generates the full response then splits into sentences.
- Background thread safety is ensured by the queue-based architecture — no shared mutable state between the LLM thread and the synthesis coroutine.
