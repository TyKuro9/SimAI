#!/usr/bin/env python3
"""Summarize FlowSim cross-rail sharing weight-grid runs."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "experiments" / "fault_tolerance" / "targeted_original_flow_mismatch"
DEFAULT_GRID_DIR = ROOT / "experiments" / "fault_tolerance" / "flowsim_sharing_weight_grid"

CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def parse_node_id(token: str) -> int:
    text = str(token).strip()
    if text.startswith("0b"):
        body = text[2:]
        node_hex = body[:-2] if len(body) > 2 else body
        return int(node_hex, 16)
    return int(text, 0)


def topology_gpus_per_server(path: Path) -> int:
    with path.open() as f:
        header = f.readline().split()
    if len(header) < 2:
        raise ValueError(f"invalid topology header: {path}")
    return int(header[1])


def pair_category(src: int, dst: int, gpus_per_server: int) -> str:
    if src // gpus_per_server == dst // gpus_per_server:
        return "same_server"
    if src % gpus_per_server == dst % gpus_per_server:
        return "cross_server_same_rail"
    return "cross_server_cross_rail"


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


def fct_stats_by_category(path: Path, *, gpus_per_server: int) -> dict[str, float | int]:
    values: dict[str, list[float]] = {category: [] for category in CATEGORY_ORDER}
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) < 7:
                raise ValueError(f"invalid FCT row in {path}:{line_no}: {line!r}")
            src = parse_node_id(parts[0])
            dst = parse_node_id(parts[1])
            category = pair_category(src, dst, gpus_per_server)
            values.setdefault(category, []).append(float(parts[6]))

    out: dict[str, float | int] = {}
    for category in CATEGORY_ORDER:
        category_values = values.get(category, [])
        out[f"count_{category}"] = len(category_values)
        out[f"p50_{category}"] = percentile(category_values, 50)
        out[f"p95_{category}"] = percentile(category_values, 95)
        out[f"p99_{category}"] = percentile(category_values, 99)
    return out


def read_total_time(path: Path) -> float:
    if not path.exists() or path.stat().st_size == 0:
        return math.nan
    rows = read_rows(path)
    if not rows:
        return math.nan
    normalized = {key.strip(): value.strip() for key, value in rows[0].items()}
    value = normalized.get("Total time")
    return float(value) if value else math.nan


def target_by_topology(target_dir: Path) -> dict[str, dict[str, str]]:
    return {row["topology"]: row for row in read_rows(target_dir / "targeted_fct_summary.csv")}


def ns3_grouped_p95(target_dir: Path) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for row in read_rows(target_dir / "flowsim_ns3_original_fct_comparison.csv"):
        out[(row["topology"], row["original_category"])] = float(
            row["ns3_grouped_p95_fct"]
        )
    return out


def build_summary(target_dir: Path, grid_dir: Path) -> list[dict[str, object]]:
    targets = target_by_topology(target_dir)
    ns3_p95 = ns3_grouped_p95(target_dir)
    rows: list[dict[str, object]] = []

    for run in read_rows(grid_dir / "flowsim_sharing_weight_grid_summary.csv"):
        topology = run["topology"]
        if topology not in targets:
            continue
        run_dir = Path(run["run_dir"])
        fct_path = run_dir / "fct.txt"
        if not fct_path.exists():
            continue

        target = targets[topology]
        topology_file = Path(run.get("topology_file") or target["topology_file"])
        serial_jct = read_total_time(Path(target["flowsim_run_dir"]) / "EndToEnd.csv")
        ns3_jct = float(target["ns3_jct"])
        jct = read_total_time(run_dir / "EndToEnd.csv")
        gpus_per_server = topology_gpus_per_server(topology_file)
        stats = fct_stats_by_category(fct_path, gpus_per_server=gpus_per_server)

        row: dict[str, object] = {
            "topology": topology,
            "weight": float(run["weight"]),
            "jct": jct,
            "jct_over_serial": jct / serial_jct if serial_jct else math.nan,
            "jct_over_ns3": jct / ns3_jct if ns3_jct else math.nan,
            "run_dir": str(run_dir),
        }
        row.update(stats)
        for category in CATEGORY_ORDER:
            value = float(row[f"p95_{category}"])
            ns3_value = ns3_p95.get((topology, category), math.nan)
            row[f"p95_over_ns3_{category}"] = (
                value / ns3_value if ns3_value and not math.isnan(ns3_value) else math.nan
            )
        rows.append(row)

    return sorted(rows, key=lambda r: (str(r["topology"]), float(r["weight"])))


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
                "Topology": str(row["topology"]),
                "Weight": fmt(row["weight"]),
                "JCT": fmt(row["jct"]),
                "JCT/serial": fmt(row["jct_over_serial"]),
                "JCT/NS3": fmt(row["jct_over_ns3"]),
                "p95 cross-rail/NS3": fmt(row["p95_over_ns3_cross_server_cross_rail"]),
                "p95 same-rail/NS3": fmt(row["p95_over_ns3_cross_server_same_rail"]),
                "p95 same-server/NS3": fmt(row["p95_over_ns3_same_server"]),
            }
        )
    content = [
        "# FlowSim Cross-Rail Sharing Weight Grid",
        "",
        markdown_table(table_rows),
        "",
        "Notes:",
        "- Weight is `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT`.",
        "- Lower weight means cross-server cross-rail chunks consume less fair-share capacity on switch-switch links.",
        "- Ratios use the reconstructed NS3 original-flow grouped p95 from the targeted mismatch runs.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    target_dir = args.target_dir.resolve()
    grid_dir = args.grid_dir.resolve()
    rows = build_summary(target_dir, grid_dir)
    csv_path = grid_dir / "flowsim_sharing_weight_grid_detailed_summary.csv"
    md_path = grid_dir / "flowsim_sharing_weight_grid_detailed_summary.md"
    write_csv(rows, csv_path)
    write_markdown(rows, md_path)
    print(csv_path)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize FlowSim cross-rail sharing weight grid"
    )
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--grid-dir", type=Path, default=DEFAULT_GRID_DIR)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
