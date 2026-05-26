# 4096 GPU 拓扑一览（H100）

生成目录：`mytopo/4096/`
GPU 规模：**4096**，每台 server **8 GPU**，共 **512 server**，每台 server 1 个 NVSwitch。

## 拓扑文件与交换机规模

| 架构 | 文件名 | ASW 个数 | ASW 端口数 | PSW 个数 | PSW 端口数 | 首行元数据 | 备注 |
|------|--------|----------|------------|----------|------------|------------|------|
| Meta | `Meta_Topo_4096g_8gps_400Gbps_H100` | 64 | 128 | 64 | 256 | `4736 8 512 128 12288 H100` | asw_port=128, alpha=0.5, psw_port=256, beta=1 |
| HPN | `AlibabaHPN_4096g_8gps_DualToR_DualPlane_200Gbps_H100` | 16 | 512 down + 256 up (= 768) | 512 | 8 used ASW-facing ports per PSW | `5136 8 512 528 16384 H100` | DualToR 双平面；switch_throughput=204800Gbps |
| DeepSeek | `DeepSeek_4096g_8gps_p128a0.5_400Gbps_H100` | 64 | 128 | 512 | 64 | `5184 8 512 576 12288 H100` | port=128, alpha=0.5, psw_port=64；每 segment 64 host |
| RO | `RailOnly_4096g_8gps_p64a0.5_400Gbps_H100` | 128 | 64 | 0 | - | `4736 8 512 128 9152 H100` | Rail-only；无 PSW；同 rank ASW 跨 segment 全互联 |
| ROFT | `ROFT_4096g_8gps_p128a0.5_400Gbps_H100` | 64 | 128 | 64 | 64 used ASW-facing ports | `4736 8 512 128 12288 H100` | asw_port=128, alpha=0.5；ASW-PSW 全连接 |
| Zcube | `Zcube_n64_k2_4096g_8gps_200Gbps_H100` | 64 | 128 | 64 | 128 | `4736 8 512 128 16384 H100` | n=64, k=2；GPU 数 = n^2；asw_port=psw_port=2n |

格式：`总节点数 gpus_per_server NVSwitch数 其他交换机数 链路数 GPU型号`。
