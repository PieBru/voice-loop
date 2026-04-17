# Implementation Plan: VoxCPM TTS Backend

**Branch**: `007-voxcpm-tts` | **Date**: 2026-04-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/007-voxcpm-tts/spec.md`

## Summary

Add `--tts voxcpm` as a fourth TTS backend using the VoxCPM2 model (2B params, 30 languages, 48kHz output). Supports voice cloning from reference audio and voice design via text descriptions. Sentence splitting for long responses. Python import via `voxcpm` pip package. Works on CUDA, CPU, and Apple MPS.

## Technical Context

**Language/Version**: Python 3.11+ (managed with `uv`)
**Primary Dependencies**: `voxcpm>=2.0`, `torch>=2.5.0` (already in project)
**Storage**: HF cache for VoxCPM2 model (~8GB), config.yaml for settings
**Testing**: Manual — `uv run voice_loop.py --tts voxcpm` + speak a full turn
**Target Platform**: All platforms (CUDA Linux, CPU Linux, Apple MPS macOS)
**Project Type**: Single-file script (`voice_loop.py`)
**Performance Goals**: VoxCPM2 RTF ~0.30 on RTX 4090; acceptable on CPU
**Constraints**: No streaming for first iteration; `optimize=False` to avoid torch.compile issues; 48kHz output needs resampling for AEC
**Scale/Scope**: Single user, on-device, one model variant (VoxCPM2 2B)

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. On-Device First | PASS | VoxCPM runs locally. No cloud API. |
| II. Simplicity & Minimalism | PASS | `--tts voxcpm` follows existing `--tts` flag pattern. Single-file. |
| III. User Sovereignty | PASS | User opts in via `--tts voxcpm`. Config controls voice cloning/design. |
| IV. Audio Pipeline Integrity | CONDITIONAL | 48kHz output resampled to 16kHz for AEC ref. Non-streaming (like QwenTTS). |
| V. Incremental Evolution | PASS | Additive. No existing codepaths modified. |

**Verdict**: CONDITIONAL — 48kHz→16kHz resampling and non-streaming are inherent to VoxCPM, not design flaws.

## Project Structure

### Documentation

```
specs/007-voxcpm-tts/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
```

### Source Code

```
voice_loop.py          # Add --tts voxcpm, VoxCPM loading, speak_voxcpm(), _print_voxcpm_info()
config.yaml.example    # Add tts.voxcpm_ref_audio, tts.voxcpm_voice_desc, tts.voxcpm_device
README.md              # Add VoxCPM section
AGENTS.md              # Update with --tts voxcpm
pyproject.toml         # Add voxcpm dependency
```

**Structure Decision**: Single-file architecture preserved. All VoxCPM code in `voice_loop.py`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Non-streaming playback | VoxCPM `generate_streaming()` exists but bidirectional streaming not supported; sentence streaming deferred | Full synthesis then playback is simpler and matches QwenTTS pattern |
| 48kHz→16kHz resampling | VoxCPM2 outputs 48kHz; AEC reference needs 16kHz | Native 16kHz model (VoxCPM-0.5B) has lower quality |
