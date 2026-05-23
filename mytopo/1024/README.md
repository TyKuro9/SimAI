# 1024 GPU 拓扑一览（H100）

生成目录：`mytopo/1024/`  
GPU 规模：**1024**，机型统一为 **H100**。  
生成脚本：`astra-sim-alibabacloud/inputs/topo/custom_topo_generator.py`

## 拓扑文件

| 架构 | 文件名 | ASW | PSW | 备注 |
|------|--------|-----|-----|------|
| **Meta** | `Meta_Topo_1024g_8gps_400Gbps_H100` | 32 | 32 | 与 256 相同比例（`asw_port=64`, `alpha=0.5`, `psw_port=256`, `beta=1`） |
| **HPN** | `AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100` | 16 | 128 | DualToR 双平面；`switch_throughput=51200`（256 为 12800，按 server 数 ×4） |
| **DeepSeek** | `DeepSeek_1024g_8gps_p16a0.5_400Gbps_H100` | 128 | 64 | `port=16`, `alpha=0.5`, `psw_port=64` |
| **RO** | `RailOnly_1024g_8gps_p64a0.5_400Gbps_H100` | 32 | 0 | Rail-only，无 PSW，跨 segment ASW 互联 |
| **ROFT** | `ROFT_1024g_8gps_p64a0.5_400Gbps_H100` | 32 | 32 | `asw_port=64`, `alpha=0.5`；ASW–PSW 全连接 |
| **Zcube** | `Zcube_n32_k2_1024g_8gps_200Gbps_H100` | 32 | 32 | `n=32`, `k=2`（GPU 数 = n² = 1024）；ASW/PSW 各 n 台，全连接 |

## 与 256 GPU 对比（ASW / PSW）

| 架构 | 256 | 1024 |
|------|-----|------|
| Meta | 8 / 32 | 32 / 32 |
| HPN | 16 / 48 | 16 / 128 |
| DeepSeek | 32 / 64 | 128 / 64 |
| RO | 8 / 0 | 32 / 0 |
| ROFT | 8 / 32 | 32 / 32 |
| Zcube | 16 / 16（`n=16`, `k=2`） | 32 / 32（`n=32`, `k=2`） |

## 首行元数据（SimAI 拓扑格式）

| 架构 | 首行 |
|------|------|
| Meta | `1216 8 128 64 3072 H100` |
| HPN | `1296 8 128 144 4096 H100` |
| DeepSeek | `1344 8 128 192 3072 H100` |
| RO | `1184 8 128 32 2096 H100` |
| ROFT | `1216 8 128 64 3072 H100` |
| Zcube | `1216 8 128 64 4096 H100` |

格式：`总节点数 gpus_per_server NVSwitch数 其他交换机数 链路数 GPU型号`

## Zcube 参数说明

- **1024**：`n=32`, `k=2` → GPU 数 = 32² = 1024，ASW/PSW 各 **32** 台
- **256**（对照）：`n=16`, `k=2` → `Zcube_n16_k2_256g_8gps_200Gbps_H100`
- 默认端口：`asw_port = psw_port = 2n`，`alpha = beta = 0.5`
- `nic_bw = asw_to_psw_bw = 200Gbps`，`nvlink_bw = 3600Gbps`

## HPN 参数说明

256 GPU 时若沿用 `switch_throughput=12800`，每台 ASW 仅 32 个下联端口，无法连接 1024 规模下的 128 台 server（同 rank 各 1 GPU）。

因此 1024 规模将 **`switch_throughput` 调整为 51200**（×4），其余保持与 256 一致：

- DualToR_DualPlane
- `nic_bw=200Gbps`，`asw_to_psw_bw=400Gbps`
- ASW 仍为固定 **16** 台；每 Plane PSW **64** 台，合计 **128** 台 PSW

## 公共参数（除 HPN 外）

- `gpus_per_server = 8`
- `nv_switch_per_server = 1`
- `nvlink_bw = 3600Gbps`（HPN / Meta / DeepSeek / RO / ROFT 均为此值，HPN 的 NIC 为 200Gbps）
- Meta / DeepSeek / RO / ROFT 的 GPU–ASW NIC：`400Gbps`（HPN、Zcube 为 `200Gbps`）
