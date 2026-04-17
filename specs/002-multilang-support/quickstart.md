# Quickstart: Multilanguage Voice Loop

## Italian (default test language)

```bash
uv run voice_loop.py --lang it
```

This automatically:
- Loads faster-whisper for Italian STT (Moonshine doesn't support Italian)
- Sets TTS voice to `if_sara` (Italian female)
- Instructs the LLM to respond in Italian

## Spanish (Moonshine-supported)

```bash
uv run voice_loop.py --lang es
```

This automatically:
- Loads Moonshine Spanish model for STT
- Sets TTS voice to `ef_dora` (Spanish female)
- Instructs the LLM to respond in Spanish

## Force a specific STT backend

```bash
# Always use Whisper, even for English
uv run voice_loop.py --lang en --stt whisper

# Always use Moonshine (error if language unsupported)
uv run voice_loop.py --lang es --stt moonshine
```

## Custom voice with a language

```bash
# Italian with male voice instead of default female
uv run voice_loop.py --lang it --voice im_nicola
```

## Available language codes

Built-in with full support (STT + TTS + LLM):
`en`, `es`, `ja`, `fr`, `it`, `pt`, `zh`, `de`

Any ISO 639-1 code works (99+ languages via faster-whisper for STT). Languages without a built-in TTS voice default to English TTS.

## Available Italian voices

| Voice | Gender |
|-------|--------|
| `if_sara` | Female (default) |
| `im_nicola` | Male |
