# Composite targeted fault policy

This composite reuses completed deterministic rows to represent:

- Baseline policy: cross=0.3, PXN same-rail=0.75, baseline hop4=0.25, direct=0.22.
- Default failed-run policy: fault hop4=0.20 and direct=0.20.
- High-stretch override only for DeepSeek rows with path_stretch >= 1.04: hop4=0.05.
- ROFT and RO stay on the default fault-only policy.

- Composite raw CSV: `targeted_composite_deepseek_h005_t104_roft_ro_faultonly_raw.csv`
