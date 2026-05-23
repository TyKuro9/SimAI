# 1024 GPU SimAI 配置文件

与 `mytopo/1024/` 拓扑一一对应。仿真参数与 `myconfig/*256*.conf` 相同，仅输出目录改为 `SimAI_TyKuro9/simulation_output/<name>1024/`。

运行前请创建对应输出目录，例如：

```bash
cd /home/zty/Topo/SimAI_TyKuro9
for d in meta1024 HPN1024 DeepSeek1024 RO1024 ROFT1024 Zcube1024; do
  mkdir -p simulation_output/$d
done
```

## 配置 ↔ 拓扑对照

| 配置 | 拓扑文件 (`mytopo/1024/`) | 输出目录 |
|------|---------------------------|----------|
| `Meta.conf` | `Meta_Topo_1024g_8gps_400Gbps_H100` | `simulation_output/meta1024/` |
| `HPN.conf` | `AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100` | `simulation_output/HPN1024/` |
| `DeepSeek.conf` | `DeepSeek_1024g_8gps_p16a0.5_400Gbps_H100` | `simulation_output/DeepSeek1024/` |
| `RO.conf` | `RailOnly_1024g_8gps_p64a0.5_400Gbps_H100` | `simulation_output/RO1024/` |
| `ROFT.conf` | `ROFT_1024g_8gps_p64a0.5_400Gbps_H100` | `simulation_output/ROFT1024/` |
| `Zcube.conf` | `Zcube_n32_k2_1024g_8gps_200Gbps_H100` | `simulation_output/Zcube1024/` |

## ns-3 仿真示例（在仓库根目录）

以 Meta + 175B 1024 workload 为例（按实际二进制与 workload 路径调整）：

```bash
AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimNetwork-debug \
  -t 8 \
  -w ./my_workloads/H100-gpt_175B-world_size1024-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/1024/Meta_Topo_1024g_8gps_400Gbps_H100 \
  -c ./myconfig/1024/Meta.conf
```

将 `-n` / `-c` 替换为上表中其它拓扑与配置即可。

## FlowSim（1024 × 175B）

FlowSim **不使用** 本目录下的 `.conf`，仅需 `-w` / `-n` / `-t` / `-o`。命令与批量脚本见：

[`experiments/flowsim_1024/README.md`](../../experiments/flowsim_1024/README.md)

```bash
# 构建（在 m4/SimAI）
cd /home/zty/Topo/m4/SimAI && ./scripts/build.sh -c flowsim

# 跑全部六种拓扑
bash /home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_1024/run_all.sh
```

## 说明

- 根目录下的 `myconfig/Meta1024.conf` 为早期副本，输出路径指向 `SimAI/`；**请以本目录 `Meta.conf` 为准**（指向 `SimAI_TyKuro9`）。
- `FLOW_FILE` / `TRACE_FILE` 等由仿真器在运行时生成或覆盖，需保证目标目录已存在。
