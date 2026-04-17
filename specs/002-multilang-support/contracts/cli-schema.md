# CLI Contract: voice_loop.py — Multilanguage Flags

## New Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--lang` | str | `en` | Language code (ISO 639-1) for STT, LLM, and TTS. Built-in: `en`, `es`, `ja`, `fr`, `it`, `pt`, `zh`, `de`. Any Whisper-supported code works (99+). |
| `--stt` | str | auto | STT backend: `whisper` (faster-whisper), `moonshine`. If not set, auto-selects: Moonshine for supported languages, faster-whisper otherwise. |

## Existing Flags (behavior changes)

| Flag | Change |
|------|--------|
| `--voice` | When `--lang` is set and `--voice` is NOT set, voice defaults to the language's mapped voice instead of `af_heart`. Explicit `--voice` always overrides. |

## Auto-Selection Logic

```
MOONSHINE_LANGS = {en, ar, es, ja, ko, vi, uk, zh}

if --stt is set:
    use the specified backend (error if language unsupported)
else:
    if --lang in MOONSHINE_LANGS:
        use Moonshine
    else:
        use faster-whisper
```

## Startup Banner (enhanced)

```
Loading Silero VAD...
Loading Moonshine (transcription)...          # or "Loading Whisper base (transcription)..."
Loading gemma-4-e4b...
Loading Kokoro TTS...
  AEC: WebRTC AEC3 (LiveKit APM)

Listening (lang: it, stt: whisper, tts: if_sara, mode: text, ...)
```

## Error Messages

| Condition | Message |
|-----------|---------|
| `--stt moonshine --lang it` | `Error: Moonshine does not support language 'it'. Supported: en, ar, es, ja, ko, vi, uk, zh. Use --stt whisper for Italian.` |
| `--lang xx` (unknown code) | `Warning: Language 'xx' not in built-in map. Using whisper STT with English TTS voice. Add a custom entry to config.yaml for better support.` |

## Exit Codes

| Code | Condition |
|------|-----------|
| 1 | STT backend does not support selected language (when explicitly set via `--stt`) |
