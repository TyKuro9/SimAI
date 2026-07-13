#!/usr/bin/env python3
"""Summarize targeted FlowSim sharing-model experiments."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "experiments" / "fault_tolerance" / "targeted_original_flow_mismatch"
DEFAULT_ECMP_DIR = ROOT / "experiments" / "fault_tolerance" / "flowsim_ecmp_smoke"
DEFAULT_SHARING_DIR = ROOT / "experiments" / "fault_tolerance" / "flowsim_sharing_smoke"

CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]

EXPERIMENTS = [
    ("Zcube", "ecmp_default", DEFAULT_ECMP_DIR / "zcube_default"),
    ("Zcube", "ecmp_ns3ish", DEFAULT_ECMP_DIR / "zcube_ns3ish"),
    ("Zcube", "switch_switch_x2", DEFAULT_SHARING_DIR / "zcube_switchx2"),
    ("RO", "switch_switch_x2", DEFAULT_SHARING_DIR / "ro_switchx2"),
    ("Meta", "crossrail_switch_w0.5", DEFAULT_SHARING_DIR / "meta_crossrail_w05"),
    ("Zcube", "crossrail_switch_w0.5", DEFAULT_SHARING_DIR / "zcube_crossrail_w05"),
    ("RO", "crossrail_switch_w0.5", DEFAULT_SHARING_DIR / "ro_crossrail_w05"),
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


def target_by_topology(target_dir: Path) -> dict[str, dict[str, str]]:
    return {row["topology"]: row for row in read_rows(target_dir / "targeted_fct_summary.csv")}


def ns3_grouped_p95(target_dir: Path) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for row in read_rows(target_dir / "flowsim_ns3_original_fct_comparison.csv"):
        out[(row["topology"], row["original_category"])] = float(
            row["ns3_grouped_p95_fct"]
        )
    return out


def add_run_row(
    rows: list[dict[str, object]],
    *,
    topology: str,
    variant: str,
    run_dir: Path,
    gpus_per_server: int,
    serial_jct: float,
    ns3_jct: float,
    ns3_p95: dict[tuple[str, str], float],
) -> None:
    if not (run_dir / "EndToEnd.csv").exists() or not (run_dir / "fct.txt").exists():
        return
    jct = read_total_time(run_dir / "EndToEnd.csv")
    p95 = fct_p95_by_category(run_dir / "fct.txt", gpus_per_server=gpus_per_server)
    row: dict[str, object] = {
        "topology": topology,
        "variant": variant,
        "jct": jct,
        "jct_over_serial": jct / serial_jct if serial_jct else math.nan,
        "jct_over_ns3": jct / ns3_jct if ns3_jct else math.nan,
    }
    for category in CATEGORY_ORDER:
        value = p95[f"p95_{category}"]
        row[f"p95_{category}"] = value
        ns3_value = ns3_p95.get((topology, category), math.nan)
        row[f"p95_over_ns3_{category}"] = (
            value / ns3_value if ns3_value and not math.isnan(ns3_value) else math.nan
        )
    rows.append(row)


def build_summary(target_dir: Path) -> list[dict[str, object]]:
    targets = target_by_topology(target_dir)
    ns3_p95 = ns3_grouped_p95(target_dir)
    rows: list[dict[str, object]] = []

    for topology, target in targets.items():
        gpus_per_server = topology_gpus_per_server(Path(target["topology_file"]))
        serial_dir = Path(target["flowsim_run_dir"])
        serial_jct = read_total_time(serial_dir / "EndToEnd.csv")
        ns3_jct = float(target["ns3_jct"])
        add_run_row(
            rows,
            topology=topology,
            variant="serial",
            run_dir=serial_dir,
            gpus_per_server=gpus_per_server,
            serial_jct=serial_jct,
            ns3_jct=ns3_jct,
            ns3_p95=ns3_p95,
        )

    for topology, variant, run_dir in EXPERIMENTS:
        if topology not in targets:
            continue
        target = targets[topology]
        gpus_per_server = topology_gpus_per_server(Path(target["topology_file"]))
        serial_jct = read_total_time(Path(target["flowsim_run_dir"]) / "EndToEnd.csv")
        add_run_row(
            rows,
            topology=topology,
            variant=variant,
            run_dir=run_dir,
            gpus_per_server=gpus_per_server,
            serial_jct=serial_jct,
            ns3_jct=float(target["ns3_jct"]),
            ns3_p95=ns3_p95,
        )
    return rows


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
    order = {"Meta": 0, "Zcube": 1, "RO": 2}
    for row in sorted(rows, key=lambda r: (order.get(str(r["topology"]), 99), str(r["variant"]))):
        table_rows.append(
            {
                "Topology": str(row["topology"]),
                "Variant": str(row["variant"]),
                "JCT": fmt(row["jct"]),
                "JCT/serial": fmt(row["jct_over_serial"]),
                "JCT/NS3": fmt(row["jct_over_ns3"]),
                "p95 cross-rail": fmt(row["p95_cross_server_cross_rail"]),
                "p95 cross-rail/NS3": fmt(row["p95_over_ns3_cross_server_cross_rail"]),
                "p95 same-rail/NS3": fmt(row["p95_over_ns3_cross_server_same_rail"]),
            }
        )
    content = [
        "# FlowSim Sharing Experiment Summary",
        "",
        markdown_table(table_rows),
        "",
        "Notes:",
        "- `serial` is the original FlowSim model.",
        "- `ecmp_ns3ish` uses `FLOWSIM_ECMP_SEED=node FLOWSIM_ECMP_SRC_PORT=10000`.",
        "- `switch_switch_x2` doubles all switch-switch effective bandwidth.",
        "- `crossrail_switch_w0.5` weights physical cross-rail traffic as 0.5 competitors on switch-switch links.",
    ]
    path.write_text("\n".join(content) + "\n")


def run(args: argparse.Namespace) -> int:
    target_dir = args.target_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_summary(target_dir)
    csv_path = output_dir / "flowsim_sharing_experiment_summary.csv"
    md_path = output_dir / "flowsim_sharing_experiment_summary.md"
    write_csv(rows, csv_path)
    write_markdown(rows, md_path)
    print(csv_path)
    print(md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize targeted FlowSim sharing experiments"
    )
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHARING_DIR)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
