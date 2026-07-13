#!/usr/bin/env python3
"""Analyze FlowSim bottleneck trace files."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "experiments" / "fault_tolerance" / "flowsim_bottleneck_trace"

LINK_CATEGORIES = [
    "local_nvswitch",
    "gpu_switch",
    "switch_switch",
    "other",
]
FLOW_CATEGORIES = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def pair_category(src: int, dst: int, gpus_per_server: int) -> str:
    if src // gpus_per_server == dst // gpus_per_server:
        return "same_server"
    if src % gpus_per_server == dst % gpus_per_server:
        return "cross_server_same_rail"
    return "cross_server_cross_rail"


def read_trace(path: Path, *, gpus_per_server: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            src = int(row["src"])
            dst = int(row["dst"])
            cross_server = src // gpus_per_server != dst // gpus_per_server
            same_rail = src % gpus_per_server == dst % gpus_per_server
            rows.append(
                {
                    "time_ns": float(row["time_ns"]),
                    "src": src,
                    "dst": dst,
                    "rate": float(row["rate"]),
                    "bottleneck_rate": float(row["bottleneck_rate"]),
                    "bottleneck_category": row["bottleneck_category"],
                    "flow_category": pair_category(src, dst, gpus_per_server),
                    "path_hops": int(row["path_hops"]),
                    "pxn_generated": int(row.get("pxn_generated", "0") or 0),
                    "cross_server": int(row.get("cross_server", int(cross_server)) or 0),
                    "same_rail": int(row.get("same_rail", int(same_rail)) or 0),
                    "path_weight": float(row.get("path_weight", "1.0") or 1.0),
                    "bottleneck_active_chunks": float(
                        row.get("bottleneck_active_chunks", "nan") or math.nan
                    ),
                    "bottleneck_total_weight": float(
                        row.get("bottleneck_total_weight", "nan") or math.nan
                    ),
                }
            )
    return rows


def summarize_scope(run: str, scope: str, rows: list[dict[str, object]]) -> dict[str, object]:
    times = [float(row["time_ns"]) for row in rows]
    rates = [float(row["bottleneck_rate"]) for row in rows]
    path_weights = [float(row["path_weight"]) for row in rows]
    active_chunks = [
        float(row["bottleneck_active_chunks"])
        for row in rows
        if not math.isnan(float(row["bottleneck_active_chunks"]))
    ]
    total_weights = [
        float(row["bottleneck_total_weight"])
        for row in rows
        if not math.isnan(float(row["bottleneck_total_weight"]))
    ]
    link_counts = Counter(str(row["bottleneck_category"]) for row in rows)
    flow_counts = Counter(str(row["flow_category"]) for row in rows)
    pxn_rows = sum(1 for row in rows if int(row["pxn_generated"]) == 1)
    same_rail_rows = sum(1 for row in rows if int(row["same_rail"]) == 1)
    out: dict[str, object] = {
        "run": run,
        "scope": scope,
        "rows": len(rows),
        "time_p50": percentile(times, 50),
        "time_p95": percentile(times, 95),
        "time_p99": percentile(times, 99),
        "time_max": max(times) if times else math.nan,
        "bottleneck_rate_p50": percentile(rates, 50),
        "bottleneck_rate_p95": percentile(rates, 95),
        "path_weight_mean": sum(path_weights) / len(path_weights) if path_weights else math.nan,
        "path_weight_p50": percentile(path_weights, 50),
        "path_weight_p95": percentile(path_weights, 95),
        "bottleneck_active_chunks_p50": percentile(active_chunks, 50),
        "bottleneck_active_chunks_p95": percentile(active_chunks, 95),
        "bottleneck_total_weight_p50": percentile(total_weights, 50),
        "bottleneck_total_weight_p95": percentile(total_weights, 95),
        "pxn_generated_rows": pxn_rows,
        "pxn_generated_frac": pxn_rows / len(rows) if rows else math.nan,
        "same_rail_rows": same_rail_rows,
        "same_rail_frac": same_rail_rows / len(rows) if rows else math.nan,
    }
    for category in LINK_CATEGORIES:
        count = link_counts.get(category, 0)
        out[f"bottleneck_{category}_rows"] = count
        out[f"bottleneck_{category}_frac"] = count / len(rows) if rows else math.nan
    for category in FLOW_CATEGORIES:
        count = flow_counts.get(category, 0)
        out[f"physical_{category}_rows"] = count
        out[f"physical_{category}_frac"] = count / len(rows) if rows else math.nan
    return out


def analyze_run(run_dir: Path, *, gpus_per_server: int) -> list[dict[str, object]]:
    trace = run_dir / "bottleneck_trace.csv"
    rows = read_trace(trace, gpus_per_server=gpus_per_server)
    time_p95 = percentile([float(row["time_ns"]) for row in rows], 95)
    time_p99 = percentile([float(row["time_ns"]) for row in rows], 99)
    return [
        summarize_scope(run_dir.name, "all", rows),
        summarize_scope(
            run_dir.name,
            "tail_p95_time",
            [row for row in rows if float(row["time_ns"]) >= time_p95],
        ),
        summarize_scope(
            run_dir.name,
            "tail_p99_time",
            [row for row in rows if float(row["time_ns"]) >= time_p99],
        ),
    ]


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


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, object]], path: Path) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            {
                "Run": str(row["run"]),
                "Scope": str(row["scope"]),
                "Rows": fmt(row["rows"], 0),
                "Time p95": fmt(row["time_p95"], 0),
                "Time max": fmt(row["time_max"], 0),
                "Local NVSwitch": fmt(float(row["bottleneck_local_nvswitch_frac"]) * 100),
                "GPU-switch": fmt(float(row["bottleneck_gpu_switch_frac"]) * 100),
                "Switch-switch": fmt(float(row["bottleneck_switch_switch_frac"]) * 100),
                "PXN": fmt(float(row["pxn_generated_frac"]) * 100),
                "Same rail": fmt(float(row["same_rail_frac"]) * 100),
                "Physical cross-rail": fmt(
                    float(row["physical_cross_server_cross_rail_frac"]) * 100
                ),
                "Path weight mean": fmt(row["path_weight_mean"]),
                "Total weight p50": fmt(row["bottleneck_total_weight_p50"]),
                "Total weight p95": fmt(row["bottleneck_total_weight_p95"]),
            }
        )
    content = [
        "# FlowSim Bottleneck Trace Summary",
        "",
        "Percent columns are fractions of rows in each scope.",
        "",
        markdown_table(table_rows),
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    rows: list[dict[str, object]] = []
    for run_dir in sorted(path for path in input_dir.iterdir() if path.is_dir()):
        if (run_dir / "bottleneck_trace.csv").exists():
            rows.extend(analyze_run(run_dir, gpus_per_server=args.gpus_per_server))
    if not rows:
        raise SystemExit(f"no bottleneck traces found under {input_dir}")
    csv_path = input_dir / "flowsim_bottleneck_trace_summary.csv"
    md_path = input_dir / "flowsim_bottleneck_trace_summary.md"
    write_csv(rows, csv_path)
    write_markdown(rows, md_path)
    print(csv_path)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze FlowSim bottleneck traces")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--gpus-per-server", type=int, default=8)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
