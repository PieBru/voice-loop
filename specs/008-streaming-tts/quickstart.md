# Quickstart: Streaming TTS Port

**Feature**: 008-streaming-tts

## Prerequisites

- Existing voice_loop.py setup (no new dependencies)

## Verify Streaming Works

1. Run `uv run voice_loop.py` (Kokoro default)
2. Speak a question that elicits a multi-sentence response
3. Observe: first sentence prints and audio starts before full response is generated
4. Confirm: no audible gaps between sentences

## Verify Incremental Printing

1. Run `uv run voice_loop.py --no-tts`
2. Speak a turn
3. Confirm: sentences appear one at a time (not all at once after generation)

## Verify Non-Kokoro Backends

```bash
uv run voice_loop.py --tts qwen-cpp
# Sentences print incrementally, audio plays after full synthesis
```

## Verify Barge-In

1. Run with AEC enabled (default)
2. Let TTS play 2+ sentences
3. Speak during the gap between sentences — should interrupt
