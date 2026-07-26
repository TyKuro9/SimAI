#!/usr/bin/env python3
"""Generate and validate the 256-GPU R-2R topology."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "astra-sim-alibabacloud" / "inputs" / "topo"
sys.path.insert(0, str(GENERATOR_DIR))

from custom_topo_generator import TopoGenerator  # noqa: E402


GPU_COUNT = 256
GPUS_PER_SERVER = 8
SERVER_COUNT = GPU_COUNT // GPUS_PER_SERVER
MODULE_COUNT = 16
SERVERS_PER_MODULE = 2
GROUP2_RAILS = 8
GROUP2_REPLICAS = 2

NVLINK_BW = "3600Gbps"
GROUP1_GPU_BW = "200Gbps"
GROUP2_GPU_BW = "100Gbps"
GROUP1_GROUP2_BW = "200Gbps"
NV_LATENCY = "0.000025ms"
SCALEOUT_LATENCY = "0.0005ms"
ERROR_RATE = "0"

DEFAULT_OUTPUT = (
    ROOT
    / "mytopo"
    / "Zcube_R2R_m8_a2_b16_h2_256g_8gps_200G100G_H100"
)


def bandwidth_gbps(value: str) -> int:
    if not value.endswith("Gbps"):
        raise ValueError(f"unsupported bandwidth: {value}")
    return int(value.removesuffix("Gbps"))


def parse_link(link: str) -> tuple[int, int, str]:
    fields = link.split()
    if len(fields) != 5:
        raise ValueError(f"malformed link: {link}")
    return int(fields[0]), int(fields[1]), fields[2]


def shortest_distance(
    adjacency: dict[int, set[int]], source: int, destination: int
) -> int:
    queue = deque([(source, 0)])
    visited = {source}
    while queue:
        node, distance = queue.popleft()
        if node == destination:
            return distance
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    raise ValueError(f"no path from {source} to {destination}")


def validate_topology(
    topo: TopoGenerator,
    nv_switch_ids: Sequence[int],
    group1_ids: Sequence[int],
    group2_ids: Sequence[int],
) -> dict[str, object]:
    expected_links = 256 + 256 + 512 + 256
    if len(topo.links) != expected_links:
        raise ValueError(
            f"expected {expected_links} links, generated {len(topo.links)}"
        )

    edges: dict[tuple[int, int], str] = {}
    adjacency: dict[int, set[int]] = defaultdict(set)
    incident: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for raw_link in topo.links:
        source, destination, bandwidth = parse_link(raw_link)
        edge = tuple(sorted((source, destination)))
        if edge in edges:
            raise ValueError(f"duplicate edge: {edge}")
        edges[edge] = bandwidth
        adjacency[source].add(destination)
        adjacency[destination].add(source)
        incident[source].append((destination, bandwidth))
        incident[destination].append((source, bandwidth))

    nv_set = set(nv_switch_ids)
    group1_set = set(group1_ids)
    group2_set = set(group2_ids)

    for gpu in range(GPU_COUNT):
        server = gpu // GPUS_PER_SERVER
        module = server // SERVERS_PER_MODULE
        local_index = gpu % GPUS_PER_SERVER
        expected = {
            nv_switch_ids[server]: NVLINK_BW,
            group1_ids[module]: GROUP1_GPU_BW,
            group2_ids[local_index * GROUP2_REPLICAS]: GROUP2_GPU_BW,
            group2_ids[local_index * GROUP2_REPLICAS + 1]: GROUP2_GPU_BW,
        }
        actual = dict(incident[gpu])
        if actual != expected:
            raise ValueError(
                f"GPU {gpu} attachment mismatch: expected {expected}, got {actual}"
            )

    for nv_switch in nv_switch_ids:
        links = incident[nv_switch]
        if len(links) != GPUS_PER_SERVER or any(
            peer >= GPU_COUNT or bandwidth != NVLINK_BW
            for peer, bandwidth in links
        ):
            raise ValueError(f"invalid NVSwitch degree/rates at {nv_switch}")

    for group1 in group1_ids:
        links = incident[group1]
        gpu_links = [
            bandwidth for peer, bandwidth in links if peer < GPU_COUNT
        ]
        group2_links = [
            bandwidth for peer, bandwidth in links if peer in group2_set
        ]
        capacity = sum(bandwidth_gbps(bandwidth) for _, bandwidth in links)
        if (
            len(gpu_links) != 16
            or set(gpu_links) != {GROUP1_GPU_BW}
            or len(group2_links) != 16
            or set(group2_links) != {GROUP1_GROUP2_BW}
            or capacity != 6400
        ):
            raise ValueError(f"invalid Group-1 switch {group1}")

    for group2 in group2_ids:
        links = incident[group2]
        gpu_links = [
            bandwidth for peer, bandwidth in links if peer < GPU_COUNT
        ]
        group1_links = [
            bandwidth for peer, bandwidth in links if peer in group1_set
        ]
        capacity = sum(bandwidth_gbps(bandwidth) for _, bandwidth in links)
        if (
            len(gpu_links) != 32
            or set(gpu_links) != {GROUP2_GPU_BW}
            or len(group1_links) != 16
            or set(group1_links) != {GROUP1_GROUP2_BW}
            or capacity != 6400
        ):
            raise ValueError(f"invalid Group-2 switch {group2}")

    scaleout_adjacency: dict[int, set[int]] = defaultdict(set)
    for (source, destination), _ in edges.items():
        if source in nv_set or destination in nv_set:
            continue
        scaleout_adjacency[source].add(destination)
        scaleout_adjacency[destination].add(source)

    path_class_counts = {
        "same_module_different_index": 0,
        "same_module_same_index": 0,
        "different_module_same_index": 0,
        "different_module_different_index": 0,
    }
    for source in range(GPU_COUNT):
        source_server = source // GPUS_PER_SERVER
        source_module = source_server // SERVERS_PER_MODULE
        source_index = source % GPUS_PER_SERVER
        for destination in range(source + 1, GPU_COUNT):
            destination_server = destination // GPUS_PER_SERVER
            if source_server == destination_server:
                continue
            destination_module = destination_server // SERVERS_PER_MODULE
            destination_index = destination % GPUS_PER_SERVER
            same_module = source_module == destination_module
            same_index = source_index == destination_index
            distance = shortest_distance(
                scaleout_adjacency, source, destination
            )
            common_switches = (
                scaleout_adjacency[source]
                & scaleout_adjacency[destination]
            )
            if same_module and same_index:
                path_class_counts["same_module_same_index"] += 1
                if distance != 2 or len(common_switches) != 3:
                    raise ValueError(
                        "same-module/same-index pair must have three "
                        "two-hop paths"
                    )
            elif same_module:
                path_class_counts["same_module_different_index"] += 1
                if distance != 2 or len(common_switches) != 1:
                    raise ValueError(
                        "same-module/different-index pair must use Group-1"
                    )
            elif same_index:
                path_class_counts["different_module_same_index"] += 1
                if distance != 2 or len(common_switches) != 2:
                    raise ValueError(
                        "cross-module/same-index pair must have two "
                        "Group-2 paths"
                    )
            else:
                path_class_counts["different_module_different_index"] += 1
                if distance != 3 or common_switches:
                    raise ValueError(
                        "cross-module/different-index pair must be three hops"
                    )

    return {
        "total_nodes": GPU_COUNT + len(topo.switches),
        "gpus": GPU_COUNT,
        "servers": SERVER_COUNT,
        "nvswitches": len(nv_switch_ids),
        "group1_switches": len(group1_ids),
        "group2_switches": len(group2_ids),
        "links": len(topo.links),
        "group1_capacity_gbps": 6400,
        "group2_capacity_gbps": 6400,
        "path_class_pair_counts": path_class_counts,
    }


def generate(output: Path) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    topo = TopoGenerator(str(output))
    topo.SetConfig(
        gpu_count=GPU_COUNT,
        gpus_per_server=GPUS_PER_SERVER,
        nv_switch_per_server=1,
        gpu_type="H100",
    )
    nv_switch_start = topo.AddNVSwitches()
    nv_switch_ids = [
        nv_switch_start + server for server in range(SERVER_COUNT)
    ]
    group1_ids = topo.AddASWSwitches(MODULE_COUNT)
    group2_ids = topo.AddPSWSwitches(GROUP2_RAILS * GROUP2_REPLICAS)

    topo.ConnectGPUsToNVSwitch(
        nvlink_bw=NVLINK_BW, nv_latency=NV_LATENCY
    )
    for gpu in range(GPU_COUNT):
        server = gpu // GPUS_PER_SERVER
        module = server // SERVERS_PER_MODULE
        local_index = gpu % GPUS_PER_SERVER
        topo.AddLink(
            gpu,
            group1_ids[module],
            GROUP1_GPU_BW,
            SCALEOUT_LATENCY,
            ERROR_RATE,
        )
        for replica in range(GROUP2_REPLICAS):
            topo.AddLink(
                gpu,
                group2_ids[local_index * GROUP2_REPLICAS + replica],
                GROUP2_GPU_BW,
                SCALEOUT_LATENCY,
                ERROR_RATE,
            )

    for group1 in group1_ids:
        for group2 in group2_ids:
            topo.AddLink(
                group1,
                group2,
                GROUP1_GROUP2_BW,
                SCALEOUT_LATENCY,
                ERROR_RATE,
            )

    summary = validate_topology(
        topo, nv_switch_ids, group1_ids, group2_ids
    )
    topo.Generate()
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    summary = generate(output)
    print(json.dumps({"output": str(output), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
