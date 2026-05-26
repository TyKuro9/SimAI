# 4096 GPU SimAI 配置文件

与 `mytopo/4096/` 拓扑一一对应。仿真参数沿用 `myconfig/1024/*.conf`，仅更新拓扑注释与输出目录。

运行前请创建对应输出目录，例如：

```bash
cd /home/zty/Topo/SimAI_TyKuro9
for d in meta4096 HPN4096 DeepSeek4096 RO4096 ROFT4096 Zcube4096; do
  mkdir -p simulation_output/$d
done
```

## 配置与拓扑对照

| 配置 | 拓扑文件 (`mytopo/4096/`) | 输出目录 |
|------|---------------------------|----------|
| `Meta.conf` | `Meta_Topo_4096g_8gps_400Gbps_H100` | `simulation_output/meta4096/` |
| `HPN.conf` | `AlibabaHPN_4096g_8gps_DualToR_DualPlane_200Gbps_H100` | `simulation_output/HPN4096/` |
| `DeepSeek.conf` | `DeepSeek_4096g_8gps_p128a0.5_400Gbps_H100` | `simulation_output/DeepSeek4096/` |
| `RO.conf` | `RailOnly_4096g_8gps_p64a0.5_400Gbps_H100` | `simulation_output/RO4096/` |
| `ROFT.conf` | `ROFT_4096g_8gps_p128a0.5_400Gbps_H100` | `simulation_output/ROFT4096/` |
| `Zcube.conf` | `Zcube_n64_k2_4096g_8gps_200Gbps_H100` | `simulation_output/Zcube4096/` |

## ns-3 仿真示例

```bash
AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimNetwork-debug \
  -t 8 \
  -w ./my_workloads/H100-gpt_175B-world_size4096-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/4096/Meta_Topo_4096g_8gps_400Gbps_H100 \
  -c ./myconfig/4096/Meta.conf
```

将 `-n` / `-c` 替换为上表中其它拓扑与配置即可。

说明：`FLOW_FILE` / `TRACE_FILE` 等由仿真器在运行时生成或覆盖，需保证目标目录已存在。
