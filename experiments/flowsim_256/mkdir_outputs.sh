#!/usr/bin/env bash
# 兼容旧入口 — 转发到 mkdir_moe_outputs.sh
exec "$(cd "$(dirname "$0")" && pwd)/mkdir_moe_outputs.sh" "$@"
