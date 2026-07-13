#!/usr/bin/env python3
"""Summarize FlowSim PXN timing smoke runs."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "experiments" / "fault_tolerance" / "targeted_original_flow_mismatch"
DEFAULT_SMOKE_DIR = ROOT / "experiments" / "fault_tolerance" / "flowsim_pxn_timing_smoke"

CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]
OVERLAP_DIRS = {
    "Meta": "overlap_meta",
    "Zcube": "overlap_zcube",
    "RO": "overlap_ro",
}


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


def fct_p95_by_category(path: Path, *, gpus_per_server: int) -> dict[str, float]:
    values = {category: [] for category in CATEGORY_ORDER}
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
    return {f"p95_{category}": percentile(v, 95) for category, v in values.items()}


def read_total_time(path: Path) -> float:
    rows = read_rows(path)
    if not rows:
        return math.nan
    normalized = {key.strip(): value.strip() for key, value in rows[0].items()}
    return float(normalized.get("Total time", "nan"))


def ns3_grouped_p95(target_dir: Path) -> dict[tuple[str, str], float]:
    path = target_dir / "flowsim_ns3_original_fct_comparison.csv"
    out: dict[tuple[str, str], float] = {}
    for row in read_rows(path):
        out[(row["topology"], row["original_category"])] = float(
            row["ns3_grouped_p95_fct"]
        )
    return out


def fmt(value: float, digits: int = 3) -> str:
    if math.isnan(value):
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.{digits}f}"


def markdown_table(rows: list[dict[str, str]]) -> str:
    headers = list(rows[0].keys()) if rows else []
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


def build_summary(target_dir: Path, smoke_dir: Path) -> list[dict[str, float | str]]:
    ns3_p95 = ns3_grouped_p95(target_dir)
    rows = []
    for target in read_rows(target_dir / "targeted_fct_summary.csv"):
        topology = target["topology"]
        if topology not in OVERLAP_DIRS:
            continue
        gpus_per_server = topology_gpus_per_server(Path(target["topology_file"]))
        serial_dir = Path(target["flowsim_run_dir"])
        overlap_dir = smoke_dir / OVERLAP_DIRS[topology]
        serial_jct = read_total_time(serial_dir / "EndToEnd.csv")
        overlap_jct = read_total_time(overlap_dir / "EndToEnd.csv")

        serial_p95 = fct_p95_by_category(
            serial_dir / "fct.txt", gpus_per_server=gpus_per_server
        )
        overlap_p95 = fct_p95_by_category(
            overlap_dir / "fct.txt", gpus_per_server=gpus_per_server
        )

        row: dict[str, float | str] = {
            "topology": topology,
            "rate": float(target["rate"]),
            "seed": int(target["seed"]),
            "serial_jct": serial_jct,
            "overlap_jct": overlap_jct,
            "overlap_over_serial_jct": overlap_jct / serial_jct,
            "jct_reduction_pct": (1.0 - overlap_jct / serial_jct) * 100.0,
            "ns3_jct": float(target["ns3_jct"]),
        }
        for category in CATEGORY_ORDER:
            serial_value = serial_p95[f"p95_{category}"]
            overlap_value = overlap_p95[f"p95_{category}"]
            row[f"serial_p95_{category}"] = serial_value
            row[f"overlap_p95_{category}"] = overlap_value
            row[f"overlap_over_serial_p95_{category}"] = (
                overlap_value / serial_value if serial_value > 0 else math.nan
            )
            row[f"ns3_grouped_p95_{category}"] = ns3_p95.get(
                (topology, category), math.nan
            )
        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, float | str]], path: Path) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, float | str]], path: Path) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            {
                "Topology": str(row["topology"]),
                "Serial JCT": fmt(float(row["serial_jct"])),
                "Overlap JCT": fmt(float(row["overlap_jct"])),
                "Reduction": f"{fmt(float(row['jct_reduction_pct']))}%",
                "NS3 JCT": fmt(float(row["ns3_jct"])),
                "Serial p95 cross-rail": fmt(
                    float(row["serial_p95_cross_server_cross_rail"])
                ),
                "Overlap p95 cross-rail": fmt(
                    float(row["overlap_p95_cross_server_cross_rail"])
                ),
                "NS3 grouped p95 cross-rail": fmt(
                    float(row["ns3_grouped_p95_cross_server_cross_rail"])
                ),
            }
        )
    content = [
        "# FlowSim PXN Timing Smoke Summary",
        "",
        markdown_table(table_rows),
        "",
        "Notes:",
        "- `serial` is the existing store-and-forward PXN leg timing.",
        "- `overlap` launches all physical PXN legs concurrently and completes the original flow after the slowest leg.",
        "- The switch is experimental and enabled with `FLOWSIM_PXN_TIMING=overlap` or `AS_PXN_TIMING=overlap`.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    target_dir = args.target_dir.resolve()
    smoke_dir = args.smoke_dir.resolve()
    rows = build_summary(target_dir, smoke_dir)
    csv_path = smoke_dir / "flowsim_pxn_timing_summary.csv"
    md_path = smoke_dir / "flowsim_pxn_timing_summary.md"
    write_csv(rows, csv_path)
    write_markdown(rows, md_path)
    print(csv_path)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize FlowSim PXN timing smoke runs")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--smoke-dir", type=Path, default=DEFAULT_SMOKE_DIR)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
