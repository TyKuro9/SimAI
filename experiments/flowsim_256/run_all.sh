#!/usr/bin/env bash
# 256 MoE FlowSim — 转发到仓库根目录脚本（兼容旧名，同 run_moe_all.sh）
exec "$(cd "$(dirname "$0")/../.." && pwd)/run_256moe_flowsim.sh" "$@"
