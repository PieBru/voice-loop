# CLI Contract: voice_loop.py

## Invocation

```text
uv run voice_loop.py [OPTIONS]
```

## Options (unchanged from macOS version)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tts` / `--no-tts` | bool | `on` | Kokoro TTS output |
| `--smart-turn` / `--no-smart-turn` | bool | `on` | Smart Turn v3 endpoint detection |
| `--aec` / `--no-aec` | bool | `on` | WebRTC AEC3 voice interrupt |
| `--chime` / `--no-chime` | bool | `on` | Chime + ticks while generating |
| `--memory` | flag | off | Read/write MEMORY.md |
| `--audio-mode` | flag | off | Send audio to LLM (experimental) |
| `--model` | str | `gemma-4-e4b` | Model alias or HuggingFace repo ID |
| `--silence-ms` | int | `700` | Silence duration before turn cutoff |
| `--record` | optional str | off | Record mic to WAV for debugging |
| `--voice` | str | `af_heart` | Kokoro voice name |

## Model Alias Resolution

When `--model` receives a value:

1. Look up value in the alias map.
2. If found: resolve to platform-specific `(repo, filename?)`.
3. If not found: treat as a raw HuggingFace repo ID, pass through.
4. If the resolved model is incompatible with the current platform
   (e.g., MLX model on Linux): print error and exit.

**Known aliases** (initial set):

| Alias | macOS Repo | Linux Repo |
|-------|-----------|------------|
| `gemma-4-e4b` | `mlx-community/gemma-4-E4B-it-4bit` | `ggml-org/gemma-4-E4B-it-GGUF` (`*Q4_K_M*`) |
| `gemma-4-e2b` | `mlx-community/gemma-4-E2B-it-4bit` | `ggml-org/gemma-4-E2B-it-GGUF` (`*Q4_K_M*`) |

## Exit Codes

| Code | Condition |
|------|-----------|
| 0 | Normal exit (Ctrl+C) |
| 1 | Missing system dependency or GPU (Linux), or missing LLM backend |
| 1 | Incompatible model for current platform |

## Error Messages (Linux-specific)

| Condition | Message Format |
|-----------|---------------|
| Missing PortAudio | `Error: PortAudio not found. Install with: pacman -S portaudio` |
| Missing espeak-ng | `Error: espeak-ng not found. Install with: pacman -S espeak-ng` |
| No CUDA GPU | `Error: No CUDA-capable GPU detected. Voice Loop on Linux requires an NVIDIA GPU with CUDA support (VRAM >= 4 GB).` |
| llama-cpp-python missing | `Error: llama-cpp-python not installed. Run: uv sync` |
| Incompatible model | `Error: Model '{model}' is not available on {platform}. Use a different model or alias.` |
