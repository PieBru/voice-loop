# Quickstart: OpenAI-Compatible TTS Endpoint Backend

**Feature**: 009-openai-tts | **Date**: 2026-04-18

## Prerequisites

1. A running OpenAI-compatible TTS server (e.g. [Qwen3-TTS-Openai-Fastapi](https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi))
2. voice_loop dependencies installed (`uv sync`)

## Start a TTS Server

Example with Qwen3-TTS-Openai-Fastapi:

```bash
git clone https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi
cd Qwen3-TTS-Openai-Fastapi
pip install -r requirements.txt
python app.py  # starts on http://localhost:8880
```

## Run voice_loop

```bash
# Default server at localhost:8880
uv run voice_loop.py --tts openai

# Custom server
uv run voice_loop.py --tts openai --tts-openai-endpoint http://myserver:9999

# With specific voice and language
uv run voice_loop.py --tts openai --voice Vivian --lang en
```

## Configuration

Add to `config.yaml`:

```yaml
tts:
  openai_endpoint: http://localhost:8880
  openai_model: qwen3-tts
  openai_voice: Chelsie
  openai_stream: false
  openai_sample_rate: 24000
  openai_timeout: 30
```

## Verify

1. Start the TTS server
2. Run `uv run voice_loop.py --tts openai`
3. Speak a sentence
4. Confirm the response is spoken back via the TTS server

## Troubleshooting

- **`[openai-tts error: Connection refused]`** — TTS server not running at configured URL
- **`[openai-tts error: HTTP 422: ...]`** — Voice name or model not recognized by server
- **`[openai-tts error: timed out]`** — Server too slow, increase `openai_timeout` in config
- **No audio but no error** — Server returned empty audio. Check server logs.

## No New Dependencies

This feature uses only stdlib (`urllib.request`, `json`) and already-available packages (`numpy`, `sounddevice`, `soundfile`). No `uv add` needed.
