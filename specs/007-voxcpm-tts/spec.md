# Feature Specification: VoxCPM TTS Backend

**Feature Branch**: `007-voxcpm-tts`
**Created**: 2026-04-17
**Status**: Draft
**Input**: Add support for TTS with VoxCPM, Italian-native TTS with externally handled voice cloning ability

## User Scenarios & Testing

### User Story 1 - Use VoxCPM as TTS backend (Priority: P1)

As a user with a CUDA GPU, I want to run `--tts voxcpm` to use VoxCPM2 for TTS, so I get high-quality 30-language speech with natural prosody — especially for Italian, where other backends (Kokoro, QwenTTS) use non-native speakers.

**Why this priority**: Core value — VoxCPM is the only backend with native-quality Italian and 29 other languages, plus tokenizer-free architecture that preserves prosody.

**Independent Test**: Run `uv run voice_loop.py --tts voxcpm --lang it`, speak a turn, confirm Italian audio output with natural prosody.

**Acceptance Scenarios**:

1. **Given** `--tts voxcpm --lang it`, **When** a response is generated, **Then** audio plays in Italian with natural prosody.
2. **Given** `--tts voxcpm --lang en`, **When** a response is generated, **Then** audio plays in English.
3. **Given** `--tts voxcpm` without VoxCPM installed, **When** voice_loop starts, **Then** a clear error message tells the user how to install it.

### User Story 2 - Voice cloning from reference audio (Priority: P1)

As a user, I want to provide a reference audio clip via config, so VoxCPM clones that specific voice for all TTS output — capturing accent, emotion, and timbre from just a few seconds of audio.

**Why this priority**: Voice cloning is VoxCPM's killer feature and the primary reason to choose it over Kokoro or QwenTTS. Without it, VoxCPM is just another TTS backend.

**Independent Test**: Configure a reference WAV, run `--tts voxcpm`, confirm the output voice matches the reference speaker.

**Acceptance Scenarios**:

1. **Given** a reference audio path in config.yaml, **When** `--tts voxcpm` is used, **Then** TTS output matches the reference voice's timbre and accent.
2. **Given** no reference audio configured, **When** `--tts voxcpm` is used, **Then** a default voice is used based on voice design with language-appropriate characteristics.

### User Story 3 - Voice design via text description (Priority: P2)

As a user, I want to describe the desired voice in natural language via config, so VoxCPM generates speech with that character (e.g., "warm elderly female voice with a slight rasp") without needing a reference audio clip.

**Why this priority**: Useful when no reference audio is available. Voice design is a differentiator but secondary to cloning.

**Independent Test**: Set voice description in config, run `--tts voxcpm`, confirm the output matches the description.

**Acceptance Scenarios**:

1. **Given** a voice description in config.yaml, **When** `--tts voxcpm` is used without reference audio, **Then** TTS output matches the described characteristics.
2. **Given** both voice description and reference audio, **When** `--tts voxcpm` is used, **Then** reference audio takes precedence (cloning overrides design).

### User Story 4 - List VoxCPM capabilities (Priority: P3)

As a user, I want `--list --tts voxcpm` to show supported languages and current configuration.

**Why this priority**: Discoverability. Not blocking.

**Independent Test**: Run `--list --tts voxcpm`, see language list and config.

**Acceptance Scenarios**:

1. **Given** `--list --tts voxcpm`, **Then** the output shows the 30 supported languages, current reference audio path, voice description, and install instructions.

### Edge Cases

- VoxCPM outputs 48kHz audio — playback path must handle resampling for AEC reference if AEC is enabled.
- Long text may cause instability (speed-up, buzzing) — text should be split into segments before synthesis.
- Very short text (< 1 second expected audio) may produce weak output.
- `torch.compile` (enabled by default with `optimize=True`) is incompatible with multi-threading — must set `optimize=False` or run single-threaded.
- VoxCPM requires CUDA >= 12.0 or CPU/MPS. On macOS, MPS support is experimental — may need CPU fallback.
- Streaming API exists (`generate_streaming()`) but bidirectional streaming (text arriving while audio generates) is not supported. Sentence-by-sentence streaming is possible.
- Reference audio quality affects cloning: noisy or very short clips produce poor results. Should warn if reference is < 5 seconds.
- Python 3.13+ may fail — recommend Python 3.10–3.12.

## Clarifications

### 2026-04-17 Session

- **Q: Subprocess or Python import?** A: Python import. VoxCPM has a proper pip package (`voxcpm`) with a clean API. Unlike qwen3-tts.cpp, there's no need for subprocess integration.
- **Q: Streaming or full synthesis?** A: VoxCPM supports `generate_streaming()` for chunk-by-chunk output. Should use streaming when possible for lower latency, with fallback to full synthesis.
- **Q: CUDA-only or cross-platform?** A: VoxCPM supports CUDA, CPU, and Apple MPS. Default to CUDA on Linux, MPS on macOS, CPU as fallback. User can override via config.
- **Q: Model variant?** A: VoxCPM2 (2B parameters) is the latest and best quality. Default to this. VoxCPM1.5 (0.8B) and VoxCPM-0.5B are lighter alternatives but not in initial scope.
- **Q: How to handle long responses?** A: Split text into sentences, synthesize each, concatenate audio. This avoids the known instability with long text.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept `--tts voxcpm` as a CLI choice alongside `kokoro`, `qwen`, and `qwen-cpp`.
- **FR-002**: When `--tts voxcpm` is selected, the system MUST load VoxCPM2 model and use it for all TTS output.
- **FR-003**: The system MUST support voice cloning via a reference audio file configured in `config.yaml` → `tts.voxcpm_ref_audio`.
- **FR-004**: The system MUST support voice design via a text description configured in `config.yaml` → `tts.voxcpm_voice_desc`.
- **FR-005**: The system MUST split long text into sentences before synthesis to avoid known instability with long inputs.
- **FR-006**: The system MUST handle 48kHz output sample rate correctly — resample to 16kHz for AEC reference if AEC is enabled, play at native rate.
- **FR-007**: If `voxcpm` package is not installed, the system MUST print a clear error with install instructions (`uv add voxcpm`) and exit.
- **FR-008**: The `--no-tts` flag MUST work with voxcpm (disables all TTS).
- **FR-009**: The system MUST auto-detect language from `--lang` flag — VoxCPM needs no explicit language tag (auto-detects from text).
- **FR-010**: The system MUST configure device (cuda/cpu/mps) based on platform: CUDA on Linux, MPS on macOS, CPU as fallback. User can override via `config.yaml` → `tts.voxcpm_device`.
- **FR-011**: The `--list --tts voxcpm` flag MUST show supported languages, current config, and install instructions.
- **FR-012**: Reference audio takes precedence over voice description when both are configured.
- **FR-013**: The system MUST use `optimize=False` to avoid torch.compile multi-threading issues.

### Key Entities

- **VoxCPM Model**: The TTS model loaded via `voxcpm.VoxCPM.from_pretrained()`. 2B parameters, 30 languages, outputs 48kHz audio.
- **Reference Audio**: A WAV file (5–30 seconds) used for voice cloning. Configured in config.yaml.
- **Voice Description**: A natural-language string describing desired voice characteristics (e.g., "warm female voice"). Used when no reference audio is provided.
- **Sentence Split**: Long text is split into sentences before synthesis to avoid quality degradation.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `uv run voice_loop.py --tts voxcpm --lang it` produces natural-sounding Italian speech.
- **SC-002**: `uv run voice_loop.py --tts voxcpm --lang en` produces English speech.
- **SC-003**: With a reference audio configured, TTS output matches the reference speaker's voice characteristics.
- **SC-004**: `uv run voice_loop.py --list --tts voxcpm` shows 30 supported languages and current configuration.
- **SC-005**: `uv run voice_loop.py` (no `--tts`) works identically to before (regression).
- **SC-006**: Responses longer than 3 sentences synthesize correctly without buzzing or speed-up artifacts.

## Assumptions

- VoxCPM is installed via `uv add voxcpm` and brings PyTorch as a dependency (already in project).
- The target machine has CUDA GPU with >= 8GB VRAM for VoxCPM2, or sufficient CPU RAM for CPU inference.
- Reference audio is provided by the user — the system does not generate or download reference clips.
- VoxCPM's auto-language-detection works correctly for all 30 supported languages — no explicit language tag needed.
- Voice descriptions work best in English or Chinese (as per VoxCPM documentation).
- The `voxcpm` package is compatible with the project's existing PyTorch and transformers versions.
- `optimize=False` is used to avoid torch.compile issues, trading some performance for stability.
