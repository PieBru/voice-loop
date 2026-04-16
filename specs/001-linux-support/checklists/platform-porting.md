# Platform Porting Requirements Quality Checklist: Linux Support

**Purpose**: Pre-implementation gate — validate requirements completeness, clarity, and consistency across the dual-platform porting specification. For reviewer sign-off before `/speckit.implement`.
**Created**: 2026-04-16
**Feature**: [spec.md](../spec.md)
**Depth**: Standard (cross-cutting)
**Audience**: Reviewer (PR review gate)

## Requirement Completeness

- [ ] CHK001 Is the behavior for `--audio-mode` on Linux specified? FR-003 requires it to "work identically" on both platforms, but the research phase identifies it as an MLX-only feature with no Linux equivalent — are these requirements reconciled? [Conflict, Spec §FR-003 vs research.md R5]
- [ ] CHK002 Are requirements defined for what happens when `config.yaml` exists but is malformed (invalid YAML, missing required fields)? [Gap]
- [ ] CHK003 Are requirements specified for GPU VRAM exhaustion during inference on Linux (CUDA OOM mid-turn)? [Gap, Exception Flow]
- [ ] CHK004 Are requirements specified for model download interruption on Linux (partial download, network failure mid-stream)? [Coverage, Spec §FR-007]
- [ ] CHK005 Is the model cache location on Linux explicitly specified, or is "the same way they are cached on macOS" (Spec §FR-007) sufficient? [Clarity, Spec §FR-007]
- [ ] CHK006 Is there a requirement for multi-GPU systems — which GPU is selected when multiple CUDA devices are present? [Gap]
- [ ] CHK007 Is the minimum CUDA toolkit version requirement documented alongside the compute capability 7.0+ assumption? [Completeness, Spec §Assumptions]

## Requirement Clarity

- [ ] CHK008 Is "mid-range CUDA GPU" in SC-002 quantified with a specific reference GPU model or compute capability tier? [Clarity, Spec §SC-002]
- [ ] CHK009 Is the "macOS/Apple Silicon baseline" latency in SC-002 documented with an actual measured value, or is the 2× target ungrounded? [Measurability, Spec §SC-002]
- [ ] CHK010 Is "clear, actionable error message" in FR-009 defined with measurable criteria, or only exemplified in the Edge Cases section? [Clarity, Spec §FR-009]
- [ ] CHK011 Is "platform-inappropriate model identifier" in FR-006 defined — what constitutes "inappropriate"? Is it format-based (MLX on Linux) or any model that fails to load? [Clarity, Spec §FR-006]
- [ ] CHK012 Is "functionally equivalent" in US2 acceptance scenario 2 defined with specific criteria (same text output? same latency range? same CLI behavior?)? [Clarity, Spec §US2]

## Requirement Consistency

- [ ] CHK013 Do FR-003 ("all existing CLI flags MUST work identically") and the `--audio-mode` flag's MLX-only nature conflict? If `--audio-mode` is macOS-only, should FR-003 enumerate exceptions? [Consistency, Spec §FR-003]
- [ ] CHK014 Is the AMD/ROCm edge case ("should not crash — should fall back gracefully or report unsupported GPU") consistent with the clarification that CPU-only is unsupported? If AMD GPUs are out of scope, is "gracefully" defined as an error message or something more? [Consistency, Spec §Edge Cases vs Clarification Q1]
- [ ] CHK015 Does the assumption that "Model download sizes and memory usage on Linux will be comparable to macOS (~3-4 GB total)" account for llama-cpp-python + CUDA runtime overhead in addition to the GGUF model weight? [Assumption, Spec §Assumptions]
- [ ] CHK016 Is the CUDA compute capability 7.0+ floor (Spec §Assumptions) a verified requirement from the chosen LLM backend, or an unvalidated assumption? If the backend supports older compute capabilities, is the floor unnecessarily restrictive? [Assumption, Spec §Assumptions]

## Acceptance Criteria Quality

- [ ] CHK017 Can SC-001 ("under 15 minutes from git clone to completed voice turn") be measured deterministically, given that model download time is excluded but `uv sync` time varies with bandwidth? [Measurability, Spec §SC-001]
- [ ] CHK018 Can SC-003 ("zero regression in macOS behavior") be verified without a baseline test suite? Is "identical results" defined as same CLI flags accepting same arguments, or also same output text/timing? [Measurability, Spec §SC-003]
- [ ] CHK019 Does SC-004 cover all three system dependencies listed in FR-009 (PortAudio, espeak-ng, CUDA runtime), or only those triggered by the test scenario? [Coverage, Spec §SC-004 vs §FR-009]

## Scenario Coverage

- [ ] CHK020 Are requirements defined for the first-run experience on Linux when NO `config.yaml` exists — is the auto-generation behavior specified, including what defaults are written? [Coverage, Spec §FR-006 + research.md R6]
- [ ] CHK021 Are requirements defined for partial CUDA installation (NVIDIA driver present but CUDA toolkit missing, or vice versa)? [Coverage, Exception Flow]
- [ ] CHK022 Are requirements defined for the upgrade path — an existing macOS user who `git pull`s and finds their `voice_loop_mac.py` renamed? Is a migration notice or compatibility symlink specified? [Coverage, Spec §FR-011]
- [ ] CHK023 Are requirements defined for `--model` receiving a valid alias that has no mapping for the current platform (e.g., an alias with only a `linux` key, run on macOS)? [Coverage, Spec §FR-006]

## Edge Case Coverage

- [ ] CHK024 Is the behavior specified when `llama-cpp-python` is installed but the CUDA driver version is too old for the compiled CUDA toolkit version? [Edge Case, Gap]
- [ ] CHK025 Is the behavior specified when the NVIDIA driver is present but no GPU is physically seated (e.g., headless server with driver installed)? [Edge Case]
- [ ] CHK026 Are error message requirements defined for when `config.yaml` specifies a model alias that maps to a nonexistent or removed HuggingFace repository? [Edge Case, Spec §FR-006]

## Dependencies & Assumptions

- [ ] CHK027 Is the assumption that "other distros may work but are not explicitly tested" acceptable for a reviewer gate, or should minimum glibc/systemd requirements be documented for broader Linux compatibility? [Assumption, Spec §Assumptions]
- [ ] CHK028 Is the `llama-cpp-python` version constraint (>=0.3.0 from research.md) reflected in the spec, or only in the plan? If only the plan, should the spec reference a minimum LLM backend version? [Traceability, research.md R1 vs Spec]

## Notes

- **Highest-priority items**: CHK001, CHK008, CHK009, CHK013 — these represent potential spec-level contradictions or unmeasurable acceptance criteria that could block reviewer sign-off.
- **CHK001 (audio-mode conflict)**: FR-003 says all flags work identically; research.md says audio-mode has no Linux equivalent. This MUST be resolved before implementation.
- **CHK008/CHK009 (latency baseline)**: SC-002's 2× target is ungrounded without a measured macOS baseline. Consider documenting the baseline or changing to an absolute latency target.
