#!/usr/bin/env bash
# 兼容旧入口 — 转发到 run_256moe_flowsim.sh
exec "$(cd "$(dirname "$0")" && pwd)/run_256moe_flowsim.sh" "$@"
