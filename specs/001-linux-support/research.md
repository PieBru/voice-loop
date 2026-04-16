# Research: Linux (Arch Linux) Support

## R1: LLM Inference Backend for Linux

**Decision**: Use `llama-cpp-python` with CUDA backend.

**Rationale**: 
- `mlx-vlm` depends on `mlx-metal` which only has macOS arm64 wheels.
  There is no Linux port and none planned — Metal is Apple GPU only.
- `llama-cpp-python` provides the best fit:
  - In-process Python API (no separate server like Ollama)
  - CUDA acceleration via pre-built wheels
  - Supports Gemma 4 E4B via GGUF quantized format
  - ~3 GB VRAM for Q4_K_M quantization (fits 4 GB target)
  - ~50-80 tok/s on mid-range CUDA GPU (RTX 3060/4060)
  - `create_chat_completion()` API mirrors the current message-based
    interface used with mlx-vlm
- Alternatives considered and rejected:
  - **Ollama**: Requires separate daemon process, adds IPC overhead,
    larger disk footprint (~9.6 GB vs ~3 GB).
  - **transformers + bitsandbytes**: Heavier VRAM usage (~4.5 GB),
    slower inference (PyTorch overhead vs optimized C++ in llama.cpp),
    cold start ~10-20s.
  - **vLLM**: Does not yet support Gemma 4; designed for concurrent
    serving, overkill for single-user voice agent.

**Python API mapping** (current → new):
```
from mlx_vlm import load, generate
model, processor = load(model_name)
prompt = processor.apply_chat_template(messages, ...)
r = generate(model, processor, prompt, max_tokens=200, ...)

→

from llama_cpp import Llama
llm = Llama.from_pretrained(repo_id=..., filename=..., n_gpu_layers=-1)
r = llm.create_chat_completion(messages=messages, max_tokens=200, ...)
```

## R2: Conditional Dependencies in pyproject.toml

**Decision**: Use PEP 508 environment markers for platform-specific deps.

**Rationale**:
- `pyproject.toml` supports inline environment markers:
  ```toml
  "mlx-vlm>=0.4.3; sys_platform == 'darwin'",
  "llama-cpp-python>=0.3.0; sys_platform == 'linux'",
  ```
- `uv` resolves these correctly — only installs deps matching the
  current platform.
- This avoids Linux users hitting `mlx-metal` install failures and
  macOS users pulling in `llama-cpp-python`.
- The shared deps (sounddevice, numpy, silero-vad, etc.) remain
  unconditionally listed.

**Alternative rejected**: Separate `pyproject.toml` files or optional
extras (`[linux]`, `[macos]`). These complicate the `uv sync` workflow
and violate the single-project simplicity goal.

## R3: GGUF Model Source for Gemma 4 E4B

**Decision**: Use `ggml-org/gemma-4-E4B-it-GGUF` on HuggingFace with
Q4_K_M quantization as the default Linux model.

**Rationale**:
- Official GGUF conversion of the same Gemma 4 E4B model used on macOS.
- Q4_K_M offers the best quality/size tradeoff (~3 GB, quality loss
  imperceptible for voice agent chat).
- `Llama.from_pretrained()` auto-downloads from HuggingFace, matching
  the macOS first-run auto-download behavior.
- Model cached in `~/.cache/huggingface/hub/` (standard HF cache).
- The model alias `gemma-4-e4b` maps to:
  - macOS: `mlx-community/gemma-4-E4B-it-4bit`
  - Linux: `ggml-org/gemma-4-E4B-it-GGUF` (Q4_K_M file)

## R4: espeak-ng Library Path Detection

**Decision**: Use `ctypes.util.find_library("espeak-ng")` as primary
detection, with platform-specific fallback paths.

**Rationale**:
- `ctypes.util` is in the standard library — no new dependency.
- On macOS: returns the Homebrew path if installed (or falls back to
  current `brew --prefix` method).
- On Linux: returns `/usr/lib/libespeak-ng.so` or equivalent based on
  the system's library search path.
- Eliminates the hardcoded `.dylib` extension and `brew` dependency.

**Implementation sketch**:
```python
import ctypes.util
import platform

def find_espeak_lib():
    lib = ctypes.util.find_library("espeak-ng")
    if lib:
        return lib
    if platform.system() == "Darwin":
        try:
            import subprocess
            prefix = subprocess.check_output(
                ["brew", "--prefix", "espeak-ng"], text=True
            ).strip()
            return f"{prefix}/lib/libespeak-ng.dylib"
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    return None
```

## R5: Platform Detection Strategy

**Decision**: Use `sys.platform` at module level, `try/except` import for
backend availability.

**Rationale**:
- `sys.platform` returns `"darwin"` on macOS, `"linux"` on Linux — fast,
  no subprocess calls, available before any third-party imports.
- For the LLM backend, use a `try/except` import pattern:
  ```python
  if sys.platform == "darwin":
      from mlx_vlm import load, generate
      # ... MLX setup
  else:
      from llama_cpp import Llama
      # ... llama-cpp setup
  ```
- This satisfies FR-008 (skip unavailable backends rather than crashing)
  and keeps the import failure path clear.
- On Linux without CUDA: `llama-cpp-python` will import but fail at
  model load time with a clear CUDA error. The script should catch this
  and print an actionable message (FR-009).

## R6: Model Alias Resolution

**Decision**: Model aliases live in `./config.yaml`, loaded at startup.
If the file is absent, built-in defaults are used.

**Rationale**:
- The spec (FR-006) requires generic aliases like `gemma-4-e4b`.
- A `config.yaml` is easy for humans to edit and for computers to parse.
  No new hard dependency — Python's stdlib doesn't include YAML, so we
  use a minimal inline YAML parser or add `pyyaml` as a dependency
  (already transitively pulled in by `transformers` and `mlx-vlm`).
- Example `config.yaml`:
  ```yaml
  models:
    gemma-4-e4b:
      darwin:
        repo: mlx-community/gemma-4-E4B-it-4bit
      linux:
        repo: ggml-org/gemma-4-E4B-it-GGUF
        filename: "*Q4_K_M*"
    gemma-4-e2b:
      darwin:
        repo: mlx-community/gemma-4-E2B-it-4bit
      linux:
        repo: ggml-org/gemma-4-E2B-it-GGUF
        filename: "*Q4_K_M*"
  ```
- Users can add custom models by editing `config.yaml` without touching
  the script. Raw HuggingFace repo IDs still work via `--model` bypass.
- Built-in defaults are used when `config.yaml` is missing (first run),
  and a sample `config.yaml` is auto-generated for the user to customize.

## R7: CUDA Availability Detection

**Decision**: Check via `llama-cpp-python` itself, not via `torch.cuda`
or `subprocess` calls to `nvidia-smi`.

**Rationale**:
- `llama-cpp-python` already handles CUDA detection internally.
- On import, it does not require CUDA (CPU builds exist). The check
  happens when creating the model with `n_gpu_layers=-1`.
- If CUDA is unavailable, it raises an error we can catch and convert
  to a user-friendly message.
- Avoids adding `torch.cuda` dependency just for detection (torch is
  already a dep for silero-vad, but using it for CUDA detection is
  fragile — torch CPU-only builds don't have `torch.cuda`).
- A pre-check can attempt:
  ```python
  try:
      import llama_cpp
      if not llama_cpp.llama_supports_gpu_offload():
          print("Error: CUDA not available ...")
          sys.exit(1)
  except ImportError:
      print("Error: llama-cpp-python not installed ...")
      sys.exit(1)
  ```
