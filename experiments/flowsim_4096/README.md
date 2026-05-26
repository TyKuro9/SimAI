# 4096 GPU FlowSim 仿真命令

Workload（固定）：

`/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_175B-world_size4096-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt`

拓扑目录：`/home/zty/Topo/SimAI_TyKuro9/mytopo/4096/`

## 前置条件

1. FlowSim 二进制在 `m4/SimAI` 中构建：

```bash
cd /home/zty/Topo/m4/SimAI
./scripts/build.sh -c flowsim
```

2. 创建输出目录：

```bash
cd /home/zty/Topo/SimAI_TyKuro9
bash experiments/flowsim_4096/mkdir_outputs.sh
```

## FlowSim 参数说明

| 参数 | 含义 |
|------|------|
| `-t` | 线程数，默认 `32`，可用 `FLOWSIM_THREADS` 覆盖 |
| `-w` | AICB workload 文件 |
| `-n` | 拓扑文件（`mytopo/4096/` 下） |
| `-o` | 结果目录（写入 `fct.txt` 等；不需要 `-c` SimAI.conf） |

`myconfig/4096/*.conf` 仅用于 ns-3 仿真，FlowSim 不使用。

## 单条命令（在 `m4/SimAI` 下执行）

公共变量（可复制到 shell）：

```bash
export FLOWSIM=/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim
export WL=/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_175B-world_size4096-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt
export TOPO=/home/zty/Topo/SimAI_TyKuro9/mytopo/4096
export OUT=/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/4096
export LOG=/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/4096
export T=32
cd /home/zty/Topo/m4/SimAI
```

### Meta

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/Meta_Topo_4096g_8gps_400Gbps_H100 -o $OUT/Meta/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_MetaH100_flowsim.log
```

### HPN

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/AlibabaHPN_4096g_8gps_DualToR_DualPlane_200Gbps_H100 -o $OUT/HPN/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_HPN4096H100_flowsim.log
```

### DeepSeek

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/DeepSeek_4096g_8gps_p128a0.5_400Gbps_H100 -o $OUT/DeepSeek/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_DeepSeek4096H100_flowsim.log
```

### RO（RailOnly）

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/RailOnly_4096g_8gps_p64a0.5_400Gbps_H100 -o $OUT/RO/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_RO4096H100_flowsim.log
```

### ROFT

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/ROFT_4096g_8gps_p128a0.5_400Gbps_H100 -o $OUT/ROFT/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_ROFT4096H100_flowsim.log
```

### Zcube（n=64, k=2）

```bash
$FLOWSIM -t $T -w $WL -n $TOPO/Zcube_n64_k2_4096g_8gps_200Gbps_H100 -o $OUT/Zcube/ \
  2>&1 | tee $LOG/Update-4096gpu_175B_Zcube4096H100_flowsim.log
```

## 批量运行

```bash
bash /home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_4096/run_all.sh
```

仅跑某一种架构：

```bash
bash /home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_4096/run_all.sh DeepSeek
```

可选架构：`Meta` `HPN` `DeepSeek` `RO` `ROFT` `Zcube`。

## 输出文件

每个 `-o` 目录下主要产物：

| 文件 | 说明 |
|------|------|
| `fct.txt` | Flow 完成时间（FlowSim 汇总） |
| 上级 `*.log` | 完整 stdout/stderr |

详见 [`mytopo/4096/README.md`](../../mytopo/4096/README.md)。
