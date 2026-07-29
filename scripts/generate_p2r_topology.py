#!/usr/bin/env python3
"""Generate and validate the three-NIC P-2R topology."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "astra-sim-alibabacloud" / "inputs" / "topo"
sys.path.insert(0, str(GENERATOR_DIR))

from custom_topo_generator import TopoGenerator  # noqa: E402


NVLINK_BW = "3600Gbps"
GROUP1_GPU_BW = "200Gbps"
GROUP2_GPU_BW = "100Gbps"
GROUP1_GROUP2_BW = "200Gbps"
NV_LATENCY = "0.000025ms"
SCALEOUT_LATENCY = "0.0005ms"
ERROR_RATE = "0"


@dataclass(frozen=True)
class P2RConfig:
    gpu_count: int
    group1_count: int
    gpus_per_server: int = 8
    group2_replicas: int = 2

    @property
    def server_count(self) -> int:
        return self.gpu_count // self.gpus_per_server

    @property
    def servers_per_module(self) -> int:
        return self.server_count // self.group1_count

    @property
    def group2_rails(self) -> int:
        return (
            self.servers_per_module
            * self.gpus_per_server
            // self.group2_replicas
        )

    @property
    def group2_count(self) -> int:
        return self.group2_rails * self.group2_replicas

    def validate(self) -> None:
        if self.gpu_count <= 0:
            raise ValueError("gpu_count must be positive")
        if self.gpus_per_server <= 0:
            raise ValueError("gpus_per_server must be positive")
        if self.gpu_count % self.gpus_per_server != 0:
            raise ValueError("gpu_count must be divisible by gpus_per_server")
        if self.server_count % self.group1_count != 0:
            raise ValueError("server_count must be divisible by group1_count")
        if self.group2_replicas != 2:
            raise ValueError("P-2R requires exactly two Group-2 replicas")
        group1_gpu_degree = (
            self.servers_per_module * self.gpus_per_server
        )
        if group1_gpu_degree % self.group2_replicas != 0:
            raise ValueError(
                "GPUs per Group-1 module must be divisible by "
                "group2_replicas"
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


def default_output(config: P2RConfig) -> Path:
    return (
        ROOT
        / "mytopo"
        / (
            f"P2R_m{config.gpus_per_server}"
            f"_a{config.servers_per_module}"
            f"_b{config.group1_count}"
            f"_h{config.group2_replicas}"
            f"_{config.gpu_count}g"
            f"_{config.gpus_per_server}gps"
            "_200G100G_H100"
        )
    )


def validate_topology(
    topo: TopoGenerator,
    config: P2RConfig,
    nv_switch_ids: Sequence[int],
    group1_ids: Sequence[int],
    group2_ids: Sequence[int],
) -> dict[str, object]:
    expected_links = (
        config.gpu_count * (2 + config.group2_replicas)
        + config.group1_count * config.group2_count
    )
    if len(topo.links) != expected_links:
        raise ValueError(
            f"expected {expected_links} links, generated {len(topo.links)}"
        )

    edges: dict[tuple[int, int], str] = {}
    incident: dict[int, list[tuple[int, str]]] = defaultdict(list)
    neighbors: dict[int, set[int]] = defaultdict(set)
    for raw_link in topo.links:
        source, destination, bandwidth = parse_link(raw_link)
        edge = tuple(sorted((source, destination)))
        if edge in edges:
            raise ValueError(f"duplicate edge: {edge}")
        edges[edge] = bandwidth
        incident[source].append((destination, bandwidth))
        incident[destination].append((source, bandwidth))
        neighbors[source].add(destination)
        neighbors[destination].add(source)

    group1_set = set(group1_ids)
    group2_set = set(group2_ids)
    for gpu in range(config.gpu_count):
        server = gpu // config.gpus_per_server
        module = server // config.servers_per_module
        module_local_position = gpu % (
            config.servers_per_module * config.gpus_per_server
        )
        group2_rail = module_local_position % config.group2_rails
        expected = {
            nv_switch_ids[server]: NVLINK_BW,
            group1_ids[module]: GROUP1_GPU_BW,
        }
        for replica in range(config.group2_replicas):
            expected[
                group2_ids[
                    group2_rail * config.group2_replicas + replica
                ]
            ] = GROUP2_GPU_BW
        actual = dict(incident[gpu])
        if actual != expected:
            raise ValueError(
                f"GPU {gpu} attachment mismatch: "
                f"expected {expected}, got {actual}"
            )

    for nv_switch in nv_switch_ids:
        links = incident[nv_switch]
        if len(links) != config.gpus_per_server or any(
            peer >= config.gpu_count or bandwidth != NVLINK_BW
            for peer, bandwidth in links
        ):
            raise ValueError(f"invalid NVSwitch {nv_switch}")

    group1_gpu_degree = (
        config.servers_per_module * config.gpus_per_server
    )
    group2_gpu_degree = config.gpu_count // config.group2_rails
    group1_capacity = (
        group1_gpu_degree * bandwidth_gbps(GROUP1_GPU_BW)
        + config.group2_count * bandwidth_gbps(GROUP1_GROUP2_BW)
    )
    group2_capacity = (
        group2_gpu_degree * bandwidth_gbps(GROUP2_GPU_BW)
        + config.group1_count * bandwidth_gbps(GROUP1_GROUP2_BW)
    )

    for group1 in group1_ids:
        gpu_links = [
            bandwidth
            for peer, bandwidth in incident[group1]
            if peer < config.gpu_count
        ]
        group2_links = [
            bandwidth
            for peer, bandwidth in incident[group1]
            if peer in group2_set
        ]
        if (
            len(gpu_links) != group1_gpu_degree
            or set(gpu_links) != {GROUP1_GPU_BW}
            or len(group2_links) != config.group2_count
            or set(group2_links) != {GROUP1_GROUP2_BW}
        ):
            raise ValueError(f"invalid Group-1 switch {group1}")

    for group2 in group2_ids:
        gpu_links = [
            bandwidth
            for peer, bandwidth in incident[group2]
            if peer < config.gpu_count
        ]
        group1_links = [
            bandwidth
            for peer, bandwidth in incident[group2]
            if peer in group1_set
        ]
        if (
            len(gpu_links) != group2_gpu_degree
            or set(gpu_links) != {GROUP2_GPU_BW}
            or len(group1_links) != config.group1_count
            or set(group1_links) != {GROUP1_GROUP2_BW}
        ):
            raise ValueError(f"invalid Group-2 switch {group2}")

    path_class_counts = {
        "same_module_same_index": 0,
        "same_module_different_index": 0,
        "different_module_same_index": 0,
        "different_module_different_index": 0,
    }
    for source in range(config.gpu_count):
        source_server = source // config.gpus_per_server
        source_module = source_server // config.servers_per_module
        source_module_position = source % group1_gpu_degree
        source_index = source_module_position % config.group2_rails
        for destination in range(source + 1, config.gpu_count):
            destination_server = destination // config.gpus_per_server
            if source_server == destination_server:
                continue
            destination_module = (
                destination_server // config.servers_per_module
            )
            destination_module_position = destination % group1_gpu_degree
            destination_index = (
                destination_module_position % config.group2_rails
            )
            same_module = source_module == destination_module
            same_index = source_index == destination_index
            common_switches = neighbors[source] & neighbors[destination]

            if same_module and same_index:
                key = "same_module_same_index"
                expected_common = 3
            elif same_module:
                key = "same_module_different_index"
                expected_common = 1
            elif same_index:
                key = "different_module_same_index"
                expected_common = 2
            else:
                key = "different_module_different_index"
                expected_common = 0
            path_class_counts[key] += 1
            if len(common_switches) != expected_common:
                raise ValueError(
                    f"pair {source}->{destination} expected "
                    f"{expected_common} common switches, "
                    f"found {len(common_switches)}"
                )

    return {
        "total_nodes": config.gpu_count + len(topo.switches),
        "gpus": config.gpu_count,
        "servers": config.server_count,
        "servers_per_group1_module": config.servers_per_module,
        "nvswitches": len(nv_switch_ids),
        "group1_switches": len(group1_ids),
        "group2_switches": len(group2_ids),
        "group2_rails": config.group2_rails,
        "group2_replicas": config.group2_replicas,
        "links": len(topo.links),
        "gpu_scaleout_bandwidth_gbps": 400,
        "group1_gpu_degree": group1_gpu_degree,
        "group2_gpu_degree": group2_gpu_degree,
        "group1_capacity_gbps": group1_capacity,
        "group2_capacity_gbps": group2_capacity,
        "path_class_pair_counts": path_class_counts,
    }


def generate(config: P2RConfig, output: Path) -> dict[str, object]:
    config.validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    topo = TopoGenerator(str(output))
    topo.SetConfig(
        gpu_count=config.gpu_count,
        gpus_per_server=config.gpus_per_server,
        nv_switch_per_server=1,
        gpu_type="H100",
    )
    nv_switch_start = topo.AddNVSwitches()
    nv_switch_ids = [
        nv_switch_start + server for server in range(config.server_count)
    ]
    group1_ids = topo.AddASWSwitches(config.group1_count)
    group2_ids = topo.AddPSWSwitches(config.group2_count)

    topo.ConnectGPUsToNVSwitch(
        nvlink_bw=NVLINK_BW, nv_latency=NV_LATENCY
    )
    for gpu in range(config.gpu_count):
        server = gpu // config.gpus_per_server
        module = server // config.servers_per_module
        module_local_position = gpu % (
            config.servers_per_module * config.gpus_per_server
        )
        group2_rail = module_local_position % config.group2_rails
        topo.AddLink(
            gpu,
            group1_ids[module],
            GROUP1_GPU_BW,
            SCALEOUT_LATENCY,
            ERROR_RATE,
        )
        for replica in range(config.group2_replicas):
            topo.AddLink(
                gpu,
                group2_ids[
                    group2_rail * config.group2_replicas + replica
                ],
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
        topo, config, nv_switch_ids, group1_ids, group2_ids
    )
    topo.Generate()
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-count", type=int, default=1024)
    parser.add_argument("--gpus-per-server", type=int, default=8)
    parser.add_argument("--group1-count", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    default_group1_count = math.isqrt(args.gpu_count)
    if (
        args.group1_count is None
        and default_group1_count * default_group1_count != args.gpu_count
    ):
        raise ValueError(
            "gpu_count must be a perfect square when --group1-count "
            "is omitted"
        )
    config = P2RConfig(
        gpu_count=args.gpu_count,
        group1_count=(
            args.group1_count
            if args.group1_count is not None
            else default_group1_count
        ),
        gpus_per_server=args.gpus_per_server,
    )
    config.validate()
    output = (
        args.output.resolve()
        if args.output is not None
        else default_output(config).resolve()
    )
    summary = generate(config, output)
    print(json.dumps({"output": str(output), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
