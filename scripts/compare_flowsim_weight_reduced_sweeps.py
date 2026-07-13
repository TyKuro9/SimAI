#!/usr/bin/env python3
"""Compare reduced FlowSim weight sweeps against original FlowSim and NS3."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FT_DIR = ROOT / "experiments" / "fault_tolerance"
DEFAULT_ORIGINAL = FT_DIR / "flowsim_256_alltoall_p01_p15_s10_chain" / "random_link_failure_summary.csv"
DEFAULT_NS3 = FT_DIR / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix" / "random_link_failure_summary.csv"
DEFAULT_W03 = FT_DIR / "flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w03" / "random_link_failure_summary.csv"
DEFAULT_W04 = FT_DIR / "flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w04" / "random_link_failure_summary.csv"
DEFAULT_OUTPUT = FT_DIR / "flowsim_crossrail_weight_reduced_comparison"

TOPOLOGY_ORDER = {"Meta": 0, "Zcube": 1, "RO": 2}
RATE_ORDER = [0.01, 0.05, 0.10, 0.15]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def load_summary(path: Path, *, topologies: set[str], rates: set[float]) -> dict[tuple[str, float], dict[str, float | str]]:
    out: dict[tuple[str, float], dict[str, float | str]] = {}
    for row in read_rows(path):
        topology = row["topology"]
        rate = round(float(row["link_failure_probability"]), 8)
        if topology not in topologies or rate not in rates:
            continue
        normal = float(row["normal_jct_mean"])
        failed = float(row["failed_jct_mean"])
        out[(topology, rate)] = {
            "normal": normal,
            "failed": failed,
            "factor": failed / normal if normal else math.nan,
            "success": f"{row['num_success']}/{row['num_samples']}",
        }
    return out


def build_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    topologies = set(args.topologies)
    rates = {round(rate, 8) for rate in args.rates}
    original = load_summary(args.original, topologies=topologies, rates=rates)
    ns3 = load_summary(args.ns3, topologies=topologies, rates=rates)
    w03 = load_summary(args.w03, topologies=topologies, rates=rates)
    w04 = load_summary(args.w04, topologies=topologies, rates=rates)

    rows: list[dict[str, object]] = []
    for topology in sorted(topologies, key=lambda item: TOPOLOGY_ORDER.get(item, 99)):
        for rate in sorted(rates):
            key = (topology, rate)
            if key not in original or key not in ns3 or key not in w03 or key not in w04:
                continue
            ns3_row = ns3[key]
            orig_row = original[key]
            w03_row = w03[key]
            w04_row = w04[key]
            ns3_factor = float(ns3_row["factor"])
            ns3_failed = float(ns3_row["failed"])
            row: dict[str, object] = {
                "topology": topology,
                "rate": rate,
                "ns3_factor": ns3_factor,
                "orig_factor": orig_row["factor"],
                "w03_factor": w03_row["factor"],
                "w04_factor": w04_row["factor"],
                "orig_factor_abs_error": abs(float(orig_row["factor"]) - ns3_factor),
                "w03_factor_abs_error": abs(float(w03_row["factor"]) - ns3_factor),
                "w04_factor_abs_error": abs(float(w04_row["factor"]) - ns3_factor),
                "ns3_failed_jct": ns3_failed,
                "orig_failed_jct": orig_row["failed"],
                "w03_failed_jct": w03_row["failed"],
                "w04_failed_jct": w04_row["failed"],
                "orig_failed_abs_error": abs(float(orig_row["failed"]) - ns3_failed),
                "w03_failed_abs_error": abs(float(w03_row["failed"]) - ns3_failed),
                "w04_failed_abs_error": abs(float(w04_row["failed"]) - ns3_failed),
                "w03_success": w03_row["success"],
                "w04_success": w04_row["success"],
            }
            rows.append(row)
    return rows


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
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


def fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "n/a"
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


def write_markdown(rows: list[dict[str, object]], path: Path) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            {
                "Topology": str(row["topology"]),
                "Rate": fmt(row["rate"], 2),
                "NS3 factor": fmt(row["ns3_factor"]),
                "Orig factor": fmt(row["orig_factor"]),
                "w0.3 factor": fmt(row["w03_factor"]),
                "w0.4 factor": fmt(row["w04_factor"]),
                "NS3 JCT": fmt(row["ns3_failed_jct"], 1),
                "Orig JCT": fmt(row["orig_failed_jct"], 1),
                "w0.3 JCT": fmt(row["w03_failed_jct"], 1),
                "w0.4 JCT": fmt(row["w04_failed_jct"], 1),
            }
        )

    content = [
        "# FlowSim Cross-Rail Weight Reduced Sweep Comparison",
        "",
        markdown_table(table_rows),
        "",
        "Notes:",
        "- Factors are `failed_jct_mean / normal_jct_mean` within each simulator/run.",
        "- Original FlowSim and NS3 use their existing 1%-15%, 10-seed summaries.",
        "- `w0.3` and `w0.4` are reduced sweeps on Meta, Zcube, and RO at 1%, 5%, 10%, and 15%.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    rows = build_rows(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "flowsim_crossrail_weight_reduced_comparison.csv"
    md_path = args.output_dir / "flowsim_crossrail_weight_reduced_comparison.md"
    write_csv(rows, csv_path)
    write_markdown(rows, md_path)
    print(csv_path)
    print(md_path)
    return 0


def parse_rates(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare reduced FlowSim cross-rail weight sweeps"
    )
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--ns3", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--w03", type=Path, default=DEFAULT_W03)
    parser.add_argument("--w04", type=Path, default=DEFAULT_W04)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--topologies", nargs="*", default=["Meta", "Zcube", "RO"])
    parser.add_argument("--rates", type=parse_rates, default=RATE_ORDER)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
