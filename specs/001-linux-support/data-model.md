# Data Model: Linux Support

## Entities

### Platform

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | `"darwin"` or `"linux"` (from `sys.platform`) |
| `llm_backend` | `str` | `"mlx"` or `"llama-cpp"` |
| `model_format` | `str` | `"mlx-4bit"` or `"gguf"` |

**Derived from**: `sys.platform` at startup. Not stored — computed once.

### ModelAlias

| Field | Type | Description |
|-------|------|-------------|
| `alias` | `str` | User-facing short name (e.g., `"gemma-4-e4b"`) |
| `darwin_repo` | `str` | HuggingFace repo for macOS |
| `linux_repo` | `str` | HuggingFace repo for Linux |
| `linux_filename` | `str` | Glob pattern for GGUF file (Linux only) |

**Constraints**:
- `alias` MUST be lowercase, alphanumeric with hyphens.
- At least one platform repo MUST be defined per alias.
- The default alias is `"gemma-4-e4b"`.

**Resolution rule**: Given `(alias, platform)` → resolve to the
appropriate repo + optional filename. If the alias is not found in the
map, treat it as a raw HuggingFace repo ID and pass through directly.

### LLMBackend (interface)

| Method | Signature | Description |
|--------|-----------|-------------|
| `generate` | `(messages: list[dict], max_tokens: int, temperature: float) → str` | Chat completion: messages in, text out |

**Implementations**:
- `MLXBackend`: Wraps `mlx_vlm.load` + `mlx_vlm.generate`. macOS only.
- `LlamaCppBackend`: Wraps `llama_cpp.Llama.create_chat_completion`. Linux only.

Both expose the same `generate()` interface. The `main()` function
instantiates the correct one based on platform detection.

### SystemDependency

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Package name (e.g., `"portaudio"`, `"espeak-ng"`) |
| `linux_install_cmd` | `str` | Install command for Arch (e.g., `"pacman -S portaudio"`) |
| `check_fn` | `callable` | Returns `True` if dependency is available |

**Usage**: At startup on Linux, check each required system dependency.
If any is missing, print the install command and exit (FR-009).

## Relationships

```text
Platform 1──1 LLMBackend
ModelAlias *──1 Platform (resolved to repo per platform)
SystemDependency *──1 Platform (checked only on Linux)
```

## State Transitions

### Startup Sequence (Linux)

```text
[Start]
  → Check sys.platform == "linux"
  → Check system deps (PortAudio, espeak-ng)
      → Missing? Print install cmd, exit(1)
  → Resolve model alias → (repo, filename)
  → Try import llama_cpp
      → ImportError? Print "pip install", exit(1)
  → Try load model with CUDA
      → CUDA error? Print GPU requirements, exit(1)
  → [Running]
```

### Startup Sequence (macOS)

```text
[Start]
  → Check sys.platform == "darwin"
  → Resolve model alias → (repo)
  → Try import mlx_vlm
      → ImportError? Print "pip install mlx-vlm", exit(1)
  → Load model via MLX
  → [Running]
```
