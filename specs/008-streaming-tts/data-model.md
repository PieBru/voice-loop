# Data Model: Streaming TTS Port

**Feature**: 008-streaming-tts | **Date**: 2026-04-17

## Entities

### Sentence Splitter (module-level)

| Field | Type | Description |
|---|---|---|
| `_SENT_END` | regex | `(?<=[.!?])\s+` — sentence boundary pattern |
| `_SENT_MIN_CHARS` | int | 20 — minimum fragment size before dispatch |

### Sentence Iterator (runtime generator)

| Field | Type | Description |
|---|---|---|
| `q` | `queue.Queue[str \| None]` | Thread-safe queue yielding sentences |
| `cancel` | `threading.Event` | Signals worker to stop (barge-in) |
| `token_buf` | string | Buffer for MLX token stream |
| `carry` | string | Accumulated short fragments |

### Synthesis Queue (asyncio, inside play_tts_stream)

| Field | Type | Description |
|---|---|---|
| `synth_q` | `asyncio.Queue(maxsize=1)` | Buffers one synthesized group |
| `GROUP` | int | 2 — sentences per synthesis call |
| `buf` | list[str] | Sentence accumulation buffer |

### Playback State (per play_tts_stream invocation)

| Field | Type | Description |
|---|---|---|
| `out_stream` | `sd.OutputStream` | Single stream kept alive across sentences |
| `interrupted` | bool | Set by barge-in or keypress |
| `tts_16k_buf` | list[np.ndarray] | 16kHz reference for AEC |
| `state` | dict | play_start, consec_speech, mic_pos |
| `first_sentence` | bool | Tracks inter-sentence gap handling |

## State Transitions

```
[LLM starts in background thread]
  → [tokens → sentence boundary regex → queue.Queue]
  → [main thread pulls sentences from queue]
  → [collecting() tees to print() + play_tts_stream()]
  → [play_tts_stream():
       _synthesizer() groups by 2, runs kokoro.create() in executor
       → synth_q.put(samples)
       → _play() loop pulls from synth_q, writes to OutputStream
       → between groups: pad_gap_and_check() for AEC barge-in
     ]
  → [None sentinel ends iteration]
  → [cleanup: cancel worker, close stream]
```

## Relationships

- `stream_sentences()` wraps LLM generation → feeds `play_tts_stream()`
- `_collecting()` wraps `stream_sentences()` → tees to `print()` and TTS
- `play_tts_stream()` replaces current async-for-chunk loop with asyncio Queue pipeline
- `pad_gap_and_check()` is called between sentence groups, not during playback
