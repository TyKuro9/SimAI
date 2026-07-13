#!/usr/bin/env python3
"""Run targeted FlowSim calibration for PXN-decomposed legs."""

from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance" / "flowsim_pxn_leg_calibration"
DEFAULT_WORKLOAD = ROOT / "my_workloads" / "synthetic_alltoall_global_world_size256_1MiB.txt"
DEFAULT_FLOWSIM_BIN = Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim")
DEFAULT_RATE_LABEL = "p0p15"
DEFAULT_SEED = 1


TOPOLOGIES = {
    "DeepSeek": {
        "baseline_topology": ROOT / "mytopo" / "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
        "failed_topology": ROOT
        / "experiments"
        / "fault_tolerance"
        / "flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full"
        / "generated_topologies"
        / "DeepSeek"
        / DEFAULT_RATE_LABEL
        / f"seed{DEFAULT_SEED}.topo",
        "ns3_baseline": ROOT
        / "experiments"
        / "fault_tolerance"
        / "ns3_256_alltoall_p01_p15_s10_chain"
        / "runs"
        / "DeepSeek"
        / "baseline"
        / "EndToEnd.csv",
        "ns3_failed": ROOT
        / "experiments"
        / "fault_tolerance"
        / "ns3_256_alltoall_p01_p15_s10_chain"
        / "runs"
        / "DeepSeek"
        / DEFAULT_RATE_LABEL
        / f"seed{DEFAULT_SEED}"
        / "EndToEnd.csv",
    },
    "RO": {
        "baseline_topology": ROOT / "mytopo" / "RailOnly_256g_8gps_p16a0.5_400Gbps_H100",
        "failed_topology": ROOT
        / "experiments"
        / "fault_tolerance"
        / "flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full"
        / "generated_topologies"
        / "RO"
        / DEFAULT_RATE_LABEL
        / f"seed{DEFAULT_SEED}.topo",
        "ns3_baseline": ROOT
        / "experiments"
        / "fault_tolerance"
        / "ns3_256_alltoall_p01_p15_s10_chain"
        / "runs"
        / "RO"
        / "baseline"
        / "EndToEnd.csv",
        "ns3_failed": ROOT
        / "experiments"
        / "fault_tolerance"
        / "ns3_256_alltoall_p01_p15_s10_chain"
        / "runs"
        / "RO"
        / DEFAULT_RATE_LABEL
        / f"seed{DEFAULT_SEED}"
        / "EndToEnd.csv",
    },
}


@dataclass(frozen=True)
class Variant:
    name: str
    local: float = 1.0
    gpu: float = 1.0
    switch: float = 1.0
    cross: float = 1.0
    pxn_same_rail: float = 1.0
    timing: str = "serial"


DEFAULT_VARIANTS = [
    Variant("default"),
    Variant("localx2", local=2.0),
    Variant("switchx2", switch=2.0),
    Variant("localx2_switchx2", local=2.0, switch=2.0),
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def read_total_time(path: Path) -> Optional[float]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    rows = read_rows(path)
    if not rows:
        return None
    normalized = {key.strip(): value.strip() for key, value in rows[0].items()}
    value = normalized.get("Total time")
    return float(value) if value else None


def parse_csv_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_variant(text: str) -> Variant:
    parts = text.split(":")
    name = parts[0].strip()
    if not name:
        raise argparse.ArgumentTypeError("variant name cannot be empty")
    values = {
        "local": 1.0,
        "gpu": 1.0,
        "switch": 1.0,
        "cross": 1.0,
        "pxn_same_rail": 1.0,
    }
    timing = "serial"
    if len(parts) > 2:
        raise argparse.ArgumentTypeError(f"invalid variant: {text}")
    if len(parts) == 2:
        for item in parse_csv_list(parts[1]):
            if "=" not in item:
                raise argparse.ArgumentTypeError(f"invalid variant item: {item}")
            key, raw_value = [piece.strip() for piece in item.split("=", 1)]
            if key == "timing":
                timing = raw_value.lower()
                if timing not in {"serial", "overlap"}:
                    raise argparse.ArgumentTypeError(
                        "timing must be either serial or overlap"
                    )
                continue
            if key not in values:
                raise argparse.ArgumentTypeError(f"unknown variant key: {key}")
            value = float(raw_value)
            if value <= 0.0 or not math.isfinite(value):
                raise argparse.ArgumentTypeError("variant values must be positive finite numbers")
            values[key] = value
    return Variant(name=name, timing=timing, **values)


def fmt_float(value: float) -> str:
    return f"{value:g}"


def variant_env(base: dict[str, str], variant: Variant) -> dict[str, str]:
    env = dict(base)
    env["FLOWSIM_LOCAL_NVSWITCH_BW_MULTIPLIER"] = fmt_float(variant.local)
    env["FLOWSIM_GPU_SWITCH_BW_MULTIPLIER"] = fmt_float(variant.gpu)
    env["FLOWSIM_SWITCH_SWITCH_BW_MULTIPLIER"] = fmt_float(variant.switch)
    env["FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT"] = fmt_float(variant.cross)
    env["FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT"] = fmt_float(variant.pxn_same_rail)
    env["FLOWSIM_PXN_TIMING"] = variant.timing
    return env


def build_base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["AS_SEND_LAT"] = env.get("AS_SEND_LAT", "3")
    env["AS_NVLS_ENABLE"] = env.get("AS_NVLS_ENABLE", "0")
    env["AS_PXN_ENABLE"] = env.get("AS_PXN_ENABLE", "1")
    env["AS_PXN_POLICY"] = env.get("AS_PXN_POLICY", "fallback")
    env["FLOWSIM_WRITE_FCT"] = "0"
    return env


def run_flowsim(
    *,
    flowsim_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    timeout: Optional[int],
    resume: bool,
    env: dict[str, str],
) -> Optional[float]:
    existing = read_total_time(output_dir / "EndToEnd.csv")
    if resume and existing is not None:
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
        try:
            subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            log.write(f"\n[TIMEOUT] exceeded {timeout} seconds\n")
            return None
    return read_total_time(output_dir / "EndToEnd.csv")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def row_timing(row: dict[str, object]) -> str:
    return str(row.get("pxn_timing", "serial") or "serial")


def row_key(row: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row["topology"]),
        str(row["variant"]),
        row_timing(row),
        str(row["run_kind"]),
    )


def dedupe_raw_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in rows:
        by_key[row_key(row)] = row
    return list(by_key.values())


def numeric_value(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "missing":
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def ratio(numerator: Optional[float], denominator: Optional[float]) -> object:
    if numerator is None or denominator is None or denominator == 0:
        return "missing"
    return numerator / denominator


def abs_error(value: Optional[float], target: Optional[float]) -> object:
    if value is None or target is None:
        return "missing"
    return abs(value - target)


def task_row(
    *,
    topology: str,
    variant: Variant,
    run_kind: str,
    run_dir: Path,
) -> dict[str, object]:
    return {
        "topology": topology,
        "variant": variant.name,
        "run_kind": run_kind,
        "local_nvswitch_multiplier": variant.local,
        "gpu_switch_multiplier": variant.gpu,
        "switch_switch_multiplier": variant.switch,
        "cross_rail_switch_switch_weight": variant.cross,
        "pxn_same_rail_switch_switch_weight": variant.pxn_same_rail,
        "pxn_timing": variant.timing,
        "run_dir": str(run_dir),
    }


def run_one(
    *,
    topology: str,
    variant: Variant,
    run_kind: str,
    topology_file: Path,
    run_dir: Path,
    args: argparse.Namespace,
    base_env: dict[str, str],
) -> dict[str, object]:
    print(f"[FLOWSIM] {topology} {variant.name} {run_kind}", flush=True)
    jct = run_flowsim(
        flowsim_bin=args.flowsim_bin,
        workload=args.workload,
        topology=topology_file,
        output_dir=run_dir,
        threads=args.threads,
        timeout=args.timeout,
        resume=args.resume,
        env=variant_env(base_env, variant),
    )
    row = task_row(topology=topology, variant=variant, run_kind=run_kind, run_dir=run_dir)
    row["jct"] = jct if jct is not None else "missing"
    row["status"] = "success" if jct is not None else "failed"
    return row


def combine_rows(raw_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in dedupe_raw_rows(raw_rows):
        timing = row_timing(row)
        key = (str(row["topology"]), str(row["variant"]), timing)
        combined = by_key.setdefault(
            key,
            {
                "topology": row["topology"],
                "variant": row["variant"],
                "local_nvswitch_multiplier": row["local_nvswitch_multiplier"],
                "gpu_switch_multiplier": row["gpu_switch_multiplier"],
                "switch_switch_multiplier": row["switch_switch_multiplier"],
                "cross_rail_switch_switch_weight": row["cross_rail_switch_switch_weight"],
                "pxn_same_rail_switch_switch_weight": row.get(
                    "pxn_same_rail_switch_switch_weight", 1.0
                ),
                "pxn_timing": timing,
            },
        )
        prefix = str(row["run_kind"])
        combined[f"{prefix}_jct"] = row["jct"]
        combined[f"{prefix}_run_dir"] = row["run_dir"]
        combined[f"{prefix}_status"] = row["status"]

    out: list[dict[str, object]] = []
    for row in by_key.values():
        config = TOPOLOGIES[str(row["topology"])]
        ns3_baseline = read_total_time(Path(config["ns3_baseline"]))
        ns3_failed = read_total_time(Path(config["ns3_failed"]))
        baseline = row.get("baseline_jct")
        failed = row.get("failed_jct")
        baseline_float = numeric_value(baseline)
        failed_float = numeric_value(failed)
        ns3_factor = ratio(ns3_failed, ns3_baseline)
        flowsim_factor = ratio(failed_float, baseline_float)
        row["ns3_baseline_jct"] = ns3_baseline if ns3_baseline is not None else "missing"
        row["ns3_failed_jct"] = ns3_failed if ns3_failed is not None else "missing"
        row["ns3_factor"] = ns3_factor
        row["flowsim_factor"] = flowsim_factor
        row["baseline_abs_error"] = abs_error(baseline_float, ns3_baseline)
        row["failed_abs_error"] = abs_error(failed_float, ns3_failed)
        if isinstance(flowsim_factor, float) and isinstance(ns3_factor, float):
            row["factor_abs_error"] = abs(flowsim_factor - ns3_factor)
        else:
            row["factor_abs_error"] = "missing"
        out.append(row)
    return sorted(out, key=lambda r: (str(r["topology"]), str(r["variant"]), str(r["pxn_timing"])))


def fmt(value: object, digits: int = 3) -> str:
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if math.isnan(number):
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:.{digits}f}"


def markdown_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    widths = {
        header: max(len(header), *(len(str(row.get(header, ""))) for row in rows))
        for header in headers
    }
    lines = []
    lines.append("| " + " | ".join(header.ljust(widths[header]) for header in headers) + " |")
    lines.append("| " + " | ".join("-" * widths[header] for header in headers) + " |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)
            + " |"
        )
    return "\n".join(lines)


def write_markdown(path: Path, rows: list[dict[str, object]]) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            {
                "Topology": str(row["topology"]),
                "Variant": str(row["variant"]),
                "Timing": str(row["pxn_timing"]),
                "Local": fmt(row["local_nvswitch_multiplier"]),
                "Switch": fmt(row["switch_switch_multiplier"]),
                "PXN same-rail": fmt(row.get("pxn_same_rail_switch_switch_weight", 1.0)),
                "Baseline": fmt(row.get("baseline_jct")),
                "Failed": fmt(row.get("failed_jct")),
                "NS3 failed": fmt(row.get("ns3_failed_jct")),
                "Factor": fmt(row.get("flowsim_factor")),
                "NS3 factor": fmt(row.get("ns3_factor")),
                "Failed err": fmt(row.get("failed_abs_error"), 1),
                "Factor err": fmt(row.get("factor_abs_error")),
            }
        )
    content = [
        "# FlowSim PXN-Leg Calibration",
        "",
        markdown_table(table_rows),
        "",
        "Notes:",
        "- Variants use FlowSim diagnostic bandwidth multipliers for link categories.",
        "- The failed topology is the 15% link-failure seed1 topology from the full fault sweep.",
        "- This is a targeted sensitivity test, not a proposed physical bandwidth change.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = args.output_dir / "pxn_leg_calibration_raw.csv"
    summary_csv = args.output_dir / "pxn_leg_calibration_summary.csv"
    summary_md = args.output_dir / "pxn_leg_calibration_summary.md"
    base_env = build_base_env()
    variants = args.variant or DEFAULT_VARIANTS
    raw_rows: list[dict[str, object]] = []
    if args.resume and raw_csv.exists() and raw_csv.stat().st_size > 0:
        raw_rows.extend(read_rows(raw_csv))
    completed = {
        row_key(row)
        for row in raw_rows
        if str(row.get("status", "")) == "success"
    }
    tasks = []

    for topology in args.topologies:
        if topology not in TOPOLOGIES:
            raise SystemExit(f"unknown topology: {topology}")
        config = TOPOLOGIES[topology]
        for key in ("baseline_topology", "failed_topology", "ns3_baseline", "ns3_failed"):
            path = Path(config[key])
            if not path.exists():
                raise SystemExit(f"missing {topology} {key}: {path}")
        for variant in variants:
            for run_kind, topology_file in (
                ("baseline", Path(config["baseline_topology"])),
                ("failed", Path(config["failed_topology"])),
            ):
                run_dir = args.output_dir / topology / variant.name / run_kind
                key = (topology, variant.name, variant.timing, run_kind)
                if args.resume and key in completed:
                    continue
                tasks.append(
                    {
                        "topology": topology,
                        "variant": variant,
                        "run_kind": run_kind,
                        "topology_file": topology_file,
                        "run_dir": run_dir,
                    }
                )

    if args.jobs == 1:
        for task in tasks:
            raw_rows.append(run_one(args=args, base_env=base_env, **task))
            raw_rows = dedupe_raw_rows(raw_rows)
            write_csv(raw_csv, raw_rows)
            write_csv(summary_csv, combine_rows(raw_rows))
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_one, args=args, base_env=base_env, **task): task
                for task in tasks
            }
            for future in as_completed(futures):
                raw_rows.append(future.result())
                raw_rows = dedupe_raw_rows(raw_rows)
                write_csv(raw_csv, raw_rows)
                write_csv(summary_csv, combine_rows(raw_rows))

    raw_rows = dedupe_raw_rows(raw_rows)
    summary_rows = combine_rows(raw_rows)
    write_csv(raw_csv, raw_rows)
    write_csv(summary_csv, summary_rows)
    write_markdown(summary_md, summary_rows)
    print(summary_csv)
    print(summary_md)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run targeted FlowSim calibration for PXN-decomposed legs"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--flowsim-bin", type=Path, default=DEFAULT_FLOWSIM_BIN)
    parser.add_argument(
        "--topologies",
        nargs="*",
        choices=sorted(TOPOLOGIES.keys()),
        default=["DeepSeek", "RO"],
    )
    parser.add_argument(
        "--variant",
        action="append",
        type=parse_variant,
        help=(
            "variant definition like name:local=2,switch=1,gpu=1,cross=1,"
            "pxn_same_rail=1,timing=serial; "
            "can be repeated"
        ),
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
