# Feature 005: QwenTTS Backend

**Branch**: `005-qwen-tts`
**Created**: 2026-04-17
**Status**: In Progress
**Input**: Add Qwen3-TTS as an alternative TTS backend for users with CUDA GPUs who want higher quality or different language coverage.

---

## User Scenarios & Testing

### US-1: Select QwenTTS via CLI flag
**Priority**: P1
As a Linux user with an NVIDIA GPU, I want to run `--tts qwen` to use Qwen3-TTS instead of Kokoro, so I can get neural TTS quality without changing any other part of the pipeline.

**Why P1**: This is the core value — a new TTS backend behind a flag.

**Independent Test**: Run `uv run voice_loop.py --tts qwen --lang en`, speak a turn, confirm audio output.

**Acceptance Scenarios**:
- Given the user passes `--tts qwen`, when voice_loop starts, then Qwen3-TTS model loads on CUDA and speaks responses.
- Given the user passes no `--tts` flag, when voice_loop starts, then Kokoro TTS loads as before (regression).
- Given the user passes `--tts kokoro`, when voice_loop starts, then Kokoro loads exactly as before.

### US-2: QwenTTS speaker selection
**Priority**: P1
As a user, I want to select a QwenTTS speaker with `--voice Ryan`, so I can choose a voice that suits my preference.

**Why P1**: Without speaker selection, QwenTTS is not usable — there must be a way to pick voices.

**Independent Test**: Run `--tts qwen --voice Chelsie`, confirm different voice from default.

**Acceptance Scenarios**:
- Given the user passes `--tts qwen --voice Ryan`, when a response is generated, then the voice used is Ryan.
- Given the user passes `--tts qwen` with no `--voice`, when a response is generated, then a default speaker is used based on language.

### US-3: Language-aware defaults for QwenTTS
**Priority**: P2
As a user running `--tts qwen --lang it`, I want the default speaker to be appropriate for Italian, so I don't have to look up speaker names.

**Why P2**: Convenience, not blocking. User can always override with `--voice`.

**Independent Test**: Run `--tts qwen --lang it` without `--voice`, confirm Italian-appropriate speaker.

**Acceptance Scenarios**:
- Given `--tts qwen --lang en`, the default speaker is an English speaker (e.g., Ryan).
- Given `--tts qwen --lang zh`, the default speaker is a Chinese speaker (e.g., Vivian).
- Given `--tts qwen --lang it` (no native Italian speaker in QwenTTS), a suitable default is chosen with a warning.

### US-4: List QwenTTS speakers
**Priority**: P2
As a user, I want `--list` to show QwenTTS speakers when `--tts qwen` is also provided, so I can discover available voices.

**Why P2**: Discoverability feature, not blocking.

**Independent Test**: Run `--list --tts qwen`, see QwenTTS speakers listed.

**Acceptance Scenarios**:
- Given `--list` alone, shows Kokoro voices (regression).
- Given `--list --tts qwen`, shows QwenTTS built-in speakers grouped by language.

### US-5: Non-streaming fallback for QwenTTS
**Priority**: P1
As a user, I accept that QwenTTS does not support streaming audio output, and responses are synthesized as complete utterances before playback.

**Why P1**: This is a technical constraint that affects UX — barge-in during QwenTTS playback will only work via keypress (no AEC reference signal during synthesis).

**Independent Test**: Run `--tts qwen`, confirm response plays after full synthesis, not streamed chunk-by-chunk.

**Acceptance Scenarios**:
- Given `--tts qwen`, when a response is generated, the full text is synthesized to audio, then played via `sd.play()`.
- Given `--tts qwen --no-aec`, playback can be interrupted by keypress.
- Given `--tts kokoro`, streaming playback works as before (regression).

---

## Edge Cases

- QwenTTS requires CUDA. If run on macOS or CPU-only Linux, print a clear error and exit.
- `qwen-tts` package pins `transformers==4.57.3` — may conflict with existing `transformers>=4.40` in pyproject.toml. Must handle version compatibility.
- QwenTTS output is 24kHz, not 16kHz. The playback path must handle resampling for AEC reference if AEC is used.
- QwenTTS model download is several GB on first run. Startup should show download progress.
- If CUDA VRAM is insufficient, Qwen3-TTS will OOM. Error should be caught with a helpful message.
- `--tts qwen` with `--lang` for unsupported QwenTTS languages (e.g., Arabic, Vietnamese) should warn and suggest Kokoro or a supported language.

---

## Clarifications

### 2026-04-17 Session
- **Q: Replace Kokoro or add as alternative?** A: Add as alternative. `--tts` flag (kokoro/qwen), Kokoro stays default.
- **Q: Auto-select based on language?** A: No. Manual only via `--tts` flag. User always chooses explicitly.
- **Q: VoxCPM integration?** A: Future spec. Not in scope for 005.
- **Q: Streaming audio?** A: Qwen3-TTS Python package has no streaming API. Full synthesis then playback.
- **Q: Which model variant?** A: CustomVoice (built-in speakers). VoiceDesign and Voice Clone are future enhancements.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept a `--tts` CLI flag with choices `kokoro` (default) and `qwen`.
- **FR-002**: When `--tts kokoro` or no `--tts` flag is given, the system MUST behave identically to the current version (regression guarantee).
- **FR-003**: When `--tts qwen` is given, the system MUST load Qwen3-TTS CustomVoice model on CUDA and use it for all TTS output.
- **FR-004**: The system MUST map `--lang` codes to appropriate QwenTTS default speakers, with a fallback and warning for unsupported languages.
- **FR-005**: The system MUST reject `--tts qwen` on macOS with a clear error message (CUDA required).
- **FR-006**: The system MUST synthesize complete utterances for QwenTTS (non-streaming) and play via `sd.play()`.
- **FR-007**: The `--list` flag MUST show QwenTTS speakers when `--tts qwen` is also provided.
- **FR-008**: The system MUST handle QwenTTS model download (several GB) gracefully with progress indication.
- **FR-009**: The `--no-tts` flag MUST work with both backends (disables TTS entirely).
- **FR-010**: The `config.yaml` MUST support a `tts` section for QwenTTS configuration (model variant, device).

### Key Entities

- **TTS Backend**: An abstraction for the TTS engine. Backends: `kokoro` (ONNX, CPU), `qwen` (PyTorch, CUDA).
- **QwenTTS Speaker**: A named voice identity in Qwen3-TTS CustomVoice (e.g., Ryan, Vivian, Chelsie).
- **Language-Speaker Map**: A mapping from language code to default QwenTTS speaker.

---

## Success Criteria

- **SC-001**: `uv run voice_loop.py` (no `--tts`) works identically to before.
- **SC-002**: `uv run voice_loop.py --tts qwen --lang en` produces spoken output using Qwen3-TTS.
- **SC-003**: `uv run voice_loop.py --tts qwen --voice Ryan` uses the Ryan speaker.
- **SC-004**: `uv run voice_loop.py --list --tts qwen` lists QwenTTS speakers.
- **SC-005**: `uv run voice_loop.py --tts qwen` on macOS exits with a clear error.
- **SC-006**: `uv run voice_loop.py --tts qwen --lang it` warns about Italian support but still works.

---

## Assumptions

- Qwen3-TTS is installed via `uv add qwen-tts` and brings PyTorch + transformers as dependencies.
- The target machine has CUDA GPU with ≥4GB VRAM for 0.6B model or ≥8GB for 1.7B model.
- `transformers==4.57.3` pin from `qwen-tts` is compatible with our existing `transformers>=4.40` requirement.
- The `--tts` flag defaults to `kokoro`, preserving zero-change behavior for existing users.
- AEC voice barge-in is NOT supported during QwenTTS playback (no streaming = no reference signal during synthesis). Keypress interrupt still works during playback.
