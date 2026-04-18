# Feature 009: OpenAI-Compatible TTS Endpoint Backend

**Branch**: `009-openai-tts`
**Created**: 2026-04-18
**Status**: Draft
**Input**: Add `--tts openai` backend that calls an OpenAI-compatible `/v1/audio/speech` HTTP endpoint (e.g. Qwen3-TTS-Openai-Fastapi, XTTS, any server exposing the standard OpenAI TTS API). This enables high-quality neural TTS from any network-accessible server without in-process model loading.

---

## User Scenarios & Testing

### US-1: Use OpenAI-compatible TTS server via CLI flag
**Priority**: P1
As a user running a local TTS server (e.g. Qwen3-TTS-Openai-Fastapi), I want to run `--tts openai` so voice_loop sends TTS requests to that server instead of loading a model in-process — saving VRAM and enabling any OpenAI-compatible TTS backend.

**Why P1**: Core value — decouples TTS from the voice_loop process, enabling any OpenAI-compatible TTS server.

**Independent Test**: Start a Qwen3-TTS-Openai-Fastapi server on localhost:8880, run `uv run voice_loop.py --tts openai`, speak a turn, confirm audio output.

**Acceptance Scenarios**:
- Given `--tts openai` and a running TTS server at the configured endpoint, when a response is generated, then audio plays from the server's output.
- Given `--tts openai` and the server is unreachable, when voice_loop starts or synthesizes, then a clear error message is printed and the turn continues without audio (no crash).
- Given `--tts openai` without `--tts-openai-endpoint`, when voice_loop starts, then the default endpoint `http://localhost:8880` is used.

### US-2: Configure endpoint URL and model
**Priority**: P1
As a user, I want to configure the TTS server URL and model name via CLI flags or config.yaml, so I can point voice_loop at any OpenAI-compatible TTS server (local or remote).

**Why P1**: Without configurable endpoint/model, the feature is locked to one specific server setup.

**Independent Test**: Run with `--tts-openai-endpoint http://192.168.1.50:8880 --tts-openai-model tts-1`, confirm requests go to that URL with that model name.

**Acceptance Scenarios**:
- Given `--tts-openai-endpoint http://myserver:9999`, when TTS is invoked, then requests go to `http://myserver:9999/v1/audio/speech`.
- Given `config.yaml` → `tts.openai_endpoint`, when `--tts-openai-endpoint` is not provided, then the config value is used.
- Given neither CLI flag nor config, when voice_loop starts, then `http://localhost:8880` is used as default.

### US-3: Select voice for OpenAI TTS
**Priority**: P1
As a user, I want to select a voice via `--voice`, so the OpenAI TTS server uses that specific voice for synthesis.

**Why P1**: Voice selection is fundamental to TTS. The OpenAI API's `voice` parameter maps directly to this.

**Independent Test**: Run `--tts openai --voice Vivian`, confirm the server receives `voice=Vivian` in the request.

**Acceptance Scenarios**:
- Given `--voice Vivian`, when TTS is invoked, the request includes `voice: "Vivian"`.
- Given no `--voice` and a default in config, the config default is used.
- Given no `--voice` and no config default, a server-appropriate default (e.g. "Chelsie") is used.

### US-4: Streaming PCM audio for low latency
**Priority**: P2
As a user, I want the OpenAI TTS backend to use streaming when the server supports it (`stream=true`, `response_format=pcm`), so audio starts playing as soon as the first chunks arrive — reducing perceived latency for long responses.

**Why P2**: Streaming significantly improves user experience but depends on server support. Fallback to non-streaming (full audio download then play) must always work.

**Independent Test**: Run `--tts openai` with a streaming-capable server, observe audio starts playing before the full response is synthesized.

**Acceptance Scenarios**:
- Given a server that supports streaming, when TTS is invoked, audio chunks are played incrementally.
- Given a server that does not support streaming (or returns an error), when streaming is attempted, fallback to full download then play occurs seamlessly.
- Given `--no-tts-openai-stream`, TTS uses full download mode regardless of server capability.

### US-5: List OpenAI TTS configuration
**Priority**: P3
As a user, I want `--list --tts openai` to show the configured endpoint, model, voice, and streaming status.

**Why P3**: Discoverability. Not blocking.

**Independent Test**: Run `--list --tts openai`, see endpoint URL, model name, default voice, streaming mode.

**Acceptance Scenarios**:
- Given `--list --tts openai`, print endpoint URL, model, default voice, streaming enabled/disabled, and config.yaml keys.

---

## Edge Cases

- Server unreachable at startup → warn and continue (TTS will fail on first synthesis, don't block startup)
- Server returns non-200 HTTP status → print error with status code, skip TTS for that turn, don't crash
- Server returns malformed audio data → catch decode error, print message, skip TTS
- Very long text > server's max input length → split into sentences, synthesize each separately
- Streaming response interrupted (server disconnects mid-stream) → play what was received, print warning
- Response format negotiation: prefer `wav` for simplicity, `pcm` for streaming, fallback to `mp3` if server doesn't support wav
- Voice name not recognized by server → server returns error, print it, skip TTS
- Endpoint URL with/without trailing slash → normalize
- HTTP vs HTTPS → support both (no certificate validation issues for localhost)
- Server slow to respond → set reasonable timeout (30s for full, configurable)
- Failed HTTP requests → no retry; fail immediately, skip TTS for that turn, continue main loop

---

## Clarifications

### 2026-04-18 Session

- **Q: Why HTTP client and not SDK?** A: The OpenAI TTS API is simple (`POST /v1/audio/speech`). Using `urllib.request` (stdlib) avoids adding `openai` or `httpx` as dependencies. Consistent with constitution principle II (Simplicity).
- **Q: Streaming implementation?** A: Use `urllib.request` for non-streaming (full response). For streaming, read chunked response in a background thread, play chunks via `sd.play()` with a ring buffer or concatenate then play per sentence. Simpler approach: collect PCM chunks into buffer, play once complete per sentence.
- **Q: What servers does this target?** A: Primarily [Qwen3-TTS-Openai-Fastapi](https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi) (default port 8880). But any server exposing `POST /v1/audio/speech` with standard OpenAI params works (XTTS-API-Server, LocalAI, etc.).
- **Q: Audio format?** A: Request `response_format=wav` for non-streaming. For streaming, request `response_format=pcm` and handle raw float32 24kHz. Fallback to `mp3` if server rejects wav.
- **Q: Coexistence with in-process backends?** A: Yes. `--tts kokoro` (default, in-process), `--tts qwen` (in-process CUDA), `--tts qwen-cpp` (subprocess), `--tts voxcpm` (in-process CUDA), `--tts openai` (HTTP client). All coexist.
- Q: How should streaming audio chunks be played back? → A: Sentence-level buffering — collect all PCM chunks for one sentence, then play the complete sentence before requesting the next. Matches existing Kokoro streaming TTS pattern.
- Q: Should failed TTS HTTP requests be retried? → A: Fail immediately — print error, skip TTS for that turn, continue main loop. No retry. Consistent with other TTS backends (qwen-cpp, voxcpm).
- Q: How to handle varying sample rates from different servers? → A: Auto-detect from WAV header for non-streaming (soundfile.read returns sr). For streaming PCM, default to 24kHz with configurable `--tts-openai-sr` override in CLI and config.yaml.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept `--tts openai` as a CLI choice alongside `kokoro`, `qwen`, `qwen-cpp`, and `voxcpm`.
- **FR-002**: When `--tts openai` is selected, the system MUST send TTS requests to the configured endpoint via `POST /v1/audio/speech` using only stdlib (`urllib.request`, `json`).
- **FR-003**: The system MUST support endpoint URL configuration via `--tts-openai-endpoint` CLI flag and `config.yaml` → `tts.openai_endpoint` (CLI takes precedence).
- **FR-004**: The system MUST support model name configuration via `--tts-openai-model` CLI flag and `config.yaml` → `tts.openai_model` (CLI takes precedence). Default: `qwen3-tts`.
- **FR-005**: The system MUST send the `voice` parameter from `--voice` flag (or config default) in the TTS request. Default: `Chelsie`.
- **FR-006**: The system MUST request `response_format=wav` for non-streaming synthesis and auto-detect sample rate from the WAV header for correct playback.
- **FR-006b**: For streaming PCM mode, the system MUST default to 24kHz sample rate, configurable via `--tts-openai-sr` CLI flag or `config.yaml` → `tts.openai_sample_rate`.
- **FR-007**: If the server is unreachable or returns an error, the system MUST print a clear error and skip TTS for that turn without crashing the main loop.
- **FR-008**: The system MUST split long text into sentences before synthesis (reuse `_split_sentences()`) to avoid server timeout on long inputs.
- **FR-009**: The system MUST support optional streaming mode via `--tts-openai-stream` flag or `config.yaml` → `tts.openai_stream`. When enabled, request `stream=true` with `response_format=pcm`, collect all chunks per sentence into a buffer, then play the complete sentence audio before requesting the next sentence.
- **FR-010**: The `--no-tts` flag MUST work with openai backend (disables all TTS).
- **FR-011**: The `--list --tts openai` flag MUST show configured endpoint, model, voice, streaming mode, and config.yaml keys.
- **FR-012**: The system MUST normalize endpoint URLs (strip trailing slash, ensure `/v1/audio/speech` path).
- **FR-013**: The system MUST set a reasonable HTTP timeout (30s default, configurable via `config.yaml` → `tts.openai_timeout`).
- **FR-014**: No new pip dependencies. All HTTP functionality via `urllib.request` (stdlib).

### Key Entities

- **OpenAI TTS Endpoint**: An HTTP server exposing `POST /v1/audio/speech` with params: `model`, `voice`, `input`, `response_format`, `speed`, `stream`.
- **Endpoint Config**: URL, model name, default voice, streaming toggle, timeout — configurable via CLI flags and config.yaml.
- **Audio Response**: WAV binary (non-streaming — sample rate auto-detected from header) or chunked PCM float32 (streaming — default 24kHz, configurable via `--tts-openai-sr`).

---

## Success Criteria

- **SC-001**: `uv run voice_loop.py --tts openai` produces spoken output when a TTS server is running at localhost:8880.
- **SC-002**: `uv run voice_loop.py --tts openai --tts-openai-endpoint http://myserver:9999` sends requests to the specified server.
- **SC-003**: `uv run voice_loop.py --tts openai` without a running server prints an error and continues without crashing.
- **SC-004**: `uv run voice_loop.py --list --tts openai` shows endpoint config and usage info.
- **SC-005**: `uv run voice_loop.py` (no `--tts`) works identically to before (regression — default Kokoro).
- **SC-006**: `uv run voice_loop.py --tts kokoro` still works (regression).
- **SC-007**: No new pip dependencies added to pyproject.toml.

---

## Assumptions

- The OpenAI-compatible TTS server is already running and accessible (user starts it separately).
- The server follows the standard OpenAI TTS API schema (`POST /v1/audio/speech`).
- For streaming, the server supports `stream=true` with chunked PCM output. Non-streaming always works as fallback.
- `urllib.request` is sufficient for HTTP calls — no need for `httpx` or `requests`.
- The server returns audio at a known sample rate. WAV responses embed sample rate in the header (auto-detected). Streaming PCM defaults to 24kHz (configurable via `--tts-openai-sr`).
- Audio format preference: WAV (non-streaming) or raw PCM (streaming). Both are easy to handle without extra libraries.
