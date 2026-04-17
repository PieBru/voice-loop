# Quickstart: VoxCPM TTS Backend

**Feature**: 007-voxcpm-tts

## Prerequisites

- CUDA GPU (≥8GB VRAM) or CPU with ≥12GB RAM
- `uv` package manager

## Install

```bash
uv add voxcpm
```

## Basic Usage

```bash
# English with default voice
uv run voice_loop.py --tts voxcpm

# Italian (native quality — VoxCPM's strength)
uv run voice_loop.py --tts voxcpm --lang it

# With voice cloning — add to config.yaml:
# tts:
#   voxcpm_ref_audio: /path/to/your/voice.wav  (5-30 seconds)

# With voice design — add to config.yaml:
# tts:
#   voxcpm_voice_desc: "warm elderly female voice"

# List capabilities
uv run voice_loop.py --list --tts voxcpm
```

## Verify

1. Run `uv run voice_loop.py --tts voxcpm --lang it`
2. Speak a turn
3. Confirm Italian audio output with natural prosody
