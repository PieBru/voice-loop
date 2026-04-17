# Research: Multilanguage STT & TTS Support

## R1: faster-whisper Integration

**Decision**: Use `faster-whisper` (v1.2.1) with CTranslate2 backend, `base` model size.

**Rationale**:
- `faster-whisper` accepts numpy float32 arrays directly at 16kHz — no format conversion needed
- `base` model is ~145 MB download (cached in `~/.cache/huggingface/hub/`)
- No PyTorch dependency (uses CTranslate2 standalone C++ engine)
- Supports 99 languages with ISO 639-1 codes (including `it` for Italian)
- Transcription is lazy (generator) — materialize with `list()` or join segments
- Auto-downloads from `Systran/faster-whisper-base` on HuggingFace

**Python API**:
```python
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = model.transcribe(audio_float32, language="it", beam_size=5)
text = " ".join(seg.text.strip() for seg in segments).strip()
```

**New dependency chain** (~70 MB install):
- `faster-whisper` ~1.1 MB
- `ctranslate2` ~37 MB
- `av` (PyAV) ~30-40 MB
- All other deps (numpy, onnxruntime, huggingface-hub, tokenizers, tqdm) already installed

## R2: STT Backend Abstraction

**Decision**: Pluggable `transcribe()` function inside `main()` that dispatches based on `args.stt`.

**Rationale**:
- Current code has a `transcribe(audio_data)` closure inside `main()` at line 411
- Replace with a function that checks the active STT backend and calls the appropriate engine
- Moonshine path: existing `moonshine.transcribe_without_streaming()` call
- Whisper path: new `WhisperModel.transcribe()` call
- Both take numpy float32 audio and return a text string
- The `--stt` flag and auto-selection logic determine which path is taken

**Auto-selection logic** (when `--stt` is not explicitly set):
```
MOONSHINE_LANGS = {"en", "ar", "es", "ja", "ko", "vi", "uk", "zh"}
if args.lang in MOONSHINE_LANGS:
    use Moonshine
else:
    use faster-whisper
```

## R3: Language Map Structure

**Decision**: Built-in `_LANG_MAP` dict in `voice_loop.py`, optionally overridable via `config.yaml`.

**Rationale**:
- Each language entry maps to: default TTS voice, TTS lang code, LLM language name
- Moonshine language support is a simple set lookup (`MOONSHINE_LANGS`)
- `config.yaml` can override default voices or add new language entries
- Same pattern as existing `_DEFAULT_ALIASES` for model aliases

**Built-in language map**:
| Code | TTS Voice | TTS Lang | LLM Language | Moonshine? |
|------|-----------|----------|--------------|------------|
| en | af_heart | en-us | English | Yes |
| es | ef_dora | es | Spanish | Yes |
| ja | jf_alpha | ja | Japanese | Yes |
| fr | ff_siwis | fr-fr | French | No |
| it | if_sara | it | Italian | No |
| pt | pf_dora | pt-br | Portuguese | No |
| zh | zf_xiaobei | cmn | Chinese | Yes |
| de | af_heart | en-us | German | No |

Languages without a native Kokoro voice (e.g., German, Korean) default to `af_heart` (English) with a startup warning.

## R4: Italian TTS Voices

**Decision**: Default Italian voice is `if_sara` (female). Alternative: `im_nicola` (male).

**Rationale**:
- Kokoro voices-v1.0.bin contains exactly 2 Italian voices: `if_sara` and `im_nicola`
- The `_lang_from_voice()` function already maps prefix `i` → `"it"`
- No changes needed to Kokoro integration — just set `--voice if_sara` when `--lang it`

## R5: faster-whisper Model Download and Caching

**Decision**: Use faster-whisper's built-in HuggingFace download. No custom download logic needed.

**Rationale**:
- `WhisperModel("base")` auto-downloads `Systran/faster-whisper-base` to HF cache
- Same caching mechanism as existing model downloads (kokoro, smart-turn)
- First-run message: "Downloading Whisper base model (~145MB)..."
- Subsequent runs use cache instantly

## R6: LLM Language Instruction

**Decision**: Append a single line to the system prompt when `--lang` is not `en`.

**Rationale**:
- The `load_system_prompt()` function loads SOUL.md (+ MEMORY.md)
- Append instruction in `main()` after loading: `"You MUST respond in {language_name}. Never use English unless the user explicitly asks for it."`
- This is a runtime append — SOUL.md is never modified (per FR-014)
- Gemma 4 natively supports 140+ languages, so no model change needed
