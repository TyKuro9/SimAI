#!/usr/bin/env bash
# 256 MoE FlowSim — 转发到仓库根目录脚本
exec "$(cd "$(dirname "$0")/../.." && pwd)/run_mixtral_256moe_flowsim.sh" "$@"
