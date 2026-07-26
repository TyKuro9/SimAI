#!/usr/bin/env python3
"""Run 256-GPU NS3 ECMP, QP spray, and dynamic flowlet comparisons."""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
GPUS_PER_SERVER = 8

TOPOLOGIES = {
    "Zcube": ROOT / "mytopo" / "Zcube_n16_k2_256g_8gps_200Gbps_H100",
    "DeepSeek": ROOT / "mytopo" / "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
    "HPN": ROOT / "mytopo" / "AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100",
    "ROFT": ROOT / "mytopo" / "ROFT_256g_8gps_p16a0.5_400Gbps_H100",
    "Meta": ROOT / "mytopo" / "Meta_Topo_256g_8gps_400Gbps_A100",
    "RO": ROOT / "mytopo" / "RailOnly_256g_8gps_p16a0.5_400Gbps_H100",
}

DEFAULT_WORKLOAD = (
    ROOT / "my_workloads" / "synthetic_alltoall_global_world_size256_1MiB.txt"
)
DEFAULT_OUTPUT = ROOT / "experiments" / "ns3_spray" / "ecmp_spray_256_zcube_roft"
DEFAULT_BINARY = ROOT / "bin" / "SimAI_simulator"

CONFIG_TEMPLATE = """ENABLE_QCN 1
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 9000

FLOW_FILE {flow_file}
TRACE_FILE {trace_file}
TRACE_OUTPUT_FILE /dev/null
FCT_OUTPUT_FILE {fct_output_file}
PFC_OUTPUT_FILE /dev/null

SIMULATOR_STOP_TIME 40000000000000.00

CC_MODE 1
ALPHA_RESUME_INTERVAL 1
RATE_DECREASE_INTERVAL 4
CLAMP_TARGET_RATE 0
RP_TIMER 900
EWMA_GAIN 0.00390625
FAST_RECOVERY_TIMES 1
RATE_AI 50Mb/s
RATE_HAI 100Mb/s
MIN_RATE 100Mb/s
DCTCP_RATE_AI 1000Mb/s

ERROR_RATE_PER_LINK 0.0000
L2_CHUNK_SIZE 4000
L2_ACK_INTERVAL 1
L2_BACK_TO_ZERO 0

HAS_WIN 1
GLOBAL_T 0
VAR_WIN 1
FAST_REACT 1
U_TARGET 0.95
MI_THRESH 0
INT_MULTI 1
MULTI_RATE 0
SAMPLE_FEEDBACK 0
PINT_LOG_BASE 1.05
PINT_PROB 1.0

RATE_BOUND 1
ACK_HIGH_PRIO 0
LINK_DOWN 0 0 0
ENABLE_TRACE 0

KMAX_MAP 6 25000000000 400 50000000000 800 100000000000 1600 200000000000 1200 400000000000 3200 1600000000000 2400
KMIN_MAP 6 25000000000 100 50000000000 200 100000000000 400 200000000000 300 400000000000 800 1600000000000 600
PMAX_MAP 6 25000000000 0.2 50000000000 0.2 100000000000 0.2 200000000000 0.8 400000000000 0.2 1600000000000 0.2

BUFFER_SIZE {buffer_size_mib}
"""

SUMMARY_RE = re.compile(
    r"\[NS3 ROUTING SUMMARY\] policy=(?P<policy>\w+) width=(?P<width>\d+) "
    r"fabric_legs=(?P<fabric_legs>\d+) sprayed_legs=(?P<sprayed_legs>\d+) "
    r"subflows=(?P<subflows>\d+) fabric_bytes=(?P<fabric_bytes>\d+) "
    r"pending_contexts=(?P<pending_contexts>\d+) "
    r"pending_send_callbacks=(?P<pending_send_callbacks>\d+) "
    r"pending_recv_callbacks=(?P<pending_recv_callbacks>\d+)"
)

FLOWLET_SUMMARY_RE = re.compile(
    r"\[NS3 (?:FLOWLET|PACKET DLB) SUMMARY\] decisions=(?P<flowlet_decisions>\d+) "
    r"switches=(?P<flowlet_switches>\d+) "
    r"gap_triggers=(?P<flowlet_gap_triggers>\d+) "
    r"byte_triggers=(?P<flowlet_byte_triggers>\d+) "
    r"link_triggers=(?P<flowlet_link_triggers>\d+) "
    r"gap_ns=(?P<flowlet_gap_ns>\d+) "
    r"max_bytes=(?P<flowlet_max_bytes>\d+) "
    r"hysteresis_ns=(?P<flowlet_hysteresis_ns>\d+)"
    r"(?: source_decisions=(?P<source_flowlet_decisions>\d+)"
    r" source_switches=(?P<source_flowlet_switches>\d+))?"
)

PATH_SUMMARY_RE = re.compile(r"\[NS3 PATH SUMMARY\](?P<fields>[^\r\n]+)")


def write_config(
    run_dir: Path,
    fct_output_file: Optional[Path] = None,
    buffer_size_mib: int = 32,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale_name in (
        "EndToEnd.csv",
        "fct.txt",
        "fct_summary.csv",
        "link_load.csv",
        "path_dispersion.csv",
        "route_choices.csv",
        "route_choices.csv.tmp",
        "run.log",
        "send.txt",
        "spray_subflows.csv",
        "stripe_metrics.csv",
        "stripe_flow_metrics.csv",
    ):
        stale_path = run_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()
    flow_file = run_dir / "flow.txt"
    trace_file = run_dir / "trace.txt"
    flow_file.write_text("0\n")
    trace_file.write_text("0\n")
    config = run_dir / "ns3.conf"
    config.write_text(
        CONFIG_TEMPLATE.format(
            flow_file=flow_file,
            trace_file=trace_file,
            fct_output_file=fct_output_file or run_dir / "fct.txt",
            buffer_size_mib=buffer_size_mib,
        )
    )
    return config


def read_jct(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    for line in reversed(path.read_text(errors="replace").splitlines()):
        for field in reversed([field.strip() for field in line.split(",")]):
            try:
                return float(field)
            except ValueError:
                continue
    return None


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_summary(log_path: Path) -> dict[str, str]:
    if not log_path.exists():
        return {}
    text = log_path.read_text(errors="replace")
    result: dict[str, str] = {}
    matches = list(SUMMARY_RE.finditer(text))
    if matches:
        result.update(matches[-1].groupdict())
    flowlet_matches = list(FLOWLET_SUMMARY_RE.finditer(text))
    if flowlet_matches:
        result.update(flowlet_matches[-1].groupdict())
    path_matches = list(PATH_SUMMARY_RE.finditer(text))
    if path_matches:
        for key, value in re.findall(
            r"([a-zA-Z0-9_]+)=(\d+)", path_matches[-1].group("fields")
        ):
            result[key] = value
    return result


def parse_fct(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 14:
            continue
        rows.append(
            {
                "sip_hex": fields[0].lower(),
                "dip_hex": fields[1].lower(),
                "sport": int(fields[2]),
                "dport": int(fields[3]),
                "bytes": int(fields[4]),
                "start_ns": int(fields[5]),
                "fct_ns": int(fields[6]),
                "standalone_fct_ns": int(fields[7]),
                "orig_src": int(fields[8]),
                "orig_dst": int(fields[9]),
                "leg_kind": fields[10],
                "leg_index": int(fields[11]),
                "leg_count": int(fields[12]),
                "flow_id": int(fields[13]),
            }
        )
    return rows


def qp_key(row: dict[str, object]) -> tuple[str, str, int, int]:
    return (
        str(row["sip_hex"]).lower(),
        str(row["dip_hex"]).lower(),
        int(row["sport"]),
        int(row["dport"]),
    )


def logical_key(row: dict[str, object]) -> tuple[int, int, int]:
    return (int(row["flow_id"]), int(row["orig_src"]), int(row["orig_dst"]))


def parse_route_choices(
    path: Path,
) -> dict[tuple[str, str, int, int], list[dict[str, object]]]:
    by_qp: dict[tuple[str, str, int, int], list[dict[str, object]]] = defaultdict(list)
    if not path.exists():
        return by_qp
    with path.open(newline="") as input_file:
        for row in csv.DictReader(input_file):
            key = (
                row["sip_hex"].lower(),
                row["dip_hex"].lower(),
                int(row["sport"]),
                int(row["dport"]),
            )
            by_qp[key].append(
                {
                    "sw_id": int(row["sw_id"]),
                    "node_type": int(row.get("node_type", "1") or 1),
                    "in_dev": int(row["in_dev"]),
                    "out_dev": int(row["out_dev"]),
                    "next_hop_count": int(row["next_hop_count"]),
                    "packets": int(row["packets"]),
                    "bytes": int(row["bytes"]),
                    "routing_mode": row.get("routing_mode", "ecmp_hash"),
                    "bind_candidate_count": int(
                        row.get("bind_candidate_count", "0") or 0
                    ),
                    "bind_queue_bytes": int(row.get("bind_queue_bytes", "0") or 0),
                    "bind_tx_bytes": int(row.get("bind_tx_bytes", "0") or 0),
                    "bind_prior_port_qps": int(
                        row.get("bind_prior_port_qps", "0") or 0
                    ),
                    "bind_path_score_ns": int(
                        row.get("bind_path_score_ns", "0") or 0
                    ),
                    "bind_path_queue_delay_ns": int(
                        row.get("bind_path_queue_delay_ns", "0") or 0
                    ),
                    "bind_path_propagation_ns": int(
                        row.get("bind_path_propagation_ns", "0") or 0
                    ),
                    "bind_path_reserved_bytes": int(
                        row.get("bind_path_reserved_bytes", "0") or 0
                    ),
                    "bind_path_hops": int(
                        row.get("bind_path_hops", "0") or 0
                    ),
                    "flowlet_decisions": int(
                        row.get("flowlet_decisions", "0") or 0
                    ),
                    "flowlet_switches": int(
                        row.get("flowlet_switches", "0") or 0
                    ),
                    "flowlet_gap_triggers": int(
                        row.get("flowlet_gap_triggers", "0") or 0
                    ),
                    "flowlet_byte_triggers": int(
                        row.get("flowlet_byte_triggers", "0") or 0
                    ),
                    "flowlet_link_triggers": int(
                        row.get("flowlet_link_triggers", "0") or 0
                    ),
                    "flowlet_last_id": int(
                        row.get("flowlet_last_id", "0") or 0
                    ),
                    "flowlet_selected_score_ns": int(
                        row.get("flowlet_selected_score_ns", "0") or 0
                    ),
                    "flowlet_previous_score_ns": int(
                        row.get("flowlet_previous_score_ns", "0") or 0
                    ),
                }
            )
    return by_qp


def load_subflow_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    with path.open(newline="") as input_file:
        for row in csv.DictReader(input_file):
            converted: dict[str, object] = dict(row)
            for key in (
                "orig_src",
                "orig_dst",
                "physical_src",
                "physical_dst",
                "flow_id",
                "tag_id",
                "channel_id",
                "leg_index",
                "leg_count",
                "stripe_index",
                "stripe_count",
                "sport",
                "dport",
                "bytes",
            ):
                converted[key] = int(converted[key])
            converted["sip_hex"] = str(converted["sip_hex"]).lower()
            converted["dip_hex"] = str(converted["dip_hex"]).lower()
            out.append(converted)
    return out


def summarize_run(run_dir: Path) -> dict[str, object]:
    fct_rows = parse_fct(run_dir / "fct.txt")
    subflow_rows = load_subflow_rows(run_dir / "spray_subflows.csv")
    routes_by_qp = parse_route_choices(run_dir / "route_choices.csv")

    qp_fct = {qp_key(row): int(row["fct_ns"]) for row in fct_rows}
    logical_fct_groups: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for row in fct_rows:
        logical_fct_groups[logical_key(row)].append(int(row["fct_ns"]))
    logical_fcts = [max(values) for values in logical_fct_groups.values()]

    dispersion_rows: list[dict[str, object]] = []
    by_logical: dict[tuple[int, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in subflow_rows:
        by_logical[logical_key(row)].append(row)

    for key, rows in by_logical.items():
        path_signatures = set()
        routed_qps = 0
        largest_local_choice_set = 1
        for row in rows:
            route_rows = routes_by_qp.get(qp_key(row), [])
            if route_rows:
                routed_qps += 1
                largest_local_choice_set = max(
                    largest_local_choice_set,
                    *(int(route["next_hop_count"]) for route in route_rows),
                )
                signature = tuple(
                    sorted(
                        (r["sw_id"], r["in_dev"], r["out_dev"])
                        for r in route_rows
                    )
                )
                path_signatures.add(signature)
        subflows = len(rows)
        unique_paths = len(path_signatures)
        target_unique_paths = min(routed_qps, largest_local_choice_set)
        is_fabric = int(
            any(
                int(row["physical_src"]) // GPUS_PER_SERVER
                != int(row["physical_dst"]) // GPUS_PER_SERVER
                for row in rows
            )
        )
        dispersion_rows.append(
            {
                "flow_id": key[0],
                "orig_src": key[1],
                "orig_dst": key[2],
                "is_fabric": is_fabric,
                "subflows": subflows,
                "routed_subflows": routed_qps,
                "unique_paths": unique_paths,
                "path_spread": unique_paths / routed_qps if routed_qps else "",
                "hash_collision": int(unique_paths < routed_qps) if routed_qps else 0,
                "largest_local_choice_set": largest_local_choice_set,
                "target_unique_paths": target_unique_paths,
                "path_coverage": unique_paths / target_unique_paths
                if target_unique_paths
                else "",
                "avoidable_collision": int(unique_paths < target_unique_paths)
                if target_unique_paths
                else 0,
                "logical_fct_ns": max(
                    (qp_fct.get(qp_key(row), 0) for row in rows),
                    default=0,
                ),
            }
        )

    link_bytes: dict[tuple[int, int], int] = defaultdict(int)
    for route_rows in routes_by_qp.values():
        for row in route_rows:
            link_bytes[(row["sw_id"], row["out_dev"])] += row["bytes"]
    link_rows = [
        {"sw_id": sw, "out_dev": out, "bytes": bytes_value}
        for (sw, out), bytes_value in sorted(link_bytes.items())
    ]

    write_csv(run_dir / "path_dispersion.csv", dispersion_rows)
    write_csv(run_dir / "link_load.csv", link_rows)

    fabric_dispersion_rows = [row for row in dispersion_rows if row["is_fabric"]]
    spreads = [
        float(row["path_spread"])
        for row in fabric_dispersion_rows
        if row["path_spread"] != ""
    ]
    coverages = [
        float(row["path_coverage"])
        for row in fabric_dispersion_rows
        if row["path_coverage"] != ""
    ]
    unique_paths = [float(row["unique_paths"]) for row in fabric_dispersion_rows]
    link_values = [float(row["bytes"]) for row in link_rows]
    physical_fcts = [float(row["fct_ns"]) for row in fct_rows]
    dynamic_bindings = [
        row
        for route_rows in routes_by_qp.values()
        for row in route_rows
        if row.get("routing_mode") in {
            "dynamic_qp",
            "path_aware_qp",
            "dynamic_flowlet",
            "dual_table_flowlet",
            "packet_dlb",
        }
    ]
    path_aware_bindings = [
        row
        for row in dynamic_bindings
        if row.get("routing_mode") in {"path_aware_qp", "dual_table_flowlet"}
    ]
    dynamic_bind_queue_bytes = [
        float(row["bind_queue_bytes"]) for row in dynamic_bindings
    ]
    path_scores = [float(row["bind_path_score_ns"]) for row in path_aware_bindings]
    path_queue_delays = [
        float(row["bind_path_queue_delay_ns"]) for row in path_aware_bindings
    ]
    path_reserved_bytes = [
        float(row["bind_path_reserved_bytes"]) for row in path_aware_bindings
    ]
    path_hops = [float(row["bind_path_hops"]) for row in path_aware_bindings]
    flowlet_bindings: dict[tuple[object, ...], dict[str, object]] = {}
    for qp, route_rows in routes_by_qp.items():
        for route in route_rows:
            if route.get("routing_mode") in {
                "dynamic_flowlet",
                "dual_table_flowlet",
                "packet_dlb",
            }:
                flowlet_bindings[(*qp, route["sw_id"])] = route
    flowlet_binding_rows = list(flowlet_bindings.values())

    fct_summary = {
        "physical_qps": len(fct_rows),
        "logical_flows": len(logical_fcts),
        "physical_fct_p50_ns": percentile(physical_fcts, 0.50),
        "physical_fct_p95_ns": percentile(physical_fcts, 0.95),
        "physical_fct_p99_ns": percentile(physical_fcts, 0.99),
        "logical_fct_p50_ns": percentile(logical_fcts, 0.50),
        "logical_fct_p95_ns": percentile(logical_fcts, 0.95),
        "logical_fct_p99_ns": percentile(logical_fcts, 0.99),
        "logical_fct_max_ns": max(logical_fcts) if logical_fcts else None,
    }
    write_csv(run_dir / "fct_summary.csv", [fct_summary])

    link_mean = statistics.mean(link_values) if link_values else None
    link_stdev = statistics.pstdev(link_values) if len(link_values) > 1 else 0.0
    return {
        **fct_summary,
        "subflow_records": len(subflow_rows),
        "route_qps": len(routes_by_qp),
        "route_rows": sum(len(rows) for rows in routes_by_qp.values()),
        "fabric_logical_flows": len(fabric_dispersion_rows),
        "mean_unique_paths_per_flow": statistics.mean(unique_paths)
        if unique_paths
        else None,
        "mean_path_spread": statistics.mean(spreads) if spreads else None,
        "mean_path_coverage": statistics.mean(coverages) if coverages else None,
        "hash_collision_ratio": statistics.mean(
            [float(row["hash_collision"]) for row in fabric_dispersion_rows]
        )
        if fabric_dispersion_rows
        else None,
        "avoidable_collision_ratio": statistics.mean(
            [float(row["avoidable_collision"]) for row in fabric_dispersion_rows]
        )
        if fabric_dispersion_rows
        else None,
        "dynamic_qp_bindings": len(dynamic_bindings),
        "dynamic_bind_queue_p50": percentile(dynamic_bind_queue_bytes, 0.50),
        "dynamic_bind_queue_p95": percentile(dynamic_bind_queue_bytes, 0.95),
        "dynamic_bind_queue_max": max(dynamic_bind_queue_bytes)
        if dynamic_bind_queue_bytes
        else None,
        "dynamic_bind_zero_queue_ratio": statistics.mean(
            [float(value == 0) for value in dynamic_bind_queue_bytes]
        )
        if dynamic_bind_queue_bytes
        else None,
        "path_aware_qp_bindings": len(path_aware_bindings),
        "path_score_p50_ns": percentile(path_scores, 0.50),
        "path_score_p95_ns": percentile(path_scores, 0.95),
        "path_queue_delay_p95_ns": percentile(path_queue_delays, 0.95),
        "path_reserved_bytes_p95": percentile(path_reserved_bytes, 0.95),
        "path_hops_mean": statistics.mean(path_hops) if path_hops else None,
        "flowlet_binding_count": len(flowlet_binding_rows),
        "flowlet_route_decisions": sum(
            int(row["flowlet_decisions"]) for row in flowlet_binding_rows
        ),
        "flowlet_route_switches": sum(
            int(row["flowlet_switches"]) for row in flowlet_binding_rows
        ),
        "link_count": len(link_values),
        "link_bytes_mean": link_mean,
        "link_bytes_p95": percentile(link_values, 0.95),
        "link_bytes_max": max(link_values) if link_values else None,
        "link_max_mean_ratio": max(link_values) / link_mean
        if link_values and link_mean
        else None,
        "link_bytes_cov": link_stdev / link_mean
        if link_values and link_mean
        else None,
    }


def run_one(args: argparse.Namespace, topology_name: str, policy: str) -> dict[str, object]:
    jct_only = bool(getattr(args, "jct_only", False))
    fct_only = bool(getattr(args, "fct_only", False))
    no_fct_output = bool(getattr(args, "no_fct_output", False))
    run_dir = args.output_dir / topology_name / policy
    config = write_config(
        run_dir,
        Path("/dev/null") if jct_only or no_fct_output else None,
        args.buffer_size_mib,
    )
    if jct_only or fct_only:
        (run_dir / "send.txt").symlink_to("/dev/null")
    route_choice_file = run_dir / "route_choices.csv"
    env = os.environ.copy()
    env.update(
        {
            "AS_SEND_LAT": str(args.send_latency),
            "AS_NVLS_ENABLE": "0",
            "AS_PXN_ENABLE": "1" if args.pxn_policy != "off" else "0",
            "AS_PXN_POLICY": args.pxn_policy,
            "AS_NS3_ROUTING_POLICY": policy,
            "AS_NS3_SPRAY_WIDTH": str(args.spray_width),
            "AS_NS3_DYNAMIC_CHUNKS": str(
                getattr(args, "dynamic_chunks", 8)
            ),
            "AS_NS3_FLOWLET_GAP_NS": str(args.flowlet_gap_ns),
            "AS_NS3_FLOWLET_BYTES": str(args.flowlet_bytes),
            "AS_NS3_FLOWLET_HYSTERESIS_NS": str(args.flowlet_hysteresis_ns),
            "AS_NS3_COMPLETION_LOG": "0" if jct_only else "1",
            "AS_FCT_OUTPUT": "0" if jct_only or no_fct_output else "1",
        }
    )
    env.update(getattr(args, "extra_env", {}))
    for variable in (
        "AS_NS3_SUBFLOW_OUTPUT_FILE",
        "AS_NS3_ROUTE_CHOICE_FILE",
        "AS_NS3_ROUTE_CHOICE_DUMP_INTERVAL_MS",
        "AS_NS3_STRIPE_METRICS_FILE",
    ):
        env.pop(variable, None)
    if not jct_only:
        env["AS_NS3_STRIPE_METRICS_FILE"] = str(
            run_dir / "stripe_metrics.csv"
        )
    if not jct_only and not fct_only:
        env.update(
            {
                "AS_NS3_SUBFLOW_OUTPUT_FILE": str(run_dir / "spray_subflows.csv"),
                "AS_NS3_ROUTE_CHOICE_FILE": str(route_choice_file),
                "AS_NS3_ROUTE_CHOICE_DUMP_INTERVAL_MS": str(
                    args.route_dump_interval_ms
                ),
            }
        )
    command = [
        str(args.binary),
        "-t",
        str(args.threads),
        "-w",
        str(args.workload),
        "-n",
        str(TOPOLOGIES[topology_name]),
        "-c",
        str(config),
        "-o",
        str(run_dir) + "/",
    ]
    started = time.monotonic()
    status = "success"
    return_code: object = 0
    log_path = run_dir / "run.log"
    with log_path.open("w") as log:
        proc = subprocess.Popen(
            command,
            cwd=run_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        saw_jct = False
        jct_seen_at: Optional[float] = None
        route_seen_at: Optional[float] = None
        fct_signature: Optional[tuple[int, int]] = None
        fct_idle_since: Optional[float] = None
        while True:
            now = time.monotonic()
            current_jct = read_jct(run_dir / "EndToEnd.csv")
            if current_jct is not None and not saw_jct:
                saw_jct = True
                jct_seen_at = now
                log.write(f"\n[RUNNER] EndToEnd.csv complete with JCT={current_jct}\n")
                log.flush()
            if (
                jct_only
                and saw_jct
                and jct_seen_at is not None
                and now - jct_seen_at >= args.route_dump_grace_seconds
            ):
                log.write("\n[RUNNER] JCT observed; terminating JCT-only run.\n")
                log.flush()
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                # A completed JCT is the success condition in this mode; the
                # runner deliberately stops NS3 before its optional teardown.
                return_code = 0
                break
            if fct_only and saw_jct:
                fct_path = run_dir / "fct.txt"
                if fct_path.exists() and fct_path.stat().st_size > 0:
                    stat = fct_path.stat()
                    current_signature = (stat.st_size, stat.st_mtime_ns)
                    if current_signature != fct_signature:
                        fct_signature = current_signature
                        fct_idle_since = now
                    elif (
                        fct_idle_since is not None
                        and now - fct_idle_since >= args.fct_idle_grace_seconds
                    ):
                        log.write(
                            "\n[RUNNER] JCT observed and FCT output idle for "
                            f"{args.fct_idle_grace_seconds}s; terminating "
                            "FCT-only run.\n"
                        )
                        log.flush()
                        if proc.poll() is None:
                            proc.terminate()
                            try:
                                proc.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=10)
                        return_code = 0
                        break
            if saw_jct and route_choice_file.exists() and route_choice_file.stat().st_size > 0:
                if route_seen_at is None:
                    route_seen_at = now
                if now - route_seen_at >= args.route_dump_grace_seconds:
                    log.write("\n[RUNNER] route choice dump observed; terminating NS3.\n")
                    log.flush()
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=10)
                    return_code = 0
                    break
            if proc.poll() is not None:
                return_code = proc.returncode
                if return_code != 0 and not saw_jct:
                    status = "failed"
                break
            if now - started > args.timeout:
                status = "timeout"
                return_code = "timeout"
                log.write(f"\n[TIMEOUT] exceeded {args.timeout} seconds\n")
                log.flush()
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                break
            if (
                not jct_only
                and not fct_only
                and saw_jct
                and jct_seen_at is not None
                and now - jct_seen_at
                > max(30, args.route_dump_grace_seconds + 5)
            ):
                log.write("\n[RUNNER] route dump not refreshed after JCT; terminating anyway.\n")
                log.flush()
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                return_code = 0
                break
            time.sleep(1.0)
    wall_seconds = round(time.monotonic() - started, 3)
    jct = read_jct(run_dir / "EndToEnd.csv")
    routing = parse_summary(log_path)
    if status == "success" and jct is None:
        status = "missing_jct"

    analysis = (
        {}
        if jct_only or bool(getattr(args, "skip_analysis", False))
        else summarize_run(run_dir)
    )
    if (
        not jct_only
        and not fct_only
        and status == "success"
        and int(analysis.get("route_qps") or 0) == 0
    ):
        status = "missing_route_choices"
    row: dict[str, object] = {
        "topology": topology_name,
        "policy": policy,
        "spray_width": args.spray_width,
        "dynamic_chunks": getattr(args, "dynamic_chunks", 8),
        "configured_flowlet_gap_ns": args.flowlet_gap_ns,
        "configured_flowlet_bytes": args.flowlet_bytes,
        "configured_flowlet_hysteresis_ns": args.flowlet_hysteresis_ns,
        "pxn_policy": args.pxn_policy,
        "workload": str(args.workload),
        "topology_file": str(TOPOLOGIES[topology_name]),
        "binary": str(args.binary),
        "threads": args.threads,
        "send_latency": args.send_latency,
        "status": status,
        "return_code": return_code,
        "jct": jct if jct is not None else "missing",
        "wall_seconds": wall_seconds,
        "run_dir": str(run_dir),
    }
    row.update(routing)
    row.update(analysis)
    return row


def validate_inputs(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise SystemExit(f"missing input: {path}")


def format_metric(value: object, digits: int = 3) -> str:
    if value is None or value == "" or value == "missing":
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def write_report(path: Path, rows: Sequence[dict[str, object]]) -> None:
    baselines = {
        str(row["topology"]): float(row["jct"])
        for row in rows
        if row["policy"] == "ecmp" and row["jct"] != "missing"
    }
    lines = [
        "# NS3 QP Spray, 256-GPU Topology",
        "",
        "The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.",
        "Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.",
        f"Workload: `{rows[0]['workload']}`" if rows else "",
        "",
        "| Topology | Policy | Status | JCT (us) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        topology = str(row["topology"])
        jct = row["jct"]
        baseline = baselines.get(topology)
        delta = "n/a"
        if baseline and jct != "missing":
            delta = f"{(float(jct) / baseline - 1.0) * 100:+.2f}%"
        lines.append(
            "| "
            + " | ".join(
                [
                    topology,
                    str(row["policy"]),
                    str(row["status"]),
                    format_metric(jct),
                    delta,
                    format_metric(row.get("logical_fct_p95_ns"), 1),
                    format_metric(row.get("mean_unique_paths_per_flow")),
                    format_metric(row.get("mean_path_coverage")),
                    format_metric(row.get("avoidable_collision_ratio")),
                    format_metric(row.get("link_max_mean_ratio")),
                    format_metric(row.get("link_bytes_cov")),
                    format_metric(row.get("dynamic_qp_bindings"), 0),
                    format_metric(row.get("flowlet_decisions"), 0),
                    format_metric(row.get("flowlet_switches"), 0),
                    format_metric(row.get("path_score_p95_ns"), 1),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--topologies",
        nargs="+",
        choices=sorted(TOPOLOGIES),
        default=["Zcube", "ROFT"],
    )
    parser.add_argument(
        "--topology-file",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="override a built-in topology path for this run",
    )
    parser.add_argument(
        "--policies",
        nargs="+",
        choices=[
            "ecmp",
            "spray",
            "spray_dynamic",
            "spray_path",
            "spray_flowlet",
            "spray_dual_table",
            "spray_adaptive",
            "spray_dynamic_chunk",
            "spray_packet_dlb",
        ],
        default=[
            "ecmp",
            "spray",
            "spray_dynamic",
            "spray_path",
            "spray_flowlet",
        ],
    )
    parser.add_argument("--spray-width", type=int, default=4)
    parser.add_argument(
        "--dynamic-chunks",
        type=int,
        default=8,
        help="total chunks per logical flow for spray_dynamic_chunk",
    )
    parser.add_argument("--flowlet-gap-ns", type=int, default=5000)
    parser.add_argument(
        "--flowlet-bytes",
        type=int,
        default=0,
        help="force reevaluation after this many QP bytes; 0 keeps gap-only flowlets",
    )
    parser.add_argument("--flowlet-hysteresis-ns", type=int, default=500)
    parser.add_argument(
        "--pxn-policy",
        choices=["off", "force", "fallback", "aggregate"],
        default="off",
        help="PXN policy passed to NS3; fallback uses PXN only when no direct route exists",
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--buffer-size-mib", type=int, default=32)
    parser.add_argument("--send-latency", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--route-dump-interval-ms", type=int, default=2000)
    parser.add_argument("--route-dump-grace-seconds", type=int, default=3)
    parser.add_argument(
        "--fct-idle-grace-seconds",
        type=int,
        default=10,
        help="in FCT-only mode, stop after JCT once fct.txt stays unchanged this long",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--jct-only",
        action="store_true",
        help="disable FCT/path dumps and stop shortly after final JCT is emitted",
    )
    output_group.add_argument(
        "--fct-only",
        action="store_true",
        help="save FCT without route/subflow dumps and stop after final JCT",
    )
    parser.add_argument(
        "--no-fct-output",
        action="store_true",
        help="save route/subflow dumps but disable FCT output to reduce disk usage",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.binary = args.binary.resolve()
    args.workload = args.workload.resolve()
    args.output_dir = args.output_dir.resolve()
    for override in args.topology_file:
        if "=" not in override:
            raise SystemExit(f"invalid --topology-file value: {override}")
        name, path = override.split("=", 1)
        if name not in TOPOLOGIES:
            raise SystemExit(
                f"unknown topology override {name!r}; expected one of "
                f"{', '.join(sorted(TOPOLOGIES))}"
            )
        TOPOLOGIES[name] = Path(path).resolve()
    if not 1 <= args.spray_width <= 16:
        raise SystemExit("--spray-width must be between 1 and 16")
    if not 1 <= args.dynamic_chunks <= 64:
        raise SystemExit("--dynamic-chunks must be between 1 and 64")
    if (
        args.threads < 1
        or args.buffer_size_mib < 1
        or args.timeout < 1
        or args.send_latency < 0
        or args.flowlet_gap_ns < 0
        or args.flowlet_bytes < 0
        or args.flowlet_hysteresis_ns < 0
        or args.route_dump_interval_ms < 1
        or args.route_dump_grace_seconds < 0
        or args.fct_idle_grace_seconds < 1
    ):
        raise SystemExit(
            "threads/buffer-size/timeout must be positive and latency non-negative"
        )
    if args.fct_only and args.no_fct_output:
        raise SystemExit("--fct-only and --no-fct-output cannot be combined")
    validate_inputs([args.binary, args.workload, *(TOPOLOGIES[name] for name in args.topologies)])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for topology in args.topologies:
        for policy in args.policies:
            print(f"[RUN] topology={topology} policy={policy}", flush=True)
            row = run_one(args, topology, policy)
            rows.append(row)
            write_csv(args.output_dir / "summary.csv", rows)
            write_report(args.output_dir / "report.md", rows)
            print(
                f"[DONE] topology={topology} policy={policy} "
                f"status={row['status']} jct={row['jct']} wall={row['wall_seconds']}s",
                flush=True,
            )
    write_csv(args.output_dir / "summary.csv", rows)
    write_report(args.output_dir / "report.md", rows)
    return 0 if all(row["status"] == "success" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
