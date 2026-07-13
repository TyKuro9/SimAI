#!/usr/bin/env python3
"""Compare NS3 original-flow leg summaries between fault and baseline runs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FAULT = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "targeted_original_flow_mismatch"
    / "ns3_original_flow_line_summary.csv"
)
DEFAULT_BASELINE = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "baseline_original_flow"
    / "ns3_original_flow_line_summary.csv"
)
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance"
TOPOLOGY_ORDER = ["Meta", "Zcube", "RO"]
COMPARE_COLUMNS = [
    "physical_rows",
    "original_flows",
    "avg_physical_rows_per_original",
    "split_original_flows",
    "original_cross_rail_split_flows",
    "original_cross_rail_with_physical_cross_rail",
    "physical_same_server_rows",
    "physical_same_rail_rows",
    "physical_cross_rail_rows",
]


def ratio(fault_value: float, baseline_value: float) -> float:
    if pd.isna(fault_value) or pd.isna(baseline_value) or float(baseline_value) == 0.0:
        return float("nan")
    return float(fault_value) / float(baseline_value)


def build_comparison(fault: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    fault = fault[fault["source"] == "send"].set_index("topology")
    baseline = baseline[baseline["source"] == "send"].set_index("topology")
    rows = []
    for topology in TOPOLOGY_ORDER:
        if topology not in fault.index or topology not in baseline.index:
            continue
        row = {"topology": topology}
        for column in COMPARE_COLUMNS:
            fault_value = fault.loc[topology, column]
            baseline_value = baseline.loc[topology, column]
            row[f"{column}_fault"] = fault_value
            row[f"{column}_baseline"] = baseline_value
            row[f"{column}_delta"] = fault_value - baseline_value
            row[f"{column}_ratio"] = ratio(fault_value, baseline_value)
        rows.append(row)
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> int:
    fault = pd.read_csv(args.fault_summary)
    baseline = pd.read_csv(args.baseline_summary)
    comparison = build_comparison(fault, baseline)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "ns3_original_flow_fault_vs_baseline.csv"
    comparison.to_csv(output, index=False)
    print(output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare NS3 original-flow fault and baseline summaries"
    )
    parser.add_argument("--fault-summary", type=Path, default=DEFAULT_FAULT)
    parser.add_argument("--baseline-summary", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
