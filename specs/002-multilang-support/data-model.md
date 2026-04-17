# Data Model: Multilanguage STT & TTS Support

## Entities

### LanguageConfig

Represents a language's configuration for all voice pipeline components.

| Field | Type | Description |
|-------|------|-------------|
| code | string (ISO 639-1) | Language identifier (e.g., `it`, `es`, `en`) |
| tts_voice | string | Default Kokoro voice name (e.g., `if_sara`, `ef_dora`) |
| tts_lang | string | Kokoro lang code (e.g., `it`, `es`, `en-us`) |
| llm_language | string | Full language name for LLM prompt (e.g., `Italian`, `Spanish`) |
| moonshine_supported | boolean | Whether Moonshine has an STT model for this language |

**Identity**: `code` is the primary key.

**Default instances** (built into `voice_loop.py`):
- `en`: voice=`af_heart`, lang=`en-us`, llm=`English`, moonshine=True
- `es`: voice=`ef_dora`, lang=`es`, llm=`Spanish`, moonshine=True
- `ja`: voice=`jf_alpha`, lang=`ja`, llm=`Japanese`, moonshine=True
- `fr`: voice=`ff_siwis`, lang=`fr-fr`, llm=`French`, moonshine=False
- `it`: voice=`if_sara`, lang=`it`, llm=`Italian`, moonshine=False
- `pt`: voice=`pf_dora`, lang=`pt-br`, llm=`Portuguese`, moonshine=False
- `zh`: voice=`zf_xiaobei`, lang=`cmn`, llm=`Chinese`, moonshine=True
- `de`: voice=`af_heart`, lang=`en-us`, llm=`German`, moonshine=False

### STTBackend

Represents a pluggable STT engine.

| Field | Type | Description |
|-------|------|-------------|
| name | string | Backend identifier (`whisper`, `moonshine`) |
| supported_languages | set[str] | ISO 639-1 codes this backend can transcribe |
| load_function | callable | Function to initialize the model |
| transcribe_function | callable | Function to transcribe audio to text |

**Identity**: `name` is the primary key.

**Instances**:
- `whisper`: languages=99+ (all Whisper languages), uses `faster_whisper.WhisperModel`
- `moonshine`: languages={en, ar, es, ja, ko, vi, uk, zh}, uses `moonshine_voice.Transcriber`

### ResolvedProfile

The computed configuration for a single Voice Loop run.

| Field | Type | Description |
|-------|------|-------------|
| language | LanguageConfig | The active language configuration |
| stt_backend | STTBackend | The active STT backend (auto-selected or explicit via `--stt`) |
| voice_override | string or None | User's explicit `--voice` value (overrides language default) |

**Lifecycle**: Computed once at startup from `--lang`, `--stt`, `--voice`, and built-in defaults. Immutable after creation.

## Relationships

```
ResolvedProfile ──1:1──> LanguageConfig
ResolvedProfile ──1:1──> STTBackend
```

## State Transitions

```
CLI args → resolve_language() → LanguageConfig lookup → resolve_stt_backend() → STTBackend selection → ResolvedProfile
                                                                                                    ↓
                                                                                          load STT model
                                                                                          configure TTS voice
                                                                                          append LLM language instruction
                                                                                          run voice loop
```

## Validation Rules

- If `stt_backend.name == "moonshine"` and `language.code not in moonshine.supported_languages`: ERROR at startup
- If `language.code` is not in the built-in map: use faster-whisper for STT, English TTS voice, LLM language name = code; print warning
- If `--voice` is explicitly set: use that voice regardless of language default
