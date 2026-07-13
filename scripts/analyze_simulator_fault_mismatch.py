#!/usr/bin/env python3
"""Diagnose sample-level FlowSim vs NS3 fault-tolerance mismatch."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from functools import lru_cache
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLOWSIM = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "flowsim_256_alltoall_p01_p15_s10_chain"
)
DEFAULT_NS3 = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "diagnose_flowsim_ns3_mismatch"
)

ORDER = ["ROFT", "Zcube", "DeepSeek", "HPN", "Meta", "RO"]
FOCUS = ["RO", "Zcube", "Meta"]
COLORS = {
    "ROFT": "#73d2ff",
    "Zcube": "#57ee5a",
    "DeepSeek": "#ff9d8e",
    "HPN": "#f78be8",
    "Meta": "#8b94a4",
    "RO": "#d7d800",
}
LABELS = {
    "ROFT": "ROFT",
    "Zcube": "ZCube",
    "DeepSeek": "DeepSeek",
    "HPN": "HPN",
    "Meta": "Meta",
    "RO": "Rail-only",
}


def parse_gbps(value: str) -> float:
    text = str(value).strip().lower()
    if text.endswith("gbps"):
        return float(text[:-4])
    if text.endswith("mbps"):
        return float(text[:-4]) / 1000.0
    if text.endswith("kbps"):
        return float(text[:-4]) / 1_000_000.0
    if text.endswith("bps"):
        return float(text[:-3]) / 1_000_000_000.0
    return float(text)


def parse_topology_for_direct_routes(path: object) -> dict[str, object]:
    topo_path = Path(str(path))
    with topo_path.open() as f:
        header = f.readline().split()
        if len(header) < 6:
            raise ValueError(f"invalid topology header: {topo_path}")
        node_count = int(header[0])
        gpus_per_server = int(header[1])
        nvswitch_count = int(header[2])
        switch_count = int(header[3])
        link_count = int(header[4])
        switch_ids = [int(x) for x in f.readline().split()]
        node_types = [0] * node_count
        for sid in switch_ids[:nvswitch_count]:
            node_types[sid] = 2
        for sid in switch_ids[nvswitch_count : nvswitch_count + switch_count]:
            node_types[sid] = 1
        adj = [[] for _ in range(node_count)]
        bandwidth_gbps = {}
        for _ in range(link_count):
            line = f.readline()
            if not line:
                break
            parts = line.split()
            if len(parts) < 2:
                continue
            src, dst = int(parts[0]), int(parts[1])
            bw = parse_gbps(parts[2])
            adj[src].append(dst)
            adj[dst].append(src)
            bandwidth_gbps[(src, dst)] = bw
            bandwidth_gbps[(dst, src)] = bw
    gpu_count = node_count - nvswitch_count - switch_count
    return {
        "node_count": node_count,
        "gpu_count": gpu_count,
        "gpus_per_server": gpus_per_server,
        "node_types": node_types,
        "adj": adj,
        "bandwidth_gbps": bandwidth_gbps,
    }


def direct_route_tree_without_host_transit(
    topo: dict[str, object], src: int
) -> tuple[dict[int, int], dict[int, int]]:
    adj = topo["adj"]
    node_types = topo["node_types"]
    dist = {src: 0}
    parent = {src: -1}
    queue: deque[int] = deque([src])
    while queue:
        node = queue.popleft()
        for nxt in adj[node]:
            if nxt in dist:
                continue
            # Match RoutingFramework::FindPath: a host cannot be an intermediate
            # transit node. It can still be a final destination.
            if node_types[nxt] == 0 and nxt != src:
                dist[nxt] = dist[node] + 1
                parent[nxt] = node
                continue
            dist[nxt] = dist[node] + 1
            parent[nxt] = node
            queue.append(nxt)
    return dist, parent


def reconstruct_path(parent: dict[int, int], src: int, dst: int) -> list[int] | None:
    if dst not in parent:
        return None
    path = [dst]
    node = dst
    while node != src:
        node = parent.get(node, -1)
        if node < 0:
            return None
        path.append(node)
    path.reverse()
    return path


def direct_paths_without_host_transit(
    topo: dict[str, object],
) -> dict[int, dict[int, list[int]]]:
    gpu_count = int(topo["gpu_count"])
    out: dict[int, dict[int, list[int]]] = {}
    for src in range(gpu_count):
        _, parent = direct_route_tree_without_host_transit(topo, src)
        per_dst = {}
        for dst in range(gpu_count):
            if src == dst:
                continue
            path = reconstruct_path(parent, src, dst)
            if path is not None:
                per_dst[dst] = path
        out[src] = per_dst
    return out


def is_cross_rail(topo: dict[str, object], src: int, dst: int) -> bool:
    gpus_per_server = int(topo["gpus_per_server"])
    return (
        src // gpus_per_server != dst // gpus_per_server
        and src % gpus_per_server != dst % gpus_per_server
    )


def local_gpu_candidates(topo: dict[str, object], gpu: int) -> list[int]:
    gpus_per_server = int(topo["gpus_per_server"])
    if gpus_per_server <= 0:
        return [gpu]
    base = (gpu // gpus_per_server) * gpus_per_server
    candidates = [gpu]
    for offset in range(gpus_per_server):
        candidate = base + offset
        if candidate != gpu:
            candidates.append(candidate)
    return candidates


def make_pxn_plan_paths(
    paths: dict[int, dict[int, list[int]]],
    src: int,
    dst: int,
    src_proxy: int,
    dst_proxy: int,
) -> list[list[int]] | None:
    leg_paths = []
    if src != src_proxy:
        path = paths.get(src, {}).get(src_proxy)
        if path is None:
            return None
        leg_paths.append(path)
    if src_proxy != dst_proxy:
        path = paths.get(src_proxy, {}).get(dst_proxy)
        if path is None:
            return None
        leg_paths.append(path)
    if dst_proxy != dst:
        path = paths.get(dst_proxy, {}).get(dst)
        if path is None:
            return None
        leg_paths.append(path)
    return leg_paths if leg_paths else None


def generic_pxn_plan_paths(
    topo: dict[str, object],
    paths: dict[int, dict[int, list[int]]],
    src: int,
    dst: int,
) -> list[list[int]] | None:
    for src_proxy in local_gpu_candidates(topo, src):
        for dst_proxy in local_gpu_candidates(topo, dst):
            if src_proxy == src and dst_proxy == dst:
                continue
            plan = make_pxn_plan_paths(paths, src, dst, src_proxy, dst_proxy)
            if plan:
                return plan
    return None


def node_type_name(topo: dict[str, object], node: int) -> str:
    node_type = topo["node_types"][node]
    if node_type == 0:
        return "gpu"
    if node_type == 1:
        return "switch"
    if node_type == 2:
        return "nvswitch"
    return "unknown"


def link_category(topo: dict[str, object], src: int, dst: int) -> str:
    src_type = node_type_name(topo, src)
    dst_type = node_type_name(topo, dst)
    if src_type == "nvswitch" or dst_type == "nvswitch":
        return "local_nvswitch"
    if src_type == "switch" and dst_type == "switch":
        return "switch_switch"
    if {src_type, dst_type} == {"gpu", "switch"}:
        return "gpu_switch"
    if src_type == "gpu" and dst_type == "gpu":
        return "gpu_gpu_inter" if is_cross_rail(topo, src, dst) else "gpu_gpu_local"
    return "other"


def percentile_or_zero(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, percentile))


def add_load_stats(
    metrics: dict[str, float],
    prefix: str,
    load_values: list[float],
    pressure_values: list[float],
) -> None:
    metrics[f"{prefix}_active_links"] = float(len(load_values))
    metrics[f"{prefix}_total_load"] = float(np.sum(load_values)) if load_values else 0.0
    metrics[f"{prefix}_max_load"] = float(np.max(load_values)) if load_values else 0.0
    metrics[f"{prefix}_p95_load"] = percentile_or_zero(load_values, 95)
    metrics[f"{prefix}_mean_load"] = float(np.mean(load_values)) if load_values else 0.0
    metrics[f"{prefix}_total_pressure"] = (
        float(np.sum(pressure_values)) if pressure_values else 0.0
    )
    metrics[f"{prefix}_max_pressure"] = (
        float(np.max(pressure_values)) if pressure_values else 0.0
    )
    metrics[f"{prefix}_p95_pressure"] = percentile_or_zero(pressure_values, 95)
    metrics[f"{prefix}_mean_pressure"] = (
        float(np.mean(pressure_values)) if pressure_values else 0.0
    )


@lru_cache(maxsize=None)
def estimate_route_load_metrics_cached(path_str: str) -> dict[str, float]:
    topo = parse_topology_for_direct_routes(path_str)
    gpu_count = int(topo["gpu_count"])
    total_pairs = gpu_count * (gpu_count - 1)
    paths = direct_paths_without_host_transit(topo)
    cross_rail_pairs = 0
    direct_cross_rail_pairs = 0
    connected_pairs = 0
    path_lengths = []
    routed_pairs = 0
    pxn_pairs = 0
    pxn_cross_rail_pairs = 0
    leg_count = 0
    directed_loads: defaultdict[tuple[int, int], float] = defaultdict(float)
    directed_pressure: defaultdict[tuple[int, int], float] = defaultdict(float)

    for src in range(gpu_count):
        for dst in range(gpu_count):
            if src == dst:
                continue
            direct_path = paths.get(src, {}).get(dst)
            if direct_path is not None:
                connected_pairs += 1
                path_lengths.append(len(direct_path) - 1)
                leg_paths = [direct_path]
                used_pxn = False
            else:
                leg_paths = generic_pxn_plan_paths(topo, paths, src, dst)
                used_pxn = leg_paths is not None
            cross_rail = is_cross_rail(topo, src, dst)
            if cross_rail:
                cross_rail_pairs += 1
                if direct_path is not None:
                    direct_cross_rail_pairs += 1
            if leg_paths is None:
                continue
            routed_pairs += 1
            if used_pxn:
                pxn_pairs += 1
                if cross_rail:
                    pxn_cross_rail_pairs += 1
            leg_count += len(leg_paths)
            for leg_path in leg_paths:
                for hop_src, hop_dst in zip(leg_path, leg_path[1:]):
                    edge = (hop_src, hop_dst)
                    directed_loads[edge] += 1.0
                    bw = topo["bandwidth_gbps"].get(edge)
                    if bw and bw > 0:
                        directed_pressure[edge] += 1.0 / bw

    pxn_split_pairs = cross_rail_pairs - direct_cross_rail_pairs
    metrics = {
        "direct_route_connectivity_ratio": connected_pairs / total_pairs
        if total_pairs
        else np.nan,
        "direct_route_avg_path_len": float(np.mean(path_lengths))
        if path_lengths
        else np.nan,
        "static_routed_pair_ratio": routed_pairs / total_pairs if total_pairs else np.nan,
        "static_unrouted_pair_ratio": 1.0 - routed_pairs / total_pairs
        if total_pairs
        else np.nan,
        "static_avg_legs_per_pair": leg_count / total_pairs if total_pairs else np.nan,
        "static_pxn_pair_ratio": pxn_pairs / total_pairs if total_pairs else np.nan,
        "static_pxn_cross_rail_pair_ratio": pxn_cross_rail_pairs / cross_rail_pairs
        if cross_rail_pairs
        else np.nan,
        "estimated_pxn_split": float(pxn_split_pairs),
        "estimated_pxn_direct_cross_rail": float(direct_cross_rail_pairs),
        "estimated_pxn_total_cross_rail": float(cross_rail_pairs),
        "estimated_pxn_split_ratio": pxn_split_pairs / cross_rail_pairs
        if cross_rail_pairs
        else np.nan,
    }

    categories = {
        "static_any": list(directed_loads.keys()),
        "static_inter_server": [
            edge
            for edge in directed_loads
            if link_category(topo, edge[0], edge[1]) != "local_nvswitch"
        ],
        "static_local_nvswitch": [
            edge
            for edge in directed_loads
            if link_category(topo, edge[0], edge[1]) == "local_nvswitch"
        ],
        "static_gpu_switch": [
            edge
            for edge in directed_loads
            if link_category(topo, edge[0], edge[1]) == "gpu_switch"
        ],
        "static_switch_switch": [
            edge
            for edge in directed_loads
            if link_category(topo, edge[0], edge[1]) == "switch_switch"
        ],
    }
    for prefix, edges in categories.items():
        load_values = [directed_loads[edge] for edge in edges]
        pressure_values = [directed_pressure[edge] for edge in edges]
        add_load_stats(metrics, prefix, load_values, pressure_values)
    return metrics


def estimate_route_load_metrics(path: object) -> dict[str, float]:
    return estimate_route_load_metrics_cached(str(path))


def normalize_failed_links(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parts = []
    for token in value.split():
        try:
            a, b = token.split("-", 1)
            x, y = sorted((int(a), int(b)))
            parts.append(f"{x}-{y}")
        except ValueError:
            parts.append(token)
    return " ".join(sorted(parts))


def parse_flowsim_log(run_dir: object) -> dict[str, float]:
    path = Path(str(run_dir)) / "run.log"
    metrics = {
        "flowsim_synced_paths": np.nan,
        "flowsim_pxn_split": np.nan,
        "flowsim_pxn_direct_cross_rail": np.nan,
        "flowsim_pxn_total": np.nan,
        "flowsim_pxn_split_ratio": np.nan,
    }
    if not path.exists():
        return metrics
    text = path.read_text(errors="replace")
    synced = re.search(r"Synced\s+(\d+)\s+pre-calculated flow paths", text)
    if synced:
        metrics["flowsim_synced_paths"] = float(synced.group(1))
    pxn = re.search(r"\[PXN SUMMARY\].*?split=(\d+)\s+direct_cross_rail=(\d+)", text)
    if pxn:
        split = float(pxn.group(1))
        direct = float(pxn.group(2))
        total = split + direct
        metrics["flowsim_pxn_split"] = split
        metrics["flowsim_pxn_direct_cross_rail"] = direct
        metrics["flowsim_pxn_total"] = total
        metrics["flowsim_pxn_split_ratio"] = split / total if total else np.nan
    return metrics


def load_flowsim_baseline_log_metrics(results_dir: Path) -> pd.DataFrame:
    rows = []
    for topology in ORDER:
        run_dir = results_dir / "runs" / topology / "baseline"
        metrics = parse_flowsim_log(run_dir)
        metrics["topology"] = topology
        rows.append(metrics)
    out = pd.DataFrame(rows)
    return out.rename(
        columns={
            "flowsim_synced_paths": "flowsim_baseline_synced_paths",
            "flowsim_pxn_split": "flowsim_baseline_pxn_split",
            "flowsim_pxn_direct_cross_rail": "flowsim_baseline_pxn_direct_cross_rail",
            "flowsim_pxn_total": "flowsim_baseline_pxn_total",
            "flowsim_pxn_split_ratio": "flowsim_baseline_pxn_split_ratio",
        }
    )


def load_flowsim_baseline_route_load_metrics(results_dir: Path) -> pd.DataFrame:
    baseline = pd.read_csv(results_dir / "baseline_jct.csv")
    rows = []
    for _, row in baseline.iterrows():
        metrics = estimate_route_load_metrics(row["topology_file"])
        metrics = {f"baseline_{key}": value for key, value in metrics.items()}
        metrics["topology"] = row["topology"]
        rows.append(metrics)
    return pd.DataFrame(rows)


def load_raw(results_dir: Path, prefix: str) -> pd.DataFrame:
    raw = pd.read_csv(results_dir / "random_link_failure_raw.csv")
    raw = raw[raw["status"] == "success"].copy()
    numeric_cols = [
        "link_failure_probability",
        "seed",
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
    for col in numeric_cols:
        if col in raw:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["rate_pct"] = raw["link_failure_probability"] * 100.0
    raw["failed_links_normalized"] = raw["failed_links"].map(normalize_failed_links)
    raw[f"{prefix}_factor"] = raw["failed_jct"] / raw["normal_jct"]
    if prefix == "flowsim":
        log_metrics = raw["run_dir"].map(parse_flowsim_log).apply(pd.Series)
        raw = pd.concat([raw, log_metrics], axis=1)

    keep = [
        "topology",
        "link_failure_probability",
        "rate_pct",
        "seed",
        "normal_jct",
        "failed_jct",
        "degradation",
        f"{prefix}_factor",
        "failed_links_normalized",
        "num_failed_links",
        "failed_link_ratio",
        "failed_flow_ratio",
        "connectivity_ratio",
        "average_path_length_after_failure",
        "path_stretch",
        "failed_topology",
        "run_dir",
    ]
    if prefix == "flowsim":
        keep.extend(
            [
                "flowsim_synced_paths",
                "flowsim_pxn_split",
                "flowsim_pxn_direct_cross_rail",
                "flowsim_pxn_total",
                "flowsim_pxn_split_ratio",
            ]
        )
    return raw[keep].rename(
        columns={
            "normal_jct": f"{prefix}_normal_jct",
            "failed_jct": f"{prefix}_failed_jct",
            "degradation": f"{prefix}_degradation",
            "failed_links_normalized": f"{prefix}_failed_links",
            "failed_topology": f"{prefix}_failed_topology",
            "run_dir": f"{prefix}_run_dir",
        }
    )


def build_joined(flowsim_dir: Path, ns3_dir: Path) -> pd.DataFrame:
    flow = load_raw(flowsim_dir, "flowsim")
    flow_baselines = load_flowsim_baseline_log_metrics(flowsim_dir)
    flow = flow.merge(flow_baselines, on="topology", how="left")
    route_baselines = load_flowsim_baseline_route_load_metrics(flowsim_dir)
    flow = flow.merge(route_baselines, on="topology", how="left")
    ns3 = load_raw(ns3_dir, "ns3")
    metric_cols = [
        "num_failed_links",
        "failed_link_ratio",
        "failed_flow_ratio",
        "connectivity_ratio",
        "average_path_length_after_failure",
        "path_stretch",
    ]
    joined = flow.merge(
        ns3,
        on=["topology", "link_failure_probability", "rate_pct", "seed"],
        suffixes=("_flowsim_metric", "_ns3_metric"),
        how="inner",
    )
    joined["failed_links_match"] = (
        joined["flowsim_failed_links"] == joined["ns3_failed_links"]
    )
    joined["failed_topology_match"] = joined["flowsim_failed_topology"].map(
        lambda p: Path(str(p)).name
    ) == joined["ns3_failed_topology"].map(lambda p: Path(str(p)).name)
    for col in metric_cols:
        flow_col = f"{col}_flowsim_metric"
        ns3_col = f"{col}_ns3_metric"
        if flow_col in joined and ns3_col in joined:
            joined[col] = joined[flow_col]
            joined[f"{col}_match"] = np.isclose(
                joined[flow_col], joined[ns3_col], equal_nan=True
            )
    joined["factor_delta_ns3_minus_flowsim"] = (
        joined["ns3_factor"] - joined["flowsim_factor"]
    )
    joined["factor_abs_delta"] = joined["factor_delta_ns3_minus_flowsim"].abs()
    joined["ns3_over_flowsim_factor"] = joined["ns3_factor"] / joined["flowsim_factor"]
    joined["ns3_over_flowsim_jct"] = (
        joined["ns3_failed_jct"] / joined["flowsim_failed_jct"]
    )
    joined["flowsim_synced_paths_ratio_to_baseline"] = (
        joined["flowsim_synced_paths"] / joined["flowsim_baseline_synced_paths"]
    )
    joined["flowsim_pxn_split_ratio_delta"] = (
        joined["flowsim_pxn_split_ratio"]
        - joined["flowsim_baseline_pxn_split_ratio"]
    )
    route_metrics = (
        joined["flowsim_failed_topology"]
        .drop_duplicates()
        .map(estimate_route_load_metrics)
        .apply(pd.Series)
    )
    route_metrics["flowsim_failed_topology"] = joined[
        "flowsim_failed_topology"
    ].drop_duplicates().to_numpy()
    joined = joined.merge(route_metrics, on="flowsim_failed_topology", how="left")
    joined["estimated_pxn_split_ratio_error"] = (
        joined["estimated_pxn_split_ratio"] - joined["flowsim_pxn_split_ratio"]
    )
    ratio_metrics = [
        "static_avg_legs_per_pair",
        "static_pxn_pair_ratio",
        "static_any_max_load",
        "static_any_p95_load",
        "static_any_max_pressure",
        "static_any_p95_pressure",
        "static_inter_server_max_load",
        "static_inter_server_p95_load",
        "static_inter_server_max_pressure",
        "static_inter_server_p95_pressure",
        "static_local_nvswitch_max_load",
        "static_local_nvswitch_p95_load",
        "static_local_nvswitch_max_pressure",
        "static_local_nvswitch_p95_pressure",
        "static_gpu_switch_max_pressure",
        "static_switch_switch_max_pressure",
    ]
    for metric in ratio_metrics:
        baseline_metric = f"baseline_{metric}"
        if metric in joined and baseline_metric in joined:
            denom = joined[baseline_metric].replace(0, np.nan)
            joined[f"{metric}_ratio_to_baseline"] = joined[metric] / denom
    joined["topology"] = pd.Categorical(
        joined["topology"], categories=ORDER, ordered=True
    )
    return joined.sort_values(["topology", "rate_pct", "seed"])


def corr(series_a: pd.Series, series_b: pd.Series) -> float:
    data = pd.DataFrame({"a": series_a, "b": series_b}).dropna()
    if len(data) < 3 or data["a"].nunique() < 2 or data["b"].nunique() < 2:
        return np.nan
    return float(data["a"].corr(data["b"]))


def build_topology_summary(joined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for topology, part in joined.groupby("topology", observed=False):
        if part.empty:
            continue
        rows.append(
            {
                "topology": str(topology),
                "samples": len(part),
                "failed_links_all_match": bool(part["failed_links_match"].all()),
                "mean_flowsim_factor": part["flowsim_factor"].mean(),
                "mean_ns3_factor": part["ns3_factor"].mean(),
                "mean_factor_delta_ns3_minus_flowsim": part[
                    "factor_delta_ns3_minus_flowsim"
                ].mean(),
                "mean_abs_factor_delta": part["factor_abs_delta"].mean(),
                "mean_ns3_over_flowsim_factor": part[
                    "ns3_over_flowsim_factor"
                ].mean(),
                "corr_delta_failed_link_ratio": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["failed_link_ratio"],
                ),
                "corr_delta_avg_path_len": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["average_path_length_after_failure"],
                ),
                "corr_delta_path_stretch": corr(
                    part["factor_delta_ns3_minus_flowsim"], part["path_stretch"]
                ),
                "corr_flowsim_factor_path_stretch": corr(
                    part["flowsim_factor"], part["path_stretch"]
                ),
                "corr_ns3_factor_path_stretch": corr(
                    part["ns3_factor"], part["path_stretch"]
                ),
                "corr_flowsim_factor_pxn_split_ratio": corr(
                    part["flowsim_factor"], part["flowsim_pxn_split_ratio"]
                ),
                "corr_flowsim_factor_synced_paths_ratio": corr(
                    part["flowsim_factor"],
                    part["flowsim_synced_paths_ratio_to_baseline"],
                ),
                "corr_flowsim_factor_estimated_pxn_split_ratio": corr(
                    part["flowsim_factor"], part["estimated_pxn_split_ratio"]
                ),
                "corr_ns3_factor_estimated_pxn_split_ratio": corr(
                    part["ns3_factor"], part["estimated_pxn_split_ratio"]
                ),
                "corr_delta_estimated_pxn_split_ratio": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["estimated_pxn_split_ratio"],
                ),
                "corr_flowsim_factor_inter_server_pressure_ratio": corr(
                    part["flowsim_factor"],
                    part["static_inter_server_max_pressure_ratio_to_baseline"],
                ),
                "corr_ns3_factor_inter_server_pressure_ratio": corr(
                    part["ns3_factor"],
                    part["static_inter_server_max_pressure_ratio_to_baseline"],
                ),
                "corr_delta_inter_server_pressure_ratio": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["static_inter_server_max_pressure_ratio_to_baseline"],
                ),
                "corr_flowsim_factor_local_nvswitch_pressure_ratio": corr(
                    part["flowsim_factor"],
                    part["static_local_nvswitch_max_pressure_ratio_to_baseline"],
                ),
                "corr_ns3_factor_local_nvswitch_pressure_ratio": corr(
                    part["ns3_factor"],
                    part["static_local_nvswitch_max_pressure_ratio_to_baseline"],
                ),
                "corr_delta_local_nvswitch_pressure_ratio": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["static_local_nvswitch_max_pressure_ratio_to_baseline"],
                ),
                "corr_flowsim_factor_avg_legs_ratio": corr(
                    part["flowsim_factor"],
                    part["static_avg_legs_per_pair_ratio_to_baseline"],
                ),
                "corr_ns3_factor_avg_legs_ratio": corr(
                    part["ns3_factor"],
                    part["static_avg_legs_per_pair_ratio_to_baseline"],
                ),
                "corr_delta_avg_legs_ratio": corr(
                    part["factor_delta_ns3_minus_flowsim"],
                    part["static_avg_legs_per_pair_ratio_to_baseline"],
                ),
                "mean_flowsim_pxn_split_ratio": part[
                    "flowsim_pxn_split_ratio"
                ].mean(),
                "mean_estimated_pxn_split_ratio": part[
                    "estimated_pxn_split_ratio"
                ].mean(),
                "max_abs_estimated_pxn_split_ratio_error": part[
                    "estimated_pxn_split_ratio_error"
                ].abs().max(),
                "mean_flowsim_synced_paths_ratio_to_baseline": part[
                    "flowsim_synced_paths_ratio_to_baseline"
                ].mean(),
                "mean_static_avg_legs_ratio_to_baseline": part[
                    "static_avg_legs_per_pair_ratio_to_baseline"
                ].mean(),
                "mean_static_inter_server_max_pressure_ratio": part[
                    "static_inter_server_max_pressure_ratio_to_baseline"
                ].mean(),
                "mean_static_local_nvswitch_max_pressure_ratio": part[
                    "static_local_nvswitch_max_pressure_ratio_to_baseline"
                ].mean(),
                "mean_static_any_max_pressure_ratio": part[
                    "static_any_max_pressure_ratio_to_baseline"
                ].mean(),
            }
        )
    out = pd.DataFrame(rows)
    out["topology"] = pd.Categorical(out["topology"], categories=ORDER, ordered=True)
    return out.sort_values("topology")


def build_rate_summary(joined: pd.DataFrame) -> pd.DataFrame:
    grouped = joined.groupby(["topology", "rate_pct"], observed=False)
    out = grouped.agg(
        samples=("seed", "count"),
        flowsim_factor_mean=("flowsim_factor", "mean"),
        ns3_factor_mean=("ns3_factor", "mean"),
        factor_delta_mean=("factor_delta_ns3_minus_flowsim", "mean"),
        factor_abs_delta_mean=("factor_abs_delta", "mean"),
        path_stretch_mean=("path_stretch", "mean"),
        avg_path_len_mean=("average_path_length_after_failure", "mean"),
        failed_link_ratio_mean=("failed_link_ratio", "mean"),
        flowsim_pxn_split_ratio_mean=("flowsim_pxn_split_ratio", "mean"),
        flowsim_synced_paths_ratio_mean=(
            "flowsim_synced_paths_ratio_to_baseline",
            "mean",
        ),
        direct_route_connectivity_ratio_mean=(
            "direct_route_connectivity_ratio",
            "mean",
        ),
        estimated_pxn_split_ratio_mean=("estimated_pxn_split_ratio", "mean"),
        static_avg_legs_ratio_mean=(
            "static_avg_legs_per_pair_ratio_to_baseline",
            "mean",
        ),
        static_inter_server_max_pressure_ratio_mean=(
            "static_inter_server_max_pressure_ratio_to_baseline",
            "mean",
        ),
        static_inter_server_p95_pressure_ratio_mean=(
            "static_inter_server_p95_pressure_ratio_to_baseline",
            "mean",
        ),
        static_local_nvswitch_max_pressure_ratio_mean=(
            "static_local_nvswitch_max_pressure_ratio_to_baseline",
            "mean",
        ),
        static_local_nvswitch_p95_pressure_ratio_mean=(
            "static_local_nvswitch_p95_pressure_ratio_to_baseline",
            "mean",
        ),
        static_any_max_pressure_ratio_mean=(
            "static_any_max_pressure_ratio_to_baseline",
            "mean",
        ),
    ).reset_index()
    return out.sort_values(["topology", "rate_pct"])


def draw_path_diagnostic(joined: pd.DataFrame, output_dir: Path) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"
    focus = [topo for topo in FOCUS if topo in set(joined["topology"].astype(str))]
    fig, axes = plt.subplots(
        1,
        len(focus),
        figsize=(16.0, 5.9),
        dpi=120,
        sharey=True,
        facecolor=bg,
    )
    if len(focus) == 1:
        axes = [axes]

    for ax, topology in zip(axes, focus):
        part = joined[joined["topology"].astype(str) == topology].copy()
        ax.set_facecolor(bg)
        for side in ["left", "right", "top", "bottom"]:
            ax.spines[side].set_color(axis)
            ax.spines[side].set_linewidth(1.0)
        ax.tick_params(colors=fg, labelsize=12, width=1.0, length=4)
        ax.axhline(0.0, color=axis, linewidth=1.0, linestyle="--", alpha=0.5)
        sc = ax.scatter(
            part["path_stretch"],
            part["factor_delta_ns3_minus_flowsim"],
            c=part["rate_pct"],
            cmap="viridis",
            s=44,
            alpha=0.78,
            edgecolor=COLORS[topology],
            linewidth=0.7,
        )
        ax.set_title(LABELS[topology], fontsize=18, color=fg, pad=10, fontweight="bold")
        ax.set_xlabel("Path stretch", fontsize=13, color=fg)
        if ax is axes[0]:
            ax.set_ylabel("NS3 factor - FlowSim factor", fontsize=13, color=fg)
        ax.grid(False)

    cbar = fig.colorbar(sc, ax=axes, fraction=0.028, pad=0.025)
    cbar.set_label("Link failure (%)", color=fg, fontsize=12)
    cbar.ax.tick_params(colors=fg, labelsize=11)
    cbar.outline.set_edgecolor(axis)

    fig.text(
        0.07,
        0.985,
        "Simulator mismatch versus path stretch",
        ha="left",
        va="top",
        fontsize=21,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.935,
        "Each point is one topology/rate/seed sample. Positive values mean NS3 predicts larger relative JCT degradation than FlowSim.",
        ha="left",
        va="top",
        fontsize=11.5,
        color=fg,
        alpha=0.86,
    )
    fig.subplots_adjust(left=0.07, right=0.9, bottom=0.15, top=0.82, wspace=0.18)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(
            output_dir / f"path_stretch_vs_simulator_delta.{ext}",
            facecolor=bg,
            edgecolor=bg,
        )
    plt.close(fig)


def draw_rate_delta(joined: pd.DataFrame, output_dir: Path) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"
    summary = build_rate_summary(joined)
    fig, ax = plt.subplots(figsize=(12.5, 6.4), dpi=120, facecolor=bg)
    ax.set_facecolor(bg)
    for side in ["left", "right", "top", "bottom"]:
        ax.spines[side].set_color(axis)
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=fg, labelsize=13, width=1.0, length=4)
    ax.axhline(0.0, color=axis, linewidth=1.0, linestyle="--", alpha=0.55)
    for topology in ORDER:
        part = summary[summary["topology"].astype(str) == topology]
        if part.empty:
            continue
        ax.plot(
            part["rate_pct"],
            part["factor_delta_mean"],
            color=COLORS[topology],
            label=LABELS[topology],
            linewidth=2.1,
            marker="o",
            markersize=5.2,
        )
    ax.set_xlim(1, 15)
    ax.set_xticks(np.arange(1, 16, 1))
    ax.set_xlabel("Link failure percentage (%)", fontsize=15, color=fg)
    ax.set_ylabel("Mean normalized-JCT delta (NS3 - FlowSim)", fontsize=15, color=fg)
    legend = ax.legend(
        title="Topology",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=13,
        title_fontsize=14,
    )
    legend.get_title().set_color(fg)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts():
        text.set_color(fg)
    fig.text(
        0.08,
        0.985,
        "Where NS3 and FlowSim diverge by fault rate",
        ha="left",
        va="top",
        fontsize=19,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.94,
        "Positive means NS3 gives higher relative JCT degradation; negative means FlowSim is more pessimistic.",
        ha="left",
        va="top",
        fontsize=11.5,
        color=fg,
        alpha=0.86,
    )
    fig.subplots_adjust(left=0.08, right=0.78, bottom=0.14, top=0.84)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(
            output_dir / f"simulator_delta_by_fault_rate.{ext}",
            facecolor=bg,
            edgecolor=bg,
        )
    plt.close(fig)


def draw_flowsim_pxn_driver(joined: pd.DataFrame, output_dir: Path) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"
    focus = [topo for topo in FOCUS if topo in set(joined["topology"].astype(str))]
    fig, axes = plt.subplots(
        1,
        len(focus),
        figsize=(16.0, 5.9),
        dpi=120,
        sharey=True,
        facecolor=bg,
    )
    if len(focus) == 1:
        axes = [axes]
    for ax, topology in zip(axes, focus):
        part = joined[joined["topology"].astype(str) == topology].copy()
        ax.set_facecolor(bg)
        for side in ["left", "right", "top", "bottom"]:
            ax.spines[side].set_color(axis)
            ax.spines[side].set_linewidth(1.0)
        ax.tick_params(colors=fg, labelsize=12, width=1.0, length=4)
        sc = ax.scatter(
            part["flowsim_pxn_split_ratio"],
            part["flowsim_factor"],
            c=part["rate_pct"],
            cmap="viridis",
            s=44,
            alpha=0.78,
            edgecolor=COLORS[topology],
            linewidth=0.7,
        )
        ax.set_title(LABELS[topology], fontsize=18, color=fg, pad=10, fontweight="bold")
        ax.set_xlabel("FlowSim PXN split ratio", fontsize=13, color=fg)
        if ax is axes[0]:
            ax.set_ylabel("FlowSim normalized JCT", fontsize=13, color=fg)
        ax.grid(False)
    cbar = fig.colorbar(sc, ax=axes, fraction=0.028, pad=0.025)
    cbar.set_label("Link failure (%)", color=fg, fontsize=12)
    cbar.ax.tick_params(colors=fg, labelsize=11)
    cbar.outline.set_edgecolor(axis)
    fig.text(
        0.07,
        0.985,
        "FlowSim slowdown versus PXN split ratio",
        ha="left",
        va="top",
        fontsize=21,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.935,
        "PXN split/direct counts are parsed from FlowSim run logs; each point is one topology/rate/seed sample.",
        ha="left",
        va="top",
        fontsize=11.5,
        color=fg,
        alpha=0.86,
    )
    fig.subplots_adjust(left=0.07, right=0.9, bottom=0.15, top=0.82, wspace=0.18)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(
            output_dir / f"flowsim_pxn_split_vs_flowsim_factor.{ext}",
            facecolor=bg,
            edgecolor=bg,
        )
    plt.close(fig)


def draw_static_pressure_driver(
    joined: pd.DataFrame,
    output_dir: Path,
    *,
    metric: str,
    xlabel: str,
    title: str,
    filename: str,
) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"
    focus = [topo for topo in FOCUS if topo in set(joined["topology"].astype(str))]
    fig, axes = plt.subplots(
        1,
        len(focus),
        figsize=(16.0, 5.9),
        dpi=120,
        sharey=True,
        facecolor=bg,
    )
    if len(focus) == 1:
        axes = [axes]
    for ax, topology in zip(axes, focus):
        part = joined[joined["topology"].astype(str) == topology].copy()
        part = part[np.isfinite(part[metric])]
        ax.set_facecolor(bg)
        for side in ["left", "right", "top", "bottom"]:
            ax.spines[side].set_color(axis)
            ax.spines[side].set_linewidth(1.0)
        ax.tick_params(colors=fg, labelsize=12, width=1.0, length=4)
        ax.axhline(0.0, color=axis, linewidth=1.0, linestyle="--", alpha=0.5)
        sc = ax.scatter(
            part[metric],
            part["factor_delta_ns3_minus_flowsim"],
            c=part["rate_pct"],
            cmap="viridis",
            s=44,
            alpha=0.78,
            edgecolor=COLORS[topology],
            linewidth=0.7,
        )
        ax.set_title(LABELS[topology], fontsize=18, color=fg, pad=10, fontweight="bold")
        ax.set_xlabel(xlabel, fontsize=13, color=fg)
        if ax is axes[0]:
            ax.set_ylabel("NS3 factor - FlowSim factor", fontsize=13, color=fg)
        ax.grid(False)

    cbar = fig.colorbar(sc, ax=axes, fraction=0.028, pad=0.025)
    cbar.set_label("Link failure (%)", color=fg, fontsize=12)
    cbar.ax.tick_params(colors=fg, labelsize=11)
    cbar.outline.set_edgecolor(axis)
    fig.text(
        0.07,
        0.985,
        title,
        ha="left",
        va="top",
        fontsize=21,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.935,
        "Static estimator counts all-to-all direct routes plus PXN fallback legs; pressure is load divided by link Gbps.",
        ha="left",
        va="top",
        fontsize=11.5,
        color=fg,
        alpha=0.86,
    )
    fig.subplots_adjust(left=0.07, right=0.9, bottom=0.15, top=0.82, wspace=0.18)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(output_dir / f"{filename}.{ext}", facecolor=bg, edgecolor=bg)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose FlowSim vs NS3 mismatch")
    parser.add_argument("--flowsim-dir", type=Path, default=DEFAULT_FLOWSIM)
    parser.add_argument("--ns3-dir", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    joined = build_joined(args.flowsim_dir, args.ns3_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    joined_path = args.output_dir / "sample_level_joined.csv"
    joined.to_csv(joined_path, index=False)

    topology_summary = build_topology_summary(joined)
    topology_path = args.output_dir / "topology_mismatch_summary.csv"
    topology_summary.to_csv(topology_path, index=False)

    rate_summary = build_rate_summary(joined)
    rate_path = args.output_dir / "rate_mismatch_summary.csv"
    rate_summary.to_csv(rate_path, index=False)

    top_samples = joined.sort_values("factor_abs_delta", ascending=False).head(40)
    top_path = args.output_dir / "top_mismatch_samples.csv"
    top_samples.to_csv(top_path, index=False)

    draw_path_diagnostic(joined, args.output_dir)
    draw_rate_delta(joined, args.output_dir)
    draw_flowsim_pxn_driver(joined, args.output_dir)
    draw_static_pressure_driver(
        joined,
        args.output_dir,
        metric="static_inter_server_max_pressure_ratio_to_baseline",
        xlabel="Inter-server max pressure / baseline",
        title="Simulator mismatch versus inter-server hotspot pressure",
        filename="inter_server_pressure_vs_simulator_delta",
    )
    draw_static_pressure_driver(
        joined,
        args.output_dir,
        metric="static_local_nvswitch_max_pressure_ratio_to_baseline",
        xlabel="Local NVSwitch max pressure / baseline",
        title="Simulator mismatch versus local NVSwitch pressure",
        filename="local_nvswitch_pressure_vs_simulator_delta",
    )

    print(joined_path)
    print(topology_path)
    print(rate_path)
    print(top_path)
    print(args.output_dir / "path_stretch_vs_simulator_delta.png")
    print(args.output_dir / "simulator_delta_by_fault_rate.png")
    print(args.output_dir / "flowsim_pxn_split_vs_flowsim_factor.png")
    print(args.output_dir / "inter_server_pressure_vs_simulator_delta.png")
    print(args.output_dir / "local_nvswitch_pressure_vs_simulator_delta.png")
    print(f"joined_samples={len(joined)}")
    print(f"failed_link_sets_all_match={bool(joined['failed_links_match'].all())}")
    print(
        "max_abs_estimated_pxn_split_ratio_error="
        f"{joined['estimated_pxn_split_ratio_error'].abs().max():.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
