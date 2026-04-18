# CLI Schema: OpenAI-Compatible TTS Endpoint Backend

**Feature**: 009-openai-tts | **Date**: 2026-04-18

## New CLI Flags

### `--tts openai`

Selects the OpenAI-compatible HTTP TTS backend.

```
--tts {kokoro,qwen,qwen-cpp,voxcpm,openai}
    TTS backend (default: kokoro)
```

**Behavior**: When `openai` is selected, TTS requests are sent to the configured HTTP endpoint instead of loading an in-process model.

### `--tts-openai-endpoint URL`

Sets the TTS server base URL.

```
--tts-openai-endpoint URL
    OpenAI-compatible TTS server URL (default: http://localhost:8880)
    Config fallback: tts.openai_endpoint in config.yaml
```

**Normalization**: Trailing slash stripped, `/v1/audio/speech` appended automatically.

### `--tts-openai-model NAME`

Sets the model name sent in TTS requests.

```
--tts-openai-model NAME
    Model name for the TTS server (default: qwen3-tts)
    Config fallback: tts.openai_model in config.yaml
```

### `--tts-openai-stream`

Enables streaming PCM mode.

```
--tts-openai-stream
    Enable streaming PCM audio from the TTS server (default: off)
    Config fallback: tts.openai_stream in config.yaml
```

When enabled, requests use `stream=true` and `response_format=pcm`. Audio is collected per sentence then played.

### `--tts-openai-sr RATE`

Sets the sample rate for streaming PCM mode.

```
--tts-openai-sr RATE
    Sample rate for streaming PCM audio (default: 24000)
    Config fallback: tts.openai_sample_rate in config.yaml
```

**Note**: Only used when `--tts-openai-stream` is enabled. Non-streaming mode auto-detects sample rate from WAV header.

## Modified Existing Flags

### `--tts` choices

Before: `{kokoro,qwen,qwen-cpp,voxcpm}`
After: `{kokoro,qwen,qwen-cpp,voxcpm,openai}`

### `--voice`

No change to flag definition. When `--tts openai`, `--voice` value is sent as the `voice` parameter in HTTP requests. Default "Chelsie" (from config or hardcoded).

### `--list --tts openai`

Shows OpenAI TTS configuration: endpoint URL, model, default voice, streaming mode, sample rate, config.yaml keys.

## Config YAML Keys

All under `tts:` section:

| Key | Type | Default | CLI Override |
|-----|------|---------|-------------|
| `openai_endpoint` | string | `http://localhost:8880` | `--tts-openai-endpoint` |
| `openai_model` | string | `qwen3-tts` | `--tts-openai-model` |
| `openai_voice` | string | `Chelsie` | `--voice` |
| `openai_stream` | bool | `false` | `--tts-openai-stream` |
| `openai_sample_rate` | int | `24000` | `--tts-openai-sr` |
| `openai_timeout` | int | `30` | (config only) |

## Exit Conditions

| Condition | Exit Code | Message |
|-----------|-----------|---------|
| Server unreachable at synthesis time | 0 (continue) | `[openai-tts error: ...]` to stderr |
| Server returns non-200 | 0 (continue) | `[openai-tts error: HTTP 404: ...]` to stderr |
| `--list --tts openai` | 0 | Print config info, exit |
| Normal operation | 0 | Audio plays, loop continues |

## Usage Examples

```bash
# Basic usage with default server
uv run voice_loop.py --tts openai

# Custom server and voice
uv run voice_loop.py --tts openai --tts-openai-endpoint http://192.168.1.50:8880 --voice Vivian

# Streaming mode with custom sample rate
uv run voice_loop.py --tts openai --tts-openai-stream --tts-openai-sr 22050

# Italian with OpenAI TTS
uv run voice_loop.py --tts openai --lang it --voice Serena

# List config
uv run voice_loop.py --list --tts openai
```
