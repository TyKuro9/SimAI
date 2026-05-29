#!/usr/bin/env bash
# 仅跑 MetaMoE（兼容旧用法）
exec "$(cd "$(dirname "$0")/../.." && pwd)/run_mixtral_256moe_flowsim.sh" Meta "$@"
