#!/usr/bin/env python3
"""Compare FlowSim original FCT with NS3 grouped original-flow FCT."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "experiments" / "fault_tolerance" / "targeted_original_flow_mismatch"
DEFAULT_OUTPUT = DEFAULT_INPUT
CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]


def parse_node_id(token: str) -> int:
    text = str(token).strip()
    if text.startswith("0b"):
        body = text[2:]
        node_hex = body[:-2] if len(body) > 2 else body
        return int(node_hex, 16)
    return int(text, 0)


def pair_category(src: int, dst: int, gpus_per_server: int) -> str:
    if src // gpus_per_server == dst // gpus_per_server:
        return "same_server"
    if src % gpus_per_server == dst % gpus_per_server:
        return "cross_server_same_rail"
    return "cross_server_cross_rail"


def topology_gpus_per_server(path: Path) -> int:
    with path.open() as f:
        header = f.readline().split()
    if len(header) < 2:
        raise ValueError(f"invalid topology header: {path}")
    return int(header[1])


def pct(values: list[float], percentile: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def summarize_flowsim_fct(path: Path, *, gpus_per_server: int) -> pd.DataFrame:
    rows_by_category: dict[str, list[float]] = {category: [] for category in CATEGORY_ORDER}
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) < 7:
                raise ValueError(f"invalid FlowSim FCT row in {path}:{line_no}: {line!r}")
            src = parse_node_id(parts[0])
            dst = parse_node_id(parts[1])
            category = pair_category(src, dst, gpus_per_server)
            rows_by_category.setdefault(category, []).append(float(parts[6]))
    rows = []
    for category, values in rows_by_category.items():
        if not values:
            continue
        rows.append(
            {
                "original_category": category,
                "flowsim_original_flows": len(values),
                "flowsim_p50_fct": pct(values, 50),
                "flowsim_p95_fct": pct(values, 95),
                "flowsim_p99_fct": pct(values, 99),
                "flowsim_max_fct": max(values),
            }
        )
    return pd.DataFrame(rows)


def build_comparison(input_dir: Path) -> pd.DataFrame:
    target_summary = pd.read_csv(input_dir / "targeted_fct_summary.csv")
    ns3_category = pd.read_csv(input_dir / "ns3_original_flow_category_summary.csv")
    ns3_category = ns3_category[ns3_category["source"] == "fct"].copy()
    rows = []
    for _, target in target_summary.iterrows():
        topology = target["topology"]
        gpus_per_server = topology_gpus_per_server(Path(target["topology_file"]))
        flowsim = summarize_flowsim_fct(
            Path(target["flowsim_run_dir"]) / "fct.txt",
            gpus_per_server=gpus_per_server,
        )
        ns3 = ns3_category[
            (ns3_category["topology"] == topology)
            & (ns3_category["rate"] == target["rate"])
            & (ns3_category["seed"] == target["seed"])
        ].copy()
        ns3 = ns3.drop(columns=["topology", "rate", "seed", "source"], errors="ignore")
        ns3 = ns3.rename(
            columns={
                "original_flows": "ns3_original_flows",
                "physical_rows": "ns3_physical_rows",
                "avg_physical_rows_per_original": "ns3_avg_physical_rows_per_original",
                "p95_original_max_value": "ns3_grouped_p95_fct",
                "max_original_max_value": "ns3_grouped_max_fct",
                "split_original_flows": "ns3_split_original_flows",
            }
        )
        merged = flowsim.merge(ns3, on="original_category", how="outer")
        merged.insert(0, "seed", target["seed"])
        merged.insert(0, "rate", target["rate"])
        merged.insert(0, "topology", topology)
        rows.append(merged)
    out = pd.concat(rows, ignore_index=True)
    out["ns3_grouped_p95_over_flowsim_p95"] = (
        out["ns3_grouped_p95_fct"] / out["flowsim_p95_fct"]
    )
    out["ns3_grouped_max_over_flowsim_max"] = (
        out["ns3_grouped_max_fct"] / out["flowsim_max_fct"]
    )
    return out


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    comparison = build_comparison(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "flowsim_ns3_original_fct_comparison.csv"
    comparison.to_csv(output, index=False)
    print(output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare FlowSim original FCT with NS3 grouped original-flow FCT"
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
