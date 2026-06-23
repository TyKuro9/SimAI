#!/usr/bin/env python3
"""Run fixed-probability fault-tolerance experiments on existing SimAI topologies.

The simulator already models link-down behavior by removing links from routing
consideration and recomputing routes.  This driver applies the same semantics at
experiment startup by writing a failed topology file, then optionally invoking
the existing FlowSim binary so routing is rebuilt from that topology.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Optional, Sequence, Set, Tuple


MISSING = "missing"


@dataclass(frozen=True)
class Link:
    index: int
    src: int
    dst: int
    bandwidth: str
    latency: str
    error_rate: str
    raw: str

    @property
    def key(self) -> Tuple[int, int]:
        return (min(self.src, self.dst), max(self.src, self.dst))


@dataclass
class Topology:
    path: Path
    total_nodes: int
    gpus_per_server: int
    nvswitch_count: int
    switch_count: int
    link_count: int
    gpu_type: str
    switch_ids: List[int]
    links: List[Link]

    @property
    def gpu_count(self) -> int:
        return self.total_nodes - self.nvswitch_count - self.switch_count

    @property
    def nvswitch_ids(self) -> Set[int]:
        return set(self.switch_ids[: self.nvswitch_count])

    @property
    def ordinary_switch_ids(self) -> Set[int]:
        start = self.nvswitch_count
        return set(self.switch_ids[start : start + self.switch_count])

    def node_type(self, node_id: int) -> str:
        if 0 <= node_id < self.gpu_count:
            return "gpu"
        if node_id in self.nvswitch_ids:
            return "nvswitch"
        if node_id in self.ordinary_switch_ids:
            return "switch"
        return "unknown"

    def is_inter_server_link(self, link: Link) -> bool:
        src_type = self.node_type(link.src)
        dst_type = self.node_type(link.dst)
        if src_type == "nvswitch" or dst_type == "nvswitch":
            return False
        if src_type == "gpu" and dst_type == "gpu":
            return link.src // self.gpus_per_server != link.dst // self.gpus_per_server
        return True


def parse_topology(path: Path) -> Topology:
    with path.open() as f:
        header = f.readline().split()
        if len(header) < 6:
            raise ValueError(f"invalid topology header in {path}")
        total_nodes, gpus_per_server, nvswitch_count, switch_count, link_count = map(
            int, header[:5]
        )
        gpu_type = header[5]
        switch_ids = [int(x) for x in f.readline().split()]
        links: List[Link] = []
        for idx, line in enumerate(f):
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) < 5:
                raise ValueError(f"invalid link line in {path}: {stripped}")
            src, dst = int(parts[0]), int(parts[1])
            links.append(Link(idx, src, dst, parts[2], parts[3], parts[4], stripped))

    if len(links) != link_count:
        raise ValueError(f"{path} declares {link_count} links but contains {len(links)}")

    return Topology(
        path=path,
        total_nodes=total_nodes,
        gpus_per_server=gpus_per_server,
        nvswitch_count=nvswitch_count,
        switch_count=switch_count,
        link_count=link_count,
        gpu_type=gpu_type,
        switch_ids=switch_ids,
        links=links,
    )


def write_topology(topology: Topology, failed_keys: Set[Tuple[int, int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept_links = [link for link in topology.links if link.key not in failed_keys]
    with out_path.open("w") as f:
        f.write(
            f"{topology.total_nodes} {topology.gpus_per_server} "
            f"{topology.nvswitch_count} {topology.switch_count} "
            f"{len(kept_links)} {topology.gpu_type}\n"
        )
        f.write(" ".join(str(x) for x in topology.switch_ids))
        f.write("\n")
        for link in kept_links:
            f.write(link.raw)
            f.write("\n")


def eligible_inter_server_links(topology: Topology) -> List[Link]:
    return [link for link in topology.links if topology.is_inter_server_link(link)]


def sample_failed_links(topology: Topology, probability: float, seed: int) -> Set[Tuple[int, int]]:
    rng = random.Random(seed)
    failed: Set[Tuple[int, int]] = set()
    for link in eligible_inter_server_links(topology):
        if rng.random() < probability:
            failed.add(link.key)
    return failed


def incident_links(topology: Topology, switch_id: int) -> Set[Tuple[int, int]]:
    return {link.key for link in topology.links if link.src == switch_id or link.dst == switch_id}


def build_adjacency(topology: Topology, failed_keys: Set[Tuple[int, int]]) -> Dict[int, Set[int]]:
    adj: Dict[int, Set[int]] = defaultdict(set)
    for node_id in range(topology.total_nodes):
        adj[node_id]
    for link in topology.links:
        if link.key in failed_keys:
            continue
        adj[link.src].add(link.dst)
        adj[link.dst].add(link.src)
    return adj


def shortest_path_lengths(
    topology: Topology, failed_keys: Set[Tuple[int, int]]
) -> Dict[Tuple[int, int], int]:
    adj = build_adjacency(topology, failed_keys)
    lengths: Dict[Tuple[int, int], int] = {}
    for src in range(topology.gpu_count):
        dist = {src: 0}
        queue: deque[int] = deque([src])
        while queue:
            node = queue.popleft()
            for nxt in adj[node]:
                if nxt in dist:
                    continue
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
        for dst in range(topology.gpu_count):
            if src == dst:
                continue
            if dst in dist:
                lengths[(src, dst)] = dist[dst]
    return lengths


def topology_metrics(
    topology: Topology,
    failed_keys: Set[Tuple[int, int]],
    baseline_lengths: Dict[Tuple[int, int], int],
    workload_name: str,
) -> Dict[str, object]:
    eligible = eligible_inter_server_links(topology)
    failed_lengths = shortest_path_lengths(topology, failed_keys)
    total_pairs = topology.gpu_count * (topology.gpu_count - 1)
    connected_pairs = len(failed_lengths)
    failed_pairs = total_pairs - connected_pairs

    avg_path = mean(failed_lengths.values()) if failed_lengths else None
    base_values = [baseline_lengths[pair] for pair in failed_lengths if pair in baseline_lengths]
    avg_base_for_connected = mean(base_values) if base_values else None
    stretch = (
        avg_path / avg_base_for_connected
        if avg_path is not None and avg_base_for_connected not in (None, 0)
        else None
    )

    all_to_all_like = workload_name.lower().replace("_", "-") == "all-to-all"
    return {
        "num_failed_links": len(failed_keys),
        "failed_link_ratio": len(failed_keys) / len(eligible) if eligible else 0.0,
        "num_failed_flows": failed_pairs if all_to_all_like else MISSING,
        "failed_flow_ratio": failed_pairs / total_pairs if all_to_all_like and total_pairs else MISSING,
        "connectivity_ratio": connected_pairs / total_pairs if total_pairs else 1.0,
        "average_path_length_after_failure": avg_path if avg_path is not None else MISSING,
        "path_stretch": stretch if stretch is not None else MISSING,
        "max_link_utilization_after_failure": MISSING,
    }


def read_total_time(end_to_end_csv: Path) -> Optional[float]:
    if not end_to_end_csv.exists() or end_to_end_csv.stat().st_size == 0:
        return None
    with end_to_end_csv.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        row = next(reader, None)
    if not header or not row:
        return None
    try:
        idx = [h.strip() for h in header].index("Total time")
    except ValueError:
        return None
    try:
        return float(row[idx].strip())
    except (ValueError, IndexError):
        return None


def run_flowsim(
    flowsim_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    env: Dict[str, str],
) -> Optional[float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(flowsim_bin),
        "-t",
        str(threads),
        "-w",
        str(workload),
        "-n",
        str(topology),
        "-o",
        str(output_dir) + "/",
    ]
    with (output_dir / "run.log").open("w") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False, env=env)
    return read_total_time(output_dir / "EndToEnd.csv")


def numeric_or_missing(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        return float(value)
    return None


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: Sequence[Dict[str, object]], group_keys: Sequence[str]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[object, ...], List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in group_keys)].append(row)

    metrics = [
        "normal_jct",
        "failed_jct",
        "degradation",
        "num_failed_links",
        "failed_link_ratio",
        "num_failed_flows",
        "failed_flow_ratio",
        "connectivity_ratio",
        "average_path_length_after_failure",
        "path_stretch",
    ]

    summaries: List[Dict[str, object]] = []
    for group, group_rows in grouped.items():
        out = {key: value for key, value in zip(group_keys, group)}
        out["num_seeds"] = len(group_rows)
        for metric in metrics:
            values = [
                numeric_or_missing(row.get(metric))
                for row in group_rows
                if numeric_or_missing(row.get(metric)) is not None
            ]
            if not values:
                out[f"{metric}_mean"] = MISSING
                out[f"{metric}_std"] = MISSING
            else:
                out[f"{metric}_mean"] = mean(values)
                out[f"{metric}_std"] = pstdev(values) if len(values) > 1 else 0.0
        summaries.append(out)
    return summaries


def make_row(
    *,
    topology_name: str,
    workload_name: str,
    failure_model: str,
    seed: int,
    probability: float,
    failed_keys: Set[Tuple[int, int]],
    metrics: Dict[str, object],
    normal_jct: Optional[float],
    failed_jct: Optional[float],
    failed_topology_path: Path,
    switch_id: Optional[int] = None,
) -> Dict[str, object]:
    if normal_jct is not None and failed_jct is not None and normal_jct != 0:
        degradation: object = (failed_jct - normal_jct) / normal_jct
    else:
        degradation = MISSING
    row: Dict[str, object] = {
        "topology": topology_name,
        "workload": workload_name,
        "failure_model": failure_model,
        "seed": seed,
        "link_failure_probability": probability,
        "failed_switch_id": switch_id if switch_id is not None else "",
        "normal_jct": normal_jct if normal_jct is not None else MISSING,
        "failed_jct": failed_jct if failed_jct is not None else MISSING,
        "degradation": degradation,
        "failed_topology": str(failed_topology_path),
        "failed_links": " ".join(f"{a}-{b}" for a, b in sorted(failed_keys)),
    }
    row.update(metrics)
    return row


def parse_seeds(args: argparse.Namespace) -> List[int]:
    if args.seeds:
        return [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    return [args.random_seed + i for i in range(args.num_seeds)]


def run_experiments(args: argparse.Namespace) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    topology = parse_topology(args.topology)
    topology_name = args.topology_name or args.topology.stem
    workload_name = args.workload_name
    out_root = args.output_dir
    generated_dir = out_root / "generated_topologies" / topology_name
    baseline_lengths = shortest_path_lengths(topology, set())
    seeds = parse_seeds(args)
    env = os.environ.copy()
    if args.disable_fct:
        env["FLOWSIM_WRITE_FCT"] = "0"

    normal_jct: Optional[float] = None
    baseline_topology_path = topology.path
    if args.run_simulator:
        normal_jct = run_flowsim(
            args.flowsim_bin,
            args.workload,
            baseline_topology_path,
            out_root / "runs" / topology_name / workload_name / "baseline",
            args.threads,
            env,
        )

    random_rows: List[Dict[str, object]] = []
    if args.mode in ("random", "both"):
        for seed in seeds:
            failed_keys = sample_failed_links(topology, args.link_failure_probability, seed)
            failed_topo = generated_dir / f"random_seed{seed}.topo"
            write_topology(topology, failed_keys, failed_topo)
            failed_jct = None
            if args.run_simulator:
                failed_jct = run_flowsim(
                    args.flowsim_bin,
                    args.workload,
                    failed_topo,
                    out_root / "runs" / topology_name / workload_name / f"random_seed{seed}",
                    args.threads,
                    env,
                )
            metrics = topology_metrics(topology, failed_keys, baseline_lengths, workload_name)
            random_rows.append(
                make_row(
                    topology_name=topology_name,
                    workload_name=workload_name,
                    failure_model="random_link_failure",
                    seed=seed,
                    probability=args.link_failure_probability,
                    failed_keys=failed_keys,
                    metrics=metrics,
                    normal_jct=normal_jct,
                    failed_jct=failed_jct,
                    failed_topology_path=failed_topo,
                )
            )

    switch_rows: List[Dict[str, object]] = []
    if args.mode in ("switch", "both"):
        if args.failed_switch_role:
            raise SystemExit(
                "--failed-switch-role is unavailable: topology files distinguish only "
                "GPU, NVSwitch, and ordinary switch nodes, not ToR roles."
            )
        if args.failed_switch_id is None:
            raise SystemExit("--failed-switch-id is required for switch failure mode")
        if args.failed_switch_id not in topology.nvswitch_ids | topology.ordinary_switch_ids:
            raise SystemExit(f"node {args.failed_switch_id} is not a switch in {args.topology}")
        failed_keys = incident_links(topology, args.failed_switch_id)
        for seed in seeds:
            failed_topo = generated_dir / f"switch{args.failed_switch_id}_seed{seed}.topo"
            write_topology(topology, failed_keys, failed_topo)
            failed_jct = None
            if args.run_simulator:
                failed_jct = run_flowsim(
                    args.flowsim_bin,
                    args.workload,
                    failed_topo,
                    out_root
                    / "runs"
                    / topology_name
                    / workload_name
                    / f"switch{args.failed_switch_id}_seed{seed}",
                    args.threads,
                    env,
                )
            metrics = topology_metrics(topology, failed_keys, baseline_lengths, workload_name)
            switch_rows.append(
                make_row(
                    topology_name=topology_name,
                    workload_name=workload_name,
                    failure_model="switch_failure_incident_links",
                    seed=seed,
                    probability=1.0,
                    failed_keys=failed_keys,
                    metrics=metrics,
                    normal_jct=normal_jct,
                    failed_jct=failed_jct,
                    failed_topology_path=failed_topo,
                    switch_id=args.failed_switch_id,
                )
            )

    return random_rows, switch_rows


def write_metadata(args: argparse.Namespace, topology: Topology, seeds: Sequence[int]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "topology": str(args.topology),
        "topology_name": args.topology_name or args.topology.stem,
        "workload": str(args.workload) if args.workload else args.workload_name,
        "fixed_link_failure_probability": args.link_failure_probability,
        "num_seeds": len(seeds),
        "random_seed": args.random_seed,
        "seeds": list(seeds),
        "routing_mode": args.routing_mode,
        "whether_pxn_is_enabled": args.pxn_enabled,
        "failure_model": args.mode,
        "failure_target": args.failure_target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_simulator": args.run_simulator,
        "backend": "flowsim" if args.run_simulator else "topology_dry_run",
        "switch_role_filtering": "unavailable",
        "topology_counts": {
            "total_nodes": topology.total_nodes,
            "gpu_count": topology.gpu_count,
            "nvswitch_count": topology.nvswitch_count,
            "ordinary_switch_count": topology.switch_count,
            "link_count": topology.link_count,
            "inter_server_link_count": len(eligible_inter_server_links(topology)),
        },
        "missing_metrics": [
            "max_link_utilization_after_failure",
            "workload-exact failed flows for non-all-to-all workloads",
        ],
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def run_sanity_checks(args: argparse.Namespace) -> None:
    topology = parse_topology(args.topology)
    baseline_lengths = shortest_path_lengths(topology, set())

    zero_failed = sample_failed_links(topology, 0.0, args.random_seed)
    assert not zero_failed, "p=0 should not fail any inter-server links"
    zero_lengths = shortest_path_lengths(topology, zero_failed)
    assert zero_lengths == baseline_lengths, "p=0 topology connectivity should match baseline"

    all_failed = sample_failed_links(topology, 1.0, args.random_seed)
    eligible = eligible_inter_server_links(topology)
    assert len(all_failed) == len(eligible), "p=1 should fail every eligible inter-server link"
    all_metrics = topology_metrics(topology, all_failed, baseline_lengths, "all-to-all")
    assert all_metrics["connectivity_ratio"] < 1.0, "p=1 should disconnect at least some GPU pairs"

    if args.failed_switch_id is not None:
        incident = incident_links(topology, args.failed_switch_id)
        non_incident = {link.key for link in topology.links} - incident
        failed = incident_links(topology, args.failed_switch_id)
        assert failed == incident, "switch failure should fail all incident links"
        assert failed.isdisjoint(non_incident), "switch failure should not fail non-incident links"

    print("sanity checks passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fixed-probability random and switch fault-tolerance experiments"
    )
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--topology-name")
    parser.add_argument("--workload", type=Path)
    parser.add_argument("--workload-name", default="all-to-all")
    parser.add_argument("--output-dir", type=Path, default=Path("results/fault_tolerance"))
    parser.add_argument("--mode", choices=["random", "switch", "both"], default="both")
    parser.add_argument("--link-failure-probability", type=float, default=0.0)
    parser.add_argument("--num-seeds", type=int, default=1)
    parser.add_argument("--random-seed", type=int, default=1)
    parser.add_argument("--seeds", help="comma-separated seed list; overrides --num-seeds")
    parser.add_argument("--failure-target", default="inter_server_links")
    parser.add_argument("--failed-switch-id", type=int)
    parser.add_argument("--failed-switch-role")
    parser.add_argument("--routing-mode", default="existing")
    parser.add_argument("--pxn-enabled", default="unknown")
    parser.add_argument("--run-simulator", action="store_true")
    parser.add_argument(
        "--flowsim-bin",
        type=Path,
        default=Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim"),
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--disable-fct", action="store_true")
    parser.add_argument("--sanity-checks", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.failure_target != "inter_server_links":
        raise SystemExit("only failure_target=inter_server_links is supported")
    if not 0.0 <= args.link_failure_probability <= 1.0:
        raise SystemExit("--link-failure-probability must be in [0, 1]")
    if args.num_seeds < 1:
        raise SystemExit("--num-seeds must be >= 1")
    if args.run_simulator:
        if args.workload is None:
            raise SystemExit("--workload is required with --run-simulator")
        if not args.workload.exists():
            raise SystemExit(f"workload not found: {args.workload}")
        if not args.flowsim_bin.exists() or not os.access(args.flowsim_bin, os.X_OK):
            raise SystemExit(f"FlowSim binary not executable: {args.flowsim_bin}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(args)

    topology = parse_topology(args.topology)
    seeds = parse_seeds(args)

    if args.sanity_checks:
        run_sanity_checks(args)

    random_rows, switch_rows = run_experiments(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "random_link_failure_raw.csv", random_rows)
    write_csv(
        args.output_dir / "random_link_failure_summary.csv",
        summarize(random_rows, ["topology", "workload", "failure_model", "link_failure_probability"]),
    )
    write_csv(args.output_dir / "switch_failure_raw.csv", switch_rows)
    write_csv(
        args.output_dir / "switch_failure_summary.csv",
        summarize(switch_rows, ["topology", "workload", "failure_model", "failed_switch_id"]),
    )
    write_metadata(args, topology, seeds)

    print(f"wrote results to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
