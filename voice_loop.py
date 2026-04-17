#!/usr/bin/env python3
"""Voice Loop — a minimal on-device voice agent.

macOS (Apple Silicon): Moonshine (CPU) transcribes, Gemma 4 E4B (Metal)
responds, Kokoro TTS speaks, WebRTC AEC3 enables voice interrupt.
Linux (NVIDIA CUDA): Same pipeline via llama.cpp server (OpenAI-compatible API).
Multilanguage: --lang it (Italian), --lang es (Spanish), 99+ languages via Whisper.

Usage:
    uv run voice_loop.py                        # defaults (TTS + smart turn + AEC)
    uv run voice_loop.py --lang it              # Italian (Whisper STT + Italian TTS)
    uv run voice_loop.py --lang es              # Spanish (Moonshine STT + Spanish TTS)
    uv run voice_loop.py --tts qwen             # Qwen3-TTS (CUDA, higher quality)
    uv run voice_loop.py --no-tts               # text out only
    uv run voice_loop.py --no-aec               # keypress interrupt only
    uv run voice_loop.py --chime                # chime + ticks while generating
    uv run voice_loop.py --memory               # persistent memory (MEMORY.md)
    uv run voice_loop.py --stt whisper           # force Whisper STT for any language
"""

import argparse
import asyncio
import ctypes.util
import json
import os
import queue
import select
import subprocess
import sys
import tempfile
import termios
import time as _time
import tty
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import sounddevice as sd

sd.default.latency = "high"
import torch

IS_DARWIN = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512  # 32ms at 16kHz (required by Silero VAD)
MAX_HISTORY = 10
CHIME_SR = 24000
_DIR = Path(__file__).parent


def load_system_prompt(include_memory: bool = False) -> str:
    names = ("SOUL.md", "MEMORY.md") if include_memory else ("SOUL.md",)
    parts = [(_DIR / n).read_text().strip() for n in names if (_DIR / n).exists()]
    return "\n\n".join(p for p in parts if p)


def _fade_tone(freq, dur, amp=0.6):
    """Tone with raised-cosine (Hann) envelope — smooth fade in/out, no clicks."""
    n = int(dur * CHIME_SR)
    t = np.linspace(0, dur, n, dtype=np.float32)
    env = 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / (n - 1)))
    return amp * np.sin(2 * np.pi * freq * t) * env


def _silence(dur):
    return np.zeros(int(dur * CHIME_SR), dtype=np.float32)


def make_chime(duration=30.0, tick_every=1.5):
    """Two-tone chime + periodic short ticks. Single buffer → one sd.play()."""
    head = np.concatenate(
        [_fade_tone(880, 0.09), _silence(0.03), _fade_tone(1320, 0.10)]
    )
    # Short soft click-style tick (shorter and quieter than a beep)
    tick = _fade_tone(550, 0.04, amp=0.18)
    total = int(duration * CHIME_SR)
    buf = np.zeros(total, dtype=np.float32)
    buf[: len(head)] = head
    step = int(tick_every * CHIME_SR)
    for pos in range(len(head), total, step):
        end = min(pos + len(tick), total)
        buf[pos:end] = tick[: end - pos]
    return buf


def _lang_from_voice(v: str) -> str:
    """Infer Kokoro lang code from voice prefix.
    Voice format: {lang}{gender}_{name}, e.g. if_sara = Italian Female sara.
    a = US English, b = UK English, e = Spanish, f = French,
    h = Hindi, i = Italian, j = Japanese, p = Portuguese, z = Chinese."""
    prefix = v[0] if v else ""
    return {
        "a": "en-us",
        "b": "en-gb",
        "e": "es",
        "f": "fr-fr",
        "h": "hi",
        "i": "it",
        "j": "ja",
        "p": "pt-br",
        "z": "cmn",
    }.get(prefix, "en-us")


def save_wav(audio, sr=SAMPLE_RATE):
    path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes())
    return path


def load_smart_turn():
    import onnxruntime as ort
    from transformers import WhisperFeatureExtractor

    model_path = os.path.join(
        tempfile.gettempdir(), "smart_turn_v3", "smart_turn_v3.2_cpu.onnx"
    )
    if not os.path.exists(model_path):
        print("Downloading Smart Turn v3.2 model...", flush=True)
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import urllib.request

        urllib.request.urlretrieve(
            "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx",
            model_path,
        )
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    extractor = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")

    def predict(audio_float32: np.ndarray) -> float:
        max_samples = 8 * SAMPLE_RATE
        audio_float32 = audio_float32[-max_samples:]
        features = extractor(
            audio_float32,
            sampling_rate=SAMPLE_RATE,
            max_length=max_samples,
            padding="max_length",
            return_attention_mask=False,
            return_tensors="np",
        )
        return float(
            session.run(
                None, {"input_features": features.input_features.astype(np.float32)}
            )[0].flatten()[0]
        )

    return predict


def _vad_prob(vad, chunk):
    p = vad(torch.from_numpy(chunk), SAMPLE_RATE)
    return p.item() if hasattr(p, "item") else p


def _get_ref_segment(tts_concat, pos, length):
    if pos >= len(tts_concat):
        return np.zeros(length, dtype=np.float32)
    seg = tts_concat[pos : pos + length]
    return (
        np.concatenate([seg, np.zeros(length - len(seg), dtype=np.float32)])
        if len(seg) < length
        else seg
    )


_DEFAULT_ALIASES = {
    "gemma-4-e4b": {
        "darwin": {"repo": "mlx-community/gemma-4-E4B-it-4bit"},
        "linux": {"api_base": "http://localhost:8088/v1", "model": "Gemma4-E4B"},
    },
    "gemma-4-26b": {
        "darwin": {"repo": "mlx-community/gemma-4-E4B-it-4bit"},
        "linux": {"api_base": "http://localhost:8088/v1", "model": "Gemma4-26B"},
    },
    "gemma-4-e2b": {
        "darwin": {"repo": "mlx-community/gemma-4-E2B-it-4bit"},
        "linux": {"api_base": "http://localhost:8088/v1", "model": "Gemma4-E4B"},
    },
}


MOONSHINE_LANGS = frozenset({"en", "ar", "es", "ja", "ko", "vi", "uk", "zh"})

_LANG_MAP = {
    "en": {"tts_voice": "af_heart", "tts_lang": "en-us", "llm_language": "English"},
    "es": {"tts_voice": "ef_dora", "tts_lang": "es", "llm_language": "Spanish"},
    "ja": {"tts_voice": "jf_alpha", "tts_lang": "ja", "llm_language": "Japanese"},
    "fr": {"tts_voice": "ff_siwis", "tts_lang": "fr-fr", "llm_language": "French"},
    "it": {"tts_voice": "if_sara", "tts_lang": "it", "llm_language": "Italian"},
    "pt": {"tts_voice": "pf_dora", "tts_lang": "pt-br", "llm_language": "Portuguese"},
    "zh": {"tts_voice": "zf_xiaobei", "tts_lang": "cmn", "llm_language": "Chinese"},
    "de": {"tts_voice": "af_heart", "tts_lang": "de", "llm_language": "German"},
}

_QWEN_SPEAKER_MAP = {
    "en": {"speaker": "Ryan", "language": "English"},
    "zh": {"speaker": "Vivian", "language": "Chinese"},
    "ja": {"speaker": "Ono_Anna", "language": "Japanese"},
    "ko": {"speaker": "Sohee", "language": "Korean"},
    "es": {"speaker": "Ryan", "language": "Spanish"},
    "fr": {"speaker": "Ryan", "language": "French"},
    "it": {"speaker": "Ryan", "language": "Italian"},
    "pt": {"speaker": "Ryan", "language": "Portuguese"},
    "de": {"speaker": "Ryan", "language": "German"},
    "ru": {"speaker": "Ryan", "language": "Russian"},
}

_QWEN_TTS_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"


def _patch_qwen_tts_compat():
    import transformers.utils.generic as _g

    _orig = _g.check_model_inputs

    def _wrapper(func=None):
        return _orig(func) if func is not None else _orig

    _g.check_model_inputs = _wrapper


_HANDLER_DEFAULTS = {
    "llm": {"description": "Direct LLM API call (default)"},
    "agentic": {
        "description": "External agentic service (configurable endpoint)",
        "api_base": "http://localhost:8089/v1",
        "model": "agentic",
        "timeout": 60,
    },
    "zeroclaw": {
        "description": "ZeroClaw personal AI assistant (webhook)",
        "api_base": "http://127.0.0.1:42617",
        "token": "",
        "timeout": 120,
    },
}


def load_model_aliases(config_path=None):
    path = Path(config_path) if config_path else _DIR / "config.yaml"
    if path.exists():
        try:
            import yaml

            data = yaml.safe_load(path.read_text())
            if data and "models" in data:
                return data["models"]
        except Exception:
            pass
    return _DEFAULT_ALIASES


def resolve_model(alias, platform_name):
    aliases = load_model_aliases()
    if alias in aliases:
        entry = aliases[alias].get(platform_name)
        if not entry:
            print(
                f"Error: Model '{alias}' is not available on {platform_name}. "
                "Use a different model or alias."
            )
            sys.exit(1)
        return entry
    return None


def resolve_language(lang_code):
    lang_map = dict(_LANG_MAP)
    config_path = _DIR / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            data = yaml.safe_load(config_path.read_text())
            if data and "languages" in data:
                for code, entry in data["languages"].items():
                    lang_map.setdefault(code, {}).update(entry)
        except Exception:
            pass
    if lang_code in lang_map:
        return lang_map[lang_code]
    print(
        f"Warning: Language '{lang_code}' not in built-in map. "
        "Using whisper STT with English TTS voice.",
        file=sys.stderr,
    )
    return {
        "tts_voice": "af_heart",
        "tts_lang": lang_code,
        "llm_language": lang_code,
    }


def load_handler_config():
    handlers = {}
    for name, defaults in _HANDLER_DEFAULTS.items():
        handlers[name] = dict(defaults)
    config_path = _DIR / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            data = yaml.safe_load(config_path.read_text())
            if data and "handlers" in data:
                for name, entry in data["handlers"].items():
                    if name in handlers:
                        handlers[name].update(entry)
                    else:
                        handlers[name] = entry
        except Exception:
            pass
    return handlers


def check_linux_deps():
    try:
        import sounddevice
    except ImportError:
        print("Error: PortAudio not found. Install with: pacman -S portaudio")
        sys.exit(1)
    lib = ctypes.util.find_library("espeak-ng")
    if not lib and IS_DARWIN:
        try:
            subprocess.check_output(["brew", "--prefix", "espeak-ng"], text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("Error: espeak-ng not found. Install with: brew install espeak-ng")
            sys.exit(1)
    elif not lib:
        print("Error: espeak-ng not found. Install with: pacman -S espeak-ng")
        sys.exit(1)


def _print_language_table():
    import tempfile

    cache_dir = os.path.join(tempfile.gettempdir(), "kokoro_tts")
    voices_file = os.path.join(cache_dir, "voices-v1.0.bin")
    if not os.path.exists(voices_file):
        print("Kokoro voices not downloaded yet. Run voice_loop.py once first.")
        return
    import numpy as np

    voices = sorted(np.load(voices_file).keys())
    prefix_lang = {
        "a": ("en-us", "English (US)", None),
        "b": ("en-gb", "English (UK)", None),
        "e": ("es", "Spanish", None),
        "f": ("fr-fr", "French", None),
        "h": ("hi", "Hindi", None),
        "i": ("it", "Italian", None),
        "j": ("ja", "Japanese", None),
        "p": ("pt-br", "Portuguese", None),
        "z": ("cmn", "Chinese", "zh"),
    }
    _tts_to_stt_code = {"cmn": "zh"}
    by_prefix = {}
    for v in voices:
        p = v[0]
        by_prefix.setdefault(p, []).append(v)
    print(f"{'Lang':<12} {'Code':<6} {'STT':<10} Voices")
    print("-" * 70)
    for prefix in sorted(by_prefix.keys()):
        entry = prefix_lang.get(prefix, ("??", f"Unknown ({prefix})", None))
        code, name = entry[0], entry[1]
        stt_code = _tts_to_stt_code.get(code, code.split("-")[0])
        stt = "moonshine" if stt_code in MOONSHINE_LANGS else "whisper"
        voice_list = ", ".join(by_prefix[prefix])
        print(f"{name:<12} {code:<6} {stt:<10} {voice_list}")
    print(f"\nTotal: {len(voices)} voices across {len(by_prefix)} languages")
    print("faster-whisper supports 99+ languages for transcription")


def _print_qwen_speaker_table():
    print(f"{'Lang':<12} {'Code':<6} {'Speaker':<12} Language Name")
    print("-" * 60)
    for code in sorted(_QWEN_SPEAKER_MAP.keys()):
        info = _QWEN_SPEAKER_MAP[code]
        native = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}
        lang_name = native.get(code, f"{info['language']} (via Ryan)")
        print(f"{lang_name:<12} {code:<6} {info['speaker']:<12} {info['language']}")
    print(f"\nTotal: {len(_QWEN_SPEAKER_MAP)} language mappings")
    print("CustomVoice model has 9 built-in speakers")
    print("Use --voice <SpeakerName> to select a specific speaker")


def _print_handler_table():
    handlers = load_handler_config()
    print(f"{'Handler':<12} Description")
    print("-" * 50)
    for name in sorted(handlers.keys()):
        desc = handlers[name].get("description", "")
        if name == "llm" and "(default)" not in desc:
            desc += " (default)"
        print(f"{name:<12} {desc}")


def main():
    ap = argparse.ArgumentParser(
        description="Voice Loop — a minimal on-device voice agent"
    )
    ap.add_argument(
        "--no-tts",
        action="store_false",
        dest="tts_enabled",
        help="Disable TTS output",
    )
    ap.add_argument(
        "--no-smart-turn",
        action="store_false",
        dest="smart_turn",
        help="Disable Smart Turn v3 endpoint detection",
    )
    ap.add_argument(
        "--no-aec",
        action="store_false",
        dest="aec",
        help="Disable WebRTC AEC3 voice interrupt",
    )
    ap.add_argument(
        "--no-chime",
        action="store_false",
        dest="chime",
        help="Disable chime on utterance + soft ticks while generating",
    )
    ap.set_defaults(tts_enabled=True, smart_turn=True, aec=True, chime=True)
    ap.add_argument(
        "--memory",
        action="store_true",
        help="Read/write MEMORY.md (auto-update durable facts, consolidate every 5 turns)",
    )
    ap.add_argument(
        "--audio-mode",
        action="store_true",
        help="Use the LLM endpoint for STT (experimental)",
    )
    ap.add_argument(
        "--model",
        default="gemma-4-e4b",
        help="Model alias or HuggingFace repo ID (default: gemma-4-e4b)",
    )
    ap.add_argument(
        "--silence-ms",
        type=int,
        default=700,
        help="Silence duration before end-of-turn in ms (default: 700)",
    )
    ap.add_argument(
        "--record",
        nargs="?",
        const="",
        metavar="FILE",
        help="Record mic to WAV for debugging (default: tmp/recording-TIMESTAMP.wav)",
    )
    ap.add_argument(
        "--lang",
        default="en",
        help="Language code for STT/LLM/TTS pipeline (default: en)",
    )
    ap.add_argument(
        "--voice",
        default=None,
        help="TTS voice/speaker (default: language-appropriate)",
    )
    ap.add_argument(
        "--stt",
        default=None,
        choices=["whisper", "moonshine"],
        help="STT backend (default: auto-select based on language)",
    )
    ap.add_argument(
        "--whisper-device",
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device for faster-whisper inference (default: cpu)",
    )
    ap.add_argument(
        "--tts",
        default="kokoro",
        choices=["kokoro", "qwen"],
        help="TTS backend (default: kokoro)",
    )
    ap.add_argument(
        "--handler",
        default="llm",
        help="Response generation handler (default: llm)",
    )
    ap.add_argument(
        "--list-handlers",
        action="store_true",
        help="List available response handlers and exit",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Skip all network access, use only cached models (default: off)",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="List available TTS voices by language and exit",
    )
    args = ap.parse_args()
    if args.tts == "qwen" and IS_DARWIN:
        print("Error: --tts qwen requires CUDA (Linux NVIDIA GPU only).")
        sys.exit(1)
    if args.list:
        if args.tts == "qwen":
            _print_qwen_speaker_table()
        else:
            _print_language_table()
        sys.exit(0)
    if args.list_handlers:
        _print_handler_table()
        sys.exit(0)
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    if args.audio_mode and IS_LINUX:
        print(
            "Error: --audio-mode is not supported on Linux (requires MLX multimodal input)."
        )
        sys.exit(1)
    if args.record == "":
        tmp_dir = _DIR / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        args.record = str(tmp_dir / f"recording-{_time.strftime('%Y%m%d-%H%M%S')}.wav")
    silence_limit = max(1, int(args.silence_ms / (CHUNK_SAMPLES / SAMPLE_RATE * 1000)))

    _lang_cfg = resolve_language(args.lang)
    if args.stt:
        _stt_backend = args.stt
    elif args.lang in MOONSHINE_LANGS:
        _stt_backend = "moonshine"
    else:
        _stt_backend = "whisper"

    if args.stt == "moonshine" and args.lang not in MOONSHINE_LANGS:
        print(
            f"Error: Moonshine does not support language '{args.lang}'. "
            f"Supported: {', '.join(sorted(MOONSHINE_LANGS))}. "
            f"Use --stt whisper for {_lang_cfg['llm_language']}."
        )
        sys.exit(1)

    if args.voice is None:
        if args.tts == "qwen":
            qinfo = _QWEN_SPEAKER_MAP.get(args.lang)
            if qinfo:
                args.voice = qinfo["speaker"]
            else:
                print(
                    f"Warning: No QwenTTS speaker for '{args.lang}', using Ryan.",
                    file=sys.stderr,
                )
                args.voice = "Ryan"
        else:
            args.voice = _lang_cfg["tts_voice"]

    _handler_cfg = load_handler_config()
    _active_handler = args.handler
    if _active_handler not in _handler_cfg:
        print(
            f"Error: Unknown handler '{_active_handler}'. "
            f"Available: {', '.join(sorted(_handler_cfg.keys()))}."
        )
        sys.exit(1)

    print("Loading Silero VAD...", flush=True)
    from silero_vad import load_silero_vad

    vad = load_silero_vad(onnx=True)
    _whisper_model = None
    moonshine = None
    if _stt_backend == "whisper":
        print(
            f"Loading Whisper base / {args.whisper_device} (transcription)...",
            flush=True,
        )
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            "base", device=args.whisper_device, compute_type="int8"
        )
    else:
        print("Loading Moonshine (transcription)...", flush=True)
        from moonshine_voice import Transcriber, get_model_for_language

        ms_path, ms_arch = get_model_for_language(args.lang)
        moonshine = Transcriber(model_path=str(ms_path), model_arch=ms_arch)
    print(f"Loading {args.model}...", flush=True)
    if IS_DARWIN:
        from mlx_vlm import load, generate

        entry = resolve_model(args.model, "darwin")
        repo_id = entry["repo"] if entry else args.model
        model, processor = load(repo_id)
    else:
        check_linux_deps()
        entry = resolve_model(args.model, "linux")
        _llm_api_base = entry["api_base"] if entry else "http://localhost:8088/v1"
        _llm_model = entry["model"] if entry else args.model
        try:
            with urllib.request.urlopen(f"{_llm_api_base}/models", timeout=5) as resp:
                models_data = json.loads(resp.read())
            model_statuses = {
                m["id"]: m["status"]["value"] for m in models_data.get("data", [])
            }
            if _llm_model not in model_statuses:
                print(
                    f"Error: Model '{_llm_model}' not found on server. "
                    f"Available: {', '.join(sorted(model_statuses.keys()))}"
                )
                sys.exit(1)
            status = model_statuses[_llm_model]
            if status == "loading":
                print(f"  Model {_llm_model} is loading, please wait...", flush=True)
                for _ in range(120):
                    _time.sleep(2)
                    with urllib.request.urlopen(
                        f"{_llm_api_base}/models", timeout=5
                    ) as r:
                        st = {
                            m["id"]: m["status"]["value"]
                            for m in json.loads(r.read()).get("data", [])
                        }
                    if st.get(_llm_model) != "loading":
                        status = st.get(_llm_model, status)
                        break
                if status == "loading":
                    print(
                        f"Error: Model {_llm_model} still loading after 4 minutes. Aborting."
                    )
                    sys.exit(1)
            elif status not in ("loaded", "ready", "sleeping", "idle"):
                print(f"  Warning: Model {_llm_model} status is '{status}'.")
        except urllib.error.URLError:
            print(
                f"Error: Cannot reach inference API at {_llm_api_base}. "
                "Is llama.cpp server running?"
            )
            sys.exit(1)
        except Exception as exc:
            print(f"Error checking inference API: ({type(exc).__name__}: {exc})")
            sys.exit(1)
        print(f"  Using {_llm_model} via {_llm_api_base}", flush=True)
    if _active_handler == "agentic":
        _agentic_api = _handler_cfg.get("agentic", {}).get(
            "api_base", "http://localhost:8089/v1"
        )
        try:
            urllib.request.urlopen(f"{_agentic_api}/models", timeout=5)
        except Exception:
            print(
                f"Warning: Agentic handler endpoint {_agentic_api} unreachable. "
                "Falling back to llm handler.",
                file=sys.stderr,
            )
            _active_handler = "llm"
    if _active_handler == "zeroclaw":
        _zc_api = _handler_cfg.get("zeroclaw", {}).get(
            "api_base", "http://127.0.0.1:42617"
        )
        try:
            urllib.request.urlopen(f"{_zc_api}/status", timeout=5)
        except Exception:
            print(
                f"Warning: ZeroClaw gateway {_zc_api} unreachable. "
                "Falling back to llm handler.",
                file=sys.stderr,
            )
            _active_handler = "llm"
    smart_turn = load_smart_turn() if args.smart_turn else None
    kokoro = None
    qwen_tts_model = None
    qwen_tts_tokenizer = None
    if args.tts == "kokoro" and args.tts_enabled:
        print("Loading Kokoro TTS...", flush=True)
        import subprocess

        try:
            lib = ctypes.util.find_library("espeak-ng")
            if lib:
                os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", lib)
            elif IS_DARWIN:
                prefix = subprocess.check_output(
                    ["brew", "--prefix", "espeak-ng"], text=True
                ).strip()
                os.environ.setdefault(
                    "PHONEMIZER_ESPEAK_LIBRARY", f"{prefix}/lib/libespeak-ng.dylib"
                )
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        from kokoro_onnx import Kokoro

        cache_dir = os.path.join(tempfile.gettempdir(), "kokoro_tts")
        model_file = os.path.join(cache_dir, "kokoro-v1.0.onnx")
        voices_file = os.path.join(cache_dir, "voices-v1.0.bin")
        if not os.path.exists(model_file):
            os.makedirs(cache_dir, exist_ok=True)

            base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
            print("  Downloading kokoro model (~300MB)...", flush=True)
            urllib.request.urlretrieve(f"{base}/kokoro-v1.0.onnx", model_file)
            urllib.request.urlretrieve(f"{base}/voices-v1.0.bin", voices_file)
        kokoro = Kokoro(model_file, voices_file)
    elif args.tts == "qwen" and args.tts_enabled:
        print("Loading QwenTTS...", flush=True)
        _patch_qwen_tts_compat()
        from qwen_tts import Qwen3TTSModel, Qwen3TTSTokenizer

        print(f"  Loading {_QWEN_TTS_MODEL_ID} (~3.4GB on first run)...", flush=True)
        qwen_tts_tokenizer = Qwen3TTSTokenizer.from_pretrained(_QWEN_TTS_MODEL_ID)
        qwen_tts_model = Qwen3TTSModel.from_pretrained(
            _QWEN_TTS_MODEL_ID,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )
        speakers = qwen_tts_model.get_supported_speakers()
        print(f"  QwenTTS loaded: {len(speakers)} speakers", flush=True)

    make_aec_processor = None
    if args.aec:
        from livekit.rtc import AudioFrame
        from livekit.rtc.apm import AudioProcessingModule

        WF = 160  # 10ms @ 16kHz

        def _to_i16(x):
            s = (x * 32767).clip(-32768, 32767).astype(np.int16)
            return np.pad(s, (0, max(0, WF - len(s)))) if len(s) < WF else s

        def _frame(b):
            return AudioFrame(
                b.tobytes(),
                sample_rate=SAMPLE_RATE,
                num_channels=1,
                samples_per_channel=WF,
            )

        def make_aec_processor():
            apm = AudioProcessingModule(echo_cancellation=True, noise_suppression=True)

            def process(mic, ref):
                cleaned = np.zeros_like(mic)
                for i in range(0, len(mic), WF):
                    mic_f = _frame(_to_i16(mic[i : i + WF]))
                    apm.process_reverse_stream(_frame(_to_i16(ref[i : i + WF])))
                    apm.process_stream(mic_f)
                    cleaned[i : i + WF] = (
                        np.frombuffer(bytes(mic_f.data), dtype=np.int16).astype(
                            np.float32
                        )
                        / 32767
                    )[: len(mic[i : i + WF])]
                return cleaned

            return process

        print("  AEC: WebRTC AEC3 (LiveKit APM)")
    executor = ThreadPoolExecutor(max_workers=1)
    # --chime-loop: single buffer (chime + ticks), one sd.play call
    # --chime only: just the chime
    chime_sound = make_chime() if args.chime else None
    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    record_buf: list[np.ndarray] | None = [] if args.record else None

    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        chunk = indata[:, 0].copy()
        if record_buf is not None:
            record_buf.append(chunk)
        audio_q.put(chunk)

    def drain_audio_q():
        while not audio_q.empty():
            audio_q.get_nowait()

    def transcribe(audio_data):
        if _stt_backend == "whisper":
            segments, info = _whisper_model.transcribe(
                audio_data, language=args.lang, beam_size=5
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        return " ".join(
            l.text
            for l in moonshine.transcribe_without_streaming(
                audio_data.tolist(), SAMPLE_RATE
            ).lines
            if l.text
        ).strip()

    def _llm_handler(messages, max_tokens=200, temperature=0.7, **kwargs):
        if IS_DARWIN:
            prompt = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            r = generate(
                model,
                processor,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=1.2,
                verbose=False,
                **kwargs,
            )
            return r.text if hasattr(r, "text") else str(r)
        else:
            data = json.dumps(
                {
                    "model": _llm_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            ).encode()
            req = urllib.request.Request(
                f"{_llm_api_base}/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
            return result["choices"][0]["message"].get("content", "") or ""

    def _agentic_handler(messages, max_tokens=200, temperature=0.7, **kwargs):
        cfg = _handler_cfg.get("agentic", {})
        data = json.dumps(
            {
                "model": cfg.get("model", "agentic"),
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        ).encode()
        req = urllib.request.Request(
            f"{cfg.get('api_base', 'http://localhost:8089/v1')}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        timeout = cfg.get("timeout", 60)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"].get("content", "") or ""

    def _zeroclaw_handler(messages, max_tokens=200, temperature=0.7, **kwargs):
        cfg = _handler_cfg.get("zeroclaw", {})
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        if not user_msg:
            user_msg = messages[-1].get("content", "") if messages else ""
        payload = json.dumps({"message": user_msg, "max_tokens": max_tokens}).encode()
        headers = {"Content-Type": "application/json"}
        token = cfg.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{cfg.get('api_base', 'http://127.0.0.1:42617')}/webhook",
            data=payload,
            headers=headers,
        )
        timeout = cfg.get("timeout", 120)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        if isinstance(body, dict):
            return body.get("response", body.get("message", body.get("content", "")))
        return str(body)

    _handlers = {
        "llm": _llm_handler,
        "agentic": _agentic_handler,
        "zeroclaw": _zeroclaw_handler,
    }

    def generate_response(messages, max_tokens=200, temperature=0.7, **kwargs):
        nonlocal _active_handler
        try:
            return _handlers[_active_handler](
                messages, max_tokens=max_tokens, temperature=temperature, **kwargs
            )
        except Exception as exc:
            if _active_handler != "llm":
                print(
                    f"Warning: {_active_handler} handler failed ({exc}). "
                    "Falling back to llm handler for this session.",
                    file=sys.stderr,
                )
                _active_handler = "llm"
                return _handlers["llm"](
                    messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                )
            raise

    llm_generate = generate_response

    def speak_tts(text):
        if not text or not text.strip():
            return
        if kokoro:
            samples, sr = kokoro.create(
                text, voice=args.voice, speed=1.0, lang=_lang_cfg["tts_lang"]
            )
            sd.play(samples, sr)
            sd.wait()
        elif qwen_tts_model:
            qinfo = _QWEN_SPEAKER_MAP.get(args.lang, {})
            wavs, sr = qwen_tts_model.generate_custom_voice(
                text=text,
                language=qinfo.get("language", "English"),
                speaker=args.voice,
                non_streaming_mode=True,
            )
            sd.play(wavs[0], sr)
            sd.wait()

    _mem_path = _DIR / "MEMORY.md"

    def _read_memory():
        return _mem_path.read_text() if _mem_path.exists() else "# Memory\n"

    def _run_memory(prompt, max_tokens, temperature, label):
        try:
            return llm_generate(
                [{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            ).strip()
        except Exception as e:
            print(f"  [{label} failed: {e}]", file=sys.stderr)
            return None

    def update_memory(heard, response):
        result = _run_memory(
            f"Current memory:\n{_read_memory()}\n\n"
            f"User said: {heard}\n\n"
            "Did the user state a new durable fact about themselves? "
            "If yes, output one short fact per line starting with '- '. "
            "If no, output ONLY: NONE. Do not invent facts.",
            max_tokens=60,
            temperature=0.2,
            label="memory update",
        )
        if result and "NONE" not in result.upper():
            lines = [l for l in result.splitlines() if l.strip().startswith("-")]
            if lines:
                with open(_mem_path, "a") as f:
                    f.write("\n" + "\n".join(lines) + "\n")
                print(f"  [memory +{len(lines)}]", flush=True)

    def consolidate_memory():
        if not _mem_path.exists():
            return
        result = _run_memory(
            f"Here is a memory file about a user:\n\n{_read_memory()}\n\n"
            "Rewrite it: merge duplicates, remove transient/session-specific "
            "items (questions asked, topics discussed, tests), keep only "
            "durable facts (identity, preferences, relationships, location, "
            "ongoing projects). Output the cleaned file, starting with '# Memory' "
            "followed by bullets starting with '- '. No explanation.",
            max_tokens=300,
            temperature=0.2,
            label="memory consolidation",
        )
        if result and result.startswith("# Memory"):
            _mem_path.write_text(result + "\n")
            print("  [memory consolidated]", flush=True)

    def _sys_messages():
        sp = load_system_prompt(include_memory=args.memory)
        if args.lang != "en" and sp:
            sp += (
                f"\n\nYou MUST respond in {_lang_cfg['llm_language']}. "
                "Never use English unless the user explicitly asks for it."
            )
        return [{"role": "system", "content": sp}] if sp else []

    def _wait_for_chime_gap():
        """Wait until we're in a silent gap between ticks, so sd.stop() doesn't
        clip a tick mid-cycle (which clicks). Max wait ~40ms."""
        if chime_sound is None or chime_started_at[0] == 0:
            return
        CHIME_HEAD = 0.22  # end of chime tones in buffer
        TICK_DUR = 0.04  # tick length
        TICK_EVERY = 1.5
        t = _time.monotonic() - chime_started_at[0]
        if t < CHIME_HEAD:
            # Still in chime head; wait for end of chime then it's safe
            _time.sleep(CHIME_HEAD - t)
            return
        phase = (t - CHIME_HEAD) % TICK_EVERY
        if phase < TICK_DUR:
            # In a tick — wait until it ends
            _time.sleep(TICK_DUR - phase + 0.005)

    def play_tts_stream(response):
        drain_audio_q()
        tts_stream = kokoro.create_stream(
            response, voice=args.voice, speed=1.0, lang=_lang_cfg["tts_lang"]
        )
        out_stream, interrupted = None, False
        tts_16k_buf: list[np.ndarray] = []
        state = {"play_start": None, "consec_speech": 0, "mic_pos": 0}
        aec_process = make_aec_processor() if make_aec_processor else None

        def check_barge_in():
            if not (aec_process and state["play_start"] and tts_16k_buf):
                return False
            if _time.monotonic() - state["play_start"] < 0.5:
                return False
            tts_concat = np.concatenate(tts_16k_buf)
            while not audio_q.empty():
                mic_chunk = audio_q.get_nowait()
                if len(mic_chunk) < CHUNK_SAMPLES:
                    continue
                ref = _get_ref_segment(tts_concat, state["mic_pos"], len(mic_chunk))
                state["mic_pos"] += len(mic_chunk)
                cleaned = aec_process(mic_chunk, ref)
                if _vad_prob(vad, cleaned.astype(np.float32)) > 0.8:
                    state["consec_speech"] += 1
                    if state["consec_speech"] >= 5:
                        return True
                else:
                    state["consec_speech"] = 0
            return False

        async def _play():
            nonlocal out_stream, interrupted
            async for chunk_samples, sr in tts_stream:
                if out_stream is None:
                    if chime_sound is not None:
                        _wait_for_chime_gap()
                        sd.stop()
                    out_stream = sd.OutputStream(
                        samplerate=sr, channels=1, dtype="float32"
                    )
                    out_stream.start()
                    drain_audio_q()
                    vad.reset_states()
                    state["play_start"] = _time.monotonic()
                if aec_process is not None:
                    if sr == SAMPLE_RATE:
                        tts_16k_buf.append(chunk_samples.astype(np.float32))
                    else:
                        idx = np.arange(0, len(chunk_samples), sr / SAMPLE_RATE)
                        tts_16k_buf.append(
                            np.interp(
                                idx, np.arange(len(chunk_samples)), chunk_samples
                            ).astype(np.float32)
                        )
                data = chunk_samples.reshape(-1, 1)
                for i in range(0, len(data), 4096):
                    if select.select([sys.stdin], [], [], 0)[0]:
                        sys.stdin.read(1)
                        interrupted = True
                    elif check_barge_in():
                        interrupted = True
                        print("  [voice interrupt]", flush=True)
                    if interrupted:
                        break
                    out_stream.write(data[i : i + 4096])
                if interrupted:
                    break
            if out_stream:
                out_stream.stop()
                out_stream.close()

        asyncio.run(_play())
        if interrupted and state["consec_speech"] < 3:
            print("  [interrupted]")
        drain_audio_q()
        vad.reset_states()
        return interrupted

    def process_utterance(audio, history):
        print(f" ({len(audio) / SAMPLE_RATE:.1f}s)")
        if chime_sound is not None:
            print("  *chime*", flush=True)
            sd.play(chime_sound, CHIME_SR)
            chime_started_at[0] = _time.monotonic()
        wav_path = save_wav(audio) if args.audio_mode else None
        try:
            messages = _sys_messages()
            for h in history[-MAX_HISTORY:]:
                messages += [
                    {"role": "user", "content": h["user"]},
                    {"role": "assistant", "content": h["assistant"]},
                ]
            if args.audio_mode:
                transcribe_future = executor.submit(transcribe, audio)
                messages.append({"role": "user", "content": [{"type": "audio"}]})
            else:
                heard = transcribe(audio)
                print(f"  [{heard}]")
                messages.append({"role": "user", "content": heard})
            response = llm_generate(
                messages, **({"audio": [wav_path]} if args.audio_mode else {})
            )
            if args.audio_mode:
                heard = transcribe_future.result(timeout=10)
                print(f"  [{heard}]")
            print(f"\n> {response}\n", flush=True)
            if response:
                if kokoro:
                    play_tts_stream(response)
                elif qwen_tts_model:
                    speak_tts(response)
                elif chime_sound is not None:
                    _wait_for_chime_gap()
                    sd.stop()
            history.append({"user": heard, "assistant": response})
            if len(history) > MAX_HISTORY:
                history.pop(0)
            if args.memory:
                update_memory(heard, response)
                if len(history) % 5 == 0:
                    consolidate_memory()
        except Exception as e:
            print(f"\nError: {e}\n", file=sys.stderr)
        finally:
            if wav_path:
                os.unlink(wav_path)

    history, buf = [], []
    chime_started_at = [
        0.0
    ]  # monotonic time when last chime started (for tick-boundary TTS start)
    speaking, silent_chunks = False, 0

    # Set terminal to raw mode so keypress interrupts work without Enter
    old_term = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    mode = "audio" if args.audio_mode else "text"
    print(
        f"\nListening (lang: {args.lang}, stt: {_stt_backend}, tts: {args.tts}/{args.voice}, handler: {_active_handler}, "
        f"mode: {mode}, silence: {args.silence_ms}ms, smart-turn: {args.smart_turn})"
    )
    tts_hint = (
        (
            " Speak or press any key to interrupt TTS."
            if args.aec
            else " Press any key to interrupt TTS."
        )
        if args.tts_enabled
        else ""
    )
    print(f"Speak into your microphone. Ctrl+C to quit.{tts_hint}\n", flush=True)

    _greeting_lang = ""
    if args.lang != "en":
        _greeting_lang = f" Respond in {_lang_cfg['llm_language']}."
    greeting = llm_generate(
        _sys_messages()
        + [
            {
                "role": "user",
                "content": (
                    "Greet the user as Voice Loop in one short sentence. "
                    "If my name is in memory, use it and ask how you can help. "
                    f"Otherwise, ask for my name.{_greeting_lang}"
                ),
            },
        ],
        max_tokens=512,
    )
    print(f"> {greeting}\n", flush=True)
    if kokoro or qwen_tts_model:
        speak_tts(greeting)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
        callback=callback,
    ):
        try:
            while True:
                chunk = audio_q.get()
                if len(chunk) < CHUNK_SAMPLES:
                    continue

                speech_prob = _vad_prob(vad, chunk)
                if speech_prob > 0.5:
                    if not speaking:
                        speaking = True
                        print("[listening...]", end="", flush=True)
                    silent_chunks = 0
                    buf.append(chunk)
                elif speaking:
                    silent_chunks += 1
                    buf.append(chunk)
                    if silent_chunks < silence_limit:
                        continue
                    if smart_turn and buf:
                        prob = smart_turn(np.concatenate(buf))
                        print(f" [turn prob: {prob:.2f}]", end="", flush=True)
                        if prob < 0.5:
                            silent_chunks = 0
                            continue
                    process_utterance(np.concatenate(buf), history)
                    buf.clear()
                    speaking, silent_chunks = False, 0
                    vad.reset_states()

        except KeyboardInterrupt:
            print("\nBye!")
            executor.shutdown(wait=False)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)
            if args.record and record_buf:
                full = np.concatenate(record_buf)
                with wave.open(args.record, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(
                        (full * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
                    )
                print(
                    f"Recorded {len(full) / SAMPLE_RATE:.1f}s to {args.record}",
                    flush=True,
                )


if __name__ == "__main__":
    main()
