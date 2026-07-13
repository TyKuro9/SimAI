#!/usr/bin/env python3
"""Run 1024-GPU NS3 random-link fault experiments for all-to-all.

This mirrors run_flowsim_fault_256_alltoall.py but invokes the NS3 backend.
Failed topology files are generated up front, NVSwitch/scale-up links are
excluded from random failures, and only JCT-level EndToEnd.csv results are
summarized.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import os
import subprocess
import sys
import time
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


TOPOLOGIES: Dict[str, str] = {
    "Meta": "Meta_Topo_1024g_8gps_400Gbps_H100_12p8T",
    "HPN": "AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100",
    "DeepSeek": "DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100",
    "Zcube": "Zcube_n32_k2_1024g_8gps_200Gbps_H100",
    "RO": "RailOnly_1024g_8gps_s5_400Gbps_H100_12p8T",
    "ROFT": "ROFT_1024g_8gps_p32a0.5_400Gbps_H100_12p8T",
}


def default_ns3_bin() -> Path:
    candidates = [
        ROOT / "bin" / "SimAI_simulator",
        ROOT
        / "astra-sim-alibabacloud"
        / "extern"
        / "network_backend"
        / "ns3-interface"
        / "simulation"
        / "build"
        / "scratch"
        / "ns3.36.1-AstraSimNetwork-debug",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return candidates[0]


CONFIG_TEMPLATE = """ENABLE_QCN 1
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 9000

FLOW_FILE {flow_file}
TRACE_FILE {trace_file}
TRACE_OUTPUT_FILE {trace_output_file}
FCT_OUTPUT_FILE {fct_output_file}
PFC_OUTPUT_FILE {pfc_output_file}

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

BUFFER_SIZE 32
"""


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


def numeric(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isnan(f):
            return None
        return f
    return None


def summarize(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[object, object], List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(row["topology"], row["link_failure_probability"])].append(row)

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
    for (topology, rate), group_rows in sorted(grouped.items()):
        row: Dict[str, object] = {
            "topology": topology,
            "link_failure_probability": rate,
            "num_samples": len(group_rows),
            "num_success": sum(1 for r in group_rows if r.get("status") == "success"),
        }
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


def build_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["AS_SEND_LAT"] = env.get("AS_SEND_LAT", "3")
    env["AS_NVLS_ENABLE"] = env.get("AS_NVLS_ENABLE", "0")
    env["AS_PXN_ENABLE"] = env.get("AS_PXN_ENABLE", "1")
    env["AS_PXN_POLICY"] = env.get("AS_PXN_POLICY", "fallback")
    return env


def write_ns3_config(run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    flow_file = run_dir / "flow.txt"
    trace_file = run_dir / "trace.txt"
    flow_file.write_text("0\n")
    trace_file.write_text("0\n")

    config_path = run_dir / "ns3.conf"
    config_path.write_text(
        CONFIG_TEMPLATE.format(
            flow_file=flow_file,
            trace_file=trace_file,
            trace_output_file="/dev/null",
            fct_output_file="/dev/null",
            pfc_output_file="/dev/null",
        )
    )
    return config_path


def run_ns3(
    *,
    ns3_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    env: Dict[str, str],
    timeout: Optional[int],
    resume: bool,
) -> Optional[float]:
    existing_jct = FT.read_total_time(output_dir / "EndToEnd.csv")
    if resume and existing_jct is not None:
        return existing_jct

    output_dir.mkdir(parents=True, exist_ok=True)
    config = write_ns3_config(output_dir)
    cmd = [
        str(ns3_bin),
        "-t",
        str(threads),
        "-w",
        str(workload),
        "-n",
        str(topology),
        "-c",
        str(config),
        "-o",
        str(output_dir) + "/",
    ]
    with (output_dir / "run.log").open("w") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=output_dir,
        )
        start = time.monotonic()
        end_to_end = output_dir / "EndToEnd.csv"
        while True:
            jct = FT.read_total_time(end_to_end)
            if jct is not None:
                log.write(f"\n[RUNNER] EndToEnd.csv complete with JCT={jct}; terminating NS3.\n")
                log.flush()
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                return jct

            if proc.poll() is not None:
                return FT.read_total_time(end_to_end)

            if timeout is not None and time.monotonic() - start > timeout:
                log.write(f"\n[TIMEOUT] exceeded {timeout} seconds\n")
                log.flush()
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                return None

            time.sleep(1.0)


def run_fault_task(task: Dict[str, object]) -> Dict[str, object]:
    failed_jct = run_ns3(
        ns3_bin=task["ns3_bin"],
        workload=task["workload"],
        topology=task["failed_topology_path"],
        output_dir=task["run_dir_path"],
        threads=task["threads"],
        env=task["env"],
        timeout=task["timeout"],
        resume=task["resume"],
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


def run(args: argparse.Namespace) -> int:
    topo_dir = args.root / "mytopo" / "1024_12p8T"
    out_root = args.output_dir
    generated_root = out_root / "generated_topologies"
    runs_root = out_root / "runs"
    env = build_env()
    rows: List[Dict[str, object]] = []
    baselines: List[Dict[str, object]] = []
    tasks: List[Dict[str, object]] = []

    selected = args.topologies or list(TOPOLOGIES.keys())
    seed_values = [args.seed_base + i for i in range(args.samples)]

    for topo_name in selected:
        topo_file = TOPOLOGIES[topo_name]
        topo_path = topo_dir / topo_file
        topology = FT.parse_topology(topo_path)
        baseline_lengths = FT.shortest_path_lengths(topology, set())
        eligible_links = FT.eligible_inter_server_links(topology)

        baseline_dir = runs_root / topo_name / "baseline"
        print(f"[BASELINE] {topo_name} -> {baseline_dir}", flush=True)
        normal_jct = run_ns3(
            ns3_bin=args.ns3_bin,
            workload=args.workload,
            topology=topo_path,
            output_dir=baseline_dir,
            threads=args.threads,
            env=env,
            timeout=args.timeout,
            resume=args.resume,
        )
        baselines.append(
            {
                "topology": topo_name,
                "topology_file": str(topo_path),
                "normal_jct": normal_jct if normal_jct is not None else "missing",
                "eligible_inter_server_links": len(eligible_links),
                "run_dir": str(baseline_dir),
            }
        )

        for rate in args.rates:
            for seed in seed_values:
                failed_keys = FT.sample_failed_links(topology, rate, seed)
                metrics = FT.topology_metrics(topology, failed_keys, baseline_lengths, "all-to-all")
                failed_topology = (
                    generated_root
                    / topo_name
                    / rate_label(rate)
                    / f"seed{seed}.topo"
                )
                FT.write_topology(topology, failed_keys, failed_topology)

                run_dir = runs_root / topo_name / rate_label(rate) / f"seed{seed}"
                row: Dict[str, object] = {
                    "topology": topo_name,
                    "workload": args.workload_label,
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
                connectivity = numeric(metrics.get("connectivity_ratio"))
                if normal_jct is None:
                    row["status"] = "baseline_failed"
                    rows.append(row)
                elif connectivity is not None and connectivity < 1.0:
                    row["status"] = "disconnected"
                    rows.append(row)
                else:
                    tasks.append(
                        {
                            "ns3_bin": args.ns3_bin,
                            "workload": args.workload,
                            "failed_topology_path": failed_topology,
                            "run_dir_path": run_dir,
                            "threads": args.threads,
                            "env": env,
                            "timeout": args.timeout,
                            "resume": args.resume,
                            "normal_jct": normal_jct,
                            "row": row,
                        }
                    )

    print(
        f"[SWEEP] {len(tasks)} runnable samples, {len(rows)} pre-classified samples, "
        f"jobs={args.jobs}, threads_per_job={args.threads}",
        flush=True,
    )
    write_csv(out_root / "baseline_jct.csv", baselines)
    write_csv(out_root / "random_link_failure_raw.csv", rows)
    write_csv(out_root / "random_link_failure_summary.csv", summarize(rows))

    if args.jobs == 1:
        for idx, task in enumerate(tasks, start=1):
            row = task["row"]
            print(
                f"[RUN {idx}/{len(tasks)}] {row['topology']} rate={row['link_failure_probability']:g} "
                f"seed={row['seed']} failed_links={row['num_failed_links']}",
                flush=True,
            )
            rows.append(run_fault_task(task))
            write_csv(out_root / "random_link_failure_raw.csv", rows)
            write_csv(out_root / "random_link_failure_summary.csv", summarize(rows))
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
                write_csv(out_root / "random_link_failure_raw.csv", rows)
                write_csv(out_root / "random_link_failure_summary.csv", summarize(rows))
                print(
                    f"[DONE {idx}/{len(tasks)}] {row['topology']} "
                    f"rate={row['link_failure_probability']:g} seed={row['seed']} "
                    f"status={result['status']}",
                    flush=True,
                )

    write_csv(out_root / "random_link_failure_raw.csv", rows)
    write_csv(out_root / "random_link_failure_summary.csv", summarize(rows))
    print(f"[DONE] wrote {len(rows)} rows to {out_root}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch NS3 1024-GPU all-to-all random-link fault sweep"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--workload",
        type=Path,
        default=ROOT / "my_workloads" / "synthetic_alltoall_global_world_size1024_tp16_dp64_1MiB.txt",
    )
    parser.add_argument(
        "--workload-label",
        default="all-to-all-tp16-dp64-1024-1MiB",
        help="label stored in result CSV files",
    )
    parser.add_argument(
        "--ns3-bin",
        type=Path,
        default=default_ns3_bin(),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "experiments" / "fault_tolerance" / "ns3_1024_12p8T_alltoall_tp16dp64_1MiB",
    )
    parser.add_argument(
        "--rates",
        type=parse_rates,
        default=default_rates(),
        help="comma-separated link failure probabilities",
    )
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="optional per-run timeout in seconds",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse existing EndToEnd.csv files when present",
    )
    parser.add_argument(
        "--topologies",
        nargs="*",
        choices=sorted(TOPOLOGIES.keys()),
        help="subset of topologies to run; default is all six",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.samples < 1:
        raise SystemExit("--samples must be >= 1")
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.threads < 1:
        raise SystemExit("--threads must be >= 1")
    if not args.workload.exists():
        raise SystemExit(f"workload not found: {args.workload}")
    if not args.ns3_bin.exists() or not os.access(args.ns3_bin, os.X_OK):
        raise SystemExit(f"NS3 binary not executable: {args.ns3_bin}")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
