#!/usr/bin/env python3
"""Run 256-GPU FlowSim random-link fault experiments for all-to-all.

This is a thin batch runner over fault_tolerance_experiments.py. It removes
failed links from generated topology files before each run, excludes
NVSwitch/NVLink links from random failure sampling, disables FCT output, and
records only JCT-level results from EndToEnd.csv.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "fault_tolerance_experiments.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("fault_tolerance_experiments", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper module: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FT = load_helper()


TOPOLOGY_SETS: Dict[str, Dict[str, str]] = {
    "256": {
        "Meta": "Meta_Topo_256g_8gps_400Gbps_A100",
        "HPN": "AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100",
        "DeepSeek": "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
        "Zcube": "Zcube_n16_k2_256g_8gps_200Gbps_H100",
        "RO": "RailOnly_256g_8gps_p16a0.5_400Gbps_H100",
        "ROFT": "ROFT_256g_8gps_p16a0.5_400Gbps_H100",
    },
    "1024_12p8T": {
        "Meta": "Meta_Topo_1024g_8gps_400Gbps_H100_12p8T",
        "HPN": "AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100",
        "DeepSeek": "DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100",
        "Zcube": "Zcube_n32_k2_1024g_8gps_200Gbps_H100",
        "RO": "RailOnly_1024g_8gps_s5_400Gbps_H100_12p8T",
        "ROFT": "ROFT_1024g_8gps_p32a0.5_400Gbps_H100_12p8T",
    },
}

TOPOLOGIES: Dict[str, str] = {
    "Meta": "Meta_Topo_256g_8gps_400Gbps_A100",
    "HPN": "AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100",
    "DeepSeek": "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
    "Zcube": "Zcube_n16_k2_256g_8gps_200Gbps_H100",
    "RO": "RailOnly_256g_8gps_p16a0.5_400Gbps_H100",
    "ROFT": "ROFT_256g_8gps_p16a0.5_400Gbps_H100",
}


SUMMARY_METADATA = [
    "scale",
    "flowsim_policy",
    "cross_rail_switch_switch_weight",
    "direct_cross_rail_switch_switch_weight",
    "pxn_same_rail_switch_switch_weight",
    "pxn_same_rail_switch_switch_hop_weights",
    "direct_cross_rail_switch_switch_hop_weights",
    "fault_cross_rail_switch_switch_weight",
    "fault_direct_cross_rail_switch_switch_weight",
    "fault_pxn_same_rail_switch_switch_weight",
    "fault_pxn_same_rail_switch_switch_hop_weights",
    "fault_direct_cross_rail_switch_switch_hop_weights",
    "high_stretch_fault_topologies",
    "high_stretch_threshold",
    "high_stretch_fault_cross_rail_switch_switch_weight",
    "high_stretch_fault_direct_cross_rail_switch_switch_weight",
    "high_stretch_fault_pxn_same_rail_switch_switch_weight",
    "high_stretch_fault_pxn_same_rail_switch_switch_hop_weights",
    "high_stretch_fault_direct_cross_rail_switch_switch_hop_weights",
    "fault_env_class",
    "as_pxn_enable",
    "as_pxn_policy",
    "flowsim_pxn_timing",
    "flowsim_pxn_local_pipeline_delay_ns",
]


def topology_map_for_scale(scale: str) -> Dict[str, str]:
    if scale not in TOPOLOGY_SETS:
        raise ValueError(f"unknown topology scale: {scale}")
    return TOPOLOGY_SETS[scale]


def default_topology_dir(root: Path, scale: str) -> Path:
    if scale == "256":
        return root / "mytopo"
    return root / "mytopo" / scale


def default_workload(root: Path, scale: str) -> Path:
    if scale == "1024_12p8T":
        return root / "my_workloads" / "synthetic_alltoall_global_world_size1024_4MiB.txt"
    return root / "my_workloads" / "synthetic_alltoall_global_world_size256_1MiB.txt"


def default_output_dir(root: Path, scale: str) -> Path:
    if scale == "1024_12p8T":
        return (
            root
            / "experiments"
            / "fault_tolerance"
            / "flowsim_1024_12p8T_alltoall_4MiB"
        )
    return root / "experiments" / "fault_tolerance" / "flowsim_256_alltoall"


def read_switch_summary(topology: FT.Topology, limit_gbps: float) -> Dict[str, object]:
    try:
        from check_switch_throughput import summarize_topology
    except ImportError as exc:
        raise RuntimeError("failed to import switch throughput checker") from exc
    return summarize_topology(topology, limit_gbps=limit_gbps)


def parse_rates(value: str) -> List[float]:
    rates = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        rate = float(part)
        if rate < 0.0 or rate > 1.0:
            raise argparse.ArgumentTypeError("rates must be in [0, 1]")
        rates.append(rate)
    if not rates:
        raise argparse.ArgumentTypeError("at least one rate is required")
    return rates


def default_rates() -> List[float]:
    return [i / 100.0 for i in range(1, 16)]


def rate_label(rate: float) -> str:
    return f"p{rate:.6g}".replace(".", "p")


def format_optional_float(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{value:g}"


def parse_hop_weights(value: str) -> List[Tuple[int, float]]:
    weights: List[Tuple[int, float]] = []
    for part in value.split(","):
        text = part.strip()
        if not text:
            continue
        if "=" not in text:
            raise argparse.ArgumentTypeError(
                "hop weights must use hop=weight entries, e.g. 4=0.4"
            )
        hop_text, weight_text = text.split("=", 1)
        try:
            hop = int(hop_text)
            weight = float(weight_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "hop weights must use integer hops and numeric weights"
            ) from exc
        if hop <= 0:
            raise argparse.ArgumentTypeError("hop values must be positive")
        if weight <= 0.0:
            raise argparse.ArgumentTypeError("hop weights must be > 0")
        weights.append((hop, weight))
    if not weights:
        raise argparse.ArgumentTypeError("at least one hop=weight entry is required")
    return weights


def format_hop_weights(weights: Optional[Sequence[Tuple[int, float]]]) -> str:
    if not weights:
        return "default"
    return ",".join(f"{hop}={weight:g}" for hop, weight in weights)


def apply_hop_weights(
    env: Dict[str, str],
    base_env_name: str,
    weights: Optional[Sequence[Tuple[int, float]]],
) -> None:
    if not weights:
        return
    for hop, weight in weights:
        env[f"{base_env_name}_HOPS{hop}"] = f"{weight:g}"


def apply_policy_env(
    env: Dict[str, str],
    *,
    cross_rail_switch_switch_weight: Optional[float],
    direct_cross_rail_switch_switch_weight: Optional[float],
    pxn_same_rail_switch_switch_weight: Optional[float],
    pxn_same_rail_switch_switch_hop_weights: Optional[Sequence[Tuple[int, float]]],
    direct_cross_rail_switch_switch_hop_weights: Optional[Sequence[Tuple[int, float]]],
) -> None:
    weight = format_optional_float(cross_rail_switch_switch_weight)
    if weight is not None:
        env["FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT"] = weight
    direct_weight = format_optional_float(direct_cross_rail_switch_switch_weight)
    if direct_weight is not None:
        env["FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT"] = direct_weight
    pxn_same_rail_weight = format_optional_float(pxn_same_rail_switch_switch_weight)
    if pxn_same_rail_weight is not None:
        env["FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT"] = pxn_same_rail_weight
    apply_hop_weights(
        env,
        "FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT",
        pxn_same_rail_switch_switch_hop_weights,
    )
    apply_hop_weights(
        env,
        "FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT",
        direct_cross_rail_switch_switch_hop_weights,
    )


def read_jct(path: Path) -> Optional[float]:
    return FT.read_total_time(path)


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


def read_csv(path: Path) -> List[Dict[str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def numeric(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isnan(f):
            return None
        return f
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "missing":
            return None
        try:
            f = float(text)
        except ValueError:
            return None
        if math.isnan(f):
            return None
        return f
    return None


def task_key(row: Dict[str, object]) -> Tuple[object, ...]:
    return (
        row.get("topology", ""),
        rate_label(float(row.get("link_failure_probability", 0.0))),
        str(row.get("seed", "")),
        *(str(row.get(field, "")) for field in SUMMARY_METADATA),
    )


def dedupe_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    by_key: Dict[Tuple[object, ...], Dict[str, object]] = {}
    passthrough: List[Dict[str, object]] = []
    for row in rows:
        if "link_failure_probability" not in row or "seed" not in row:
            passthrough.append(row)
            continue
        by_key[task_key(row)] = dict(row)
    return passthrough + list(by_key.values())


def baseline_key(row: Dict[str, object]) -> Tuple[object, ...]:
    return (
        row.get("topology", ""),
        *(str(row.get(field, "")) for field in SUMMARY_METADATA),
    )


def dedupe_baselines(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    by_key: Dict[Tuple[object, ...], Dict[str, object]] = {}
    for row in rows:
        by_key[baseline_key(row)] = dict(row)
    return list(by_key.values())


def summarize(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[object, ...], List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["topology"]),
            float(row["link_failure_probability"]),
            *(str(row.get(field, "")) for field in SUMMARY_METADATA),
        )
        grouped[key].append(row)

    metrics = [
        "normal_jct",
        "failed_jct",
        "degradation",
        "num_failed_links",
        "failed_link_ratio",
        "failed_flow_ratio",
        "connectivity_ratio",
        "average_path_length_after_failure",
        "path_stretch",
    ]
    out: List[Dict[str, object]] = []
    for key, group_rows in sorted(grouped.items()):
        topology, rate = key[:2]
        first = group_rows[0]
        row: Dict[str, object] = {
            "topology": topology,
            "link_failure_probability": rate,
            "num_samples": len(group_rows),
            "num_success": sum(1 for r in group_rows if r.get("status") == "success"),
        }
        for field in SUMMARY_METADATA:
            if field in first:
                row[field] = first[field]
        for metric in metrics:
            values = [numeric(r.get(metric)) for r in group_rows]
            values = [v for v in values if v is not None]
            if values:
                row[f"{metric}_mean"] = mean(values)
                row[f"{metric}_std"] = pstdev(values) if len(values) > 1 else 0.0
            else:
                row[f"{metric}_mean"] = "missing"
                row[f"{metric}_std"] = "missing"
        out.append(row)
    return out


def run_flowsim(
    *,
    flowsim_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    env: Dict[str, str],
    resume: bool,
    timeout_seconds: Optional[int],
) -> Optional[float]:
    if resume:
        existing = read_jct(output_dir / "EndToEnd.csv")
        if existing is not None:
            return existing
    if timeout_seconds is None:
        return FT.run_flowsim(flowsim_bin, workload, topology, output_dir, threads, env)

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
        try:
            subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                env=env,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            log.write(f"\n[RUNNER] timeout after {timeout_seconds}s\n")
            return None
    return read_jct(output_dir / "EndToEnd.csv")


def run_fault_task(task: Dict[str, object]) -> Dict[str, object]:
    failed_jct = run_flowsim(
        flowsim_bin=task["flowsim_bin"],
        workload=task["workload"],
        topology=task["failed_topology_path"],
        output_dir=task["run_dir_path"],
        threads=task["threads"],
        env=task["env"],
        resume=task["resume"],
        timeout_seconds=task["timeout_seconds"],
    )
    normal_jct = task["normal_jct"]
    if normal_jct is not None and failed_jct is not None and normal_jct != 0:
        degradation: object = (failed_jct - normal_jct) / normal_jct
    else:
        degradation = "missing"
    row = dict(task["row"])
    row["status"] = "success" if failed_jct is not None else "failed"
    row["failed_jct"] = failed_jct if failed_jct is not None else "missing"
    row["degradation"] = degradation
    return row


def build_env(args: argparse.Namespace) -> Dict[str, str]:
    env = os.environ.copy()
    env["AS_SEND_LAT"] = env.get("AS_SEND_LAT", "3")
    env["AS_NVLS_ENABLE"] = env.get("AS_NVLS_ENABLE", "0")
    env["AS_PXN_ENABLE"] = env.get("AS_PXN_ENABLE", "1")
    env["AS_PXN_POLICY"] = env.get("AS_PXN_POLICY", "fallback")
    if args.flowsim_pxn_timing:
        env["FLOWSIM_PXN_TIMING"] = args.flowsim_pxn_timing
    if args.pxn_local_pipeline_delay_ns is not None:
        env["FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS"] = str(
            args.pxn_local_pipeline_delay_ns
        )
    apply_policy_env(
        env,
        cross_rail_switch_switch_weight=args.cross_rail_switch_switch_weight,
        direct_cross_rail_switch_switch_weight=args.direct_cross_rail_switch_switch_weight,
        pxn_same_rail_switch_switch_weight=args.pxn_same_rail_switch_switch_weight,
        pxn_same_rail_switch_switch_hop_weights=args.pxn_same_rail_switch_switch_hop_weights,
        direct_cross_rail_switch_switch_hop_weights=args.direct_cross_rail_switch_switch_hop_weights,
    )
    env["FLOWSIM_WRITE_FCT"] = "0"
    return env


def build_fault_env(args: argparse.Namespace, baseline_env: Dict[str, str]) -> Dict[str, str]:
    env = baseline_env.copy()
    apply_policy_env(
        env,
        cross_rail_switch_switch_weight=args.fault_cross_rail_switch_switch_weight,
        direct_cross_rail_switch_switch_weight=args.fault_direct_cross_rail_switch_switch_weight,
        pxn_same_rail_switch_switch_weight=args.fault_pxn_same_rail_switch_switch_weight,
        pxn_same_rail_switch_switch_hop_weights=args.fault_pxn_same_rail_switch_switch_hop_weights,
        direct_cross_rail_switch_switch_hop_weights=args.fault_direct_cross_rail_switch_switch_hop_weights,
    )
    return env


def build_high_stretch_fault_env(
    args: argparse.Namespace, fault_env: Dict[str, str]
) -> Dict[str, str]:
    env = fault_env.copy()
    apply_policy_env(
        env,
        cross_rail_switch_switch_weight=args.high_stretch_fault_cross_rail_switch_switch_weight,
        direct_cross_rail_switch_switch_weight=(
            args.high_stretch_fault_direct_cross_rail_switch_switch_weight
        ),
        pxn_same_rail_switch_switch_weight=(
            args.high_stretch_fault_pxn_same_rail_switch_switch_weight
        ),
        pxn_same_rail_switch_switch_hop_weights=(
            args.high_stretch_fault_pxn_same_rail_switch_switch_hop_weights
        ),
        direct_cross_rail_switch_switch_hop_weights=(
            args.high_stretch_fault_direct_cross_rail_switch_switch_hop_weights
        ),
    )
    return env


def high_stretch_fault_enabled(args: argparse.Namespace) -> bool:
    return bool(args.high_stretch_fault_topologies) and args.high_stretch_threshold is not None


def select_fault_env(
    args: argparse.Namespace,
    *,
    topology: str,
    metrics: Dict[str, object],
    fault_env: Dict[str, str],
    high_stretch_fault_env: Dict[str, str],
) -> Tuple[Dict[str, str], str]:
    if not high_stretch_fault_enabled(args):
        return fault_env, "fault_default"
    path_stretch = numeric(metrics.get("path_stretch"))
    if (
        topology in set(args.high_stretch_fault_topologies or [])
        and path_stretch is not None
        and path_stretch >= float(args.high_stretch_threshold)
    ):
        return high_stretch_fault_env, "fault_high_stretch"
    return fault_env, "fault_default"


def policy_metadata(
    args: argparse.Namespace,
    env: Dict[str, str],
    fault_env: Dict[str, str],
    high_stretch_fault_env: Dict[str, str],
) -> Dict[str, object]:
    weight = env.get("FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default")
    direct_weight = env.get("FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default")
    pxn_same_rail_weight = env.get(
        "FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    pxn_hop_weights = format_hop_weights(args.pxn_same_rail_switch_switch_hop_weights)
    direct_hop_weights = format_hop_weights(args.direct_cross_rail_switch_switch_hop_weights)
    fault_weight = fault_env.get("FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default")
    fault_direct_weight = fault_env.get(
        "FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    fault_pxn_same_rail_weight = fault_env.get(
        "FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    fault_pxn_hop_weights = format_hop_weights(
        args.fault_pxn_same_rail_switch_switch_hop_weights
        or args.pxn_same_rail_switch_switch_hop_weights
    )
    fault_direct_hop_weights = format_hop_weights(
        args.fault_direct_cross_rail_switch_switch_hop_weights
        or args.direct_cross_rail_switch_switch_hop_weights
    )
    high_stretch_topologies = (
        ",".join(args.high_stretch_fault_topologies)
        if args.high_stretch_fault_topologies
        else "off"
    )
    high_stretch_threshold = format_optional_float(args.high_stretch_threshold) or "off"
    high_stretch_weight = high_stretch_fault_env.get(
        "FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    high_stretch_direct_weight = high_stretch_fault_env.get(
        "FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    high_stretch_pxn_same_rail_weight = high_stretch_fault_env.get(
        "FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT", "default"
    )
    high_stretch_pxn_hop_weights = format_hop_weights(
        args.high_stretch_fault_pxn_same_rail_switch_switch_hop_weights
        or args.fault_pxn_same_rail_switch_switch_hop_weights
        or args.pxn_same_rail_switch_switch_hop_weights
    )
    high_stretch_direct_hop_weights = format_hop_weights(
        args.high_stretch_fault_direct_cross_rail_switch_switch_hop_weights
        or args.fault_direct_cross_rail_switch_switch_hop_weights
        or args.direct_cross_rail_switch_switch_hop_weights
    )
    label = args.policy_label
    if label is None:
        if (
            weight == "default"
            and direct_weight == "default"
            and pxn_same_rail_weight == "default"
            and pxn_hop_weights == "default"
            and direct_hop_weights == "default"
            and fault_weight == weight
            and fault_direct_weight == direct_weight
            and fault_pxn_same_rail_weight == pxn_same_rail_weight
            and fault_pxn_hop_weights == pxn_hop_weights
            and fault_direct_hop_weights == direct_hop_weights
            and high_stretch_topologies == "off"
        ):
            label = "default"
        else:
            label_parts = []
            if weight != "default":
                label_parts.append(f"crossrail-switch-switch-w{weight}")
            if direct_weight != "default":
                label_parts.append(f"direct-crossrail-switch-switch-w{direct_weight}")
            if pxn_same_rail_weight != "default":
                label_parts.append(f"pxn-same-rail-switch-switch-w{pxn_same_rail_weight}")
            if pxn_hop_weights != "default":
                label_parts.append(
                    f"pxn-same-rail-hop-{pxn_hop_weights.replace(',', '_')}"
                )
            if direct_hop_weights != "default":
                label_parts.append(
                    f"direct-crossrail-hop-{direct_hop_weights.replace(',', '_')}"
                )
            if fault_weight != weight:
                label_parts.append(f"fault-crossrail-switch-switch-w{fault_weight}")
            if fault_direct_weight != direct_weight:
                label_parts.append(
                    f"fault-direct-crossrail-switch-switch-w{fault_direct_weight}"
                )
            if fault_pxn_same_rail_weight != pxn_same_rail_weight:
                label_parts.append(
                    f"fault-pxn-same-rail-switch-switch-w{fault_pxn_same_rail_weight}"
                )
            if fault_pxn_hop_weights != pxn_hop_weights:
                label_parts.append(
                    f"fault-pxn-same-rail-hop-{fault_pxn_hop_weights.replace(',', '_')}"
                )
            if fault_direct_hop_weights != direct_hop_weights:
                label_parts.append(
                    f"fault-direct-crossrail-hop-{fault_direct_hop_weights.replace(',', '_')}"
                )
            if high_stretch_topologies != "off":
                label_parts.append(
                    f"highstretch-{high_stretch_topologies.replace(',', '+')}"
                )
                label_parts.append(f"pathstretch-ge-{high_stretch_threshold}")
                if high_stretch_weight != fault_weight:
                    label_parts.append(f"highstretch-fault-crossrail-w{high_stretch_weight}")
                if high_stretch_direct_weight != fault_direct_weight:
                    label_parts.append(
                        f"highstretch-fault-direct-crossrail-w{high_stretch_direct_weight}"
                    )
                if high_stretch_pxn_same_rail_weight != fault_pxn_same_rail_weight:
                    label_parts.append(
                        f"highstretch-fault-pxn-same-rail-w{high_stretch_pxn_same_rail_weight}"
                    )
                if high_stretch_pxn_hop_weights != fault_pxn_hop_weights:
                    label_parts.append(
                        "highstretch-fault-pxn-same-rail-hop-"
                        f"{high_stretch_pxn_hop_weights.replace(',', '_')}"
                    )
                if high_stretch_direct_hop_weights != fault_direct_hop_weights:
                    label_parts.append(
                        "highstretch-fault-direct-crossrail-hop-"
                        f"{high_stretch_direct_hop_weights.replace(',', '_')}"
                    )
            label = "_".join(label_parts)
    return {
        "flowsim_policy": label,
        "cross_rail_switch_switch_weight": weight,
        "direct_cross_rail_switch_switch_weight": direct_weight,
        "pxn_same_rail_switch_switch_weight": pxn_same_rail_weight,
        "pxn_same_rail_switch_switch_hop_weights": pxn_hop_weights,
        "direct_cross_rail_switch_switch_hop_weights": direct_hop_weights,
        "fault_cross_rail_switch_switch_weight": fault_weight,
        "fault_direct_cross_rail_switch_switch_weight": fault_direct_weight,
        "fault_pxn_same_rail_switch_switch_weight": fault_pxn_same_rail_weight,
        "fault_pxn_same_rail_switch_switch_hop_weights": fault_pxn_hop_weights,
        "fault_direct_cross_rail_switch_switch_hop_weights": fault_direct_hop_weights,
        "high_stretch_fault_topologies": high_stretch_topologies,
        "high_stretch_threshold": high_stretch_threshold,
        "high_stretch_fault_cross_rail_switch_switch_weight": high_stretch_weight,
        "high_stretch_fault_direct_cross_rail_switch_switch_weight": (
            high_stretch_direct_weight
        ),
        "high_stretch_fault_pxn_same_rail_switch_switch_weight": (
            high_stretch_pxn_same_rail_weight
        ),
        "high_stretch_fault_pxn_same_rail_switch_switch_hop_weights": (
            high_stretch_pxn_hop_weights
        ),
        "high_stretch_fault_direct_cross_rail_switch_switch_hop_weights": (
            high_stretch_direct_hop_weights
        ),
        "as_pxn_enable": env.get("AS_PXN_ENABLE", ""),
        "as_pxn_policy": env.get("AS_PXN_POLICY", ""),
        "flowsim_pxn_timing": env.get(
            "FLOWSIM_PXN_TIMING", env.get("AS_PXN_TIMING", "serial")
        ),
        "flowsim_pxn_local_pipeline_delay_ns": env.get(
            "FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS",
            env.get("AS_PXN_LOCAL_PIPELINE_DELAY_NS", ""),
        ),
    }


def run(args: argparse.Namespace) -> int:
    topology_map = topology_map_for_scale(args.scale)
    topo_dir = args.topology_dir or default_topology_dir(args.root, args.scale)
    out_root = args.output_dir
    generated_root = out_root / "generated_topologies"
    runs_root = out_root / "runs"
    env = build_env(args)
    fault_env = build_fault_env(args, env)
    high_stretch_fault_env = build_high_stretch_fault_env(args, fault_env)
    metadata = policy_metadata(args, env, fault_env, high_stretch_fault_env)
    rows: List[Dict[str, object]] = []
    baselines: List[Dict[str, object]] = []
    tasks: List[Dict[str, object]] = []
    raw_csv = out_root / "random_link_failure_raw.csv"
    baseline_csv = out_root / "baseline_jct.csv"
    summary_csv = out_root / "random_link_failure_summary.csv"
    if args.resume:
        rows = dedupe_rows(read_csv(raw_csv))
        baselines = read_csv(baseline_csv)
    completed = {
        task_key(row)
        for row in rows
        if str(row.get("status", "")) in {"success", "disconnected", "baseline_failed"}
    }
    completed_basic = {
        (
            row.get("topology", ""),
            rate_label(float(row.get("link_failure_probability", 0.0))),
            str(row.get("seed", "")),
        )
        for row in rows
        if str(row.get("status", "")) in {"success", "disconnected", "baseline_failed"}
        and "link_failure_probability" in row
        and "seed" in row
    }

    selected = args.topologies or list(topology_map.keys())
    seed_values = [args.seed_base + i for i in range(args.samples)]
    print(
        f"[POLICY] {metadata['flowsim_policy']} "
        f"cross_rail_switch_switch_weight={metadata['cross_rail_switch_switch_weight']} "
        f"direct_cross_rail_switch_switch_weight={metadata['direct_cross_rail_switch_switch_weight']} "
        f"pxn_same_rail_switch_switch_weight={metadata['pxn_same_rail_switch_switch_weight']} "
        f"pxn_same_rail_hop_weights={metadata['pxn_same_rail_switch_switch_hop_weights']} "
        f"direct_cross_rail_hop_weights={metadata['direct_cross_rail_switch_switch_hop_weights']} "
        f"fault_cross_rail_switch_switch_weight={metadata['fault_cross_rail_switch_switch_weight']} "
        f"fault_direct_cross_rail_switch_switch_weight={metadata['fault_direct_cross_rail_switch_switch_weight']} "
        f"fault_pxn_same_rail_switch_switch_weight={metadata['fault_pxn_same_rail_switch_switch_weight']} "
        f"fault_pxn_same_rail_hop_weights={metadata['fault_pxn_same_rail_switch_switch_hop_weights']} "
        f"fault_direct_cross_rail_hop_weights={metadata['fault_direct_cross_rail_switch_switch_hop_weights']} "
        f"high_stretch_topologies={metadata['high_stretch_fault_topologies']} "
        f"high_stretch_threshold={metadata['high_stretch_threshold']} "
        f"high_stretch_fault_direct_weight={metadata['high_stretch_fault_direct_cross_rail_switch_switch_weight']} "
        f"high_stretch_fault_pxn_hop_weights={metadata['high_stretch_fault_pxn_same_rail_switch_switch_hop_weights']} "
        f"high_stretch_fault_direct_hop_weights={metadata['high_stretch_fault_direct_cross_rail_switch_switch_hop_weights']} "
        f"pxn={metadata['as_pxn_enable']} pxn_policy={metadata['as_pxn_policy']} "
        f"pxn_timing={metadata['flowsim_pxn_timing']} "
        f"pxn_local_pipeline_delay_ns={metadata['flowsim_pxn_local_pipeline_delay_ns']}",
        flush=True,
    )

    for topo_name in selected:
        topo_file = topology_map[topo_name]
        topo_path = topo_dir / topo_file
        topology = FT.parse_topology(topo_path)
        if args.switch_throughput_limit_gbps is not None:
            throughput_summary = read_switch_summary(
                topology, args.switch_throughput_limit_gbps
            )
            over_limit_count = int(throughput_summary["over_limit_count"])
            if over_limit_count:
                raise RuntimeError(
                    f"{topo_name} exceeds switch throughput limit "
                    f"{args.switch_throughput_limit_gbps:g}Gbps: "
                    f"{over_limit_count} switches over limit, "
                    f"max={throughput_summary['max_gbps']}Gbps, topology={topo_path}"
                )
        baseline_lengths = FT.shortest_path_lengths(topology, set())
        eligible_links = FT.eligible_inter_server_links(topology)
        topology_writer = ThreadPoolExecutor(max_workers=max(1, args.jobs))

        baseline_dir = runs_root / topo_name / "baseline"
        print(f"[BASELINE] {topo_name} -> {baseline_dir}", flush=True)
        normal_jct = run_flowsim(
            flowsim_bin=args.flowsim_bin,
            workload=args.workload,
            topology=topo_path,
            output_dir=baseline_dir,
            threads=args.threads,
            env=env,
            resume=args.resume,
            timeout_seconds=args.run_timeout_seconds,
        )
        baselines.append(
            {
                "topology": topo_name,
                "scale": args.scale,
                "topology_file": str(topo_path),
                "normal_jct": normal_jct if normal_jct is not None else "missing",
                "eligible_inter_server_links": len(eligible_links),
                "run_dir": str(baseline_dir),
                **metadata,
            }
        )

        for rate in args.rates:
            for seed in seed_values:
                basic_key = (topo_name, rate_label(rate), str(seed))
                if args.resume and not args.high_stretch_fault_topologies:
                    if basic_key in completed_basic:
                        continue
                failed_keys = FT.sample_failed_links(topology, rate, seed)
                metrics = FT.topology_metrics(topology, failed_keys, baseline_lengths, "all-to-all")
                failed_topology = (
                    generated_root
                    / topo_name
                    / rate_label(rate)
                    / f"seed{seed}.topo"
                )
                topology_writer.submit(FT.write_topology, topology, failed_keys, failed_topology)

                run_dir = runs_root / topo_name / rate_label(rate) / f"seed{seed}"
                selected_fault_env, fault_env_class = select_fault_env(
                    args,
                    topology=topo_name,
                    metrics=metrics,
                    fault_env=fault_env,
                    high_stretch_fault_env=high_stretch_fault_env,
                )
                row: Dict[str, object] = {
                    "topology": topo_name,
                    "scale": args.scale,
                    "workload": args.workload_label,
                    **metadata,
                    "fault_env_class": fault_env_class,
                    "link_failure_probability": rate,
                    "seed": seed,
                    "status": "queued",
                    "normal_jct": normal_jct if normal_jct is not None else "missing",
                    "failed_jct": "missing",
                    "degradation": "missing",
                    "failed_topology": str(failed_topology),
                    "run_dir": str(run_dir),
                    "failed_links": " ".join(f"{a}-{b}" for a, b in sorted(failed_keys)),
                }
                row.update(metrics)
                key = task_key(row)
                if args.resume and key in completed:
                    continue
                connectivity = numeric(metrics.get("connectivity_ratio"))
                if normal_jct is None:
                    row["status"] = "baseline_failed"
                    rows.append(row)
                    completed.add(key)
                    completed_basic.add(basic_key)
                elif connectivity is not None and connectivity < 1.0:
                    row["status"] = "disconnected"
                    rows.append(row)
                    completed.add(key)
                    completed_basic.add(basic_key)
                else:
                    existing_failed_jct = (
                        read_jct(run_dir / "EndToEnd.csv") if args.resume else None
                    )
                    if existing_failed_jct is not None:
                        row["status"] = "success"
                        row["failed_jct"] = existing_failed_jct
                        row["degradation"] = (
                            (existing_failed_jct - normal_jct) / normal_jct
                            if normal_jct
                            else "missing"
                        )
                        rows.append(row)
                        completed.add(task_key(row))
                        completed_basic.add(basic_key)
                        continue
                    tasks.append(
                        {
                            "flowsim_bin": args.flowsim_bin,
                            "workload": args.workload,
                            "failed_topology_path": failed_topology,
                            "run_dir_path": run_dir,
                            "threads": args.threads,
                            "env": selected_fault_env,
                            "resume": args.resume,
                            "timeout_seconds": args.run_timeout_seconds,
                            "normal_jct": normal_jct,
                            "row": row,
                        }
                    )

        topology_writer.shutdown(wait=True)

    print(
        f"[SWEEP] {len(tasks)} runnable samples, {len(rows)} pre-classified samples, "
        f"jobs={args.jobs}, threads_per_job={args.threads}",
        flush=True,
    )
    rows = dedupe_rows(rows)
    baselines = dedupe_baselines(baselines)
    write_csv(baseline_csv, baselines)
    write_csv(raw_csv, rows)
    write_csv(summary_csv, summarize(rows))
    if args.jobs == 1:
        for idx, task in enumerate(tasks, start=1):
            row = task["row"]
            print(
                f"[RUN {idx}/{len(tasks)}] {row['topology']} rate={row['link_failure_probability']:g} "
                f"seed={row['seed']} failed_links={row['num_failed_links']} "
                f"fault_env={row.get('fault_env_class', 'fault_default')}",
                flush=True,
            )
            rows.append(run_fault_task(task))
            rows = dedupe_rows(rows)
            write_csv(raw_csv, rows)
            write_csv(summary_csv, summarize(rows))
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(run_fault_task, task): task for task in tasks}
            for idx, future in enumerate(as_completed(futures), start=1):
                task = futures[future]
                row = task["row"]
                try:
                    result = future.result()
                except Exception as exc:
                    result = dict(row)
                    result["status"] = "error"
                    result["error"] = str(exc)
                rows.append(result)
                rows = dedupe_rows(rows)
                write_csv(raw_csv, rows)
                write_csv(summary_csv, summarize(rows))
                print(
                    f"[DONE {idx}/{len(tasks)}] {row['topology']} "
                    f"rate={row['link_failure_probability']:g} seed={row['seed']} "
                    f"fault_env={row.get('fault_env_class', 'fault_default')} "
                    f"status={result['status']}",
                    flush=True,
                )

    rows = dedupe_rows(rows)
    baselines = dedupe_baselines(baselines)
    write_csv(baseline_csv, baselines)
    write_csv(raw_csv, rows)
    write_csv(summary_csv, summarize(rows))
    print(f"[DONE] wrote {len(rows)} rows to {out_root}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch FlowSim all-to-all random-link fault sweep"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--scale",
        choices=sorted(TOPOLOGY_SETS.keys()),
        default="256",
        help="topology set to run; 1024_12p8T uses the 12.8Tbps-constrained topologies",
    )
    parser.add_argument(
        "--topology-dir",
        type=Path,
        default=None,
        help="directory containing topology files; default depends on --scale",
    )
    parser.add_argument(
        "--workload",
        type=Path,
        default=None,
        help="workload file; default depends on --scale",
    )
    parser.add_argument(
        "--workload-label",
        default=None,
        help="label written to output CSVs; default is derived from --scale and workload file",
    )
    parser.add_argument(
        "--flowsim-bin",
        type=Path,
        default=Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="output directory; default depends on --scale",
    )
    parser.add_argument(
        "--rates",
        type=parse_rates,
        default=default_rates(),
        help="comma-separated link failure probabilities",
    )
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--run-timeout-seconds",
        type=int,
        default=None,
        help="optional per-FlowSim-run timeout; timed out runs are recorded as failed",
    )
    parser.add_argument(
        "--switch-throughput-limit-gbps",
        type=float,
        default=None,
        help=(
            "optional preflight limit for ordinary switch incident port bandwidth; "
            "use 12800 for the 12.8Tbps topology set"
        ),
    )
    parser.add_argument(
        "--flowsim-pxn-timing",
        choices=[
            "serial",
            "overlap",
            "local_pipeline",
            "local-pipeline",
            "localpipeline",
            "staggered",
            "staggered_pipeline",
            "staggered-pipeline",
        ],
        default=None,
        help=(
            "set FLOWSIM_PXN_TIMING for the sweep; omit to keep the current "
            "environment/default"
        ),
    )
    parser.add_argument(
        "--pxn-local-pipeline-delay-ns",
        type=int,
        default=None,
        help=(
            "set FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS when using local_pipeline timing"
        ),
    )
    parser.add_argument(
        "--cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "set FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT explicitly for this sweep; "
            "omit to keep the current environment/default"
        ),
    )
    parser.add_argument(
        "--direct-cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "set FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT explicitly; "
            "omit to inherit FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT/default"
        ),
    )
    parser.add_argument(
        "--pxn-same-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "set FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT explicitly for this sweep; "
            "omit to keep the current environment/default"
        ),
    )
    parser.add_argument(
        "--pxn-same-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped PXN same-rail weights, e.g. 4=0.4; "
            "sets FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS<N>"
        ),
    )
    parser.add_argument(
        "--direct-cross-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped direct cross-rail weights, e.g. 4=0.25; "
            "sets FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT_HOPS<N>"
        ),
    )
    parser.add_argument(
        "--fault-cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT only for failed-topology runs"
        ),
    )
    parser.add_argument(
        "--fault-direct-cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT only for failed-topology runs"
        ),
    )
    parser.add_argument(
        "--fault-pxn-same-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT only for failed-topology runs"
        ),
    )
    parser.add_argument(
        "--fault-pxn-same-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped PXN same-rail weights only for failed-topology runs"
        ),
    )
    parser.add_argument(
        "--fault-direct-cross-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped direct cross-rail weights only for failed-topology runs"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-topologies",
        nargs="*",
        choices=sorted(TOPOLOGIES.keys()),
        default=None,
        help=(
            "topologies where failed runs may use the high-stretch fault override; "
            "requires --high-stretch-threshold"
        ),
    )
    parser.add_argument(
        "--high-stretch-threshold",
        type=float,
        default=None,
        help=(
            "use the high-stretch fault override when topology path_stretch is >= this value"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT for selected high-stretch failed runs"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-direct-cross-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT for selected high-stretch failed runs"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-pxn-same-rail-switch-switch-weight",
        type=float,
        default=None,
        help=(
            "override FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT for selected high-stretch failed runs"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-pxn-same-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped PXN same-rail weights for selected high-stretch failed runs"
        ),
    )
    parser.add_argument(
        "--high-stretch-fault-direct-cross-rail-switch-switch-hop-weights",
        type=parse_hop_weights,
        default=None,
        help=(
            "comma-separated hop-scoped direct cross-rail weights for selected high-stretch failed runs"
        ),
    )
    parser.add_argument(
        "--policy-label",
        default=None,
        help="label written to output CSVs for the selected FlowSim policy",
    )
    parser.add_argument(
        "--topologies",
        nargs="*",
        choices=sorted(TOPOLOGIES.keys()),
        help="subset of topologies to run; default is all six",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse existing EndToEnd.csv files and skip successful raw rows",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.workload is None:
        args.workload = default_workload(args.root, args.scale)
    if args.output_dir is None:
        args.output_dir = default_output_dir(args.root, args.scale)
    if args.workload_label is None:
        args.workload_label = f"all-to-all-global-{args.scale}-{args.workload.stem}"
    if args.samples < 1:
        raise SystemExit("--samples must be >= 1")
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.run_timeout_seconds is not None and args.run_timeout_seconds < 1:
        raise SystemExit("--run-timeout-seconds must be >= 1")
    if (
        args.switch_throughput_limit_gbps is not None
        and args.switch_throughput_limit_gbps <= 0.0
    ):
        raise SystemExit("--switch-throughput-limit-gbps must be > 0")
    if (
        args.cross_rail_switch_switch_weight is not None
        and args.cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--cross-rail-switch-switch-weight must be > 0")
    if (
        args.direct_cross_rail_switch_switch_weight is not None
        and args.direct_cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--direct-cross-rail-switch-switch-weight must be > 0")
    if (
        args.pxn_same_rail_switch_switch_weight is not None
        and args.pxn_same_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--pxn-same-rail-switch-switch-weight must be > 0")
    if (
        args.pxn_local_pipeline_delay_ns is not None
        and args.pxn_local_pipeline_delay_ns < 0
    ):
        raise SystemExit("--pxn-local-pipeline-delay-ns must be >= 0")
    if (
        args.fault_cross_rail_switch_switch_weight is not None
        and args.fault_cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--fault-cross-rail-switch-switch-weight must be > 0")
    if (
        args.fault_direct_cross_rail_switch_switch_weight is not None
        and args.fault_direct_cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--fault-direct-cross-rail-switch-switch-weight must be > 0")
    if (
        args.fault_pxn_same_rail_switch_switch_weight is not None
        and args.fault_pxn_same_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit("--fault-pxn-same-rail-switch-switch-weight must be > 0")
    if bool(args.high_stretch_fault_topologies) != (
        args.high_stretch_threshold is not None
    ):
        raise SystemExit(
            "--high-stretch-fault-topologies and --high-stretch-threshold must be used together"
        )
    if args.high_stretch_threshold is not None and args.high_stretch_threshold <= 0.0:
        raise SystemExit("--high-stretch-threshold must be > 0")
    if (
        args.high_stretch_fault_cross_rail_switch_switch_weight is not None
        and args.high_stretch_fault_cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit(
            "--high-stretch-fault-cross-rail-switch-switch-weight must be > 0"
        )
    if (
        args.high_stretch_fault_direct_cross_rail_switch_switch_weight is not None
        and args.high_stretch_fault_direct_cross_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit(
            "--high-stretch-fault-direct-cross-rail-switch-switch-weight must be > 0"
        )
    if (
        args.high_stretch_fault_pxn_same_rail_switch_switch_weight is not None
        and args.high_stretch_fault_pxn_same_rail_switch_switch_weight <= 0.0
    ):
        raise SystemExit(
            "--high-stretch-fault-pxn-same-rail-switch-switch-weight must be > 0"
        )
    if not args.workload.exists():
        raise SystemExit(f"workload not found: {args.workload}")
    if not args.flowsim_bin.exists() or not os.access(args.flowsim_bin, os.X_OK):
        raise SystemExit(f"FlowSim binary not executable: {args.flowsim_bin}")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
