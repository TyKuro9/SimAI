#!/usr/bin/env python3
"""Rerun representative mismatch samples with optional detailed NS3 monitors."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import time
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance" / "targeted_fct_mismatch"
DEFAULT_WORKLOAD = ROOT / "my_workloads" / "synthetic_alltoall_global_world_size256_1MiB.txt"
DEFAULT_FLOWSIM_BIN = Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim")
DEFAULT_NS3_BIN = ROOT / "bin" / "SimAI_simulator"
DEFAULT_SOURCE_RESULTS = (
    ROOT / "experiments" / "fault_tolerance" / "flowsim_256_alltoall_p01_p15_s10_chain"
)

TARGETS = [
    ("Meta", 0.15, 3),
    ("Zcube", 0.15, 7),
    ("RO", 0.15, 6),
]

CONFIG_TEMPLATE = """ENABLE_QCN 1
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 9000

FLOW_FILE {flow_file}
TRACE_FILE {trace_file}
TRACE_OUTPUT_FILE {trace_output_file}
FCT_OUTPUT_FILE {fct_output_file}
PFC_OUTPUT_FILE {pfc_output_file}
SEND_OUTPUT_FILE {send_output_file}

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

ENABLE_TRACE {enable_trace}

{monitor_config}

KMAX_MAP 6 25000000000 400 50000000000 800 100000000000 1600 200000000000 1200 400000000000 3200 1600000000000 2400
KMIN_MAP 6 25000000000 100 50000000000 200 100000000000 400 200000000000 300 400000000000 800 1600000000000 600
PMAX_MAP 6 25000000000 0.2 50000000000 0.2 100000000000 0.2 200000000000 0.8 400000000000 0.2 1600000000000 0.2

BUFFER_SIZE 32
"""


def rate_label(rate: float) -> str:
    return f"p{rate:.6g}".replace(".", "p")


def parse_target(value: str) -> tuple[str, float, int]:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 3 or not all(parts):
        raise argparse.ArgumentTypeError(
            "target must be formatted as topology:rate:seed, e.g. DeepSeek:0.15:1"
        )
    topology, rate, seed = parts
    return topology, float(rate), int(seed)


def build_env(*, flowsim_fct: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["AS_SEND_LAT"] = env.get("AS_SEND_LAT", "3")
    env["AS_NVLS_ENABLE"] = env.get("AS_NVLS_ENABLE", "0")
    env["AS_PXN_ENABLE"] = env.get("AS_PXN_ENABLE", "1")
    env["AS_PXN_POLICY"] = env.get("AS_PXN_POLICY", "fallback")
    if flowsim_fct:
        env.pop("FLOWSIM_WRITE_FCT", None)
    else:
        env["FLOWSIM_WRITE_FCT"] = "0"
    return env


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
        return float(row[idx].strip())
    except (ValueError, IndexError):
        return None


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(errors="replace") as f:
        return sum(1 for _ in f)


def ns3_monitor_output(run_dir: Path, stem: str) -> Path:
    expected = run_dir / f"{stem}.csv"
    if expected.exists():
        return expected
    legacy = run_dir / f"{stem}nf"
    if legacy.exists():
        return legacy
    return expected


def topology_path(source_results: Path, topology: str, rate: float, seed: int) -> Path:
    return (
        source_results
        / "generated_topologies"
        / topology
        / rate_label(rate)
        / f"seed{seed}.topo"
    )


def run_flowsim(
    *,
    flowsim_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    timeout: Optional[int],
    resume: bool,
) -> Optional[float]:
    existing = read_total_time(output_dir / "EndToEnd.csv")
    if resume and existing is not None and count_lines(output_dir / "fct.txt") > 0:
        return existing
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
        subprocess.run(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            env=build_env(flowsim_fct=True),
            timeout=timeout,
        )
    return read_total_time(output_dir / "EndToEnd.csv")


def build_monitor_config(
    output_dir: Path,
    *,
    enable_monitors: bool,
    monitor_start_us: int,
    monitor_end_us: int,
    qlen_interval_us: int,
    bw_interval_us: int,
    qp_interval_us: int,
) -> str:
    if not enable_monitors:
        return ""
    return "\n".join(
        [
            f"QLEN_MON_FILE {output_dir / 'qlen.csv'}",
            f"BW_MON_FILE {output_dir / 'bw.csv'}",
            f"RATE_MON_FILE {output_dir / 'rate.csv'}",
            f"CNP_MON_FILE {output_dir / 'cnp.csv'}",
            f"MON_START {monitor_start_us}",
            f"MON_END {monitor_end_us}",
            f"QLEN_MON_INTERVAL {qlen_interval_us}",
            f"BW_MON_INTERVAL {bw_interval_us}",
            f"QP_MON_INTERVAL {qp_interval_us}",
        ]
    )


def write_ns3_config(
    output_dir: Path,
    *,
    enable_trace: bool,
    enable_monitors: bool,
    monitor_start_us: int,
    monitor_end_us: int,
    qlen_interval_us: int,
    bw_interval_us: int,
    qp_interval_us: int,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    flow_file = output_dir / "flow.txt"
    trace_file = output_dir / "trace.txt"
    flow_file.write_text("0\n")
    trace_file.write_text("0\n")
    config = output_dir / "ns3.conf"
    config.write_text(
        CONFIG_TEMPLATE.format(
            flow_file=flow_file,
            trace_file=trace_file,
            trace_output_file=output_dir / "trace.tr",
            fct_output_file=output_dir / "fct.txt",
            pfc_output_file=output_dir / "pfc.txt",
            send_output_file=output_dir / "send.txt",
            enable_trace=1 if enable_trace else 0,
            monitor_config=build_monitor_config(
                output_dir,
                enable_monitors=enable_monitors,
                monitor_start_us=monitor_start_us,
                monitor_end_us=monitor_end_us,
                qlen_interval_us=qlen_interval_us,
                bw_interval_us=bw_interval_us,
                qp_interval_us=qp_interval_us,
            ),
        )
    )
    return config


def run_ns3(
    *,
    ns3_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    timeout: Optional[int],
    enable_trace: bool,
    enable_monitors: bool,
    monitor_start_us: int,
    monitor_end_us: int,
    qlen_interval_us: int,
    bw_interval_us: int,
    qp_interval_us: int,
    jct_linger_timeout: int,
    resume: bool,
) -> Optional[float]:
    existing = read_total_time(output_dir / "EndToEnd.csv")
    if resume and existing is not None:
        required = [output_dir / "fct.txt", output_dir / "send.txt", output_dir / "pfc.txt"]
        if enable_trace:
            required.append(output_dir / "trace.tr")
        if enable_monitors:
            required.extend(
                [
                    ns3_monitor_output(output_dir, "qlen"),
                    ns3_monitor_output(output_dir, "bw"),
                    ns3_monitor_output(output_dir, "rate"),
                    ns3_monitor_output(output_dir, "cnp"),
                ]
            )
        if all(path.exists() for path in required):
            return existing
    output_dir.mkdir(parents=True, exist_ok=True)
    config = write_ns3_config(
        output_dir,
        enable_trace=enable_trace,
        enable_monitors=enable_monitors,
        monitor_start_us=monitor_start_us,
        monitor_end_us=monitor_end_us,
        qlen_interval_us=qlen_interval_us,
        bw_interval_us=bw_interval_us,
        qp_interval_us=qp_interval_us,
    )
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
            env=build_env(flowsim_fct=False),
            cwd=output_dir,
        )
        start = time.monotonic()
        jct_seen_at: Optional[float] = None
        last_jct: Optional[float] = None
        while True:
            jct = read_total_time(output_dir / "EndToEnd.csv")
            if jct is not None:
                if jct_seen_at is None:
                    jct_seen_at = time.monotonic()
                    last_jct = jct
                    log.write(
                        f"\n[RUNNER] EndToEnd.csv complete with JCT={jct}; "
                        "waiting for natural NS3 exit/monitor flush.\n"
                    )
                    log.flush()
                if proc.poll() is not None:
                    return read_total_time(output_dir / "EndToEnd.csv")
                if time.monotonic() - jct_seen_at > jct_linger_timeout:
                    log.write(
                        f"\n[RUNNER] JCT linger timeout {jct_linger_timeout}s "
                        "exceeded; terminating NS3.\n"
                    )
                    log.flush()
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                    return last_jct
            if proc.poll() is not None:
                return read_total_time(output_dir / "EndToEnd.csv")
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


def run(args: argparse.Namespace) -> int:
    args.output_dir = args.output_dir.resolve()
    args.source_results = args.source_results.resolve()
    args.workload = args.workload.resolve()
    args.flowsim_bin = args.flowsim_bin.resolve()
    args.ns3_bin = args.ns3_bin.resolve()
    rows = []
    targets = args.target or TARGETS
    for topology, rate, seed in targets:
        topo = topology_path(args.source_results, topology, rate, seed)
        if not topo.exists():
            raise SystemExit(f"topology not found: {topo}")
        label = rate_label(rate)
        flow_dir = args.output_dir / "flowsim" / topology / label / f"seed{seed}"
        ns3_dir = args.output_dir / "ns3" / topology / label / f"seed{seed}"
        print(f"[FLOWSIM] {topology} {label} seed{seed}", flush=True)
        flow_jct = run_flowsim(
            flowsim_bin=args.flowsim_bin,
            workload=args.workload,
            topology=topo,
            output_dir=flow_dir,
            threads=args.threads,
            timeout=args.timeout,
            resume=args.resume,
        )
        print(f"[NS3] {topology} {label} seed{seed}", flush=True)
        ns3_jct = run_ns3(
            ns3_bin=args.ns3_bin,
            workload=args.workload,
            topology=topo,
            output_dir=ns3_dir,
            threads=args.threads,
            timeout=args.timeout,
            enable_trace=args.enable_trace,
            enable_monitors=args.enable_monitors,
            monitor_start_us=args.monitor_start_us,
            monitor_end_us=args.monitor_end_us,
            qlen_interval_us=args.qlen_interval_us,
            bw_interval_us=args.bw_interval_us,
            qp_interval_us=args.qp_interval_us,
            jct_linger_timeout=args.jct_linger_timeout,
            resume=args.resume,
        )
        rows.append(
            {
                "topology": topology,
                "rate": rate,
                "seed": seed,
                "topology_file": str(topo),
                "flowsim_jct": flow_jct if flow_jct is not None else "missing",
                "ns3_jct": ns3_jct if ns3_jct is not None else "missing",
                "flowsim_run_dir": str(flow_dir),
                "ns3_run_dir": str(ns3_dir),
                "flowsim_fct_lines": count_lines(flow_dir / "fct.txt"),
                "ns3_fct_lines": count_lines(ns3_dir / "fct.txt"),
                "ns3_send_lines": count_lines(ns3_dir / "send.txt"),
                "ns3_pfc_lines": count_lines(ns3_dir / "pfc.txt"),
                "ns3_trace_lines": count_lines(ns3_dir / "trace.tr"),
                "ns3_qlen_lines": count_lines(ns3_monitor_output(ns3_dir, "qlen")),
                "ns3_bw_lines": count_lines(ns3_monitor_output(ns3_dir, "bw")),
                "ns3_rate_lines": count_lines(ns3_monitor_output(ns3_dir, "rate")),
                "ns3_cnp_lines": count_lines(ns3_monitor_output(ns3_dir, "cnp")),
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "targeted_fct_summary.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun targeted mismatch samples with FCT")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-results", type=Path, default=DEFAULT_SOURCE_RESULTS)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--flowsim-bin", type=Path, default=DEFAULT_FLOWSIM_BIN)
    parser.add_argument("--ns3-bin", type=Path, default=DEFAULT_NS3_BIN)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--enable-trace", action="store_true")
    parser.add_argument("--enable-monitors", action="store_true")
    parser.add_argument(
        "--target",
        action="append",
        type=parse_target,
        help="target formatted as topology:rate:seed; can be repeated",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--monitor-start-us", type=int, default=0)
    parser.add_argument("--monitor-end-us", type=int, default=700)
    parser.add_argument("--qlen-interval-us", type=int, default=10)
    parser.add_argument("--bw-interval-us", type=int, default=10)
    parser.add_argument("--qp-interval-us", type=int, default=10)
    parser.add_argument("--jct-linger-timeout", type=int, default=60)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
