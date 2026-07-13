#!/usr/bin/env python3
"""Compare targeted FlowSim fault policies against NS3.

The runner can split one topology/rate across different fault_env_class values.
This script reads raw or summary CSVs and collapses them back to topology/rate
before computing policy errors.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
FT_DIR = ROOT / "experiments" / "fault_tolerance"

DEFAULT_NEW = (
    FT_DIR
    / "flowsim_256_alltoall_targeted_highstretch_hop4w016_directw018_threshold103_p01_p05_p10_p15_s3"
    / "random_link_failure_raw.csv"
)
DEFAULT_FAULT = (
    FT_DIR
    / "flowsim_256_alltoall_targeted_faultonly_hop4w020_directw020_p01_p05_p10_p15_s3"
    / "random_link_failure_raw.csv"
)
DEFAULT_CANDIDATE = (
    FT_DIR
    / "flowsim_256_alltoall_targeted_hop4w025_directw022_p01_p05_p10_p15_s3"
    / "random_link_failure_raw.csv"
)
DEFAULT_PREVIOUS = (
    FT_DIR
    / "flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full"
    / "random_link_failure_summary.csv"
)
DEFAULT_NS3 = (
    FT_DIR
    / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix"
    / "random_link_failure_summary.csv"
)
DEFAULT_OUTPUT = FT_DIR / "flowsim_targeted_highstretch_hop4w016_directw018_comparison"

TOPOLOGY_ORDER = {
    "ROFT": 0,
    "HPN": 1,
    "DeepSeek": 2,
    "Meta": 3,
    "Zcube": 4,
    "RO": 5,
}


def default_rates() -> List[float]:
    return [0.01, 0.05, 0.10, 0.15]


def parse_rates(value: str) -> List[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def numeric(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        out = float(value)
    else:
        text = str(value).strip()
        if not text or text == "missing":
            return None
        try:
            out = float(text)
        except ValueError:
            return None
    if math.isnan(out):
        return None
    return out


def load_dataset(
    path: Path,
    *,
    topologies: Optional[set[str]],
    rates: Optional[set[float]],
) -> Dict[Tuple[str, float], Dict[str, object]]:
    rows = read_rows(path)
    if not rows:
        return {}
    if "normal_jct_mean" in rows[0]:
        return load_summary_rows(rows, topologies=topologies, rates=rates)
    return load_raw_rows(rows, topologies=topologies, rates=rates)


def load_summary_rows(
    rows: Sequence[Dict[str, str]],
    *,
    topologies: Optional[set[str]],
    rates: Optional[set[float]],
) -> Dict[Tuple[str, float], Dict[str, object]]:
    grouped: Dict[Tuple[str, float], List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        topology = row.get("topology", "")
        rate = round(float(row.get("link_failure_probability", 0.0)), 8)
        if topologies and topology not in topologies:
            continue
        if rates and rate not in rates:
            continue
        normal = numeric(row.get("normal_jct_mean"))
        failed = numeric(row.get("failed_jct_mean"))
        if normal is None or failed is None:
            continue
        grouped[(topology, rate)].append(
            {
                "normal": normal,
                "failed": failed,
                "weight": int(float(row.get("num_success", row.get("num_samples", 1)))),
                "num_samples": int(float(row.get("num_samples", 0))),
                "num_success": int(float(row.get("num_success", 0))),
                "classes": row.get("fault_env_class", ""),
            }
        )
    return collapse_grouped(grouped)


def load_raw_rows(
    rows: Sequence[Dict[str, str]],
    *,
    topologies: Optional[set[str]],
    rates: Optional[set[float]],
) -> Dict[Tuple[str, float], Dict[str, object]]:
    grouped: Dict[Tuple[str, float], List[Dict[str, object]]] = defaultdict(list)
    totals: Dict[Tuple[str, float], int] = defaultdict(int)
    for row in rows:
        topology = row.get("topology", "")
        rate = round(float(row.get("link_failure_probability", 0.0)), 8)
        if topologies and topology not in topologies:
            continue
        if rates and rate not in rates:
            continue
        key = (topology, rate)
        totals[key] += 1
        normal = numeric(row.get("normal_jct"))
        failed = numeric(row.get("failed_jct"))
        if row.get("status") != "success" or normal is None or failed is None:
            continue
        grouped[key].append(
            {
                "normal": normal,
                "failed": failed,
                "weight": 1,
                "num_samples": 1,
                "num_success": 1,
                "classes": row.get("fault_env_class", ""),
            }
        )
    collapsed = collapse_grouped(grouped)
    for key, total in totals.items():
        if key in collapsed:
            collapsed[key]["num_samples"] = total
    return collapsed


def collapse_grouped(
    grouped: Dict[Tuple[str, float], List[Dict[str, object]]]
) -> Dict[Tuple[str, float], Dict[str, object]]:
    out: Dict[Tuple[str, float], Dict[str, object]] = {}
    for key, group in grouped.items():
        weights = [int(row["weight"]) for row in group]
        total_weight = sum(weights)
        if total_weight <= 0:
            continue
        normal = sum(float(row["normal"]) * w for row, w in zip(group, weights)) / total_weight
        failed = sum(float(row["failed"]) * w for row, w in zip(group, weights)) / total_weight
        classes = sorted({str(row.get("classes", "")) for row in group if row.get("classes")})
        out[key] = {
            "normal": normal,
            "failed": failed,
            "factor": failed / normal if normal else math.nan,
            "num_samples": sum(int(row.get("num_samples", 0)) for row in group),
            "num_success": sum(int(row.get("num_success", 0)) for row in group),
            "classes": ",".join(classes) if classes else "",
        }
    return out


def ordered_keys(keys: Iterable[Tuple[str, float]]) -> List[Tuple[str, float]]:
    return sorted(keys, key=lambda item: (TOPOLOGY_ORDER.get(item[0], 99), item[0], item[1]))


def build_rows(args: argparse.Namespace) -> List[Dict[str, object]]:
    rates = {round(rate, 8) for rate in args.rates} if args.rates else None
    topologies = set(args.topologies) if args.topologies else None
    datasets = {
        "new": load_dataset(args.new, topologies=topologies, rates=rates),
        "fault": load_dataset(args.fault, topologies=topologies, rates=rates),
        "candidate": load_dataset(args.candidate, topologies=topologies, rates=rates),
        "previous": load_dataset(args.previous, topologies=topologies, rates=rates),
        "ns3": load_dataset(args.ns3, topologies=topologies, rates=rates),
    }
    keys = set.intersection(*(set(data) for data in datasets.values()))
    rows: List[Dict[str, object]] = []
    for key in ordered_keys(keys):
        topology, rate = key
        values = {name: data[key] for name, data in datasets.items()}
        ns3 = values["ns3"]
        row: Dict[str, object] = {
            "topology": topology,
            "link_failure_probability": rate,
            "rate_pct": rate * 100.0,
            "new_num_samples": values["new"]["num_samples"],
            "new_num_success": values["new"]["num_success"],
            "new_fault_env_classes": values["new"].get("classes", ""),
        }
        for name, stats in values.items():
            row[f"{name}_normal_jct_mean"] = stats["normal"]
            row[f"{name}_failed_jct_mean"] = stats["failed"]
            row[f"{name}_factor"] = stats["factor"]
            row[f"{name}_failed_abs_err_vs_ns3"] = abs(
                float(stats["failed"]) - float(ns3["failed"])
            )
            row[f"{name}_factor_abs_err_vs_ns3"] = abs(
                float(stats["factor"]) - float(ns3["factor"])
            )
        for ref in ("fault", "candidate", "previous"):
            row[f"new_failed_abs_err_delta_vs_{ref}"] = (
                float(row["new_failed_abs_err_vs_ns3"])
                - float(row[f"{ref}_failed_abs_err_vs_ns3"])
            )
            row[f"new_factor_abs_err_delta_vs_{ref}"] = (
                float(row["new_factor_abs_err_vs_ns3"])
                - float(row[f"{ref}_factor_abs_err_vs_ns3"])
            )
        rows.append(row)
    return rows


def aggregate_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["topology"])].append(row)
    out: List[Dict[str, object]] = []
    for topology, group in sorted(
        grouped.items(), key=lambda item: (TOPOLOGY_ORDER.get(item[0], 99), item[0])
    ):
        row: Dict[str, object] = {
            "topology": topology,
            "num_rates": len(group),
            "new_success": f"{sum(int(r['new_num_success']) for r in group)}/"
            f"{sum(int(r['new_num_samples']) for r in group)}",
        }
        for name in ("new", "fault", "candidate", "previous"):
            row[f"{name}_failed_mae"] = mean_float(group, f"{name}_failed_abs_err_vs_ns3")
            row[f"{name}_factor_mae"] = mean_float(group, f"{name}_factor_abs_err_vs_ns3")
        for ref in ("fault", "candidate", "previous"):
            row[f"failed_mae_delta_vs_{ref}"] = mean_float(
                group, f"new_failed_abs_err_delta_vs_{ref}"
            )
            row[f"factor_mae_delta_vs_{ref}"] = mean_float(
                group, f"new_factor_abs_err_delta_vs_{ref}"
            )
        out.append(row)
    return out


def mean_float(rows: Sequence[Dict[str, object]], key: str) -> float:
    values = [float(row[key]) for row in rows]
    return sum(values) / len(values) if values else math.nan


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: List[str] = []
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


def markdown_table(rows: Sequence[Dict[str, object]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    widths = {
        header: max(len(header), *(len(str(row.get(header, ""))) for row in rows))
        for header in headers
    }
    lines = [
        "| " + " | ".join(header.ljust(widths[header]) for header in headers) + " |",
        "| " + " | ".join("-" * widths[header] for header in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)
            + " |"
        )
    return "\n".join(lines)


def write_markdown(
    *,
    detail: Sequence[Dict[str, object]],
    aggregate: Sequence[Dict[str, object]],
    args: argparse.Namespace,
    path: Path,
) -> None:
    agg_table = []
    for row in aggregate:
        agg_table.append(
            {
                "Topology": row["topology"],
                "Rates": row["num_rates"],
                "New success": row["new_success"],
                "New JCT MAE": fmt(row["new_failed_mae"], 2),
                "Fault JCT MAE": fmt(row["fault_failed_mae"], 2),
                "Cand JCT MAE": fmt(row["candidate_failed_mae"], 2),
                "Prev JCT MAE": fmt(row["previous_failed_mae"], 2),
                "New factor MAE": fmt(row["new_factor_mae"], 3),
                "Fault factor MAE": fmt(row["fault_factor_mae"], 3),
                "Delta vs fault JCT": fmt(row["failed_mae_delta_vs_fault"], 2),
                "Delta vs fault factor": fmt(row["factor_mae_delta_vs_fault"], 3),
            }
        )
    detail_table = []
    for row in detail:
        detail_table.append(
            {
                "Topology": row["topology"],
                "Rate": fmt(row["rate_pct"], 0) + "%",
                "Class": row["new_fault_env_classes"],
                "NS3 JCT": fmt(row["ns3_failed_jct_mean"], 1),
                "New JCT": fmt(row["new_failed_jct_mean"], 1),
                "Fault JCT": fmt(row["fault_failed_jct_mean"], 1),
                "Cand JCT": fmt(row["candidate_failed_jct_mean"], 1),
                "NS3 factor": fmt(row["ns3_factor"], 3),
                "New factor": fmt(row["new_factor"], 3),
                "Fault factor": fmt(row["fault_factor"], 3),
            }
        )
    content = [
        f"# {args.label}",
        "",
        "Inputs:",
        f"- New: `{args.new}`",
        f"- Fault-only reference: `{args.fault}`",
        f"- Baseline-calibrated candidate: `{args.candidate}`",
        f"- Previous w0.3+PXN0.75: `{args.previous}`",
        f"- NS3: `{args.ns3}`",
        "",
        "## Aggregate",
        "",
        markdown_table(agg_table),
        "",
        "## Detail",
        "",
        markdown_table(detail_table),
        "",
        "Notes:",
        "- Lower MAE is better.",
        "- Negative deltas mean the new policy is closer to NS3 than the fault-only reference.",
        "- New rows are collapsed from raw samples, so split `fault_env_class` samples are still averaged at topology/rate level.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    detail = build_rows(args)
    aggregate = aggregate_rows(detail)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    detail_csv = args.output_dir / f"{args.output_prefix}_detail.csv"
    aggregate_csv = args.output_dir / f"{args.output_prefix}_aggregate.csv"
    md_path = args.output_dir / f"{args.output_prefix}.md"
    write_csv(detail_csv, detail)
    write_csv(aggregate_csv, aggregate)
    write_markdown(detail=detail, aggregate=aggregate, args=args, path=md_path)
    print(detail_csv)
    print(aggregate_csv)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare targeted FlowSim fault policies")
    parser.add_argument("--new", type=Path, default=DEFAULT_NEW)
    parser.add_argument("--fault", type=Path, default=DEFAULT_FAULT)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--previous", type=Path, default=DEFAULT_PREVIOUS)
    parser.add_argument("--ns3", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-prefix", default="targeted_highstretch_fault_comparison")
    parser.add_argument("--label", default="Targeted High-Stretch Fault Policy Comparison")
    parser.add_argument("--topologies", nargs="*", default=["DeepSeek", "ROFT", "RO"])
    parser.add_argument("--rates", type=parse_rates, default=default_rates())
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
