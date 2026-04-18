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

import re as _re
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
import threading
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

_SENT_END = _re.compile(r"(?<=[.!?])\s+")
_SENT_MIN_CHARS = 20
_GAP_BLANK_SAMPLES = int(0.15 * SAMPLE_RATE)


def load_system_prompt(include_memory: bool = False) -> str:
    names = ("SOUL.md", "MEMORY.md") if include_memory else ("SOUL.md",)
    parts = [(_DIR / n).read_text().strip() for n in names if (_DIR / n).exists()]
    return "\n\n".join(p for p in parts if p)


def _split_sentences(text: str) -> list[str]:
    parts, carry = [], ""
    for p in _SENT_END.split(text.strip()):
        p = p.strip()
        if not p:
            continue
        carry = f"{carry} {p}".strip() if carry else p
        if len(carry) >= _SENT_MIN_CHARS:
            parts.append(carry)
            carry = ""
    if carry:
        parts.append(carry)
    return parts


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
_QWEN_CPP_LANGS = frozenset({"en", "ru", "zh", "ja", "ko", "de", "fr", "es"})


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

    print("=== Kokoro TTS (default, CPU ONNX) ===")
    print()
    cache_dir = os.path.join(tempfile.gettempdir(), "kokoro_tts")
    voices_file = os.path.join(cache_dir, "voices-v1.0.bin")
    if not os.path.exists(voices_file):
        print("  Kokoro voices not downloaded yet. Run voice_loop.py once first.")
    else:
        import numpy as np

        voices = sorted(np.load(voices_file).keys())
        prefix_lang = {
            "a": ("en-us", "English (US)"),
            "b": ("en-gb", "English (UK)"),
            "e": ("es", "Spanish"),
            "f": ("fr-fr", "French"),
            "h": ("hi", "Hindi"),
            "i": ("it", "Italian"),
            "j": ("ja", "Japanese"),
            "p": ("pt-br", "Portuguese"),
            "z": ("cmn", "Chinese"),
        }
        by_prefix = {}
        for v in voices:
            p = v[0]
            by_prefix.setdefault(p, []).append(v)
        print(f"  {'Lang':<16} {'Code':<6} Voices")
        print("  " + "-" * 65)
        for prefix in sorted(by_prefix.keys()):
            code, name = prefix_lang.get(prefix, ("??", f"Unknown ({prefix})"))
            voice_list = ", ".join(by_prefix[prefix])
            print(f"  {name:<16} {code:<6} {voice_list}")
        print(f"\n  Total: {len(voices)} voices across {len(by_prefix)} languages")

    print()
    print("=== Qwen3-TTS (--tts qwen, CUDA Linux, 9 speakers) ===")
    print()
    _print_qwen_speaker_table()

    print()
    print("=== QwenTTS C++ (--tts qwen-cpp, CPU/CUDA/Metal) ===")
    print()
    print(f"  {'Lang':<16} {'Code':<6} Notes")
    print("  " + "-" * 55)
    for code, name in [
        ("en", "English"),
        ("ru", "Russian"),
        ("zh", "Chinese"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("de", "German"),
        ("fr", "French"),
        ("es", "Spanish"),
    ]:
        print(f"  {name:<16} {code:<6} native pronunciation")
    print(f"\n  Other languages: use --lang with a reference audio for voice cloning")

    print()
    print("=== VoxCPM2 (--tts voxcpm, 30 languages) ===")
    print()
    print("  ar, zh, da, nl, en, fi, fr, de, el, he, hi, id, it, ja, km,")
    print("  ko, lo, ms, no, pl, pt, ru, es, sw, sv, tl, th, tr, vi")
    print("  (+ Chinese dialects)")
    print("  Install: uv add voxcpm")

    print()
    print("=== STT Backends ===")
    print()
    print(f"  Moonshine:  {', '.join(sorted(MOONSHINE_LANGS))}")
    print("  Whisper:    99+ languages (faster-whisper)")
    print("  Auto-selected per language, override with --stt")


def _print_qwen_speaker_table():
    print(f"  {'Lang':<14} {'Code':<6} {'Speaker':<12} Language Name")
    print("  " + "-" * 55)
    for code in sorted(_QWEN_SPEAKER_MAP.keys()):
        info = _QWEN_SPEAKER_MAP[code]
        native = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}
        lang_name = native.get(code, f"{info['language']} (via Ryan)")
        print(f"  {lang_name:<14} {code:<6} {info['speaker']:<12} {info['language']}")
    print(
        f"\n  9 speakers: Chelsie, Dylan, Eric, Ono_Anna, Aiden, Ryan, Serena, Sohee, Vivian"
    )
    print("  Use --voice <SpeakerName> to select")


def _print_handler_table():
    handlers = load_handler_config()
    print(f"{'Handler':<12} Description")
    print("-" * 50)
    for name in sorted(handlers.keys()):
        desc = handlers[name].get("description", "")
        if name == "llm" and "(default)" not in desc:
            desc += " (default)"
        print(f"{name:<12} {desc}")


def _load_qwen_cpp_config():
    cfg = {"bin": "qwen3-tts-cli", "model_dir": None, "ref_audio": None}
    config_path = _DIR / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            data = yaml.safe_load(config_path.read_text())
            if data and "tts" in data:
                tts = data["tts"]
                cfg["bin"] = tts.get("qwen_cpp_bin", cfg["bin"])
                cfg["model_dir"] = tts.get("qwen_cpp_model_dir", cfg["model_dir"])
                cfg["ref_audio"] = tts.get("qwen_cpp_ref_audio", cfg["ref_audio"])
        except Exception:
            pass
    return cfg


def _find_qwen_cpp_bin(cfg):
    import shutil

    bin_path = cfg.get("bin") or "qwen3-tts-cli"
    if os.path.isabs(bin_path) and os.path.isfile(bin_path):
        return bin_path
    found = shutil.which(bin_path)
    if found:
        return found
    return None


def _print_qwen_cpp_info():
    cfg = _load_qwen_cpp_config()
    print("QwenTTS C++ Backend (qwen3-tts.cpp)")
    print("=" * 50)
    print(f"  Binary:     {cfg['bin']}")
    print(f"  Model dir:  {cfg['model_dir'] or '(not configured)'}")
    print(
        f"  Ref audio:  {cfg['ref_audio'] or '(not configured — uses default voice)'}"
    )
    print()
    print("Install:")
    print("  git clone https://github.com/predict-woo/qwen3-tts.cpp")
    print("  cd qwen3-tts.cpp && git submodule update --init --recursive")
    print("  cmake -S ggml -B ggml/build -DGGML_METAL=ON  # or -DGGML_CUDA=ON")
    print("  cmake --build ggml/build -j$(nproc)")
    print("  cmake -S . -B build && cmake --build build -j$(nproc)")
    print("  uv venv .venv && source .venv/bin/activate")
    print("  uv pip install huggingface_hub gguf torch safetensors numpy tqdm")
    print("  python scripts/setup_pipeline_models.py")
    print()
    print("  Or download pre-converted models from:")
    print("    https://huggingface.co/endo5501/qwen3-tts.cpp")
    print("  # Add to PATH or set tts.qwen_cpp_bin in config.yaml")
    print()
    print("config.yaml example:")
    print("  tts:")
    print("    qwen_cpp_bin: /path/to/qwen3-tts-cli")
    print("    qwen_cpp_model_dir: /path/to/qwen3-tts.cpp/models")
    print("    qwen_cpp_ref_audio: /path/to/reference.wav")
    print()
    print("Supported languages: en, ru, zh, ja, ko, de, fr, es")
    print("  Pass --lang <code> to select (default: en)")
    print("  Without --lang or for unsupported languages, output uses English.")
    print("  Voice cloning via ref_audio works for any language.")


def _load_voxcpm_config():
    cfg = {"ref_audio": None, "voice_desc": None, "device": None}
    config_path = _DIR / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            data = yaml.safe_load(config_path.read_text())
            if data and "tts" in data:
                tts = data["tts"]
                cfg["ref_audio"] = tts.get("voxcpm_ref_audio", cfg["ref_audio"])
                cfg["voice_desc"] = tts.get("voxcpm_voice_desc", cfg["voice_desc"])
                cfg["device"] = tts.get("voxcpm_device", cfg["device"])
        except Exception:
            pass
    return cfg


def _print_voxcpm_info():
    cfg = _load_voxcpm_config()
    print("VoxCPM TTS Backend (VoxCPM2)")
    print("=" * 50)
    print("  30 languages: ar, zh, da, nl, en, fi, fr, de, el, he, hi,")
    print("  id, it, ja, km, ko, lo, ms, no, pl, pt, ru, es, sw, sv,")
    print("  tl, th, tr, vi (+ Chinese dialects)")
    print()
    print(
        f"  Ref audio:   {cfg['ref_audio'] or '(not configured — uses default voice)'}"
    )
    print(f"  Voice desc:  {cfg['voice_desc'] or '(not configured)'}")
    print(f"  Device:      {cfg['device'] or 'auto (CUDA/MPS/CPU)'}")
    print()
    print("Install:")
    print("  uv add voxcpm")
    print()
    print("config.yaml example:")
    print("  tts:")
    print("    voxcpm_ref_audio: /path/to/voice.wav   # 5-30s for voice cloning")
    print("    voxcpm_voice_desc: warm female voice    # or describe a voice")
    print("    voxcpm_device: cuda                     # cuda, cpu, mps, or auto")


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
        choices=["kokoro", "qwen", "qwen-cpp", "voxcpm"],
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
        print(
            "Error: --tts qwen requires CUDA (Linux NVIDIA GPU only). Use --tts qwen-cpp for macOS."
        )
        sys.exit(1)
    if args.list:
        if args.tts == "qwen":
            _print_qwen_speaker_table()
        elif args.tts == "qwen-cpp":
            _print_qwen_cpp_info()
        elif args.tts == "voxcpm":
            _print_voxcpm_info()
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

    _qwen_cpp_cfg = _load_qwen_cpp_config() if args.tts == "qwen-cpp" else None
    _qwen_cpp_bin = None
    if args.tts == "qwen-cpp" and args.tts_enabled:
        _qwen_cpp_bin = _find_qwen_cpp_bin(_qwen_cpp_cfg)
        if not _qwen_cpp_bin:
            print(
                "Error: qwen3-tts-cli not found.\n"
                "Install qwen3-tts.cpp: https://github.com/predict-woo/qwen3-tts.cpp\n"
                "Then add to PATH or set tts.qwen_cpp_bin in config.yaml."
            )
            sys.exit(1)
        model_dir = _qwen_cpp_cfg.get("model_dir")
        if not model_dir:
            print(
                "Error: tts.qwen_cpp_model_dir not set in config.yaml.\n"
                "Set it to the directory containing your GGUF model files."
            )
            sys.exit(1)
        print(f"  QwenTTS C++ backend: {_qwen_cpp_bin}", flush=True)
        print(f"  Model dir: {model_dir}", flush=True)
        if args.lang not in _QWEN_CPP_LANGS:
            print(
                f"  Warning: qwen-cpp does not support '{args.lang}'. "
                f"Supported: {', '.join(sorted(_QWEN_CPP_LANGS))}. "
                "Output will use English pronunciation.",
                flush=True,
            )

    _voxcpm_cfg = _load_voxcpm_config() if args.tts == "voxcpm" else None
    voxcpm_model = None
    voxcpm_sr = None
    if args.tts == "voxcpm" and args.tts_enabled:
        try:
            from voxcpm import VoxCPM as _VoxCPM
        except ImportError:
            print("Error: voxcpm not installed.\nRun: uv add voxcpm\nThen try again.")
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
        from qwen_tts import Qwen3TTSModel, Qwen3TTSTokenizer

        print(f"  Loading {_QWEN_TTS_MODEL_ID} (~3.4GB on first run)...", flush=True)
        qwen_tts_model = Qwen3TTSModel.from_pretrained(
            _QWEN_TTS_MODEL_ID,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )
        qwen_tts_tokenizer = Qwen3TTSTokenizer.from_pretrained(_QWEN_TTS_MODEL_ID)
        speakers = qwen_tts_model.get_supported_speakers()
        print(f"  QwenTTS loaded: {len(speakers)} speakers", flush=True)
    elif args.tts == "voxcpm" and args.tts_enabled:
        print("Loading VoxCPM TTS...", flush=True)
        from voxcpm import VoxCPM as _VoxCPM

        device = _voxcpm_cfg.get("device") or "auto"
        print(f"  Loading VoxCPM2 (~8GB on first run, device={device})...", flush=True)
        voxcpm_model = _VoxCPM.from_pretrained(
            "openbmb/VoxCPM2",
            load_denoiser=False,
            optimize=False,
            device=device,
        )
        voxcpm_sr = voxcpm_model.tts_model.sample_rate
        print(f"  VoxCPM loaded: {voxcpm_sr}Hz output", flush=True)
        ref = _voxcpm_cfg.get("ref_audio")
        desc = _voxcpm_cfg.get("voice_desc")
        if ref:
            print(f"  Voice cloning from: {ref}", flush=True)
        elif desc:
            print(f"  Voice design: {desc}", flush=True)
        else:
            print("  Default voice (no cloning or design)", flush=True)

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

    def stream_sentences(messages, max_tokens=200, temperature=0.7):
        q: queue.Queue[str | None] = queue.Queue()
        cancel = threading.Event()

        def _worker():
            def _merge(carry, fragment):
                return f"{carry} {fragment}".strip() if carry else fragment

            try:
                if IS_DARWIN:
                    try:
                        from mlx_vlm import stream_generate as _mlx_stream
                    except ImportError:
                        _mlx_stream = None
                    if _mlx_stream is not None:
                        token_buf, carry = "", ""
                        prompt = processor.apply_chat_template(
                            messages, tokenize=False, add_generation_prompt=True
                        )
                        for result in _mlx_stream(
                            model,
                            processor,
                            prompt,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            repetition_penalty=1.2,
                            verbose=False,
                        ):
                            if cancel.is_set():
                                return
                            token_buf += (
                                result.text if hasattr(result, "text") else str(result)
                            )
                            while True:
                                m = _SENT_END.search(token_buf)
                                if not m:
                                    break
                                carry = _merge(
                                    carry, token_buf[: m.start() + 1].strip()
                                )
                                token_buf = token_buf[m.end() :]
                                if len(carry) >= _SENT_MIN_CHARS:
                                    q.put(carry)
                                    carry = ""
                        remainder = (
                            _merge(carry, token_buf.strip())
                            if token_buf.strip()
                            else carry
                        )
                        if remainder:
                            q.put(remainder)
                    else:
                        text = llm_generate(
                            messages, max_tokens=max_tokens, temperature=temperature
                        )
                        for s in _split_sentences(text) or [text]:
                            if cancel.is_set():
                                return
                            q.put(s)
                else:
                    text = llm_generate(
                        messages, max_tokens=max_tokens, temperature=temperature
                    )
                    for s in _split_sentences(text) or [text]:
                        if cancel.is_set():
                            return
                        q.put(s)
            except Exception as e:
                print(f"  [LLM error: {e}]", file=sys.stderr)
            finally:
                q.put(None)

        threading.Thread(target=_worker, daemon=True).start()
        try:
            while True:
                s = q.get()
                if s is None:
                    return
                yield s
        finally:
            cancel.set()

    def speak_tts(text):
        if not text or not text.strip():
            return
        drain_audio_q()
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
        elif _qwen_cpp_bin:
            import subprocess as _sp
            import soundfile as _sf

            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                tmp.close()
                cmd = [
                    _qwen_cpp_bin,
                    "-m",
                    _qwen_cpp_cfg["model_dir"],
                    "-t",
                    text,
                    "-o",
                    tmp_path,
                ]
                if args.lang in _QWEN_CPP_LANGS:
                    cmd.extend(["-l", args.lang])
                ref = _qwen_cpp_cfg.get("ref_audio")
                if ref:
                    cmd.extend(["-r", ref])
                _sp.run(cmd, capture_output=True, timeout=120, check=True)
                samples, sr = _sf.read(tmp_path)
                sd.play(samples, sr)
                sd.wait()
            except _sp.CalledProcessError as e:
                print(f"  [qwen-cpp error: {e.stderr.decode()[:200]}]", file=sys.stderr)
            except _sp.TimeoutExpired:
                print("  [qwen-cpp timeout: synthesis took >120s]", file=sys.stderr)
            except Exception as e:
                print(f"  [qwen-cpp error: {e}]", file=sys.stderr)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        elif voxcpm_model:
            try:
                sentences = _split_sentences(text) or [text]
                chunks = []
                ref = _voxcpm_cfg.get("ref_audio")
                desc = _voxcpm_cfg.get("voice_desc")
                for sent in sentences:
                    if ref:
                        wav = voxcpm_model.generate(text=sent, reference_wav_path=ref)
                    elif desc:
                        wav = voxcpm_model.generate(
                            text=f"({desc}){sent}",
                            cfg_value=2.0,
                            inference_timesteps=10,
                        )
                    else:
                        wav = voxcpm_model.generate(
                            text=sent, cfg_value=2.0, inference_timesteps=10
                        )
                    chunks.append(wav)
                full = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
                sd.play(full, voxcpm_sr)
                sd.wait()
            except Exception as e:
                print(f"  [voxcpm error: {e}]", file=sys.stderr)
        drain_audio_q()
        vad.reset_states()

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

    def play_tts_stream(sentence_source):
        if isinstance(sentence_source, str):
            sentence_iter = iter(_split_sentences(sentence_source) or [sentence_source])
        else:
            sentence_iter = sentence_source

        drain_audio_q()
        out_stream, interrupted = None, False
        tts_16k_buf: list[np.ndarray] = []
        _cache_arr = np.array([], dtype=np.float32)
        _cache_len = 0
        state = {"play_start": None, "consec_speech": 0, "mic_pos": 0}
        aec_process = make_aec_processor() if make_aec_processor else None

        def _get_tts_concat():
            nonlocal _cache_arr, _cache_len
            if len(tts_16k_buf) != _cache_len:
                _cache_arr = (
                    np.concatenate(tts_16k_buf)
                    if tts_16k_buf
                    else np.array([], dtype=np.float32)
                )
                _cache_len = len(tts_16k_buf)
            return _cache_arr

        def _append_ref(chunk_samples, sr):
            if aec_process is None:
                return
            if sr == SAMPLE_RATE:
                tts_16k_buf.append(chunk_samples.astype(np.float32))
            else:
                idx = np.arange(0, len(chunk_samples), sr / SAMPLE_RATE)
                tts_16k_buf.append(
                    np.interp(idx, np.arange(len(chunk_samples)), chunk_samples).astype(
                        np.float32
                    )
                )

        def check_barge_in():
            if not (
                aec_process
                and state["play_start"]
                and _time.monotonic() - state["play_start"] >= 0.5
            ):
                return False
            tts_concat = _get_tts_concat()
            if not len(tts_concat):
                return False
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

        def pad_gap_and_check():
            if aec_process is None:
                return False
            blanked = 0
            while not audio_q.empty():
                mic_chunk = audio_q.get_nowait()
                if len(mic_chunk) < CHUNK_SAMPLES:
                    continue
                silence_ref = np.zeros(len(mic_chunk), dtype=np.float32)
                tts_16k_buf.append(silence_ref)
                state["mic_pos"] += len(mic_chunk)
                if blanked < _GAP_BLANK_SAMPLES:
                    state["consec_speech"] = 0
                    blanked += len(mic_chunk)
                    continue
                cleaned = aec_process(mic_chunk, silence_ref)
                if _vad_prob(vad, cleaned.astype(np.float32)) > 0.8:
                    state["consec_speech"] += 1
                    if state["consec_speech"] >= 5:
                        return True
                else:
                    state["consec_speech"] = 0
            return False

        async def _play():
            nonlocal out_stream, interrupted
            loop = asyncio.get_running_loop()
            synth_q: asyncio.Queue = asyncio.Queue(maxsize=1)

            async def _synthesizer():
                async def _synth(text):
                    return await loop.run_in_executor(
                        None,
                        lambda t=text: kokoro.create(
                            t,
                            voice=args.voice,
                            speed=1.0,
                            lang=_lang_cfg["tts_lang"],
                        ),
                    )

                GROUP = 2
                buf: list[str] = []
                for sentence in sentence_iter:
                    if interrupted:
                        break
                    buf.append(sentence)
                    if len(buf) == GROUP:
                        await synth_q.put(await _synth(" ".join(buf)))
                        buf = []
                if buf and not interrupted:
                    await synth_q.put(await _synth(" ".join(buf)))
                await synth_q.put(None)

            synth_task = asyncio.create_task(_synthesizer())
            first_sentence = True
            try:
                while True:
                    item = await synth_q.get()
                    if item is None or interrupted:
                        break
                    samples, sr = item

                    if not first_sentence and pad_gap_and_check():
                        interrupted = True
                        print("  [voice interrupt]", flush=True)
                        break

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
                    state["consec_speech"] = 0
                    first_sentence = False

                    _append_ref(samples, sr)
                    data = samples.reshape(-1, 1)
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
            finally:
                synth_task.cancel()
                try:
                    await synth_task
                except asyncio.CancelledError:
                    pass
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
        heard, response = "", ""
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
            if args.audio_mode:
                response = llm_generate(messages, audio=[wav_path])
                heard = transcribe_future.result(timeout=10)
                print(f"  [{heard}]")
                print(f"\n> {response}\n", flush=True)
                if kokoro and response:
                    play_tts_stream(response)
                elif qwen_tts_model or _qwen_cpp_bin or voxcpm_model:
                    speak_tts(response)
                elif chime_sound is not None:
                    _wait_for_chime_gap()
                    sd.stop()
            else:
                response_parts: list[str] = []

                def _collecting(gen):
                    def _emit(s):
                        response_parts.append(s)
                        print(f"> {s}", flush=True)
                        return s

                    last = None
                    for s in gen:
                        yield _emit(s)
                        last = s
                    if last and last[-1] not in ".!?":
                        yield _emit("Wait, I've gone on a bit — want me to continue?")

                print()
                if kokoro:
                    play_tts_stream(_collecting(stream_sentences(messages)))
                else:
                    for _ in _collecting(stream_sentences(messages)):
                        pass
                    if response_parts and (
                        qwen_tts_model or _qwen_cpp_bin or voxcpm_model
                    ):
                        speak_tts(" ".join(response_parts))
                    elif chime_sound is not None:
                        _wait_for_chime_gap()
                        sd.stop()

                response = " ".join(response_parts)
                print()
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
    if kokoro or qwen_tts_model or _qwen_cpp_bin or voxcpm_model:
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
