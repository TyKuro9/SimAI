# Dense 256 Meta full workload cross-backend run started 20260624_114003
# workload: /home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt
# topology: /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100

# NS-3
cd /home/zty/Topo/SimAI_TyKuro9 && env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 ./bin/SimAI_simulator -t 16 -w /home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c /home/zty/Topo/SimAI_TyKuro9/myconfig/Meta256.conf -o /home/zty/Topo/SimAI_TyKuro9/experiments/cross_backend_dense256_meta_20260624_114003/ns3/

# htsim packet RoCE PLB
cd /home/zty/Topo/SimAI_TyKuro9 && ./bin/SimAI_htsim -w /home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c /home/zty/Topo/SimAI_TyKuro9/myconfig/Meta256MoE.conf -o /home/zty/Topo/SimAI_TyKuro9/experiments/cross_backend_dense256_meta_20260624_114003/htsim_spray_plb/ -r spray_plb

# FlowSim
cd /home/zty/Topo/m4/SimAI && /home/zty/Topo/m4/SimAI/bin/SimAI_flowsim -t 16 -w /home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -o /home/zty/Topo/SimAI_TyKuro9/experiments/cross_backend_dense256_meta_20260624_114003/flowsim/
