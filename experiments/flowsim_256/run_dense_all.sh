#!/usr/bin/env bash
# 256 Dense FlowSim — 转发到仓库根目录脚本
exec "$(cd "$(dirname "$0")/../.." && pwd)/run_256dense_flowsim.sh" "$@"
