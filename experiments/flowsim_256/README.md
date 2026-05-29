# 256 GPU × Mixtral 8x7B MoE — FlowSim

Workload（固定）：

`my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt`

拓扑目录：`mytopo/`（256 规模文件在根目录，非子目录）

## 用法

```bash
cd /home/zty/Topo/SimAI_TyKuro9

# 全部拓扑
bash run_mixtral_256moe_flowsim.sh

# 指定拓扑（可多选）
bash run_mixtral_256moe_flowsim.sh Meta HPN DeepSeek
bash run_mixtral_256moe_flowsim.sh ROFT256
```

等价入口：

```bash
bash experiments/flowsim_256/run_all.sh Meta
```

## 可选拓扑

| 参数名 | 拓扑文件 | 输出目录 |
|--------|----------|----------|
| Meta | Meta_Topo_256g_8gps_400Gbps_A100 | `flowsim_results/256/MetaMoE/` |
| HPN | AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100 | `HPNMoE/` |
| DeepSeek | DeepSeek_256g_8gps_p16a0.5_400Gbps_H800 | `DeepSeekMoE/` |
| Zcube | Zcube_n16_k2_256g_8gps_200Gbps_H100 | `ZcubeMoE/` |
| RO | RailOnly_256g_8gps_p64a0.5_400Gbps_H100 | `ROMoE/` |
| ROFT | ROFT_256g_8gps_p64a0.5_400Gbps_H100 | `ROFTMoE/` |

FlowSim **不需要** `myconfig/*256MoE.conf`（仅 NS3 使用）。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `FLOWSIM_THREADS` | `16` | `-t` 线程数 |
| `FLOWSIM_BIN` | `m4/SimAI/bin/SimAI_flowsim` | 可执行文件路径 |

## 输出

- 各拓扑：`experiments/flowsim_results/256/<Topo>MoE/fct.txt`
- 日志：`experiments/flowsim_results/256/Update-256gpu_Mixtral8x7B-MoE_*_flowsim.log`
