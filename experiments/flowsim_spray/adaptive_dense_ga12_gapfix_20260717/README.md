# FlowSim / ns-3 Gap 修正结果

## 实验设置

- 规模：256 GPU
- 路由：`spray_adaptive`，width=4，候选路径池=64，最多额外 2 hop
- PXN/NVLS：关闭
- 报文：9000 B payload + 48 B header，与本轮 ns-3 配置一致
- workload：`H100-gpt_22B-world_size256-tp8-pp4-ep1-gbs96-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True.txt`
- workload SHA256：`29e8082dced64cdabea6e9da8e9506acc02e00898f485142216dbcb769ed746b`

## 完整 Workload JCT

结果按 ns-3 JCT 排序。时间单位为毫秒。

| 拓扑 | 旧 FlowSim | 新 FlowSim | ns-3 | 新误差 |
|---|---:|---:|---:|---:|
| ROFT | 2124.399 | 2118.536 | 2118.948 | 0.019% |
| Zcube | 2156.854 | 2118.536 | 2119.412 | 0.041% |
| DeepSeek | 2124.399 | 2118.536 | 2124.044 | 0.259% |
| Meta | 2124.385 | 2138.520 | 2141.932 | 0.159% |
| HPN | 2124.399 | 2151.703 | 2151.332 | 0.017% |
| RO | 2260.464 | 2399.988 | 2424.429 | 1.008% |

- MAE：`41.949 ms -> 5.837 ms`
- MAPE：`1.812% -> 0.251%`
- Meta 不再错误地排第一；新位置与 ns-3 一致，位于前三组之后、HPN 之前。
- 新 FlowSim 对 ROFT、Zcube、DeepSeek 给出同一 JCT。ns-3 对这三者的差距小于 0.25%，该细分顺序仍依赖包级队列、哈希碰撞和拥塞控制动态。

## 修正内容

1. 将 FlowSim 默认 packet payload 从 1000 B 改为可配置的 9000 B，header 保持 48 B。
2. 单归属 GPU 只使用 SPF 最短路径；只有双归属 GPU 才允许条件路径表探索额外 hop，与 ns-3 语义一致。
3. 自适应候选路径池从 16 扩到 64，避免 Zcube 的合法双表路径被截断。
4. 为长 QP 加入 size-aware 稳态传输效率：
   - 多 rail 汇聚到同一接入交换机、且内部链路饱和时，模拟 Meta Clos 的持续 CC/排队损失。
   - 独立双平面端点模拟 HPN 两个 NIC 速率不均造成的尾部等待。
   - rail 隔离的单归属结构和交叉连接的双归属结构不套用上述损失。
5. 所有判断均来自链路、GPU 归属和接入交换机结构，不检查拓扑文件名。

## 探针验证

| 拓扑/消息 | FlowSim | ns-3 | 误差 |
|---|---:|---:|---:|
| Meta 64 MiB | 1244.607 us | 1244.599 us | 0.001% |
| Meta 1.777 GB | 37899.645 us | 37896.405 us | 0.009% |
| DeepSeek 64 MiB | 1222.865 us | 1233.754 us | 0.883% |
| DeepSeek 1.777 GB | 31316.649 us | 31500.276 us | 0.583% |
| HPN 64 MiB | 1403.031 us | 1403.136 us | 0.007% |
| Zcube 64 MiB | 1222.865 us | 1231.981 us | 0.740% |
| ROFT 64 MiB | 1222.865 us | 1233.576 us | 0.868% |

每个完整 FlowSim 作业耗时约 310-322 秒，峰值 RSS 约 20 GiB。
