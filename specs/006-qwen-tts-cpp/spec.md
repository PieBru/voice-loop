# Feature 006: QwenTTS C++ Backend (qwen3-tts.cpp)

**Branch**: `006-qwen-tts-cpp`
**Created**: 2026-04-17
**Status**: In Progress
**Input**: Integrate [qwen3-tts.cpp](https://github.com/predict-woo/qwen3-tts.cpp) as a subprocess-based TTS backend that runs on CPU, CUDA, and Apple Metal — enabling Qwen3-TTS on macOS, Raspberry Pi, and Linux without the Python PyTorch dependency.

---

## User Scenarios & Testing

### US-1: Select qwen-cpp via CLI flag
**Priority**: P1
As a macOS user, I want to run `--tts qwen-cpp` to use Qwen3-TTS via the C++ binary, so I can get neural TTS quality without CUDA.

**Why P1**: Core value — unlocks QwenTTS on macOS and CPU-only systems.

**Independent Test**: Run `uv run voice_loop.py --tts qwen-cpp --lang en`, speak a turn, confirm audio output.

**Acceptance Scenarios**:
- Given `--tts qwen-cpp` on macOS, when voice_loop starts, then qwen3-tts-cli is found on PATH and used for TTS.
- Given `--tts qwen-cpp` on Linux, when voice_loop starts, then qwen3-tts-cli is used (CPU or CUDA depending on build).
- Given `--tts qwen-cpp` and qwen3-tts-cli is not found, then a clear error message tells the user how to install it.

### US-2: Voice cloning with reference audio
**Priority**: P1
As a user, I want to provide a reference audio file via config, so the C++ backend clones that voice for all TTS output.

**Why P1**: qwen3-tts.cpp has no built-in speakers — voice cloning from reference audio is the primary mode.

**Independent Test**: Configure a reference WAV, run `--tts qwen-cpp`, confirm the voice matches the reference.

**Acceptance Scenarios**:
- Given a reference audio file in config, when `--tts qwen-cpp` is used, then TTS output matches the reference voice.
- Given no reference audio configured, when `--tts qwen-cpp` is used, then a default/basic voice is used with a warning.

### US-3: Model directory configuration
**Priority**: P1
As a user, I want to configure the model directory in config.yaml, so I can control where GGUF models are stored.

**Why P1**: Required for the CLI binary to find its models.

**Independent Test**: Set `tts.qwen_cpp_model_dir` in config.yaml, confirm models are found there.

**Acceptance Scenarios**:
- Given `tts.qwen_cpp_model_dir: /path/to/models` in config.yaml, when qwen3-tts-cli runs, it uses `-m /path/to/models`.
- Given no config, when qwen3-tts-cli runs, it uses a default path (`~/.cache/qwen3-tts-cpp/models` or similar).

### US-4: List qwen-cpp as a TTS option
**Priority**: P2
As a user, I want `--list --tts qwen-cpp` to show usage instructions (model dir, reference audio path).

**Why P2**: Discoverability. The C++ backend has no voice list — show config info instead.

**Independent Test**: Run `--list --tts qwen-cpp`, see configuration guide.

**Acceptance Scenarios**:
- Given `--list --tts qwen-cpp`, print model directory, reference audio path, and install instructions.

---

## Edge Cases

- qwen3-tts-cli not found on PATH → clear error with install instructions (clone, build, add to PATH)
- GGUF model files not downloaded yet → guide user to run `scripts/setup_pipeline_models.py`
- Subprocess crash or timeout → catch error, print message, continue without TTS for that turn
- Very long text → qwen3-tts-cli may take a long time; set a reasonable timeout
- Reference audio file missing → warn and use default voice
- Multiple reference audio files → not supported initially, pick one from config
- qwen3-tts-cli writes WAV to disk → use temp file, clean up after playback
- Sample rate mismatch: qwen3-tts.cpp outputs 24kHz, playback path handles resampling

---

## Clarifications

### 2026-04-17 Session
- **Q: Why subprocess and not Python bindings?** A: qwen3-tts.cpp has no Python bindings. It's a standalone C++ CLI. Subprocess is the only integration path.
- **Q: Which model?** A: 0.6B Base (GGUF format, F16 or Q8_0). The 1.7B CustomVoice is not yet supported by qwen3-tts.cpp.
- **Q: Streaming?** A: No. Same limitation as Python qwen-tts. Full synthesis then playback.
- **Q: Install experience?** A: User clones qwen3-tts.cpp, builds with CMake, downloads/converts models, adds binary to PATH. Documented in README.
- **Q: Coexistence with --tts qwen (Python)?** A: Yes. Three options: `kokoro` (default), `qwen` (Python/CUDA), `qwen-cpp` (C++/CPU/CUDA/Metal).

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept `--tts qwen-cpp` as a CLI choice alongside `kokoro` and `qwen`.
- **FR-002**: When `--tts qwen-cpp` is selected, the system MUST locate `qwen3-tts-cli` on PATH and verify it executes.
- **FR-003**: The system MUST synthesize audio by calling `qwen3-tts-cli` as a subprocess with text input and receiving a WAV output file.
- **FR-004**: The system MUST support voice cloning via a reference audio file configured in `config.yaml` → `tts.qwen_cpp_ref_audio`.
- **FR-005**: The system MUST support model directory configuration in `config.yaml` → `tts.qwen_cpp_model_dir`.
- **FR-006**: If `qwen3-tts-cli` is not found, the system MUST print a clear error with install instructions and exit.
- **FR-007**: The system MUST work on macOS (Metal), Linux (CUDA/CPU), and ARM (RPi) — any platform where `qwen3-tts-cli` runs.
- **FR-008**: The `--no-tts` flag MUST work with qwen-cpp (disables all TTS).
- **FR-009**: The `--list --tts qwen-cpp` flag MUST show configuration info and install instructions.
- **FR-010**: Subprocess failures MUST be caught gracefully — print error, skip TTS for that turn, do not crash the main loop.

### Key Entities

- **qwen3-tts-cli**: The C++ binary executable. Located on PATH. Takes text, reference audio, model dir, output path as arguments.
- **GGUF Model**: The quantized model file (F16 or Q8_0). Stored in a configurable directory.
- **Reference Audio**: A WAV file used for voice cloning. Configured in config.yaml.

---

## Success Criteria

- **SC-001**: `uv run voice_loop.py --tts qwen-cpp --lang en` produces spoken output via qwen3-tts-cli on Linux.
- **SC-002**: `uv run voice_loop.py --tts qwen-cpp --lang en` produces spoken output on macOS.
- **SC-003**: `uv run voice_loop.py --tts qwen-cpp` without qwen3-tts-cli installed exits with a clear error.
- **SC-004**: `uv run voice_loop.py --list --tts qwen-cpp` shows config/install info.
- **SC-005**: `uv run voice_loop.py` (no `--tts`) works identically to before (regression).
- **SC-006**: `uv run voice_loop.py --tts qwen` still works (Python backend regression).

---

## Assumptions

- qwen3-tts.cpp is built and `qwen3-tts-cli` is on PATH (or path configured in config.yaml).
- GGUF model files are already downloaded and converted (one-time setup via `scripts/setup_pipeline_models.py`).
- The 0.6B Base model is used (1.7B not yet supported by qwen3-tts.cpp).
- Output is 24kHz WAV. Playback via `sd.play()` handles resampling.
- No Python dependency changes needed — qwen3-tts.cpp is an external binary.
