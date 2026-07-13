#!/usr/bin/env bash
# 创建 256 MoE FlowSim 输出子目录
set -euo pipefail

BASE="/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/256"
for d in MetaMoE HPNMoE DeepSeekMoE ZcubeMoE ROMoE ROFTMoE; do
  mkdir -p "${BASE}/${d}"
done
