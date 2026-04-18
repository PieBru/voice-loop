# Data Model: OpenAI-Compatible TTS Endpoint Backend

**Feature**: 009-openai-tts | **Date**: 2026-04-18

## Entities

### OpenAITTSConfig

Runtime configuration for the OpenAI TTS backend. Loaded from CLI flags + config.yaml.

| Field | Type | Default | Source | Validation |
|-------|------|---------|--------|------------|
| `endpoint` | `str` | `"http://localhost:8880"` | CLI `--tts-openai-endpoint` > config `tts.openai_endpoint` | Must be valid HTTP(S) URL. Normalized to end with `/v1/audio/speech`. |
| `model` | `str` | `"qwen3-tts"` | CLI `--tts-openai-model` > config `tts.openai_model` | Non-empty string |
| `voice` | `str` | `"Chelsie"` | CLI `--voice` > config `tts.openai_voice` > hardcoded default | Non-empty string. Server may reject unknown voices. |
| `stream` | `bool` | `False` | CLI `--tts-openai-stream` > config `tts.openai_stream` | Boolean |
| `sample_rate` | `int` | `24000` | CLI `--tts-openai-sr` > config `tts.openai_sample_rate` | Positive integer. Only used for streaming PCM mode. |
| `timeout` | `int` | `30` | config `tts.openai_timeout` | Positive integer (seconds) |

**Precedence**: CLI flag > config.yaml value > hardcoded default.

### HTTPRequest

The HTTP request sent to the TTS server for each sentence.

| Field | Type | Description |
|-------|------|-------------|
| `method` | `str` | Always `"POST"` |
| `url` | `str` | Normalized endpoint URL |
| `headers` | `dict` | `{"Content-Type": "application/json"}` |
| `body.model` | `str` | From `OpenAITTSConfig.model` |
| `body.voice` | `str` | From `OpenAITTSConfig.voice` |
| `body.input` | `str` | Text to synthesize (one sentence) |
| `body.response_format` | `str` | `"wav"` (non-streaming) or `"pcm"` (streaming) |
| `body.speed` | `float` | `1.0` (fixed — not user-configurable for now) |
| `body.stream` | `bool` | `True` only if streaming mode enabled |

### AudioResponse

Audio data received from the server, converted to playable numpy array.

| Mode | Raw Format | Conversion | Sample Rate |
|------|-----------|------------|-------------|
| Non-streaming (WAV) | Binary WAV | `soundfile.read(BytesIO(data))` | Auto-detected from WAV header |
| Streaming (PCM) | Chunked float32 bytes | `np.frombuffer(chunk, dtype=np.float32)`, concatenate | From `OpenAITTSConfig.sample_rate` |

## State Transitions

```
[Config Loaded] → [speak_tts() called]
                       │
                       ├─ Split text into sentences
                       │
                       └─ For each sentence:
                            │
                            ├─ Build HTTPRequest
                            ├─ Send POST to endpoint
                            │    │
                            │    ├─ 200 OK → Parse audio → sd.play() → sd.wait()
                            │    │
                            │    └─ Error / Timeout → print error, skip sentence
                            │
                            └─ Continue to next sentence (or stop if error)
```

No persistent state. Each `speak_tts()` call is independent.

## Relationships

- `OpenAITTSConfig` is owned by the main voice_loop function (local variable `_openai_cfg`)
- `HTTPRequest` is created transiently inside `speak_tts()` for each sentence
- `AudioResponse` is created transiently, played, then discarded

## Config YAML Schema Addition

```yaml
tts:
  # ... existing keys ...
  openai_endpoint: http://localhost:8880    # TTS server base URL
  openai_model: qwen3-tts                   # Model name sent to server
  openai_voice: Chelsie                     # Default voice (override with --voice)
  openai_stream: false                      # Enable streaming PCM mode
  openai_sample_rate: 24000                 # Sample rate for streaming PCM
  openai_timeout: 30                        # HTTP timeout in seconds
```
