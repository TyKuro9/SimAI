#!/usr/bin/env python3
"""
生成 1024 GPU 全速拓扑（交换机容量 12.8 Tbps）。

与 256 规模（6.4 Tbps）对照：
  - Meta / DeepSeek / RO / ROFT（400G NIC）：port/asw_port = 32（256 为 16）
  - HPN：switch_throughput = 12800 Gbps（256 为 6400）
  - Zcube（200G NIC）：n=32 → asw_port = 2n = 64（256 为 n=16, port=32）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "mytopo" / "1024"
GENERATOR_DIR = ROOT / "astra-sim-alibabacloud" / "inputs" / "topo"

sys.path.insert(0, str(GENERATOR_DIR))

from custom_topo_generator import (  # noqa: E402
    GenerateHPNTopo,
    GenerateMetaTopo,
    GenerateRailOnlyTopo,
    GenerateROFTTopo,
    GenerateZcubeTopo,
    generateDeepSeekTopo,
)

SWITCH_CAPACITY_Gbps = 12800
GPU_COUNT = 1024
GPUS_PER_SERVER = 8
GPU_TYPE = "H100"

# 400G 架构：asw_port=32 → 16 down + 16 up @400G = 12.8 Tbps
PORT_400G = 32

# 旧版文件名（p16/p64），生成成功后删除
LEGACY_FILES = [
    "DeepSeek_1024g_8gps_p16a0.5_400Gbps_H100",
    "RailOnly_1024g_8gps_p64a0.5_400Gbps_H100",
    "ROFT_1024g_8gps_p64a0.5_400Gbps_H100",
]


def Main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    original_cwd = Path.cwd()
    try:
        import os

        os.chdir(OUT_DIR)

        print(f"输出目录: {OUT_DIR}")
        print(f"交换机容量: {SWITCH_CAPACITY_Gbps} Gbps (= 12.8 Tbps)")
        print()

        GenerateMetaTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            asw_port=PORT_400G,
            psw_port=256,
            alpha=0.5,
            beta=1,
            nvlink_bw="3600Gbps",
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
        )
        print()

        GenerateHPNTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            switch_throughput=SWITCH_CAPACITY_Gbps,
            alpha=0.5,
            dual_plane=True,
            nvlink_bw="3600Gbps",
            nic_bw="200Gbps",
            asw_to_psw_bw="400Gbps",
        )
        print()

        generateDeepSeekTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            port=PORT_400G,
            alpha=0.5,
            psw_port=64,
            gpu_type=GPU_TYPE,
            nv_switch_per_server=1,
            nvlink_bw="3600Gbps",
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
        )
        print()

        GenerateRailOnlyTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            asw_port=PORT_400G,
            alpha=0.5,
            nvlink_bw="3600Gbps",
            nic_bw="400Gbps",
        )
        print()

        GenerateROFTTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            asw_port=PORT_400G,
            alpha=0.5,
            psw_port=64,
            beta=1.0,
            nvlink_bw="3600Gbps",
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
        )
        print()

        GenerateZcubeTopo(
            n=32,
            k=2,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            nvlink_bw="3600Gbps",
            nic_bw="200Gbps",
            asw_to_psw_bw="200Gbps",
        )
        print()

        for legacy in LEGACY_FILES:
            legacy_path = OUT_DIR / legacy
            if legacy_path.is_file():
                legacy_path.unlink()
                print(f"[清理] 已删除旧拓扑: {legacy}")

        print()
        print("全部 6 套 1024 拓扑（12.8 Tbps）已写入", OUT_DIR)
        return 0
    finally:
        import os

        os.chdir(original_cwd)


if __name__ == "__main__":
    sys.exit(Main())
