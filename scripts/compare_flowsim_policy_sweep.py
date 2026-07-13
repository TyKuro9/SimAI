#!/usr/bin/env python3
"""Compare one FlowSim policy sweep against original FlowSim and NS3."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FT_DIR = ROOT / "experiments" / "fault_tolerance"
DEFAULT_ORIGINAL = FT_DIR / "flowsim_256_alltoall_p01_p15_s10_chain" / "random_link_failure_summary.csv"
DEFAULT_NS3 = FT_DIR / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix" / "random_link_failure_summary.csv"
DEFAULT_POLICY = FT_DIR / "flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full" / "random_link_failure_summary.csv"
DEFAULT_OUTPUT = FT_DIR / "flowsim_crossrail_w03_full_comparison"

TOPOLOGY_ORDER = {
    "ROFT": 0,
    "HPN": 1,
    "DeepSeek": 2,
    "Meta": 3,
    "Zcube": 4,
    "RO": 5,
}


def default_rates() -> list[float]:
    return [i / 100.0 for i in range(1, 16)]


def parse_rates(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def load_summary(
    path: Path, *, topologies: set[str] | None, rates: set[float] | None
) -> dict[tuple[str, float], dict[str, float | str]]:
    out: dict[tuple[str, float], dict[str, float | str]] = {}
    for row in read_rows(path):
        topology = row["topology"]
        rate = round(float(row["link_failure_probability"]), 8)
        if topologies and topology not in topologies:
            continue
        if rates and rate not in rates:
            continue
        normal = float(row["normal_jct_mean"])
        failed = float(row["failed_jct_mean"])
        out[(topology, rate)] = {
            "normal": normal,
            "failed": failed,
            "factor": failed / normal if normal else math.nan,
            "num_samples": int(row["num_samples"]),
            "num_success": int(row["num_success"]),
            "success": f"{row['num_success']}/{row['num_samples']}",
        }
    return out


def ordered_keys(keys: set[tuple[str, float]]) -> list[tuple[str, float]]:
    return sorted(keys, key=lambda item: (TOPOLOGY_ORDER.get(item[0], 99), item[0], item[1]))


def build_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    rates = {round(rate, 8) for rate in args.rates} if args.rates else None
    topologies = set(args.topologies) if args.topologies else None
    original = load_summary(args.original, topologies=topologies, rates=rates)
    ns3 = load_summary(args.ns3, topologies=topologies, rates=rates)
    policy = load_summary(args.policy, topologies=topologies, rates=rates)
    keys = set(original) & set(ns3) & set(policy)
    rows: list[dict[str, object]] = []

    for key in ordered_keys(keys):
        topology, rate = key
        orig_row = original[key]
        ns3_row = ns3[key]
        policy_row = policy[key]
        ns3_factor = float(ns3_row["factor"])
        orig_factor = float(orig_row["factor"])
        policy_factor = float(policy_row["factor"])
        ns3_failed = float(ns3_row["failed"])
        orig_failed = float(orig_row["failed"])
        policy_failed = float(policy_row["failed"])
        policy_num_samples = int(policy_row["num_samples"])
        policy_num_success = int(policy_row["num_success"])
        policy_complete = (
            policy_num_samples >= args.min_samples
            and policy_num_success >= args.min_samples
        )
        if args.complete_only and not policy_complete:
            continue
        rows.append(
            {
                "topology": topology,
                "rate": rate,
                "ns3_factor": ns3_factor,
                "orig_factor": orig_factor,
                "policy_factor": policy_factor,
                "orig_factor_abs_error": abs(orig_factor - ns3_factor),
                "policy_factor_abs_error": abs(policy_factor - ns3_factor),
                "factor_error_delta": abs(policy_factor - ns3_factor)
                - abs(orig_factor - ns3_factor),
                "ns3_failed_jct": ns3_failed,
                "orig_failed_jct": orig_failed,
                "policy_failed_jct": policy_failed,
                "orig_failed_abs_error": abs(orig_failed - ns3_failed),
                "policy_failed_abs_error": abs(policy_failed - ns3_failed),
                "failed_error_delta": abs(policy_failed - ns3_failed)
                - abs(orig_failed - ns3_failed),
                "policy_num_samples": policy_num_samples,
                "policy_num_success": policy_num_success,
                "policy_complete": policy_complete,
                "policy_success": policy_row["success"],
            }
        )
    return rows


def aggregate_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["topology"])].append(row)

    out: list[dict[str, object]] = []
    for topology, group in sorted(
        grouped.items(), key=lambda item: (TOPOLOGY_ORDER.get(item[0], 99), item[0])
    ):
        out.append(
            {
                "topology": topology,
                "num_rates": len(group),
                "orig_factor_mae": mean_float(group, "orig_factor_abs_error"),
                "policy_factor_mae": mean_float(group, "policy_factor_abs_error"),
                "factor_mae_delta": mean_float(group, "factor_error_delta"),
                "orig_failed_jct_mae": mean_float(group, "orig_failed_abs_error"),
                "policy_failed_jct_mae": mean_float(group, "policy_failed_abs_error"),
                "failed_jct_mae_delta": mean_float(group, "failed_error_delta"),
            }
        )
    return out


def mean_float(rows: list[dict[str, object]], key: str) -> float:
    values = [float(row[key]) for row in rows]
    return sum(values) / len(values) if values else math.nan


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


def write_markdown(
    *,
    rows: list[dict[str, object]],
    aggregate: list[dict[str, object]],
    args: argparse.Namespace,
    path: Path,
) -> None:
    aggregate_table = []
    for row in aggregate:
        aggregate_table.append(
            {
                "Topology": str(row["topology"]),
                "Rates": str(row["num_rates"]),
                "Orig factor MAE": fmt(row["orig_factor_mae"]),
                "Policy factor MAE": fmt(row["policy_factor_mae"]),
                "Factor delta": fmt(row["factor_mae_delta"]),
                "Orig JCT MAE": fmt(row["orig_failed_jct_mae"], 1),
                "Policy JCT MAE": fmt(row["policy_failed_jct_mae"], 1),
                "JCT delta": fmt(row["failed_jct_mae_delta"], 1),
            }
        )

    detail_table = []
    for row in rows:
        detail_table.append(
            {
                "Topology": str(row["topology"]),
                "Rate": fmt(row["rate"], 2),
                "NS3 factor": fmt(row["ns3_factor"]),
                "Orig factor": fmt(row["orig_factor"]),
                "Policy factor": fmt(row["policy_factor"]),
                "NS3 JCT": fmt(row["ns3_failed_jct"], 1),
                "Orig JCT": fmt(row["orig_failed_jct"], 1),
                "Policy JCT": fmt(row["policy_failed_jct"], 1),
                "Complete": str(row["policy_complete"]),
                "Success": str(row["policy_success"]),
            }
        )

    content = [
        f"# {args.policy_label} FlowSim Policy Sweep Comparison",
        "",
        "## Topology Aggregate",
        "",
        markdown_table(aggregate_table),
        "",
        "## Rate Detail",
        "",
        markdown_table(detail_table),
        "",
        "Notes:",
        "- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.",
        "- Negative deltas mean the policy is closer to NS3 than original FlowSim.",
        f"- A complete policy row requires at least {args.min_samples} successful samples.",
        f"- Policy summary: `{args.policy}`",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    rows = build_rows(args)
    aggregate = aggregate_rows(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    detail_csv = args.output_dir / f"{args.output_prefix}_detail.csv"
    aggregate_csv = args.output_dir / f"{args.output_prefix}_aggregate.csv"
    md_path = args.output_dir / f"{args.output_prefix}.md"
    write_csv(rows, detail_csv)
    write_csv(aggregate, aggregate_csv)
    write_markdown(rows=rows, aggregate=aggregate, args=args, path=md_path)
    print(detail_csv)
    print(aggregate_csv)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one FlowSim policy sweep")
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--ns3", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-prefix", default="flowsim_policy_comparison")
    parser.add_argument("--policy-label", default="w0.3 cross-rail")
    parser.add_argument("--topologies", nargs="*", default=None)
    parser.add_argument("--rates", type=parse_rates, default=default_rates())
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--complete-only", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
