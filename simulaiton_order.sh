NS3_CSV_BASE="./experiments/ns3_results/csv"
mkdir -p "${NS3_CSV_BASE}"

sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c ./myconfig/Meta256.conf \
  -o "${NS3_CSV_BASE}/MetaA100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_MetaA100_ns3.log

  # HPN256 拓扑 - 阿里巴巴双平面架构
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 32 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100 \
  -c ./myconfig/HPN256.conf \
  -o "${NS3_CSV_BASE}/HPN256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_HPN256H100_ns3.log

# Meta 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c ./myconfig/Meta.conf \
  -o "${NS3_CSV_BASE}/MetaA100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_MetaA100_ns3.log

# Fast Meta 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimFastNetwork-debug \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c ./myconfig/Meta-fast.conf \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_Meta-fastA100_ns3.log

# DeepSeek256 拓扑 (port=16, 4 segment)
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800 \
  -c ./myconfig/DeepSeek256.conf \
  -o "${NS3_CSV_BASE}/DeepSeek256H800/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_DeepSeek256H800_ns3.log

# Zcube 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100 \
  -c ./myconfig/Zcube256.conf \
  -o "${NS3_CSV_BASE}/Zcube256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_Zcube256H100_ns3.log

sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
-t 32 \
-w ./my_workloads/H100-gpt_175B-world_size1024-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt \
-n ./mytopo/Meta_Topo_1024g_8gps_400Gbps_A100 \
-c ./myconfig/Meta1024.conf \
-o "${NS3_CSV_BASE}/Meta1024A100/" \
2>&1 | tee experiments/ns3_results/Update-1024gpu_175B_Meta1024A100_ns3.log

# RO256 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=1 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/RO256.conf \
  -o "${NS3_CSV_BASE}/RO256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_RO256H100_ns3.log

# ROFT256 拓扑（墙钟：运行结束后看 wall= 行，或 tail 本段 .time 文件）
/usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
  -o experiments/ns3_results/Update-256gpu_22B_ROFT256H100_ns3.time \
  sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=1 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/ROFT256.conf \
  -o "${NS3_CSV_BASE}/ROFT256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_ROFT256H100_ns3.log

# ROFTwoPXN 
/usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
  -o experiments/ns3_results/Update-256gpu_22B_ROFT256woPXNH100_ns3.time \
  sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w ./my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/ROFT256_woPXN.conf \
  -o "${NS3_CSV_BASE}/ROFT256woPXNH100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_22B_ROFT256woPXNH100_ns3.log


# =============================================================================
# Mixtral 8x7B MoE workload (256 GPU, tp8 pp2 ep8, gbs256, seq2048)
# workload: my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt
# config:   myconfig/*256MoE.conf（输出/trace 文件名含 MoE，与 gpt_22B 区分）
# 注意：文件名含 *，-w 路径必须加引号
# MoE 在 layer11 大 ALLGATHER 曾触发 double free：MockNcclGroup task_list[-1] 越界（已修）
# 修改 astra-sim 后须 ./scripts/build.sh -c ns3 重编；RO/ROFT 仍建议 AS_PXN_ENABLE=0
# =============================================================================

# HPN256 拓扑 - 阿里巴巴双平面架构
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 32 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100 \
  -c ./myconfig/HPN256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-HPN256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_HPN256H100_ns3.log

# Meta 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c ./myconfig/Meta256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-Meta256A100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_Meta256A100_ns3.log

# Fast Meta 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimFastNetwork-debug \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c ./myconfig/Meta-fast256MoE.conf \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_Meta-fast256A100_ns3.log

# DeepSeek256 拓扑 (port=16, 4 segment)
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800 \
  -c ./myconfig/DeepSeek256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-DeepSeek256H800/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_DeepSeek256H800_ns3.log

# Zcube 拓扑
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100 \
  -c ./myconfig/Zcube256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-Zcube256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_Zcube256H100_ns3.log

# RO256 拓扑（MoE 须关闭 PXN，与下方 ROFT256_woPXN 相同）
sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=1 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/RO256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-RO256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_RO256H100_ns3.log

# ROFT256 拓扑（墙钟：运行结束后看 wall= 行，或 tail 本段 .time 文件）
/usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
  -o experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_ROFT256H100_ns3.time \
  sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/ROFT256MoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-ROFT256H100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_ROFT256H100_ns3.log

# ROFT256 关闭 PXN
/usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
  -o experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_ROFT256woPXNH100_ns3.time \
  sudo AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 ./bin/SimAI_simulator \
  -t 16 \
  -w './my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt' \
  -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
  -c ./myconfig/ROFT256_woPXNMoE.conf \
  -o "${NS3_CSV_BASE}/Mixtral-ROFT256woPXNH100/" \
  2>&1 | tee experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_ROFT256woPXNH100_ns3.log