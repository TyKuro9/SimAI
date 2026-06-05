# FlowSim 并行化回归基线

## 1) 热点剖析（stage-b-hotspot-profile）

```bash
bash scripts/flowsim_hotspot_profile.sh \
  -t 16 \
  -b /home/zty/Topo/m4/SimAI/bin/SimAI_flowsim \
  -w "/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt" \
  -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -o /home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_profile/meta_t16
```

- 关键输出:
  - `profile_summary.txt`: 内置 section 级耗时统计，定位事件队列与通信建模热点
  - `perf.data`/`perf_report.txt`（若系统支持 perf）

## 2) 优化验证 + 基线指标（stage-b-kernel-opt + benchmark-regression）

```bash
bash scripts/run_flowsim_regression.sh \
  -b /home/zty/Topo/m4/SimAI/bin/SimAI_flowsim \
  -w "/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt" \
  -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -o /home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_regression/meta \
  -t "1 2 4 8 16" \
  -r 3
```

- 自动生成:
  - 每次运行目录 `t{thread}/r{idx}/`（含 `fct.txt`、`runtime.txt`、`run.log`）
  - 汇总 `regression_metrics.csv`

## 3) 四类指标定义

- 正确性: 不同线程下 `P99` 相对基线线程偏差阈值（默认 5%）  
- 可重复性: 同线程多次运行 `P99` 变异系数阈值（默认 5%）  
- 性能: `runtime_median_sec` 和 `speedup_vs_baseline`  
- 扩展性: `threads` 维度 speedup 曲线（由 CSV 可直接绘图）
