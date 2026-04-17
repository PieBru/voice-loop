# Feature Specification: Multilanguage STT & TTS Support

**Feature Branch**: `002-multilang-support`  
**Created**: 2026-04-16  
**Status**: Draft  
**Input**: User description: "Add multilanguage support to both the STT and the TTS, test it with Italian language."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Speak and hear responses in a non-English language (Priority: P1)

A user wants to interact with Voice Loop entirely in a non-English language (e.g., Spanish, French, Japanese). They set a language flag at startup, speak in that language, and the agent transcribes, responds, and speaks back in the same language — without any code changes or manual configuration.

**Why this priority**: This is the core value proposition — a single flag that makes the entire voice loop work in another language. Without this, multilanguage support doesn't exist.

**Independent Test**: Can be fully tested by passing a language flag (e.g., `--lang es`), speaking a full turn in Spanish, and confirming STT → LLM → TTS all work in Spanish.

**Acceptance Scenarios**:

1. **Given** Voice Loop is started with a non-English language flag, **When** the user speaks in that language, **Then** the speech is transcribed in that language, the LLM responds in that language, and TTS speaks the response in that language
2. **Given** Voice Loop is started with a non-English language flag, **When** the greeting is generated, **Then** the greeting is spoken in the selected language
3. **Given** Voice Loop is started without a language flag, **When** the user interacts normally, **Then** behavior is identical to the current English-only version (zero regression)

---

### User Story 2 - Italian language end-to-end (Priority: P1)

A user wants to use Voice Loop in Italian. They pass an Italian language flag, speak Italian, and the full pipeline works — STT transcribes Italian, the LLM responds in Italian, and TTS speaks Italian.

**Why this priority**: The user explicitly requested Italian as the test language. This validates the feature works for a real non-English use case.

**Independent Test**: Run `uv run voice_loop.py --lang it`, speak Italian, confirm the entire turn completes in Italian.

**Acceptance Scenarios**:

1. **Given** Voice Loop is started with `--lang it`, **When** the user speaks Italian, **Then** the transcription contains Italian text, the LLM responds in Italian, and TTS speaks Italian
2. **Given** Voice Loop is started with `--lang it`, **When** the greeting plays, **Then** it is spoken in Italian with an Italian voice

---

### User Story 3 - Consistent language across all components (Priority: P2)

When a user selects a language, all components that have language-dependent behavior are configured consistently: STT model, TTS voice/language, and LLM system prompt language instruction.

**Why this priority**: Without consistency, the user might speak Spanish but hear English responses — which breaks the experience.

**Independent Test**: Set `--lang` to a language and verify at startup that STT model, TTS voice, and system prompt are all aligned to that language.

**Acceptance Scenarios**:

1. **Given** a language is selected via `--lang`, **When** the system starts, **Then** the STT backend matches the language, the TTS voice speaks that language, and the LLM system prompt instructs responses in that language
2. **Given** Moonshine is selected via `--stt moonshine` but the language is not supported, **When** the system starts, **Then** a clear error message lists supported languages for Moonshine

---

### Edge Cases

- If the selected STT backend does not support the requested language, a clear error is shown at startup listing supported languages for that backend (FR-012)
- If `--stt` is not set and the language is not in Moonshine's supported set, faster-whisper is used automatically (FR-009)
- When `--voice` is explicitly set, it overrides the language-inferred default voice (FR-013)
- `--memory` works with any language — the LLM naturally processes memory extraction in the active language since the system prompt includes the language instruction

## Clarifications

### Session 2026-04-16

- Q: Italian STT not available in Moonshine — add fallback? → A: Use faster-whisper as automatic fallback for unsupported STT languages (user chose option B)
- Q: faster-whisper model size? → A: Base model (user specified during spec discussion)
- Q: Edge cases resolved → A: faster-whisper auto-fallback, TTS defaults to English with warning for unmapped languages, --voice overrides language-inferred voice, --memory works naturally in any language
- Q: STT backend architecture? → A: STT is configurable via `--stt` flag. Auto-select: Moonshine if language is supported, else faster-whisper. Explicit `--stt` overrides auto-selection. Pluggable for future backends.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Voice Loop MUST accept a `--lang` CLI flag that sets the language for the entire voice pipeline (STT, LLM, TTS)
- **FR-002**: The `--lang` flag MUST default to `en` (English), preserving existing behavior when absent
- **FR-003**: When `--lang` is set, the STT engine MUST load and use the appropriate language model for transcription
- **FR-004**: When `--lang` is set, the TTS engine MUST select a voice and language code appropriate for that language
- **FR-005**: When `--lang` is set, the LLM system prompt MUST include an instruction to respond in the selected language
- **FR-006**: Voice Loop MUST support at minimum the following languages where both STT and TTS are available: English (`en`), Spanish (`es`), Japanese (`ja`), French (`fr`)
- **FR-007**: Voice Loop MUST accept a `--stt` CLI flag to select the STT backend; valid values include at minimum `whisper` and `moonshine`; the flag MUST be extensible for future backends
- **FR-008**: When `--stt` is explicitly set, the selected backend MUST be used regardless of language
- **FR-009**: When `--stt` is NOT set, the system MUST select the STT backend automatically based on language: use Moonshine if it supports the requested language, otherwise fall back to faster-whisper
- **FR-010**: faster-whisper MUST support 99+ languages using the `base` model size
- **FR-011**: Moonshine MUST support `en`, `ar`, `es`, `ja`, `ko`, `vi`, `uk`, `zh`
- **FR-012**: If the selected STT backend (whether explicit or auto-selected) does not support the requested language, the system MUST print a clear error at startup listing supported languages for that backend
- **FR-013**: The `--voice` flag MUST continue to work as an override — if explicitly set, it takes precedence over the language-inferred default voice
- **FR-014**: The `--lang` flag MUST be documented in the CLI help text with a list of supported language codes
- **FR-015**: Language selection MUST NOT break existing functionality: VAD, Smart Turn, AEC, chime, memory, recording — all must continue to work regardless of language
- **FR-016**: The SOUL.md persona MUST remain editable by the user; the language instruction MUST be appended to the system prompt without modifying SOUL.md

### Key Entities

- **Language**: A language code (ISO 639-1 two-letter), associated default TTS voice name, and TTS language code. The built-in language map defines the mapping between language codes and component configurations.
- **STT Backend**: A pluggable transcription engine identified by name (e.g., `whisper`, `moonshine`). Each backend has its own set of supported languages and loading/initialization procedure. The `--stt` flag selects the active backend at startup.
- **Language Profile**: The resolved configuration for a given language: active STT backend and model, TTS voice, TTS lang code, and LLM language instruction. Computed at startup from the language map plus any CLI overrides.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can complete a full voice turn (speak → transcription → LLM response → TTS playback) in Italian with a single `--lang` flag, with all components operating in Italian
- **SC-002**: Running without `--lang` produces identical behavior to the pre-feature version (zero regression on English)
- **SC-003**: Users see a clear, actionable error message when selecting a language not supported by any component
- **SC-004**: The startup sequence clearly indicates which STT backend, language, and TTS voice are active (e.g., "STT: whisper (base), TTS: Spanish (ef_rosa), LLM: Spanish")

## Assumptions

- faster-whisper and Moonshine are the two supported STT backends. When `--stt` is not set, the backend is chosen automatically: Moonshine if it supports the requested language, otherwise faster-whisper. The architecture is pluggable to allow future backends (e.g., Gemma-4-E4B multimodal transcription).
- faster-whisper uses CTranslate2 for efficient CPU/CUDA inference and supports 99+ languages. The `base` model size is used, balancing speed and accuracy for real-time voice use.
- Moonshine STT supports a limited set of languages (`en`, `ar`, `es`, `ja`, `ko`, `vi`, `uk`, `zh`) and is preferred for those languages when `--stt` is not explicitly set
- The LLM (Gemma 4) natively supports 140+ languages, so language-specific LLM behavior is controlled only via the system prompt, not via model selection
- Smart Turn endpoint detection works reasonably across languages without language-specific tuning (it is a prosodic classifier)
- Silero VAD is language-agnostic and requires no changes
- The existing `--voice` flag remains the mechanism for advanced voice customization; `--lang` selects a sensible default voice
- Kokoro TTS voice files include voices for all mapped languages; if a voice is missing, the system will fail with a clear error at TTS load time
- Users can still manually set `--voice` to override the language-default voice for fine-grained control
