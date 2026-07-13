# 1024 GPU 拓扑一览（H100）

生成目录：`mytopo/1024/`  
GPU 规模：**1024**，机型统一为 **H100**。  
生成脚本：`scripts/generate_1024_topos.py`

## 交换机容量

| 规模 | 交换机总容量 | 400G 架构 port | 200G 架构 port | HPN switch_throughput |
|------|-------------|----------------|----------------|----------------------|
| **256** | **6.4 Tbps** | 16 | 32（Zcube n=16） | 6400 Gbps |
| **1024** | **12.8 Tbps** | 32 | 64（Zcube n=32） | 12800 Gbps |

容量计算（α=0.5）：`port × (1−α) × link_bw × 2 = 总吞吐量`  
例：400G 架构 `32 × 0.5 × 400G × 2 = 12800 Gbps = 12.8 Tbps`

## 拓扑文件

| 架构 | 文件名 | ASW | PSW | 关键参数 |
|------|--------|-----|-----|----------|
| **Meta** | `Meta_Topo_1024g_8gps_400Gbps_H100` | 64 | 16 | `asw_port=32`, `alpha=0.5`, `psw_port=256`, `beta=1` |
| **HPN** | `AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100` | 64 | 32 | DualToR 双平面；`switch_throughput=12800` |
| **DeepSeek** | `DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100` | 64 | 128 | `port=32`, `alpha=0.5`, `psw_port=64` |
| **RO** | `RailOnly_1024g_8gps_p32a0.5_400Gbps_H100` | 64 | 0 | Rail-only，无 PSW，跨 segment ASW 互联 |
| **ROFT** | `ROFT_1024g_8gps_p32a0.5_400Gbps_H100` | 64 | 16 | `asw_port=32`, `alpha=0.5`；ASW–PSW 全连接 |
| **Zcube** | `Zcube_n32_k2_1024g_8gps_200Gbps_H100` | 32 | 32 | `n=32`, `k=2`；`asw_port=psw_port=2n=64` |

## 与 256 GPU 对比（ASW / PSW）

| 架构 | 256（6.4T） | 1024（12.8T） |
|------|-------------|---------------|
| Meta | 32 / 8 | 64 / 16 |
| HPN | 32 / 16 | 64 / 32 |
| DeepSeek | 32 / 64 | 64 / 128 |
| RO | 32 / 0 | 64 / 0 |
| ROFT | 32 / 8 | 64 / 16 |
| Zcube | 16 / 16（`n=16`） | 32 / 32（`n=32`） |

## 首行元数据（SimAI 拓扑格式）

| 架构 | 首行 |
|------|------|
| Meta | `1232 8 128 80 3072 H100` |
| HPN | `1248 8 128 96 4096 H100` |
| DeepSeek | `1344 8 128 192 3072 H100` |
| RO | `1216 8 128 64 2272 H100` |
| ROFT | `1232 8 128 80 3072 H100` |
| Zcube | `1216 8 128 64 4096 H100` |

格式：`总节点数 gpus_per_server NVSwitch数 其他交换机数 链路数 GPU型号`

## 重新生成

```bash
cd /home/zty/Topo/SimAI_TyKuro9
python3 scripts/generate_1024_topos.py
```

## 公共参数

- `gpus_per_server = 8`，`nv_switch_per_server = 1`
- `nvlink_bw = 3600Gbps`
- Meta / DeepSeek / RO / ROFT 的 GPU–ASW NIC：`400Gbps`
- HPN / Zcube 的 GPU–ASW NIC：`200Gbps`
