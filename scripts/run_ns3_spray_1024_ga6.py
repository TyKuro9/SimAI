#!/usr/bin/env python3
"""Run 1024-GPU GA=6 JCT and DP-FCT experiments for spray policies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import run_ns3_ecmp_spray_256 as spray_runner


ROOT = Path(__file__).resolve().parents[1]

TOPOLOGIES = {
    "ROFT": ROOT
    / "mytopo"
    / "1024_12p8T"
    / "ROFT_1024g_8gps_p32a0.5_400Gbps_H100_12p8T",
    "Zcube": ROOT
    / "mytopo"
    / "1024_12p8T"
    / "Zcube_n32_k2_1024g_8gps_200Gbps_H100",
    "DeepSeek": ROOT
    / "mytopo"
    / "1024_12p8T"
    / "DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100",
    "Meta": ROOT
    / "mytopo"
    / "1024_12p8T"
    / "Meta_Topo_1024g_8gps_400Gbps_H100_12p8T",
    "HPN": ROOT
    / "mytopo"
    / "1024_12p8T"
    / "AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100",
}

WORKLOADS = {
    "Dense": ROOT
    / "my_workloads"
    / (
        "H100-gpt_22B-world_size1024-tp8-pp4-ep1-gbs192-mbs1-"
        "seq2048-MOE-False-GEMM-False-flash_attn-True.txt"
    ),
    "MoE": ROOT
    / "my_workloads"
    / (
        "H100-Mixtral_8x7B-world_size1024-tp8-pp4-ep8-gbs192-mbs1-"
        "seq2048-MOE-True-GEMM-True-flash_attn-True-GA6.txt"
    ),
}

EXPECTED_EP = {"Dense": 1, "MoE": 8}
EXPECTED_PP = {"Dense": 4, "MoE": 4}
POLICIES = [
    "spray_dynamic",
    "spray_flowlet",
    "spray_dual_table",
    "spray_adaptive",
    "spray_dynamic_chunk",
    "spray_packet_dlb",
]
DEFAULT_OUTPUT = (
    ROOT / "experiments" / "ns3_spray" / "adaptive_1024_dense_ga6_20260717"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_workload(name: str, path: Path) -> dict[str, int]:
    if not path.exists():
        raise SystemExit(f"missing workload: {path}")
    header = path.open(errors="replace").readline().strip()
    values: dict[str, int] = {}
    for key in (
        "model_parallel_NPU_group",
        "ep",
        "pp",
        "vpp",
        "ga",
        "all_gpus",
    ):
        match = re.search(rf"(?:^|\s){key}:\s*(\d+)", header)
        if not match:
            raise SystemExit(f"{path}: missing {key} in workload header")
        values[key] = int(match.group(1))
    expected = {
        "model_parallel_NPU_group": 8,
        "ep": EXPECTED_EP[name],
        "pp": EXPECTED_PP[name],
        "ga": 6,
        "all_gpus": 1024,
    }
    pp_comm = re.search(r"(?:^|\s)pp_comm:\s*([0-9]+(?:\.[0-9]+)?)", header)
    if not pp_comm:
        raise SystemExit(f"{path}: missing pp_comm in workload header")
    values["pp_comm"] = int(float(pp_comm.group(1)))
    mismatches = {
        key: (expected_value, values.get(key))
        for key, expected_value in expected.items()
        if values.get(key) != expected_value
    }
    if mismatches:
        raise SystemExit(f"{path}: workload metadata mismatch: {mismatches}")
    return values


def validate_topology(name: str, path: Path) -> dict[str, int | str]:
    if not path.exists():
        raise SystemExit(f"missing topology: {path}")
    fields = path.open(errors="replace").readline().split()
    if len(fields) < 6:
        raise SystemExit(f"{path}: malformed topology header")
    result: dict[str, int | str] = {
        "nodes": int(fields[0]),
        "gpus_per_server": int(fields[1]),
        "servers": int(fields[2]),
        "switches": int(fields[3]),
        "links": int(fields[4]),
        "gpu_type": fields[5],
    }
    if result["gpus_per_server"] != 8 or result["servers"] != 128:
        raise SystemExit(f"{name}: topology is not the expected 1024-GPU layout")
    return result


def read_existing(path: Path) -> dict[tuple[str, str, str], dict[str, object]]:
    rows: dict[tuple[str, str, str], dict[str, object]] = {}
    if not path.exists():
        return rows
    with path.open(newline="") as input_file:
        for row in csv.DictReader(input_file):
            key = (row["workload_kind"], row["topology"], row["policy"])
            rows[key] = dict(row)
    return rows


def result_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(row["workload_kind"]),
        str(row["topology"]),
        str(row["policy"]),
    )


def is_complete(row: dict[str, object]) -> bool:
    complete = row.get("status") == "success" and row.get("jct_us") not in {
        None,
        "",
        "missing",
    }
    if not complete:
        return False
    if row.get("record_mode") == "dp-fct":
        run_dir = row.get("run_dir")
        return bool(
            run_dir
            and (Path(str(run_dir)) / "fct.txt").exists()
            and (Path(str(run_dir)) / "fct.txt").stat().st_size > 0
        )
    return True


def normalize_result(
    workload_kind: str,
    row: dict[str, object],
    binary_hash: str,
    workload_hash: str,
    topology_hash: str,
) -> dict[str, object]:
    raw_jct = row.get("jct", "missing")
    try:
        jct_us: object = float(raw_jct)
        jct_s: object = float(raw_jct) / 1_000_000.0
    except (TypeError, ValueError):
        jct_us = "missing"
        jct_s = "missing"
    return {
        "workload_kind": workload_kind,
        "world_size": 1024,
        "ga": 6,
        "jct_us": jct_us,
        "jct_s": jct_s,
        "binary_sha256": binary_hash,
        "workload_sha256": workload_hash,
        "topology_sha256": topology_hash,
        **row,
    }


def failed_result(
    workload_kind: str,
    topology: str,
    policy: str,
    args: argparse.Namespace,
    error: Exception,
) -> dict[str, object]:
    return {
        "workload_kind": workload_kind,
        "world_size": 1024,
        "ga": 6,
        "record_mode": args.record_mode,
        "topology": topology,
        "policy": policy,
        "spray_width": args.spray_width,
        "configured_flowlet_gap_ns": args.flowlet_gap_ns,
        "configured_flowlet_bytes": args.flowlet_bytes,
        "configured_flowlet_hysteresis_ns": args.flowlet_hysteresis_ns,
        "workload": str(WORKLOADS[workload_kind]),
        "topology_file": str(TOPOLOGIES[topology]),
        "binary": str(args.binary),
        "threads": args.threads,
        "send_latency": args.send_latency,
        "status": "runner_error",
        "return_code": "runner_error",
        "jct": "missing",
        "jct_us": "missing",
        "jct_s": "missing",
        "wall_seconds": "missing",
        "error": repr(error),
        "run_dir": str(args.output_dir / workload_kind / topology / policy),
    }


def run_case(
    args: argparse.Namespace,
    workload_kind: str,
    topology: str,
    policy: str,
    workload_hash: str,
    topology_hash: str,
    binary_hash: str,
) -> dict[str, object]:
    record_dp_fct = args.record_mode == "dp-fct"
    workload_values = args.workload_metadata[workload_kind]
    dp_group_count = (
        workload_values["model_parallel_NPU_group"] * workload_values["pp"]
    )
    extra_env: dict[str, str] = {}
    if record_dp_fct:
        extra_env = {
            "AS_NS3_FCT_FILTER": "dp",
            "AS_NS3_DP_GROUP_COUNT": str(dp_group_count),
        }
    case_args = argparse.Namespace(
        binary=args.binary,
        workload=WORKLOADS[workload_kind],
        output_dir=args.output_dir / workload_kind,
        spray_width=args.spray_width,
        dynamic_chunks=args.dynamic_chunks,
        flowlet_gap_ns=args.flowlet_gap_ns,
        flowlet_bytes=args.flowlet_bytes,
        flowlet_hysteresis_ns=args.flowlet_hysteresis_ns,
        pxn_policy=args.pxn_policy,
        threads=args.threads,
        buffer_size_mib=args.buffer_size_mib,
        send_latency=args.send_latency,
        timeout=args.timeout,
        route_dump_interval_ms=2000,
        route_dump_grace_seconds=1,
        jct_only=not record_dp_fct,
        fct_only=record_dp_fct,
        no_fct_output=False,
        fct_idle_grace_seconds=args.fct_idle_grace_seconds,
        skip_analysis=record_dp_fct,
        extra_env=extra_env,
    )
    print(
        f"[RUN] workload={workload_kind} topology={topology} policy={policy}",
        flush=True,
    )
    try:
        row = spray_runner.run_one(case_args, topology, policy)
        result = normalize_result(
            workload_kind, row, binary_hash, workload_hash, topology_hash
        )
        result["record_mode"] = args.record_mode
        result["dp_size"] = workload_values["all_gpus"] // dp_group_count
        result["dp_group_count"] = dp_group_count
    except Exception as error:  # Preserve the other long-running cases.
        result = failed_result(workload_kind, topology, policy, args, error)
    print(
        f"[DONE] workload={workload_kind} topology={topology} policy={policy} "
        f"status={result['status']} jct_us={result['jct_us']} "
        f"wall={result['wall_seconds']}s",
        flush=True,
    )
    return result


def sorted_rows(
    rows: dict[tuple[str, str, str], dict[str, object]],
) -> list[dict[str, object]]:
    workload_order = {name: index for index, name in enumerate(WORKLOADS)}
    topology_order = {name: index for index, name in enumerate(TOPOLOGIES)}
    policy_order = {name: index for index, name in enumerate(POLICIES)}
    return sorted(
        rows.values(),
        key=lambda row: (
            workload_order.get(str(row["workload_kind"]), 99),
            topology_order.get(str(row["topology"]), 99),
            policy_order.get(str(row["policy"]), 99),
        ),
    )


def metric(value: object, digits: int = 6) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    baselines = {
        (str(row["workload_kind"]), str(row["topology"])): float(row["jct_us"])
        for row in rows
        if row.get("policy") == "spray_dual_table" and is_complete(row)
    }
    lines = [
        "# NS3 1024-GPU GA=6 Spray Results",
        "",
        "JCT is read from the final `total time` in `EndToEnd.csv`. "
        "ASTRA-Sim reports this value in microseconds.",
        "",
        "PXN is disabled. Runs use the record mode, spray width, and NS3 thread "
        "count stored in the CSV and manifest. In `dp-fct` mode, `fct.txt` contains "
        "only real DP-group traffic.",
        "",
        "| Workload | Topology | Policy | Record mode | Status | JCT (us) | JCT (s) | vs equal-path | Wall time (s) |",
        "|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        baseline = baselines.get(
            (str(row["workload_kind"]), str(row["topology"]))
        )
        delta = "n/a"
        if baseline and is_complete(row):
            delta = f"{(float(row['jct_us']) / baseline - 1.0) * 100:+.3f}%"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["workload_kind"]),
                    str(row["topology"]),
                    str(row["policy"]),
                    str(row.get("record_mode", "jct")),
                    str(row["status"]),
                    metric(row.get("jct_us"), 3),
                    metric(row.get("jct_s"), 6),
                    delta,
                    metric(row.get("wall_seconds"), 1),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        default=ROOT
        / "astra-sim-alibabacloud"
        / "extern"
        / "network_backend"
        / "ns3-interface"
        / "simulation"
        / "build"
        / "scratch"
        / "ns3.36.1-AstraSimNetwork-debug",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--workloads", nargs="+", choices=WORKLOADS, default=["Dense"]
    )
    parser.add_argument(
        "--topologies", nargs="+", choices=TOPOLOGIES, default=list(TOPOLOGIES)
    )
    parser.add_argument(
        "--policies", nargs="+", choices=POLICIES, default=["spray_adaptive"]
    )
    parser.add_argument("--spray-width", type=int, default=4)
    parser.add_argument("--dynamic-chunks", type=int, default=8)
    parser.add_argument("--flowlet-gap-ns", type=int, default=5000)
    parser.add_argument("--flowlet-bytes", type=int, default=0)
    parser.add_argument("--flowlet-hysteresis-ns", type=int, default=500)
    parser.add_argument(
        "--pxn-policy",
        choices=["off", "force", "fallback", "aggregate"],
        default="off",
    )
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--buffer-size-mib", type=int, default=128)
    parser.add_argument("--parallel-runs", type=int, default=5)
    parser.add_argument("--send-latency", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=259200)
    parser.add_argument(
        "--record-mode",
        choices=("jct", "dp-fct"),
        default="jct",
        help="record JCT only, or JCT plus DP-only completion records",
    )
    parser.add_argument(
        "--fct-idle-grace-seconds",
        type=int,
        default=30,
        help="after JCT, stop an FCT run once fct.txt is unchanged this long",
    )
    parser.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.binary = args.binary.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.binary.exists():
        raise SystemExit(f"missing binary: {args.binary}")
    if not 1 <= args.spray_width <= 16:
        raise SystemExit("--spray-width must be between 1 and 16")
    if not 1 <= args.dynamic_chunks <= 64:
        raise SystemExit("--dynamic-chunks must be between 1 and 64")
    if (
        args.threads < 1
        or args.buffer_size_mib < 1
        or args.parallel_runs < 1
        or args.timeout < 1
        or args.fct_idle_grace_seconds < 1
    ):
        raise SystemExit(
            "threads, buffer-size, parallel-runs, timeout, and FCT idle grace "
            "must be positive"
        )
    if min(
        args.flowlet_gap_ns,
        args.flowlet_bytes,
        args.flowlet_hysteresis_ns,
        args.send_latency,
    ) < 0:
        raise SystemExit("flowlet settings and send latency must be non-negative")

    workload_metadata = {
        name: validate_workload(name, WORKLOADS[name]) for name in args.workloads
    }
    args.workload_metadata = workload_metadata
    topology_metadata = {
        name: validate_topology(name, TOPOLOGIES[name]) for name in args.topologies
    }
    workload_hashes = {
        name: file_sha256(WORKLOADS[name]) for name in args.workloads
    }
    topology_hashes = {
        name: file_sha256(TOPOLOGIES[name]) for name in args.topologies
    }
    binary_hash = file_sha256(args.binary)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "binary": str(args.binary),
        "binary_sha256": binary_hash,
        "workloads": {
            name: {
                "path": str(WORKLOADS[name]),
                "sha256": workload_hashes[name],
                "dp_size": workload_metadata[name]["all_gpus"]
                // (
                    workload_metadata[name]["model_parallel_NPU_group"]
                    * workload_metadata[name]["pp"]
                ),
                "dp_group_count": (
                    workload_metadata[name]["model_parallel_NPU_group"]
                    * workload_metadata[name]["pp"]
                ),
                **workload_metadata[name],
            }
            for name in args.workloads
        },
        "topologies": {
            name: {
                "path": str(TOPOLOGIES[name]),
                "sha256": topology_hashes[name],
                **topology_metadata[name],
            }
            for name in args.topologies
        },
        "policies": args.policies,
        "spray_width": args.spray_width,
        "dynamic_chunks": args.dynamic_chunks,
        "flowlet_gap_ns": args.flowlet_gap_ns,
        "flowlet_bytes": args.flowlet_bytes,
        "flowlet_hysteresis_ns": args.flowlet_hysteresis_ns,
        "threads_per_run": args.threads,
        "buffer_size_mib": args.buffer_size_mib,
        "parallel_runs": args.parallel_runs,
        "send_latency": args.send_latency,
        "timeout_seconds": args.timeout,
        "pxn_policy": args.pxn_policy,
        "record_mode": args.record_mode,
        "jct_only": args.record_mode == "jct",
        "completion_log": args.record_mode == "dp-fct",
        "fct_filter": "dp" if args.record_mode == "dp-fct" else "off",
        "fct_grain": "logical flow = max physical-stripe FCT",
        "fct_idle_grace_seconds": args.fct_idle_grace_seconds,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )

    spray_runner.TOPOLOGIES = TOPOLOGIES
    selected_cases = [
        (workload, topology, policy)
        for workload in args.workloads
        for topology in args.topologies
        for policy in args.policies
    ]
    if args.dry_run:
        for workload, topology, policy in selected_cases:
            print(f"{workload},{topology},{policy}")
        return 0

    result_path = args.output_dir / "jct_results.csv"
    results = read_existing(result_path) if args.resume else {}
    pending = [
        case
        for case in selected_cases
        if not is_complete(results.get(case, {}))
    ]
    skipped = len(selected_cases) - len(pending)
    print(
        f"[MATRIX] selected={len(selected_cases)} pending={len(pending)} "
        f"resumed={skipped}",
        flush=True,
    )

    with ThreadPoolExecutor(
        max_workers=min(args.parallel_runs, max(1, len(pending)))
    ) as executor:
        futures = {
            executor.submit(
                run_case,
                args,
                workload,
                topology,
                policy,
                workload_hashes[workload],
                topology_hashes[topology],
                binary_hash,
            ): (workload, topology, policy)
            for workload, topology, policy in pending
        }
        for future in as_completed(futures):
            row = future.result()
            results[result_key(row)] = row
            output_rows = sorted_rows(results)
            spray_runner.write_csv(result_path, output_rows)
            write_report(args.output_dir / "report.md", output_rows)

    output_rows = sorted_rows(results)
    spray_runner.write_csv(result_path, output_rows)
    write_report(args.output_dir / "report.md", output_rows)
    selected_results = [results.get(case, {}) for case in selected_cases]
    return 0 if all(is_complete(row) for row in selected_results) else 1


if __name__ == "__main__":
    sys.exit(main())
