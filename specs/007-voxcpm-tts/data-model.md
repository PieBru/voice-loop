# Data Model: VoxCPM TTS Backend

**Feature**: 007-voxcpm-tts | **Date**: 2026-04-17

## Entities

### VoxCPM Config (config.yaml → tts)

| Field | Type | Default | Description |
|---|---|---|---|
| `voxcpm_ref_audio` | string (path) | None | Reference WAV for voice cloning (5-30s) |
| `voxcpm_voice_desc` | string | None | Voice design description (e.g., "warm female voice") |
| `voxcpm_device` | string | "auto" | Device: "cuda", "cpu", "mps", "auto" |

### VoxCPM Model (runtime, in-memory)

| Field | Type | Description |
|---|---|---|
| `voxcpm_model` | VoxCPM instance | Loaded via `VoxCPM.from_pretrained("openbmb/VoxCPM2")` |
| `voxcpm_sr` | int | Sample rate (48000) |
| `voxcpm_ref_audio` | string or None | Path to reference audio for cloning |
| `voxcpm_voice_desc` | string or None | Voice design text |

## State Transitions

```
[args.tts == "voxcpm"] → [import check] → [model load] → [ready]
                                                    ↓
                                              [synthesize per call]
                                                    ↓
                                          [sentence split → synthesize each → concatenate → play]
```

## Relationships

- `VoxCPM Config` ← loaded by `_load_voxcpm_config()` from config.yaml
- `VoxCPM Model` ← created in `main()` TTS loading section
- `speak_tts()` dispatches to VoxCPM path when `voxcpm_model` is not None
