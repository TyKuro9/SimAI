#!/usr/bin/env bash
# 1024 Mixtral MoE FlowSim — 转发到仓库根目录脚本
exec "$(cd "$(dirname "$0")/../.." && pwd)/run_mixtral_1024moe_flowsim.sh" "$@"
