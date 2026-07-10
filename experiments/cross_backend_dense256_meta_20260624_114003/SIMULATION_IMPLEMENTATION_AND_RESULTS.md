# Dense256 Meta 仿真实验设计、实现差异与运行状态

## 目标

这组实验要拆开两个容易混在一起的因素：

1. **仿真器/模型差异**：NS-3、htsim、FlowSim 本身的建模粒度不同。
2. **路由算法差异**：ECMP、逐包 spray、PLB 在同一个 packet-level htsim RoCE 后端里的差异。

因此不能只用 `NS-3 ECMP` 对比 `htsim spray_plb` 下结论。这个对比同时改变了仿真器和路由算法，解释上不干净。当前新增的关键桥接实验是 `htsim ECMP`。

## 固定输入

| 项目 | 值 |
| --- | --- |
| workload | `my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt` |
| workload 类型 | Dense，不是 MoE |
| GPU 规模 | 256 |
| 主拓扑 | `mytopo/Meta_Topo_256g_8gps_400Gbps_A100` |
| htsim 配置 | `myconfig/Meta256MoE.conf` |
| NS-3 配置 | `experiments/cross_backend_dense256_meta_20260624_114003/ns3_rerun_20260624_143409/retry_fixed_conf/Meta256_run.conf` |

## 实验矩阵

### A. 仿真器差异：尽量保持路由语义接近

| Case | 后端 | 路由/路径语义 | 状态 | 目的 |
| --- | --- | --- | --- | --- |
| A1 | NS-3 | ECMP | 已完成 | packet/QP/protocol baseline |
| A2 | htsim | ECMP，单 flow 稳定 hash 到一条 shortest path | 正在运行 | 隔离 htsim packet RoCE 模型差异 |
| A3 | FlowSim | 每个 `(src,dst)` 固定预计算路径 | 已完成 | flow/chunk/link-sharing baseline |

读法：

- `NS-3 ECMP` vs `htsim ECMP`：主要看仿真器/模型差异。
- `FlowSim` 只作为 flow-level/chunk-level 快速近似基线，不作为 packet-level ECMP/Spray 实现。

### B. 路由算法差异：固定在 htsim packet RoCE 后端内比较

| Case | 后端 | 路由策略 | 状态 | 目的 |
| --- | --- | --- | --- | --- |
| B1 | htsim | `ecmp` | 正在运行 | 稳定 per-flow ECMP baseline |
| B2 | htsim | `spray_rr` | 已排队，ECMP 完成后自动运行 | deterministic per-data-packet spray baseline |
| B3 | htsim | `spray_plb` | 已完成 | source-side adaptive PLB 近似 |
| B4 | htsim | `single` | 短 workload 已完成 | first shortest path 诊断 baseline |
| B5 | htsim | `spray_reps` | 短 workload 已完成 | REPS-inspired path recycling，可后续 full run |
| B6 | htsim | `spray_oblivious` | 短 workload 已完成 | random per-packet stress baseline |

读法：

- `htsim ECMP` vs `htsim spray_rr`：稳定 flow ECMP 与 deterministic packet spray 的差异。
- `htsim ECMP` vs `htsim spray_plb`：稳定 flow ECMP 与 adaptive packet path selection 的差异。
- `htsim spray_rr` vs `htsim spray_plb`：无反馈轮询 spray 与反馈驱动 PLB 的差异。

### C. 拓扑 sanity 实验

已有 256-scale 短 workload 验证覆盖 6 个拓扑，目的是确认 packet-level htsim RoCE 在不同拓扑上可用，并且 `ecmp`/`spray_rr` 能产生非空 `EndToEnd.csv` 与 `fct.txt`。

| workload | 拓扑 | 策略 | 状态 |
| --- | --- | --- | --- |
| first 10 layers, 1 MiB cap | Meta, HPN, DeepSeek, Zcube, RO, ROFT | `ecmp`, `spray_rr` | 已完成 |
| first 100 layers, 1 MiB cap | Meta | 7 个 htsim 策略 | 已完成 |

之前的 full 6-topology `spray_rr` 批次是在内存修复前启动的，Meta case 以 exit code 137 退出，不能作为有效结果。当前有效 full run 先跑 Meta route-isolation；等 `htsim ECMP` 和 `htsim spray_rr` 完成后，再决定是否排队 full 6-topology。

### D. 短 workload cross-simulator sanity 实验

为了在 full htsim ECMP/spray_rr 长跑结束前先验证对比方法，新增同一份短 workload 的 cross-simulator sanity 矩阵：

| 项目 | 值 |
| --- | --- |
| 输出目录 | `short_cross_sim_20260626_short10_1mib_r2/` |
| workload | `/tmp/htsim_dense256_short10_1mib.txt` |
| workload 生成方式 | normal dense workload 的 first 10 layers，通信量 capped at 1 MiB |
| topology | `mytopo/Meta_Topo_256g_8gps_400Gbps_A100` |
| runner | `run_short_cross_sim_compare.sh 20260626_short10_1mib_r2` |
| summary | `short_cross_sim_20260626_short10_1mib_r2/summary.md` |

结果：

| Case | 模型 | 路由 | EndToEnd 行数 | Total time | Exposed comm | DP | TP | FCT rows | Wall time | Max RSS KB |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| FlowSim | flow/chunk/link sharing | fixed path per `(src,dst)` | 15 | 65580 | 492 | 466 | 26 | 159232 | 0:05.18 | 303768 |
| htsim ECMP | packet RoCE | stable per-flow ECMP | 15 | 65367 | 279 | 102 | 177 | 144813 | 0:11.72 | 433976 |
| htsim spray_rr | packet RoCE | deterministic per-packet RR spray | 15 | 65258 | 170 | 62 | 108 | 144865 | 0:11.75 | 483380 |
| NS-3 ECMP | packet/QP/protocol | switch-side ECMP | 15 | 65416 | 328 | 93 | 234 | 144636 | 0:33.84 | 2828368 |

短 workload 读法：

- `NS-3 ECMP` 与 `htsim ECMP` 的 total time 接近，但 exposed comm 和 DP/TP 分解不同，说明即使路由语义接近，packet/QP/protocol 模型与 htsim packet RoCE 模型仍会给出不同分解。
- `htsim spray_rr` 比 `htsim ECMP` 的 exposed comm 更低，说明逐 data packet round-robin 在这个短 workload 上已经能体现路由策略差异。
- `FlowSim` 暴露通信最高，符合固定路径 + flow/chunk/link-sharing 近似模型的边界。
- 这组短结果只能作为 sanity/trend evidence；最终结论仍以 full dense htsim ECMP 和 htsim spray_rr 完成后的表格为准。

## 实现差异

| 后端 | 粒度 | 路由实现 | 主要输出 | 解释边界 |
| --- | --- | --- | --- | --- |
| NS-3 | packet/QP/protocol | switch/NVSwitch 侧 ECMP hash，按 flow/QP 字段稳定选择 next hop | `EndToEnd.csv`, NS-3 FCT/trace | 高保真但慢；当前用于 ECMP baseline |
| htsim | packet-level RoCE event model | ASTRA frontend 枚举 GPU-pair shortest paths；`ecmp` 每个 flow 固定一条 path；`spray_rr` 对 data packet 轮询 path；`spray_plb` 根据 NACK/RTT 反馈切换 active path；ACK/NACK 走稳定反向路径 | `EndToEnd.csv`, `fct.txt` | 当前 PLB/REPS 是 source-side 近似，不是 Tomahawk5 switch-port DLB |
| FlowSim | flow/chunk/link sharing | `GetFlowSimPathByNodeIds(src,dst)` 为每个 GPU pair 使用固定预计算路径 | `EndToEnd.csv`, optional `fct.txt` | 快速趋势筛查；不是 packet-level ECMP/Spray |

## 已完成 full Dense256 Meta 结果

| Case | 模型 | 路由 | EndToEnd 行数 | Total time | Exposed comm | DP | TP | Wall time | Max RSS KB |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| NS-3 ECMP | packet/QP/protocol | ECMP | 1267 | 8101602.519 | 311149.403 | 130878 | 180268 | 10:24:10 | 42389416 |
| htsim spray_plb | packet RoCE | source-side adaptive PLB | 1267 | 8109356.972 | 318903.856 | 203984 | 114916 | 2:31:17 | 29812020 |
| FlowSim | flow/chunk/link sharing | fixed path per `(src,dst)` | 1267 | 8420704.972 | 630251.856 | 496810 | 133438 | 14:32.01 | 51131984 |

初步读法：

- `NS-3 ECMP` 与 `htsim spray_plb` 的 total time 很接近，但这不是纯路由算法比较，因为两边后端和路由都不同。
- `FlowSim` 的 exposed comm 明显更高，符合它的 flow/chunk/link-sharing 近似和固定路径语义；它适合做拓扑趋势筛查，不适合直接证明 packet spray 的收益。

## 正在运行的 full route-isolation 批次

tmux session：

```bash
dense256_meta_htsim_route_compare_20260626
```

脚本：

```bash
experiments/cross_backend_dense256_meta_20260624_114003/run_htsim_route_compare.sh 20260626_route_compare
```

顺序：

1. `htsim_ecmp_full_20260626_route_compare/`
2. `htsim_spray_rr_full_20260626_route_compare/`

当前进度快照（2026-06-27 00:21 CST）：

| Case | 状态 | 进度 | FCT 行数 | EndToEnd 行数 |
| --- | --- | --- | ---: | ---: |
| htsim ECMP | running | forward `801/1262`，约 `63.47%`，ETA `2441s` | 22808733 | 0 |
| htsim spray_rr | queued | ECMP 完成后自动开始 | 0 | 0 |

`EndToEnd.csv` 在 workload 完整结束前保持 0 行是预期行为；当前判断运行是否健康主要看 `run.log` 持续前进、`packet_level=1`、`fct.txt` 持续增长。最新健康检查只匹配到启动行 `route_strategy=ecmp packet_level=1`，没有 fatal/killed/segfault/error 标记；原始 `wc -l` 已看到 `fct.txt` 增长到 22880374 行。`summarize_route_compare.py` 现在会在 full case 未完成时解析 latest `phase_progress` 并显示 FCT 行数，因此 `route_compare_summary.md` 可直接用于监控 running case。

## 2026-07-06 htsim `ns3_ecmp` 诊断与修复更新

后续 full `ns3_ecmp` 状态：

- FCT-enabled full `ns3_ecmp` 和 no-FCT full `ns3_ecmp` 都在接近最后的 `input_grad 1259/1262` 时未能产出 `EndToEnd.csv`，说明瓶颈不是 `fct.txt` 写盘。
- `HTSIM_DISABLE_FCT_OUTPUT=1` 仍然保留，用于减少 full run I/O，但它不是这次卡住的根因修复。

新增诊断工具：

| 文件 | 作用 |
| --- | --- |
| `make_htsim_repro_workloads.py` | 从 full Dense256 Meta workload 生成 layernorm/core7/prefix/capped 小复现 |
| `run_htsim_ns3_ecmp_diagnostics.sh` | 对指定 workload 和策略运行 htsim no-FCT，并可开启 htsim/ASTRA watchdog |

关键小复现：

| Workload | 策略 | 状态 | EndToEnd 行数 | all passes finished at | Wall |
| --- | --- | ---: | ---: | ---: | --- |
| `dense256_cap256m_core7` | old htsim `ecmp` | 0 | 12 | `54483474` | `1:27.69` |
| `dense256_cap256m_core7` | original `ns3_ecmp` | 124 timeout | 0 | - | `7:00.06` |
| `dense256_cap256m_core7` | reverse-stable-only `ns3_ecmp` | 124 timeout | 0 | - | `7:00.06` |
| `dense256_cap256m_core7` | fixed `ns3_ecmp` | 0 | 12 | `734051676` | `2:20.67` |
| `dense256_fullsize_layernorm_only` | fixed `ns3_ecmp` | 0 | 6 | `230716551` | `2:08.07` |

结论：

- Watchdog 显示 `ns3_ecmp` 卡住时有少量 RoCE flow 的 `_highest_sent` 已经到达 flow size，但 `_last_acked` 停止推进，ASTRA stream 等这些 flow 完成。
- 只稳定 ACK/NACK 反向路径不够；根因更像 htsim RoCE 缺少 tail loss timeout 恢复，尾包/drop 后没有后续包触发 NACK。
- 当前修复是 conservative correctness fix：`ns3_ecmp` forward 仍是 per-hop ECMP shortest-successor source route，ACK/NACK 使用稳定反向最短路径，并且仅对 `ns3_ecmp` 默认开启 `RoceSrc` tail RTO。
- 可调参数：`HTSIM_ROCE_TAIL_RTO=0|1`，`HTSIM_ROCE_MIN_RTO_US=<us>`，`HTSIM_WATCHDOG_EVENTS=<N>`，`HTSIM_WATCHDOG_DUMP_ASTRA=1`。
- 固定 100us tail watchdog 曾被测试并停止，因为它造成重传风暴；保留 adaptive `_rto` lower-bounded by min RTO 的保守版本。
- 该修复证明 full `ns3_ecmp` 不应再永久卡在 tail loss，但 fixed `ns3_ecmp` 的数值仍明显偏慢；后续若要做最终 NS-3 对齐，需要继续对 htsim queue/RDMA/RTO timing 做校准。

## 后续运行安排

1. 等 `htsim ECMP` 完成，刷新 `route_compare_summary.md`。
2. 脚本自动进入 `htsim spray_rr` full run。
3. `spray_rr` 完成后再次运行：

```bash
experiments/cross_backend_dense256_meta_20260624_114003/summarize_route_compare.py
```

4. 用最终表格给出两层结论：
   - `NS-3 ECMP` vs `htsim ECMP`：仿真器/模型差异。
   - `htsim ECMP` vs `htsim spray_rr/spray_plb`：路由算法差异。
