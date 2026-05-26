#!/usr/bin/env bash
# 创建 4096 FlowSim 输出子目录
set -euo pipefail

BASE="/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/4096"
for d in Meta HPN DeepSeek RO ROFT Zcube; do
  mkdir -p "${BASE}/${d}"
done
echo "Created under ${BASE}/"
