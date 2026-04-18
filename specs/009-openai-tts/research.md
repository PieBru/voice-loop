# Research: OpenAI-Compatible TTS Endpoint Backend

**Feature**: 009-openai-tts | **Date**: 2026-04-18

## R1: WAV parsing — stdlib vs soundfile

**Decision**: Use `io.BytesIO` + `soundfile.read()` (already available as transitive dependency via qwen-cpp path).

**Rationale**: `soundfile` is already in the dependency tree (imported in qwen-cpp branch at line 1236). It provides `sf.read(BytesIO(data))` returning `(samples, sr)` — exactly what we need for WAV auto-detection. Using stdlib `wave` module would work for PCM WAV but not for MP3 fallback; `soundfile` handles more formats.

**Alternatives considered**:
- `wave` module (stdlib) — works for WAV only, doesn't handle MP3 fallback. Would need separate handling.
- `scipy.io.wavfile` — not in dependency tree, would be a new dep.
- Direct numpy from buffer — requires knowing sample rate upfront, defeats auto-detection purpose.

## R2: urllib.request streaming (chunked response)

**Decision**: Use `urllib.request.urlopen()` with `.read()` in a loop for chunked PCM streaming.

**Rationale**: `urllib.request.urlopen()` returns a file-like object. For chunked transfer encoding, calling `.read(chunk_size)` in a loop yields chunks as they arrive. No need for `httpx` or `requests`. The `Qwen3-TTS-Openai-Fastapi` server returns chunked PCM float32 data when `stream=true` and `response_format=pcm`.

**Alternatives considered**:
- `httpx` with streaming — requires new dependency. Rejected (FR-014).
- `requests` with `iter_content` — requires new dependency. Rejected (FR-014).
- `aiohttp` — async dependency, overkill for this simple use case.

**Implementation note**: PCM float32 chunks from the server are raw numpy-compatible data. Use `np.frombuffer(chunk, dtype=np.float32)` to convert each chunk. Concatenate all chunks per sentence into a single array, then `sd.play()`.

## R3: URL normalization strategy

**Decision**: Strip trailing slash, append `/v1/audio/speech`.

**Rationale**: Users may configure `http://localhost:8880` or `http://localhost:8880/` or even `http://localhost:8880/v1`. Normalize by stripping trailing `/`, then appending `/v1/audio/speech`. If the URL already ends with `/v1/audio/speech`, don't double-append.

**Implementation**:
```python
def _normalize_endpoint(url):
    url = url.rstrip("/")
    if not url.endswith("/v1/audio/speech"):
        if url.endswith("/v1"):
            url += "/audio/speech"
        else:
            url += "/v1/audio/speech"
    return url
```

## R4: Voice default and config precedence

**Decision**: CLI `--voice` > config.yaml `tts.openai_voice` > default "Chelsie".

**Rationale**: "Chelsie" is the first speaker in Qwen3-TTS-Openai-Fastapi's default list. Matches the pattern used by other backends: CLI flag takes precedence, then config, then hardcoded default.

**Alternatives considered**:
- No default voice — would require `--voice` to be mandatory, breaking UX.
- "alloy" (OpenAI API default) — less meaningful for Qwen3-TTS servers.

## R5: Streaming mode — integration with play_tts_stream

**Decision**: For `--tts openai`, use `speak_tts()` path (non-streaming, sentence-by-sentence) for initial implementation. Streaming via `play_tts_stream()` is P2 and can be added later.

**Rationale**: The current `play_tts_stream()` is tightly coupled to Kokoro's async synthesis pattern (asyncio Queue, GROUP=2 batching). Adapting it for HTTP streaming would require refactoring the async synth coroutine. The `speak_tts()` path already handles sentence-by-sentence synthesis (used by qwen-cpp and voxcpm) and is simpler. The `--tts-openai-stream` flag controls whether individual sentence HTTP requests use `stream=true` (sentence-level buffering), not whether the whole response uses the `play_tts_stream()` architecture.

**Implementation**: In `speak_tts()`, the openai branch splits text into sentences, sends one HTTP request per sentence (streaming or non-streaming depending on flag), plays each sentence audio, then continues to next. Same flow as voxcpm sentence loop.

## R6: Error handling pattern

**Decision**: Follow existing pattern — `try/except` around HTTP call, print `[openai-tts error: ...]` to stderr, continue without crashing.

**Rationale**: Consistent with qwen-cpp (line 1260-1265) and voxcpm (line 1294-1295) error handling. The main loop doesn't need to know about TTS failures.

## R7: HTTP timeout configuration

**Decision**: Default 30s, configurable via `config.yaml` → `tts.openai_timeout`. Pass as `timeout` param to `urllib.request.urlopen()`.

**Rationale**: 30s is generous for TTS synthesis of a single sentence. Long texts are split into sentences (FR-008), so each request should be short. Configurable for slow servers or very long sentences.

## R8: Non-streaming TTS integration with play_tts_stream

**Decision**: OpenAI TTS (both streaming and non-streaming) goes through `speak_tts()` path, NOT `play_tts_stream()`. In `process_utterance()`, the dispatch is: if `kokoro` → `play_tts_stream()`, else → `speak_tts()` after collecting all sentences. This matches existing pattern for qwen/qwen-cpp/voxcpm.

**Rationale**: `play_tts_stream()` is Kokoro-specific (async Kokoro synthesis in background). All other backends use `speak_tts()` because they don't support true streaming synthesis (they generate full audio then play). OpenAI streaming is sentence-level HTTP streaming, not word-level — it still fits the `speak_tts()` pattern better.

**Impact on process_utterance()**: The condition at line 1584 needs to include the openai case: `qwen_tts_model or _qwen_cpp_bin or voxcpm_model or args.tts == "openai"`.
