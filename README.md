# Voice Loop

A minimal on-device voice agent loop. Runs entirely on macOS (Apple Silicon) and Linux (NVIDIA CUDA).

**Now with even snappier audio responses** — TTS starts on the first sentence while the LLM is still generating the rest, so you hear the reply almost immediately.

> Need a custom voice model or production voice agent? See [Trelis Voice AI Services](https://trelis.com/voice-ai-services/).

## Features

- **Smart turn detection** — Silero VAD + pipecat's Smart Turn v3, so the agent waits when you pause mid-sentence
- **Voice interruption** — speak over the agent; WebRTC AEC3 cancels echo from speakers so your voice cuts through
- **Editable persona** — `SOUL.md` controls the agent's style, live-reloaded each turn
- **Optional long-term memory** — enable with `--memory`; the agent learns durable facts about you in `MEMORY.md` and consolidates every 5 turns
- **Fully local** — no API keys, no cloud. Everything runs on-device

## Stack

- **Moonshine** (CPU) or **faster-whisper** (CPU/CUDA) for speech-to-text transcription
- **Gemma 4 E4B** (MLX/Metal on macOS, llama.cpp/CUDA on Linux) for response generation
- **Kokoro** (CPU) or **Qwen3-TTS** (CUDA) for TTS
- **Silero VAD** + **Smart Turn v3** for turn detection
- **WebRTC AEC3** (via LiveKit APM) for voice interruption

## Setup

### macOS (Apple Silicon)

```bash
brew install portaudio espeak-ng uv
git clone https://github.com/TrelisResearch/voice-loop.git
cd voice-loop
uv sync
```

### Arch Linux (NVIDIA CUDA, VRAM ≥ 4 GB)

```bash
pacman -S portaudio espeak-ng cuda nvidia uv
git clone https://github.com/TrelisResearch/voice-loop.git
cd voice-loop
uv sync
```

First run downloads Gemma 4 E4B (~3GB), Moonshine (~250MB), Kokoro (~300MB), Whisper base (~145MB if used).

## Usage

```bash
# Recommended defaults (TTS + smart turn + voice interrupt all on)
uv run voice_loop.py

# + chime on utterance + soft ticks while generating
uv run voice_loop.py --chime

# + persistent memory (reads/writes MEMORY.md)
uv run voice_loop.py --memory

# Text-only mode (no TTS)
uv run voice_loop.py --no-tts

# Disable voice interruption (keypress only)
uv run voice_loop.py --no-aec

# Different voice (see below)
uv run voice_loop.py --voice bf_emma

# Multilanguage: Italian (uses faster-whisper for STT)
uv run voice_loop.py --lang it

# Multilanguage: Spanish (uses Moonshine for STT)
uv run voice_loop.py --lang es

# Force Whisper STT even for English
uv run voice_loop.py --lang en --stt whisper

# Italian with male voice
uv run voice_loop.py --lang it --voice im_nicola

# Use the smaller E2B model (faster, slightly lower quality)
uv run voice_loop.py --model gemma-4-e2b

# Custom silence timeout
uv run voice_loop.py --silence-ms 500

# Debug: record mic stream to a WAV
uv run voice_loop.py --record

# Use an agentic handler (e.g. Hermes-agent on port 8089)
uv run voice_loop.py --handler agentic

# Use ZeroClaw personal AI assistant
uv run voice_loop.py --handler zeroclaw

# List available response handlers
uv run voice_loop.py --list-handlers

# Qwen3-TTS (higher quality, requires CUDA GPU with ≥8GB VRAM)
uv run voice_loop.py --tts qwen

# Qwen3-TTS with specific speaker
uv run voice_loop.py --tts qwen --voice Vivian

# List QwenTTS speakers
uv run voice_loop.py --list --tts qwen

# QwenTTS via C++ subprocess (works on macOS/Linux/RPi)
uv run voice_loop.py --tts qwen-cpp

# List qwen-cpp config and install instructions
uv run voice_loop.py --list --tts qwen-cpp

# VoxCPM2 TTS (30 languages, voice cloning/design)
uv run voice_loop.py --tts voxcpm

# List VoxCPM capabilities and config
uv run voice_loop.py --list --tts voxcpm
```

## ZeroClaw Integration

[ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) is a fast, fully autonomous AI assistant written in Rust. It supports tool use, multi-step reasoning, and 70+ integrations out of the box.

### Install on Arch Linux

```bash
# Option A: Pre-built binary (recommended)
curl -LO https://github.com/zeroclaw-labs/zeroclaw/releases/latest/download/zeroclaw-linux-x86_64.tar.gz
tar xzf zeroclaw-linux-x86_64.tar.gz
sudo mv zeroclaw /usr/local/bin/

# Option B: Build from source (requires Rust toolchain)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
git clone https://github.com/zeroclaw-labs/zeroclaw.git
cd zeroclaw
cargo build --release --locked
sudo cp target/release/zeroclaw /usr/local/bin/

# Option C: One-line installer
curl -LsSf https://raw.githubusercontent.com/zeroclaw-labs/zeroclaw/master/install.sh | bash
```

### Configure ZeroClaw

```bash
# Interactive setup (provider, channels, etc.)
zeroclaw onboard

# Edit config: set your LLM provider and API key
# Config file: ~/.zeroclaw/config.toml
```

### Run Voice Loop with ZeroClaw

```bash
# Terminal 1: Start ZeroClaw gateway
zeroclaw gateway

# Terminal 2: Start Voice Loop with ZeroClaw handler
uv run voice_loop.py --handler zeroclaw
```

If the ZeroClaw gateway is not running when Voice Loop starts, it falls back to the direct LLM handler with a warning.

### ZeroClaw Handler Configuration

Add to `config.yaml` to customize:

```yaml
handlers:
  zeroclaw:
    api_base: http://127.0.0.1:42617
    token: ""  # Bearer token from `zeroclaw gateway` pairing (optional if pairing is disabled)
    timeout: 120
```

## Qwen3-TTS (Alternative TTS Backend)

[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) is a neural TTS model that produces higher-quality speech than Kokoro, at the cost of requiring a CUDA GPU.

### Requirements

- Linux with NVIDIA CUDA GPU
- ≥8 GB VRAM (1.7B model) or ≥4 GB VRAM (0.6B model, not yet supported)
- First run downloads ~3.4 GB model from HuggingFace

### Supported Languages

| Code | Language | Default Speaker |
|------|----------|----------------|
| `en` | English | `Ryan` |
| `zh` | Chinese | `Vivian` |
| `ja` | Japanese | `Ono_Anna` |
| `ko` | Korean | `Sohee` |
| `es` | Spanish | `Ryan` |
| `fr` | French | `Ryan` |
| `it` | Italian | `Ryan` |
| `pt` | Portuguese | `Ryan` |
| `de` | German | `Ryan` |
| `ru` | Russian | `Ryan` |

### Limitations

- **No streaming**: audio plays after full synthesis (no chunk-by-chunk playback like Kokoro)
- **No AEC barge-in**: voice interruption is not available during QwenTTS synthesis. Keypress interrupt works during playback.
- **macOS not supported**: requires CUDA

### Built-in Speakers

9 speakers: `Chelsie`, `Dylan`, `Eric`, `Ono_Anna`, `Aiden`, `Ryan`, `Serena`, `Sohee`, `Vivian`. Override with `--voice <SpeakerName>`.

## QwenTTS C++ Backend (`--tts qwen-cpp`)

Uses [qwen3-tts.cpp](https://github.com/predict-woo/qwen3-tts.cpp) — a C++ inference engine built on GGML. Runs the 0.6B model on **CPU, CUDA, or Apple Metal**. No PyTorch required.

### When to use

- You want QwenTTS quality but don't have a CUDA GPU (macOS, RPi, CPU-only Linux)
- You want lower memory usage (~1.2GB vs ~8GB for the Python backend)
- You want voice cloning from a reference audio clip

### Install

```bash
git clone https://github.com/predict-woo/qwen3-tts.cpp
cd qwen3-tts.cpp && git submodule update --init --recursive

# Build GGML (Metal on macOS, CUDA on Linux)
cmake -S ggml -B ggml/build -DGGML_METAL=ON   # or -DGGML_CUDA=ON
cmake --build ggml/build -j$(nproc)

# Build the CLI
cmake -S . -B build && cmake --build build -j$(nproc)

# Download and convert models (one-time, ~1.2GB)
uv venv .venv && source .venv/bin/activate
uv pip install huggingface_hub gguf torch safetensors numpy tqdm
python scripts/setup_pipeline_models.py
```

### Configure

Add to `config.yaml`:

```yaml
tts:
  qwen_cpp_bin: /path/to/qwen3-tts.cpp/build/qwen3-tts-cli
  qwen_cpp_model_dir: /path/to/qwen3-tts.cpp/models
  qwen_cpp_ref_audio: /path/to/reference.wav  # optional: for voice cloning
```

### Limitations

- **No streaming**: full synthesis then playback (same as Python QwenTTS)
- **No built-in speakers**: voice cloning from reference audio only. Without reference audio, uses a generic default voice.
- **0.6B model only**: lower quality than the 1.7B Python backend

## VoxCPM2 Backend (`--tts voxcpm`)

Uses [VoxCPM2](https://github.com/OpenBMB/VoxCPM) by OpenBMB — a tokenizer-free diffusion autoregressive TTS model (2B params, 48kHz output). Supports **30 languages** including native Italian.

### When to use

- You need a language not covered by Kokoro or QwenTTS (e.g., Italian with native voice)
- You want voice cloning from a reference audio clip
- You want voice design via text descriptions (e.g., "warm female voice")

### Install

```bash
uv add voxcpm
```

First run downloads ~8GB model weights.

### Configure

Add to `config.yaml`:

```yaml
tts:
  voxcpm_ref_audio: /path/to/voice.wav   # 5-30s for voice cloning
  voxcpm_voice_desc: warm female voice    # or describe a voice
  voxcpm_device: auto                     # cuda, cpu, mps, or auto
```

When both `ref_audio` and `voice_desc` are set, `ref_audio` takes precedence.

### Supported languages

ar, zh, da, nl, en, fi, fr, de, el, he, hi, id, it, ja, km, ko, lo, ms, no, pl, pt, ru, es, sw, sv, tl, th, tr, vi (+ Chinese dialects)

### Limitations

- **No streaming**: full synthesis then playback
- **Heavy model**: ~8GB download, requires significant RAM/VRAM
- **Requires torch>=2.5.0**

## Recommended Kokoro voices

Only the higher-quality voices are listed here:

| Voice | Accent | Gender | Notes |
|-------|--------|--------|-------|
| `af_heart` | US | Female | **Top pick** — Grade A (default) |
| `af_bella` | US | Female | Grade A-, HH training |
| `bf_emma` | UK | Female | Grade B-, HH training |
| `am_fenrir` | US | Male | Grade C+, H training |
| `am_puck` | US | Male | Grade C+, H training |
| `am_michael` | US | Male | Grade C+, H training |
| `bm_fable` | UK | Male | Grade C, MM training |
| `bm_george` | UK | Male | Grade C, MM training |

## Languages

| Code | Language | STT Backend | TTS Voice |
|------|----------|-------------|-----------|
| `en` | English | Moonshine | `af_heart` |
| `es` | Spanish | Moonshine | `ef_dora` |
| `ja` | Japanese | Moonshine | `jf_alpha` |
| `fr` | French | Whisper | `ff_siwis` |
| `it` | Italian | Whisper | `if_sara` |
| `pt` | Portuguese | Whisper | `pf_dora` |
| `zh` | Chinese | Moonshine | `zf_xiaobei` |
| `de` | German | Whisper | `af_heart` |

Any ISO 639-1 code works for STT (99+ languages via Whisper). Only languages with a built-in TTS voice are listed above — others use the English voice as fallback. Override the default voice with `--voice`.

## Architecture

```
   Mic (16kHz) ──► Silero VAD ──► Smart Turn ──► Moonshine/Whisper ──► Gemma 4 E4B ──► Kokoro/QwenTTS ──► Speakers
                                                                     ▲                              │
                                                         SOUL.md + MEMORY.md                   │
                                                                                                ▼
   Mic during TTS ──► WebRTC AEC3 (LiveKit APM) ──► Silero VAD ──► voice interrupt ◄──────────────┘ (Kokoro only)
```

## How it works

1. **Mic capture** via sounddevice (16kHz mono)
2. **Silero VAD** detects speech vs silence
3. **Smart Turn** confirms end-of-turn on silence (default on)
4. **Moonshine or faster-whisper** transcribes your audio to text (auto-selected per language)
5. **Gemma 4 E4B** responds using SOUL.md (+ MEMORY.md if `--memory`) as system prompt
6. **Kokoro** synthesizes sentence pairs in a background thread while the previous pair plays — gapless, low-latency audio (or **Qwen3-TTS** synthesizes full response then plays)
7. **WebRTC AEC3** cleans mic during TTS playback → Silero VAD on cleaned audio → voice interrupt

Press any key during TTS to interrupt.

## Persona & Memory

- `SOUL.md` — persona / style (always loaded, live-reloaded each turn)
- `MEMORY.md` — long-term facts. Only read/written when `--memory` is passed. When enabled, the agent extracts new durable facts after each turn and consolidates every 5 turns.

Both files are re-read at the start of every turn, so edits take effect immediately.

## Memory usage

~3.5 GB total (macOS), ~3 GB VRAM + ~3 GB RAM (Linux with CUDA). With `--tts qwen`: ~6 GB VRAM + ~4 GB RAM.

## Credits

Built with:
- [Moonshine](https://github.com/moonshine-ai/moonshine) — STT
- [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) — TTS
- [Silero VAD](https://github.com/snakers4/silero-vad) — voice activity detection
- [Smart Turn v3](https://github.com/pipecat-ai/smart-turn) — end-of-turn detection
- [LiveKit APM](https://github.com/livekit/python-sdks) — WebRTC AEC3
- [mlx-vlm](https://github.com/Blaizzy/mlx-vlm) — MLX multimodal inference (macOS)
- [llama.cpp](https://github.com/ggerganov/llama.cpp) — CUDA inference (Linux)
- [Gemma 4](https://huggingface.co/google/gemma-4-E4B-it) — LLM

## What's in this fork

Changes on top of the upstream [TrelisResearch/voice-loop](https://github.com/TrelisResearch/voice-loop):

### Linux support (merged to main)

- Linux (NVIDIA CUDA, VRAM ≥ 4 GB) as a first-class target alongside macOS Apple Silicon
- LLM inference via llama.cpp server (OpenAI-compatible API at `localhost:8088/v1`) instead of in-process MLX
- Cross-platform espeak-ng detection (`ctypes.util.find_library`)
- Model aliases via `config.yaml` (e.g. `gemma-4-e4b` → server model `Gemma4-E4B`)
- Constitution v1.1.x: dual-platform technology constraints

### Multilanguage support (`002-multilang-support` branch)

- **`--lang` flag** — sets the language for the entire pipeline (STT + LLM + TTS) with a single argument (default: `en`). Supports any ISO 639-1 code; built-in mappings for 8 languages (en, es, ja, fr, it, pt, zh, de) with appropriate TTS voices and LLM language instructions.
- **Dual STT backend** — **Moonshine** (8 languages, CPU) auto-selected when possible; **faster-whisper** (99+ languages, CPU/CUDA) auto-selected as fallback. Force either with `--stt whisper` or `--stt moonshine`.
- **Language-aware TTS** — default Kokoro voice inferred from `--lang` (e.g. `--lang it` → `if_sara`). Override with `--voice`.
- **LLM language instruction** — non-English languages append a language constraint to the system prompt (never modifies `SOUL.md`).
- **`--list` flag** — shows all available TTS voices grouped by language with STT backend info.
- **Startup model check** — detects if the llama.cpp server model is still loading, waits with progress, and errors clearly instead of hanging silently.
- **LLM API timeout** — 120-second timeout on inference requests to prevent indefinite hangs.
- **`config.yaml` overrides** — `languages` section lets users override built-in TTS voices and language mappings.
- **Error handling** — clear errors for unsupported Moonshine+language combinations; actionable messages for missing faster-whisper or unreachable servers.

### Pluggable response handler (`003-pluggable-response-handler` branch)

- **`--handler` flag** — selects the response generation backend (`llm` for direct API call, `agentic` for external agent service, `zeroclaw` for ZeroClaw). Default is `llm`.
- **Agentic handler** — delegates response generation to an external agentic service (OpenAI-compatible API) at a configurable endpoint (`http://localhost:8089/v1` by default). Waits for full response; chime/ticks provide audible feedback during processing.
- **ZeroClaw handler** — delegates to [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) personal AI assistant via its webhook API (`http://127.0.0.1:42617` by default). Supports tool use, multi-step reasoning, and 70+ integrations.
- **Automatic fallback** — if the selected handler endpoint is unreachable or times out, the system prints a warning and falls back to the `llm` handler for the session.
- **`--list-handlers` flag** — shows all available response handlers with descriptions.
- **`--offline` flag** — sets `HF_HUB_OFFLINE=1` for fully offline operation after first model download.
- **`config.yaml` handlers section** — configure endpoint URL, model name, token, and timeout per handler.

### QwenTTS and VoxCPM backends (`005`–`007` branches)

- **`--tts` flag** — selects TTS backend: `kokoro` (default), `qwen` (CUDA Linux), `qwen-cpp` (all platforms), `voxcpm` (all platforms).
- **Qwen3-TTS** — 1.7B neural TTS with 9 built-in speakers, 10 languages. Requires CUDA GPU with ≥8GB VRAM. `--list --tts qwen` shows speakers.
- **QwenTTS C++** — lightweight 0.6B model via `qwen3-tts-cli` subprocess. Voice cloning from reference audio. Runs on CPU/CUDA/Metal.
- **VoxCPM2** — 2B diffusion TTS with 30 languages, voice cloning (5-30s reference audio), and voice design (text descriptions). Install: `uv add voxcpm`.

## Raspberry Pi

See [docs/raspberry-pi.md](docs/raspberry-pi.md) for a full feasibility analysis. Short version: Pi 4 is too slow; Pi 5 + LiteRT-LM is the best current option but still borderline for natural-feeling voice.

## License

Apache 2.0.
