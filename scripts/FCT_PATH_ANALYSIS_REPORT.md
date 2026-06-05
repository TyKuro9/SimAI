# FCT Path 分析报告

> 256 GPU 规模 · 生成时间：2026-05-31  
> 工具：`scripts/analyze_fct_paths.py`  
> 原始运行日志：`scripts/fct_path_analysis_report.txt`

---

## 1. 概述

本报告汇总 SimAI ns-3 仿真中的 **Path（路径）分析**：原理、方法、路径类型定义，以及对 Meta / HPN / DeepSeek / Zcube / RO / ROFT 等拓扑的横向对比。

Path 分析与 FCT 分析互补：

| 分析类型 | 回答的问题 |
|---------|-----------|
| **FCT 分析** | 流有多慢？（P50/P95/P99 慢化、按 m_size 分桶） |
| **Path 分析** | 流走了哪条路？（机内 NVLink vs 跨 ASW/PSW） |

---

## 2. 分析原理

### 2.1 两层结构

Path 分析分为**静态**与**动态**两层：

```
拓扑文件 (.topo)
    │
    ├─► [静态] ParseTopo → 识别 NVSW/ASW/PSW
    │         BuildNextHopTables → 复现 ns-3 CalculateRoute
    │         256×256 GPU 对 TracePath + ClassifyPath
    │         → pairclass 缓存（每对 GPU 的路径类型）
    │
    └─► [动态] 扫描 FCT 文件 (*_fct.txt)
              每条流 (src, dst, m_size) 查 pairclass
              → 按路径类型聚合流数与字节量
```

- **pairclass（静态）**：拓扑能力——任意 GPU 对之间**应该**走什么路，与 workload 无关。
- **FCT 归因（动态）**：实际 workload 中，各路径类型承载了多少流量。

### 2.2 路由算法

与 ns-3 `CalculateRoute` 保持一致：

1. 对每个目的 GPU，从全网节点做 **BFS 最短路**；
2. **NVSwitch 优先**：同等跳数时，优先选择经 NVSwitch 的路径；
3. 沿 next-hop 表从 src 追溯到 dst，得到完整路径；
4. 根据路径经过的交换机层级分类。

### 2.3 ASW / PSW 识别

| 拓扑类型 | 识别规则 |
|---------|---------|
| Meta / HPN / ROFT 等 | ASW = 与 GPU 直连的 non-NV 交换机；PSW = 其余 |
| **Zcube (k=2)** | ASW、PSW **均**直连 GPU；按生成器顺序（前 n 台 ASW、后 n 台 PSW）+ seg/rail 连线模式校验 |

Zcube 修复说明：旧逻辑将 PSW 误判为 ASW（因 PSW 也直连 GPU），导致 `PSW_ONLY` / `ASW_PSW` 分类错误；已在 `InferAswPswIds()` 中修复。

---

## 3. 路径类型定义

| 路径类型 | 含义 | 典型场景 |
|---------|------|---------|
| **LOCAL** | src = dst | 本地 |
| **NVSW_ONLY** | GPU → NVSwitch → GPU | 同 host 8 GPU 经 NVLink |
| **ASW_ONLY** | 经 ASW，不经 PSW | 同 segment / 同 ToR 域跨 host |
| **PSW_ONLY** | 经 PSW，不经 ASW | Zcube 同 rail 跨 segment |
| **ASW_PSW** | 经 ASW + PSW | 跨 segment 跨 rail（常见跨网路径） |
| **PXN_NVSW_ASW** | 首跳 NVSwitch 且含 ASW | PXN 代理发送 |
| **PXN_NVSW_ASW_PSW** | 首跳 NVSwitch 且含 ASW+PSW | PXN + 跨 spine |
| **NO_ROUTE** | 无路由 | DeepSeek segment 隔离等 |
| **OTHER** | 无法归类 | 极少见 |

---

## 4. 拓扑结构对比（256 GPU）

| 拓扑 | GPU | NVSW | ASW | PSW | NIC | 结构特点 |
|------|-----|------|-----|-----|-----|---------|
| **Meta** | 256 | 32 | 32 | 8 | 400G | 经典 Clos：GPU→ASW→PSW |
| **HPN** | 256 | 32 | 16 | 32 | 200G | DualToR 双平面 |
| **DeepSeek** | 256 | 32 | 32 | 64 | 400G | 多 segment，部分 GPU 对无路由 |
| **Zcube** | 256 | 32 | 16 | 16 | 200G | GPU 同时连 ASW[seg] 与 PSW[rail] |
| **RO** | 256 | 32 | 8 | 32 | 400G | Rail-only |
| **ROFT** | 256 | 32 | 8 | 32 | 400G | RO + Fat-tree spine |

### 4.1 Zcube 拓扑要点（n=16, k=2）

- GPU 编号：`gid = seg × n + rail`（seg=segment, rail=列）
- 连线：GPU ↔ ASW[seg]、GPU ↔ PSW[rail]、ASW ↔ PSW 全连接
- 节点 ID：GPU 0–255，NVSW 256–287，ASW 288–303，PSW 304–319

**Zcube 静态 pairclass 分布（65536 GPU 对）：**

| 路径类型 | GPU 对数 | 占比 |
|---------|---------|------|
| LOCAL | 256 | 0.4% |
| NVSW_ONLY | 1,792 | 2.7% |
| ASW_ONLY | 2,048 | 3.1% |
| PSW_ONLY | 3,840 | 5.9% |
| ASW_PSW | 57,600 | 87.9% |

Zcube 是唯一在静态 pairclass 中有大量 **PSW_ONLY** 的拓扑，体现「GPU 直连 PSW」设计。

---

## 5. FCT 实际流量对比

数据来源：`simulation_output/*/`*`_fct.txt`（256 GPU 22B / MoE 类 workload，除 RO256 外规模相近）。

### 5.1 总览表

| 拓扑 / 场景 | 总流数 | NVSW_ONLY | ASW_ONLY | ASW_PSW | PSW_ONLY | 跨网流数 | 跨网占比 |
|------------|--------|-----------|----------|---------|----------|---------|---------|
| Meta256 | 30,086,790 | 30,086,054 | — | 736 | — | 736 | 0.002% |
| Meta256 (meta_fct2) | 33,401,514 | 33,398,186 | — | 3,328 | — | 3,328 | 0.01% |
| DeepSeek256 | 30,191,525 | 30,190,845 | 600 | 80 | — | 680 | 0.002% |
| HPN256 | 33,965,252 | 33,963,924 | 1,328 | — | — | 1,328 | 0.004% |
| **Zcube256** | 34,011,306 | 34,010,242 | **536** | **528** | — | **1,064** | 0.003% |
| RO256 (PXN=1) | 37,485 | 37,485 | — | — | — | 0 | 0% |
| ROFT256 (PXN=1) | 31,984,346 | 31,982,938 | 1,408 | — | — | 1,408 | 0.004% |
| ROFT256 woPXN | 32,014,844 | 32,014,012 | 832 | — | — | 832 | 0.003% |

> **跨网流** = ASW_ONLY + ASW_PSW + PSW_ONLY（不含 NVSW_ONLY）

### 5.2 消息大小（m_size）特征

| 路径类型 | 典型 m_size | 说明 |
|---------|------------|------|
| NVSW_ONLY | 393216 B（384 KB）为主 | 机内 collective 小消息 |
| 跨网流 | **63700992 B（≈60.7 MB）** | All-to-All 跨 host 大消息 |

### 5.3 各拓扑详细统计

#### Meta256

```
GPU=256, NVSW=32, ASW=32, PSW=8
NVSW_ONLY   30,086,054  (100.00%)  平均 m_size 402,351 B
ASW_PSW            736  ( 0.00%)  平均 m_size 63,700,992 B
```

#### Meta256 (meta_fct2)

```
GPU=256, NVSW=32, ASW=32, PSW=8
NVSW_ONLY   33,398,186  (99.99%)  平均 m_size 413,724 B
ASW_PSW          3,328  ( 0.01%)  平均 m_size 63,700,992 B
```

#### DeepSeek256

```
GPU=256, NVSW=32, ASW=32, PSW=64
路由表警告: 55,552 个 GPU 对 NO_ROUTE（segment 隔离），FCT 中未出现无法解析的流
NVSW_ONLY   30,190,845  (100.00%)
ASW_ONLY           600  ( 0.00%)
ASW_PSW             80  ( 0.00%)
```

#### HPN256

```
GPU=256, NVSW=32, ASW=16, PSW=32
NVSW_ONLY   33,963,924  (100.00%)
ASW_ONLY         1,328  ( 0.00%)
```

#### Zcube256（修复 pairclass 后）

```
GPU=256, NVSW=32, ASW=16, PSW=16  [topo_kind: Zcube_k2]
NVSW_ONLY   34,010,242  (100.00%)
ASW_ONLY           536  ( 0.00%)   同 segment 跨 rail
ASW_PSW            528  ( 0.00%)   跨 segment 跨 rail
PSW_ONLY             0            pairclass 有能力，本 workload 未命中
```

修复前 1064 条跨网流全部被误标为 ASW_ONLY；修复后正确拆分为 536 + 528。

#### RO256 (PXN=1)

```
GPU=256, NVSW=32, ASW=8, PSW=32
NVSW_ONLY       37,485  (100.00%)  — 总流数远小于其他拓扑（不同 workload 规模）
```

#### ROFT256 (PXN=1) vs woPXN

| 配置 | 跨网流数 | 说明 |
|------|---------|------|
| PXN=1 | 1,408 | PXN 代理增加跨网路径 |
| woPXN | 832 | 无 PXN，跨网流更少（约 −41%） |

---

## 6. 结论与解读

### 6.1 流量高度本地化

所有大模型 workload 中 **>99.99%** 的流走 **NVSW_ONLY**（机内 NVLink）。跨网流占比均 **< 0.01%**，主要来自 All-to-All 的跨 host 大消息（63700992 B）。

8 GPU/server + NVLink 掩盖了绝大部分跨网通信需求。

### 6.2 拓扑对跨网路径类型的影响

| 观察 | 解释 |
|------|------|
| Meta / DeepSeek 跨网走 **ASW_PSW** | 经典 Clos，必须经 spine |
| HPN / ROFT 跨网走 **ASW_ONLY** | 本 workload 未触发 PSW 层 |
| Zcube 跨网分为 **ASW_ONLY + ASW_PSW** | 同 segment 走 ASW；跨 segment 走 ASW→PSW |
| Zcube 无 PSW_ONLY 实际流量 | 静态有 3840 对能力，All-to-All 模式未命中「同 rail 跨 segment」 |
| DeepSeek 大量 NO_ROUTE 对 | 拓扑 segment 隔离，实际 FCT 流均在可达范围内 |

### 6.3 Path 分析与 FCT 的关系

```
FCT 分析  →  各拓扑慢化、tail latency、按 m_size 分桶
     ↑
Path 分析 →  解释差异来源：跨网占比、路径层级、PXN 影响
```

Path 分析**不能替代** FCT，但用于理解 FCT 差异、验证拓扑设计、对比 PXN 等配置。

### 6.4 跨拓扑横向对比（一句话）

| 拓扑 | 跨网路径特点 | 跨网流规模（本次） |
|------|-------------|-------------------|
| Meta | ASW+PSW 两级 | 736–3328 |
| HPN | 仅 ASW | 1328 |
| DeepSeek | ASW 或 ASW+PSW，路由受限 | 680 |
| Zcube | ASW 或 ASW+PSW，路径类型最丰富 | 1064 |
| ROFT | 仅 ASW，PXN 影响明显 | 832–1408 |

---

## 7. 使用方法

### 7.1 运行分析

```bash
cd SimAI_TyKuro9

# 全拓扑分析（重建 pairclass）
python3 scripts/analyze_fct_paths.py --rebuild-cache

# 仅 Zcube
python3 scripts/analyze_fct_paths.py --jobs Zcube256 --rebuild-cache
```

### 7.2 输出文件

| 文件 | 说明 |
|------|------|
| `scripts/fct_path_analysis_report.txt` | 终端运行日志 |
| `scripts/.fct_path_pair_cache/*.pairclass` | GPU 对路径分类缓存 |
| `scripts/FCT_PATH_ANALYSIS_REPORT.md` | 本报告 |

### 7.3 查询示例

```bash
# GPU 0 → GPU 16 在 Zcube 上的路径类型
grep "^0 16 " scripts/.fct_path_pair_cache/Zcube_n16_k2_256g_8gps_200Gbps_H100_nopxn.pairclass
# 输出: 0 16 PSW_ONLY

# 统计某拓扑 pairclass 分布
python3 -c "
from collections import Counter
p='scripts/.fct_path_pair_cache/Zcube_n16_k2_256g_8gps_200Gbps_H100_nopxn.pairclass'
print(Counter(l.split()[2] for l in open(p)))
"
```

---

## 8. 附录

### 8.1 相关代码

| 文件 | 作用 |
|------|------|
| `scripts/analyze_fct_paths.py` | Path 分析主脚本 |
| `astra-sim-alibabacloud/inputs/topo/custom_topo_generator.py` | 拓扑生成（含 `GenerateZcubeTopo`） |
| `ns-3-alibabacloud/analysis/fct_standard_report.py` | FCT 标准报告（与 Path 分析互补） |

### 8.2 路径类型判定逻辑（代码摘要）

```python
# ClassifyPath 优先级：
# 1. 首跳 NVSW 且含 ASW → PXN_NVSW_ASW(_PSW)
# 2. 仅 NVSW → NVSW_ONLY
# 3. 仅 ASW → ASW_ONLY
# 4. ASW + PSW → ASW_PSW
# 5. 仅 PSW → PSW_ONLY
```

### 8.3 数据文件路径

| 拓扑 | FCT 文件 | 拓扑文件 |
|------|---------|---------|
| Meta256 | `simulation_output/meta256/meta256_fct.txt` | `mytopo/Meta_Topo_256g_8gps_400Gbps_A100` |
| HPN256 | `simulation_output/HPN256/HPN256_fct.txt` | `mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100` |
| DeepSeek256 | `simulation_output/DeepSeek256/DeepSeek256_fct.txt` | `mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800` |
| Zcube256 | `simulation_output/Zcube256/Zcube256_fct.txt` | `mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100` |
| RO256 | `simulation_output/RO256/RO256_fct.txt` | `mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100` |
| ROFT256 | `simulation_output/ROFT256/ROFT256_fct.txt` | `mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100` |

---

*报告由 path 分析流程自动生成与整理。如需更新数据，请重新运行 `analyze_fct_paths.py --rebuild-cache` 并同步修订本报告第 5 节。*
