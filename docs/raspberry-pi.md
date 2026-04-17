# Raspberry Pi — Feasibility Notes

Short answer: **not yet practical for a good voice experience**, but worth revisiting as Pi 5 + purpose-built runtimes mature.

## What needs swapping

| Component | Mac (current) | Raspberry Pi |
|-----------|--------------|-------------|
| LLM runtime | mlx-vlm (Apple Silicon only) | llama.cpp or LiteRT-LM |
| AEC | LiveKit APM (WebRTC AEC3) | speexdsp or [thewh1teagle/aec](https://github.com/thewh1teagle/aec) |
| Everything else | — | unchanged (Moonshine, Kokoro, Silero VAD, Smart Turn — all ONNX, ARM-compatible) |

The architecture — VAD → ASR → streaming LLM → sentence-pipeline → TTS — ports cleanly. It's really two dependency swaps.

## The LLM bottleneck

Benchmarked on **Raspberry Pi 4** (Cortex-A72, 4 cores, 8 GB RAM) with llama.cpp b8816, CPU-only:

| Model | Size | Prompt | Generation |
|-------|------|--------|-----------|
| Gemma 3 1B Q4_K_M | 769 MB | 5.9 t/s | 2.9 t/s |
| Gemma 4 E2B Q4_K_M | 2.9 GB | 2.0 t/s | 1.0 t/s |

**1.0 t/s is not viable for voice.** A typical response of 80–120 tokens takes 80–120 seconds. Even the sentence-streaming pipeline (which starts TTS on the first sentence) can't save you when the LLM is that slow — the first sentence alone takes ~15 seconds to generate.

**2.9 t/s (Gemma 3 1B)** is marginal — first sentence arrives in ~5 s, full response in ~20–30 s. Usable only for very patient, low-frequency conversation.

For voice you realistically need **20+ t/s** to feel natural.

## Pi 5 + LiteRT-LM — the best near-term hope

- Pi 5 (Cortex-A76) is ~2–3× faster per core than Pi 4
- Google's [LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM) is purpose-built for edge deployment and supports macOS/Linux/Pi
- Google claim ~7.6 t/s for Gemma 4 E2B on Pi 5 with LiteRT-LM — unverified but plausible given the per-core uplift
- Even 7–8 t/s is borderline: first sentence ~2 s, but a full 100-token response still takes ~13 s

### To test LiteRT-LM on Pi 5

```bash
pip install litert-lm-api

# Downloads model (~1.5 GB) and runs inference
litert-lm run \
  --from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm \
  gemma-4-E2B-it.litertlm \
  --prompt="Tell me about the solar system in a few sentences."
```

## Verdict

| Platform | Verdict |
|----------|---------|
| Pi 4 | Too slow — not recommended |
| Pi 5 + llama.cpp | Better, unverified — likely still borderline |
| Pi 5 + LiteRT-LM | Best bet — test before committing |
| Pi 5 + NPU accelerator (future) | Could change things significantly |

PRs welcome if you get it running well on Pi 5.
