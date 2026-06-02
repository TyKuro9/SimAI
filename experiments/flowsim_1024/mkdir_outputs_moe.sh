#!/usr/bin/env bash
# 创建 1024 Mixtral MoE FlowSim 输出子目录
set -euo pipefail

BASE="/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/1024"
for d in MetaMoE HPNMoE DeepSeekMoE ZcubeMoE ROMoE ROFTMoE; do
  mkdir -p "${BASE}/${d}"
done
echo "Created MoE output dirs under ${BASE}/"
