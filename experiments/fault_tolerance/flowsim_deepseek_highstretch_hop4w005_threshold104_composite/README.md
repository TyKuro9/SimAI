# DeepSeek h4=0.05 threshold 1.04 composite

This composite reuses completed deterministic seed/rate rows instead of rerunning:

- DeepSeek 1%, 5%, and 10% rows are from the fault-only h4=0.20/direct=0.20 sweep.
- DeepSeek 15% rows are from the h4=0.05 DeepSeek sweep.
- The selector is equivalent to `high_stretch_threshold=1.04` for the sampled rows: DeepSeek 10% path_stretch is below 1.04, and DeepSeek 15% is above 1.04 for all three seeds.

- Composite raw CSV: `deepseek_highstretch_hop4w005_threshold104_composite_raw.csv`
