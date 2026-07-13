#!/usr/bin/env python3
"""Build a compact mechanism-oriented FlowSim/NS3 mismatch summary."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FAULT_DIR = ROOT / "experiments" / "fault_tolerance"
DEFAULT_TARGET_DIR = DEFAULT_FAULT_DIR / "targeted_original_flow_mismatch"

CATEGORIES = [
    "cross_server_same_rail",
    "cross_server_cross_rail",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def to_float(value: str | int | float | None) -> float:
    if value is None:
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = value.strip()
    if not text:
        return math.nan
    return float(text)


def fmt_number(value: float | int | str | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value
    value = float(value)
    if math.isnan(value):
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.{digits}f}"


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


def load_mechanism_summary(fault_dir: Path, target_dir: Path) -> list[dict[str, float | str]]:
    fct_rows = read_rows(target_dir / "flowsim_ns3_original_fct_comparison.csv")
    monitor_rows = {row["topology"]: row for row in read_rows(fault_dir / "targeted_monitor_fault_vs_baseline.csv")}
    original_rows = {row["topology"]: row for row in read_rows(fault_dir / "ns3_original_flow_fault_vs_baseline.csv")}

    by_topology: dict[str, dict[str, float | str]] = {}
    for row in fct_rows:
        category = row["original_category"]
        if category not in CATEGORIES:
            continue
        topology = row["topology"]
        out = by_topology.setdefault(topology, {"topology": topology})
        suffix = category
        out[f"flowsim_p95_fct_{suffix}"] = to_float(row["flowsim_p95_fct"])
        out[f"ns3_grouped_p95_fct_{suffix}"] = to_float(row["ns3_grouped_p95_fct"])
        out[f"ns3_grouped_p95_over_flowsim_p95_{suffix}"] = to_float(
            row["ns3_grouped_p95_over_flowsim_p95"]
        )
        out[f"ns3_split_original_flows_{suffix}"] = to_float(row["ns3_split_original_flows"])
        out[f"ns3_avg_physical_rows_per_original_{suffix}"] = to_float(
            row["ns3_avg_physical_rows_per_original"]
        )

    monitor_keys = [
        "flowsim_jct_ratio",
        "ns3_jct_ratio",
        "ns3_send_lines_ratio",
        "max_local_nvswitch_bw_ratio",
        "max_gpu_switch_bw_ratio",
        "max_switch_switch_bw_ratio",
        "max_local_nvswitch_queue_ratio",
        "max_gpu_switch_queue_ratio",
        "max_switch_switch_queue_ratio",
        "pfc_events_fault",
        "pfc_events_baseline",
        "send_same_server_ratio",
        "send_cross_server_same_rail_ratio",
        "send_cross_server_cross_rail_ratio",
    ]
    original_keys = [
        "physical_rows_ratio",
        "split_original_flows_fault",
        "split_original_flows_baseline",
        "original_cross_rail_split_flows_fault",
        "original_cross_rail_split_flows_baseline",
        "physical_same_server_rows_ratio",
        "physical_same_rail_rows_ratio",
        "physical_cross_rail_rows_ratio",
    ]

    for topology, out in by_topology.items():
        for key in monitor_keys:
            out[key] = to_float(monitor_rows.get(topology, {}).get(key))
        for key in original_keys:
            out[key] = to_float(original_rows.get(topology, {}).get(key))

        out["flowsim_minus_ns3_jct_ratio"] = (
            to_float(out.get("flowsim_jct_ratio")) - to_float(out.get("ns3_jct_ratio"))
        )
        for category in CATEGORIES:
            ratio = to_float(out.get(f"ns3_grouped_p95_over_flowsim_p95_{category}"))
            out[f"flowsim_p95_over_ns3_grouped_p95_{category}"] = (
                1.0 / ratio if ratio > 0 else math.nan
            )

    return [by_topology[topology] for topology in sorted(by_topology)]


def write_csv(rows: list[dict[str, float | str]], path: Path) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(summary: list[dict[str, float | str]], path: Path) -> None:
    rows = []
    for row in summary:
        rows.append(
            {
                "Topology": str(row["topology"]),
                "FlowSim JCT ratio": fmt_number(row.get("flowsim_jct_ratio")),
                "NS3 JCT ratio": fmt_number(row.get("ns3_jct_ratio")),
                "FlowSim/NS3 p95 same-rail": fmt_number(
                    row.get("flowsim_p95_over_ns3_grouped_p95_cross_server_same_rail")
                ),
                "FlowSim/NS3 p95 cross-rail": fmt_number(
                    row.get("flowsim_p95_over_ns3_grouped_p95_cross_server_cross_rail")
                ),
                "NS3 physical row ratio": fmt_number(row.get("physical_rows_ratio")),
                "Fault split originals": fmt_number(row.get("split_original_flows_fault"), 0),
                "Fault cross-rail split": fmt_number(
                    row.get("original_cross_rail_split_flows_fault"), 0
                ),
                "GPU-switch queue ratio": fmt_number(row.get("max_gpu_switch_queue_ratio")),
                "Switch-switch queue ratio": fmt_number(row.get("max_switch_switch_queue_ratio")),
                "PFC events": (
                    f"{fmt_number(row.get('pfc_events_baseline'), 0)} -> "
                    f"{fmt_number(row.get('pfc_events_fault'), 0)}"
                ),
            }
        )

    markdown = [
        "# FlowSim/NS3 Mechanism Summary",
        "",
        "This table combines the targeted original-flow FCT comparison, NS3 physical-leg reconstruction, and baseline-normalized monitor data.",
        "",
        markdown_table(rows),
        "",
        "Reading guide:",
        "- `FlowSim/NS3 p95` compares FlowSim original-flow p95 FCT with NS3 physical legs grouped back to original flows.",
        "- Values above 1 mean FlowSim is slower at the same original-flow grain.",
        "- Queue ratios are fault/baseline ratios from the targeted NS3 monitor reruns.",
    ]
    path.write_text("\n".join(markdown) + "\n")


def run(args: argparse.Namespace) -> int:
    fault_dir = args.fault_dir.resolve()
    target_dir = args.target_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = load_mechanism_summary(fault_dir, target_dir)
    csv_path = output_dir / "flowsim_ns3_mechanism_summary.csv"
    md_path = output_dir / "flowsim_ns3_mechanism_summary.md"
    write_csv(summary, csv_path)
    write_markdown(summary, md_path)
    print(csv_path)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize mechanism-level FlowSim/NS3 mismatch evidence"
    )
    parser.add_argument("--fault-dir", type=Path, default=DEFAULT_FAULT_DIR)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FAULT_DIR)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
