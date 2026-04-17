# Feature Specification: Pluggable Response Handler

**Feature Branch**: `003-pluggable-response-handler`
**Created**: 2026-04-17
**Status**: Draft
**Input**: User description: "Add a CLI option to define the handling of the input message from the user STT, handling that will then produce the output message played with TTS. The default can be the current only option (the configured LLM API endpoint), but we may add more option, starting with an 'agentic' option that delegates the user message handling to a generic agent like Hermes-agent, ZeroClaw, OpenFang, etc."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use a direct LLM for responses (Priority: P1)

A user runs Voice Loop with the default behavior: STT transcribes speech, the transcribed text is sent to a configured LLM endpoint, the LLM generates a response, and TTS speaks it. This is the existing behavior and MUST continue to work identically when no response-handler flag is provided.

**Why this priority**: This is the existing, working behavior. It must remain the default and must not regress. Everything else builds on top of this.

**Independent Test**: Run `uv run voice_loop.py` without any response-handler flag. Behavior is identical to the current version (LLM endpoint generates responses via the configured API).

**Acceptance Scenarios**:

1. **Given** Voice Loop is started without a response-handler flag, **When** the user speaks, **Then** the transcribed text is sent to the configured LLM API endpoint and the response is spoken via TTS (identical to current behavior)
2. **Given** Voice Loop is started with `--handler llm` (explicit default), **When** the user speaks, **Then** behavior is identical to running without the flag

---

### User Story 2 - Use an agentic handler for responses (Priority: P1)

A user wants the transcribed speech to be handled by an autonomous agent (e.g., Hermes-agent, OpenFang) instead of a direct LLM call. The agent may use tools, search, multi-step reasoning, or external APIs to produce a richer response. The user selects this via a CLI flag, and the rest of the pipeline (STT, TTS, VAD, etc.) remains unchanged.

**Why this priority**: This is the core new capability. The user explicitly requested agentic delegation as the first alternative handler.

**Independent Test**: Run `uv run voice_loop.py --handler agentic` (or similar), speak a question that benefits from tool use or multi-step reasoning, and confirm the response reflects agentic processing rather than a single-shot LLM call.

**Acceptance Scenarios**:

1. **Given** Voice Loop is started with the agentic handler flag, **When** the user speaks, **Then** the transcribed text is sent to the configured agentic endpoint and the response is spoken via TTS
2. **Given** Voice Loop is started with the agentic handler flag, **When** the agent takes longer than a direct LLM call, **Then** the user is informed of processing status (e.g., chime or visual indicator continues)
3. **Given** Voice Loop is started with the agentic handler flag but the agentic endpoint is unreachable, **Then** a clear error message is shown at startup or on first use

---

### User Story 3 - Discover available response handlers (Priority: P2)

A user wants to see which response handlers are available and what each one does before choosing one.

**Why this priority**: Discoverability is important for usability but not required for the feature to function.

**Independent Test**: Run `uv run voice_loop.py --list-handlers` (or similar) and see a list of available handlers with brief descriptions.

**Acceptance Scenarios**:

1. **Given** Voice Loop is started with a list-handlers flag, **Then** all registered handlers are listed with their name and a brief description

---

### Edge Cases

- When the configured agentic endpoint URL is invalid or unreachable: print warning, fall back to `llm` handler (FR-008a)
- When the agentic handler returns an empty or malformed response: treat as empty response (no TTS), continue listening
- When the agentic handler takes significantly longer than the LLM handler (e.g., 30+ seconds): chime/ticks continue; a request timeout triggers fallback per FR-008a
- Handler selection is per-session only (set at startup via CLI flag); runtime switching is out of scope for v1
- If `--handler` is set to a name that doesn't exist: clear error at startup listing available handlers (FR-008)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A `--handler` CLI flag MUST be added to select the response generation backend (default: `llm`)
- **FR-002**: The `llm` handler MUST behave identically to the current response generation logic (direct LLM API call)
- **FR-003**: An `agentic` handler MUST be available that delegates response generation to an external agentic service
- **FR-004**: The agentic handler MUST be configurable via `config.yaml` (endpoint URL, model name, any handler-specific parameters)
- **FR-005**: The handler interface MUST accept transcribed text (and conversation history) and return a response string suitable for TTS
- **FR-006**: The greeting message generation MUST use the same handler as the main conversation loop
- **FR-007**: Each handler MUST report its identity in the startup banner (e.g., `handler: llm` or `handler: agentic`)
- **FR-008**: Invalid or unavailable handler names MUST produce a clear error at startup listing available handlers
- **FR-008a**: If the selected handler's endpoint is unreachable or the request times out (60 seconds), the system MUST print a warning and fall back to the `llm` handler for the remainder of the session
- **FR-009**: The handler selection MUST NOT affect STT, TTS, VAD, or any other pipeline component
- **FR-010**: The agentic handler's endpoint URL MUST default to `http://localhost:8089/v1` (distinct from the LLM endpoint at 8088) but be overridable in `config.yaml`
- **FR-011**: The agentic handler MUST send the conversation in a format compatible with OpenAI-compatible chat completion APIs (reusing the same message format as the `llm` handler)
- **FR-012**: The agentic handler MUST wait for the full response before passing it to TTS (no streaming). While waiting, the existing chime/ticks mechanism (`--chime`) provides audible progress indication to the user.

## Clarifications

### Session 2026-04-17

- Q: When the agentic handler's endpoint is unreachable or the request times out, what should happen? → A: Print warning, fall back to the direct LLM handler for that session, continue working.
- Q: How long should the agentic handler wait before considering the request timed out? → A: 60 seconds (long enough for multi-step agentic reasoning but bounded to avoid indefinite silence).

### Key Entities

- **ResponseHandler**: Represents a response generation backend. Has a name, a description, and a callable interface that accepts messages and returns a response string. The `llm` handler wraps the existing direct API call; the `agentic` handler wraps a call to an external agentic service.
- **HandlerConfig**: Configuration for a specific handler instance. Stored in `config.yaml` under a `handlers` section. Contains handler-specific settings (e.g., endpoint URL, model name, timeout).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running without `--handler` produces identical behavior to the version before this feature (zero regression)
- **SC-002**: Users can switch between at least two response handlers with a single CLI flag change, with no code modification
- **SC-003**: A new handler can be added by editing only `config.yaml` and adding a handler function in `voice_loop.py`, without changing any other pipeline code
- **SC-004**: The agentic handler successfully delegates to an external service and returns a spoken response within the configured timeout (60 seconds default) for typical queries
- **SC-005**: Startup clearly indicates which handler is active so the user can verify their selection before speaking

## Assumptions

- The agentic service exposes an OpenAI-compatible chat completion API (same interface as llama.cpp server). This allows reusing the existing HTTP client logic.
- The agentic service runs locally (on-device first principle). No cloud API keys or external network calls.
- Handler selection is per-session (set at startup via CLI flag). Runtime switching is out of scope for v1.
- The agentic endpoint defaults to port 8089 to avoid conflicting with the LLM endpoint on 8088.
- Memory features (`--memory`) continue to work with any handler, since memory reads/writes happen outside the handler call.
- The `--handler` flag name is preferred over `--backend` to avoid confusion with `--stt` which already uses "backend" terminology.
