#!/usr/bin/env python3
"""Generate 1024-GPU topologies with a 12.8Tbps switch port target.

Single-link rates are preserved from the existing 1024 H100 topology family:
400Gbps for Meta/DeepSeek/RO/ROFT scale-out links, 200Gbps for HPN/Zcube NICs,
and 3600Gbps for NVSwitch scale-up links.  The 12.8Tbps budget applies only to
ordinary scale-out switches, not NVSwitch nodes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "astra-sim-alibabacloud" / "inputs" / "topo"
sys.path.insert(0, str(GENERATOR_DIR))
sys.path.insert(0, str(ROOT / "scripts"))

from check_switch_throughput import summarize_topology  # noqa: E402
from custom_topo_generator import (  # noqa: E402
    GenerateHPNTopo,
    GenerateZcubeTopo,
    TopoGenerator,
    generateDeepSeekTopo,
)
from fault_tolerance_experiments import parse_topology  # noqa: E402


GPU_COUNT = 1024
GPUS_PER_SERVER = 8
SERVER_COUNT = GPU_COUNT // GPUS_PER_SERVER
GPU_TYPE = "H100"
NVLINK_BW = "3600Gbps"
NV_LATENCY = "0.000025ms"
LATENCY = "0.0005ms"
ERROR_RATE = "0"
SWITCH_LIMIT_GBPS = 12_800.0

# The original 64-ASW/32-PSW bounded Clos pattern used by ROFT.
BOUNDED_CLOS_BASE_A = [2, 3, 6, 8, 12, 14, 15, 18, 20, 21, 23, 24, 25, 27, 29, 31]
BOUNDED_CLOS_BASE_B = [0, 1, 3, 7, 8, 10, 12, 13, 14, 18, 19, 22, 24, 25, 26, 28]


def cyclic_bounded_clos_adjacency(asw_count: int = 64, psw_count: int = 32) -> List[List[int]]:
    if asw_count != 64 or psw_count != 32:
        raise ValueError("the bounded 12.8T Clos pattern is defined for 64 ASW and 32 PSW")

    rows: List[List[int]] = []
    for base in (BOUNDED_CLOS_BASE_A, BOUNDED_CLOS_BASE_B):
        for shift in range(psw_count):
            rows.append(sorted((item + shift) % psw_count for item in base))

    psw_degrees = [0] * psw_count
    for row in rows:
        if len(row) != 16 or len(set(row)) != 16:
            raise ValueError(f"invalid bounded Clos row: {row}")
        for psw_index in row:
            psw_degrees[psw_index] += 1
    if psw_degrees != [32] * psw_count:
        raise ValueError(f"invalid bounded Clos PSW degrees: {psw_degrees}")
    return rows


def cyclic_full_64x16_adjacency() -> List[List[int]]:
    """Return a full 64-ASW/16-PSW upper fabric.

    Each ASW connects to all 16 PSWs.  ASWs remain at 12.8Tbps, while
    each PSW has 64 x 400Gbps ports, or 25.6Tbps, by design.
    """
    asw_count = 64
    psw_count = 16
    asw_degree = 16
    rows = [
        sorted((offset + asw_index) % psw_count for offset in range(asw_degree))
        for asw_index in range(asw_count)
    ]
    psw_degrees = [0] * psw_count
    for row in rows:
        if len(row) != asw_degree or len(set(row)) != asw_degree:
            raise ValueError(f"invalid 64x16 upper-fabric row: {row}")
        for psw_index in row:
            psw_degrees[psw_index] += 1
    if psw_degrees != [64] * psw_count:
        raise ValueError(f"invalid 64x16 PSW degrees: {psw_degrees}")
    return rows


def connect_nv_and_generate(topo: TopoGenerator) -> None:
    topo.ConnectGPUsToNVSwitch(nvlink_bw=NVLINK_BW, nv_latency=NV_LATENCY)


def generate_bounded_meta(output_dir: Path) -> Path:
    filename = "Meta_Topo_1024g_8gps_400Gbps_H100_12p8T"
    topo = TopoGenerator(str(output_dir / filename))
    topo.SetConfig(GPU_COUNT, GPUS_PER_SERVER, nv_switch_per_server=1, gpu_type=GPU_TYPE)
    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(64)
    psw_ids = topo.AddPSWSwitches(16)
    connect_nv_and_generate(topo)

    servers_per_asw = 2
    for server_id in range(SERVER_COUNT):
        asw_id = asw_ids[server_id // servers_per_asw]
        for gpu_offset in range(GPUS_PER_SERVER):
            gpu_id = server_id * GPUS_PER_SERVER + gpu_offset
            topo.AddLink(gpu_id, asw_id, "400Gbps", LATENCY, ERROR_RATE)

    for asw_index, psw_offsets in enumerate(cyclic_full_64x16_adjacency()):
        for psw_offset in psw_offsets:
            topo.AddLink(asw_ids[asw_index], psw_ids[psw_offset], "400Gbps", LATENCY, ERROR_RATE)

    topo.Generate()
    return output_dir / filename


def generate_bounded_roft(output_dir: Path) -> Path:
    filename = "ROFT_1024g_8gps_p32a0.5_400Gbps_H100_12p8T"
    topo = TopoGenerator(str(output_dir / filename))
    topo.SetConfig(GPU_COUNT, GPUS_PER_SERVER, nv_switch_per_server=1, gpu_type=GPU_TYPE)
    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(64)
    psw_ids = topo.AddPSWSwitches(16)
    connect_nv_and_generate(topo)

    hosts_per_segment = 16
    for gpu_id in range(GPU_COUNT):
        host = gpu_id // GPUS_PER_SERVER
        rank = gpu_id % GPUS_PER_SERVER
        segment = host // hosts_per_segment
        asw_id = asw_ids[segment * GPUS_PER_SERVER + rank]
        topo.AddLink(gpu_id, asw_id, "400Gbps", LATENCY, ERROR_RATE)

    for asw_index, psw_offsets in enumerate(cyclic_full_64x16_adjacency()):
        for psw_offset in psw_offsets:
            topo.AddLink(asw_ids[asw_index], psw_ids[psw_offset], "400Gbps", LATENCY, ERROR_RATE)

    topo.Generate()
    return output_dir / filename


def generate_rail_only_s5(output_dir: Path) -> Path:
    filename = "RailOnly_1024g_8gps_s5_400Gbps_H100_12p8T"
    segment_host_counts = [28, 25, 25, 25, 25]
    if sum(segment_host_counts) != SERVER_COUNT:
        raise ValueError("rail-only segment host counts must sum to 128")

    topo = TopoGenerator(str(output_dir / filename))
    topo.SetConfig(GPU_COUNT, GPUS_PER_SERVER, nv_switch_per_server=1, gpu_type=GPU_TYPE)
    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(len(segment_host_counts) * GPUS_PER_SERVER)
    connect_nv_and_generate(topo)

    segment_by_host: List[int] = []
    for segment, count in enumerate(segment_host_counts):
        segment_by_host.extend([segment] * count)
    if len(segment_by_host) != SERVER_COUNT:
        raise ValueError("invalid rail-only host-to-segment map")

    def asw_for(segment: int, rank: int) -> int:
        return asw_ids[segment * GPUS_PER_SERVER + rank]

    for gpu_id in range(GPU_COUNT):
        host = gpu_id // GPUS_PER_SERVER
        rank = gpu_id % GPUS_PER_SERVER
        topo.AddLink(gpu_id, asw_for(segment_by_host[host], rank), "400Gbps", LATENCY, ERROR_RATE)

    segment_count = len(segment_host_counts)
    for rank in range(GPUS_PER_SERVER):
        for left in range(segment_count):
            for right in range(left + 1, segment_count):
                topo.AddLink(asw_for(left, rank), asw_for(right, rank), "400Gbps", LATENCY, ERROR_RATE)

    topo.Generate()
    return output_dir / filename


def generate_with_existing_function(output_dir: Path, generate_fn) -> Path:
    cwd = Path.cwd()
    try:
        os.chdir(output_dir)
        filename = generate_fn()
    finally:
        os.chdir(cwd)
    return output_dir / filename


def generate_all(output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}

    paths["Meta"] = generate_bounded_meta(output_dir)
    paths["HPN"] = generate_with_existing_function(
        output_dir,
        lambda: GenerateHPNTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            gpu_type=GPU_TYPE,
            switch_throughput=12_800,
            alpha=0.5,
            nvlink_bw=NVLINK_BW,
            nic_bw="200Gbps",
            asw_to_psw_bw="400Gbps",
            nv_latency=NV_LATENCY,
            latency=LATENCY,
            error_rate=ERROR_RATE,
            dual_plane=True,
        ),
    )
    paths["DeepSeek"] = generate_with_existing_function(
        output_dir,
        lambda: generateDeepSeekTopo(
            gpu_count=GPU_COUNT,
            gpus_per_server=GPUS_PER_SERVER,
            port=32,
            alpha=0.5,
            psw_port=64,
            gpu_type=GPU_TYPE,
            nv_switch_per_server=1,
            nvlink_bw=NVLINK_BW,
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
            nv_latency=NV_LATENCY,
            latency=LATENCY,
            error_rate=ERROR_RATE,
        ),
    )
    paths["RO"] = generate_rail_only_s5(output_dir)
    paths["ROFT"] = generate_bounded_roft(output_dir)
    paths["Zcube"] = generate_with_existing_function(
        output_dir,
        lambda: GenerateZcubeTopo(
            n=32,
            k=2,
            gpus_per_server=GPUS_PER_SERVER,
            nv_switch_per_server=1,
            gpu_type=GPU_TYPE,
            nvlink_bw=NVLINK_BW,
            nic_bw="200Gbps",
            asw_to_psw_bw="200Gbps",
            nv_latency=NV_LATENCY,
            latency=LATENCY,
            error_rate=ERROR_RATE,
        ),
    )
    return paths


def write_manifest(output_dir: Path, paths: Dict[str, Path]) -> Path:
    summaries = {
        name: summarize_topology(parse_topology(path), limit_gbps=SWITCH_LIMIT_GBPS)
        for name, path in paths.items()
    }
    manifest = {
        "description": "1024-GPU H100 topology set with a 12.8Tbps ordinary-switch target; Meta PSWs may use 25.6Tbps.",
        "switch_limit_gbps": SWITCH_LIMIT_GBPS,
        "nvswitch_excluded_from_limit": True,
        "topologies": {
            name: {
                "path": str(path),
                "max_gbps": summaries[name]["max_gbps"],
                "mean_gbps": summaries[name]["mean_gbps"],
                "mean_utilization": summaries[name]["mean_utilization"],
                "over_limit_count": summaries[name]["over_limit_count"],
            }
            for name, path in paths.items()
        },
        "notes": {
            "Meta": "Full 64 ASW x 16 PSW, each ASW has 16 PSW uplinks plus 16 GPU ports; each PSW is 25.6Tbps.",
            "HPN": "Existing DualToR-DualPlane generator with switch_throughput=12800Gbps.",
            "DeepSeek": "port=32 keeps ASW at 32 x 400Gbps; PSWs are below the limit by design.",
            "RO": "Rail-only full mesh across five uneven host segments [28,25,25,25,25].",
            "ROFT": "Rail GPU mapping plus full 64 ASW x 16 PSW connectivity; PSWs are 25.6Tbps.",
            "Zcube": "Existing n=32,k=2 topology already uses 64 x 200Gbps ports per switch.",
        },
    }
    manifest_path = output_dir / "manifest_12p8T.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "mytopo" / "1024_12p8T",
        help="directory for generated topology files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = generate_all(args.output_dir)
    manifest = write_manifest(args.output_dir, paths)
    print(f"Generated {len(paths)} topologies under {args.output_dir}")
    print(f"Manifest: {manifest}")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
