#!/usr/bin/env python3
"""Compare an in-progress FlowSim full sweep against previous FlowSim and NS3.

Only local FlowSim topology/rate groups with enough successful samples are
included. This keeps partial reports from drawing conclusions on half-finished
rate points while a long sweep is still running.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-summary", required=True, type=Path)
    parser.add_argument("--previous-summary", required=True, type=Path)
    parser.add_argument("--ns3-raw", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-csv", required=True, type=Path)
    parser.add_argument("--min-success", default=10, type=int)
    parser.add_argument("--title", default="Partial Full-Sweep Comparison")
    return parser.parse_args()


def to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def rate_key(value: str | float) -> float:
    return round(float(value), 6)


def load_flowsim_summary(path: Path) -> dict[tuple[str, float], dict[str, float | int | str]]:
    rows: dict[tuple[str, float], dict[str, float | int | str]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            topology = row["topology"]
            rate = rate_key(row["link_failure_probability"])
            normal = to_float(row.get("normal_jct_mean"))
            failed = to_float(row.get("failed_jct_mean"))
            num_success = to_int(row.get("num_success"))
            num_samples = to_int(row.get("num_samples"))
            if normal is None or failed is None or num_success is None:
                continue
            rows[(topology, rate)] = {
                "topology": topology,
                "rate": rate,
                "normal_jct": normal,
                "failed_jct": failed,
                "num_success": num_success,
                "num_samples": num_samples or num_success,
            }
    return rows


def load_ns3_raw(path: Path) -> dict[tuple[str, float], dict[str, float | int | str]]:
    grouped: dict[tuple[str, float], list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "success":
                continue
            grouped[(row["topology"], rate_key(row["link_failure_probability"]))].append(row)

    rows: dict[tuple[str, float], dict[str, float | int | str]] = {}
    for key, group in grouped.items():
        normal_values = [to_float(row.get("normal_jct")) for row in group]
        failed_values = [to_float(row.get("failed_jct")) for row in group]
        normal = [value for value in normal_values if value is not None]
        failed = [value for value in failed_values if value is not None]
        if not normal or not failed:
            continue
        topology, rate = key
        rows[key] = {
            "topology": topology,
            "rate": rate,
            "normal_jct": mean(normal),
            "failed_jct": mean(failed),
            "num_success": len(failed),
            "num_samples": len(group),
        }
    return rows


def factor(row: dict[str, float | int | str]) -> float:
    normal = float(row["normal_jct"])
    if normal == 0:
        return 0.0
    return float(row["failed_jct"]) / normal


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def fmt_factor(value: float) -> str:
    return f"{value:.3f}"


def average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return mean(values)


def build_rows(
    local: dict[tuple[str, float], dict[str, float | int | str]],
    previous: dict[tuple[str, float], dict[str, float | int | str]],
    ns3: dict[tuple[str, float], dict[str, float | int | str]],
    min_success: int,
) -> list[dict[str, float | int | str]]:
    comparison_rows: list[dict[str, float | int | str]] = []
    for key in sorted(local, key=lambda item: (item[0], item[1])):
        local_row = local[key]
        if int(local_row["num_success"]) < min_success:
            continue
        if key not in previous or key not in ns3:
            continue

        previous_row = previous[key]
        ns3_row = ns3[key]
        local_failed = float(local_row["failed_jct"])
        previous_failed = float(previous_row["failed_jct"])
        ns3_failed = float(ns3_row["failed_jct"])
        local_factor = factor(local_row)
        previous_factor = factor(previous_row)
        ns3_factor = factor(ns3_row)

        comparison_rows.append(
            {
                "topology": key[0],
                "rate": key[1],
                "local_num_success": int(local_row["num_success"]),
                "previous_num_success": int(previous_row["num_success"]),
                "ns3_num_success": int(ns3_row["num_success"]),
                "local_failed_jct": local_failed,
                "previous_failed_jct": previous_failed,
                "ns3_failed_jct": ns3_failed,
                "local_err": local_failed - ns3_failed,
                "previous_err": previous_failed - ns3_failed,
                "local_factor": local_factor,
                "previous_factor": previous_factor,
                "ns3_factor": ns3_factor,
                "local_factor_err": local_factor - ns3_factor,
                "previous_factor_err": previous_factor - ns3_factor,
            }
        )
    return comparison_rows


def grouped_by_topology(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    by_topology: dict[str, list[dict[str, float | int | str]]] = defaultdict(list)
    for row in rows:
        by_topology[str(row["topology"])].append(row)

    summary_rows: list[dict[str, float | int | str]] = []
    for topology in sorted(by_topology):
        group = by_topology[topology]
        summary_rows.append(
            {
                "topology": topology,
                "groups": len(group),
                "local_failed_jct_mae": average(abs(float(row["local_err"])) for row in group),
                "previous_failed_jct_mae": average(abs(float(row["previous_err"])) for row in group),
                "local_factor_mae": average(abs(float(row["local_factor_err"])) for row in group),
                "previous_factor_mae": average(abs(float(row["previous_factor_err"])) for row in group),
                "local_failed_jct_bias": average(float(row["local_err"]) for row in group),
                "previous_failed_jct_bias": average(float(row["previous_err"]) for row in group),
            }
        )
    return summary_rows


def write_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "topology",
        "rate",
        "local_num_success",
        "previous_num_success",
        "ns3_num_success",
        "local_failed_jct",
        "previous_failed_jct",
        "ns3_failed_jct",
        "local_err",
        "previous_err",
        "local_factor",
        "previous_factor",
        "ns3_factor",
        "local_factor_err",
        "previous_factor_err",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path,
    rows: list[dict[str, float | int | str]],
    local_summary: Path,
    previous_summary: Path,
    ns3_raw: Path,
    min_success: int,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    local_mae = average(abs(float(row["local_err"])) for row in rows)
    previous_mae = average(abs(float(row["previous_err"])) for row in rows)
    local_bias = average(float(row["local_err"]) for row in rows)
    previous_bias = average(float(row["previous_err"]) for row in rows)
    local_factor_mae = average(abs(float(row["local_factor_err"])) for row in rows)
    previous_factor_mae = average(abs(float(row["previous_factor_err"])) for row in rows)

    lines = [
        f"# {title}",
        "",
        f"Completed full local groups included: `{len(rows)}`. Only local groups with at least `{min_success}` successful seeds are included.",
        "",
        f"Local failed-JCT MAE on completed groups: `{fmt(local_mae)}`",
        f"Previous failed-JCT MAE on same groups: `{fmt(previous_mae)}`",
        f"Local failed-JCT bias on completed groups: `{fmt(local_bias)}`",
        f"Previous failed-JCT bias on same groups: `{fmt(previous_bias)}`",
        f"Local factor MAE on completed groups: `{fmt_factor(local_factor_mae)}`",
        f"Previous factor MAE on same groups: `{fmt_factor(previous_factor_mae)}`",
        "",
        "Sources:",
        f"- Local FlowSim: `{local_summary}`",
        f"- Previous FlowSim: `{previous_summary}`",
        f"- NS3 raw: `{ns3_raw}`",
        "",
        "## By Topology",
        "",
        "| Topology | Groups | Local JCT MAE | Previous JCT MAE | Local factor MAE | Previous factor MAE | Local bias | Previous bias |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in grouped_by_topology(rows):
        lines.append(
            "| {topology} | {groups} | {local_mae} | {previous_mae} | {local_factor} | {previous_factor} | {local_bias} | {previous_bias} |".format(
                topology=row["topology"],
                groups=row["groups"],
                local_mae=fmt(float(row["local_failed_jct_mae"])),
                previous_mae=fmt(float(row["previous_failed_jct_mae"])),
                local_factor=fmt_factor(float(row["local_factor_mae"])),
                previous_factor=fmt_factor(float(row["previous_factor_mae"])),
                local_bias=fmt(float(row["local_failed_jct_bias"])),
                previous_bias=fmt(float(row["previous_failed_jct_bias"])),
            )
        )

    lines.extend(
        [
            "",
            "## By Rate",
            "",
            "| Topology | Rate | Local JCT | Previous JCT | NS3 JCT | Local err | Previous err | Local factor | Previous factor | NS3 factor |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            "| {topology} | {rate:.0%} | {local_jct} | {previous_jct} | {ns3_jct} | {local_err} | {previous_err} | {local_factor} | {previous_factor} | {ns3_factor} |".format(
                topology=row["topology"],
                rate=float(row["rate"]),
                local_jct=fmt(float(row["local_failed_jct"])),
                previous_jct=fmt(float(row["previous_failed_jct"])),
                ns3_jct=fmt(float(row["ns3_failed_jct"])),
                local_err=fmt(float(row["local_err"])),
                previous_err=fmt(float(row["previous_err"])),
                local_factor=fmt_factor(float(row["local_factor"])),
                previous_factor=fmt_factor(float(row["previous_factor"])),
                ns3_factor=fmt_factor(float(row["ns3_factor"])),
            )
        )

    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    local = load_flowsim_summary(args.local_summary)
    previous = load_flowsim_summary(args.previous_summary)
    ns3 = load_ns3_raw(args.ns3_raw)
    rows = build_rows(local, previous, ns3, args.min_success)
    write_csv(args.out_csv, rows)
    write_markdown(
        args.out_md,
        rows,
        args.local_summary,
        args.previous_summary,
        args.ns3_raw,
        args.min_success,
        args.title,
    )
    print(args.out_md)
    print(args.out_csv)


if __name__ == "__main__":
    main()
