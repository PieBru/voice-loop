# Quickstart: Voice Loop on Arch Linux

## Prerequisites

- Arch Linux with an NVIDIA GPU (VRAM ≥ 4 GB)
- NVIDIA driver installed (`pacman -S nvidia`)
- CUDA toolkit: `pacman -S cuda`
- System audio libraries: `pacman -S portaudio espeak-ng`
- Python manager: `pacman -S uv` or install via [astral.sh](https://docs.astral.sh/uv/)

## Setup

```bash
git clone https://github.com/PieBru/voice-loop.git
cd voice-loop
uv sync
```

On first run, the LLM model (~3 GB GGUF) downloads automatically.

## Run

```bash
uv run voice_loop.py
```

Speak into your microphone. The agent transcribes, responds, and speaks
back. Press any key during TTS to interrupt, or speak over the agent.

## Common Options

```bash
uv run voice_loop.py --memory          # Enable persistent memory
uv run voice_loop.py --no-tts          # Text output only
uv run voice_loop.py --no-aec          # Keypress interrupt only
uv run voice_loop.py --voice bf_emma   # Different TTS voice
uv run voice_loop.py --record          # Debug: record mic to WAV
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Error: PortAudio not found` | `pacman -S portaudio` |
| `Error: espeak-ng not found` | `pacman -S espeak-ng` |
| `Error: No CUDA-capable GPU detected` | Install NVIDIA driver + CUDA toolkit |
| `Error: llama-cpp-python not installed` | Run `uv sync` to install Python deps |
| Models not downloading | Check internet connection for first run |

## Platform Differences

Voice Loop auto-detects your platform at startup:

- **macOS**: Uses MLX/Metal for LLM inference (Apple Silicon).
- **Linux**: Uses llama.cpp with CUDA for LLM inference (NVIDIA GPU).

All CLI flags, persona system (`SOUL.md`), and memory (`MEMORY.md`)
work identically on both platforms.
