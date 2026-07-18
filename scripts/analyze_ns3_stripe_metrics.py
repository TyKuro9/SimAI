#!/usr/bin/env python3
"""Summarize completion-level NS3 spray telemetry for one or more runs."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence


NUMERIC_FIELDS = {
    "orig_src",
    "orig_dst",
    "physical_src",
    "physical_dst",
    "flow_id",
    "tag_id",
    "channel_id",
    "sport",
    "dport",
    "bytes",
    "stripe_index",
    "stripe_count",
    "dynamic_chunk",
    "source_nic",
    "initial_source_nic",
    "destination_nic",
    "source_nic_ordinal_hint",
    "source_nic_hint_fallback",
    "nic_reassignments",
    "path_signature",
    "path_hops",
    "candidate_count",
    "path_score_ns",
    "path_queue_delay_ns",
    "path_propagation_ns",
    "path_reserved_bytes",
    "cnp_count",
    "start_ns",
    "finish_ns",
    "fct_ns",
    "standalone_fct_ns",
}
OPTIONAL_NUMERIC_DEFAULTS = {
    "source_nic_ordinal_hint": (1 << 32) - 1,
    "source_nic_hint_fallback": 0,
}


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (
        position - lower
    )


def mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return statistics.mean(materialized) if materialized else None


def normalized_entropy(weights: Iterable[int]) -> float | None:
    positive = [value for value in weights if value > 0]
    if not positive:
        return None
    if len(positive) == 1:
        return 0.0
    total = sum(positive)
    entropy = -sum(
        (value / total) * math.log(value / total) for value in positive
    )
    return entropy / math.log(len(positive))


def read_rows(path: Path) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    with path.open(newline="") as input_file:
        reader = csv.DictReader(input_file)
        required_fields = NUMERIC_FIELDS.difference(OPTIONAL_NUMERIC_DEFAULTS)
        missing = required_fields.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path} is missing fields: {', '.join(sorted(missing))}"
            )
        for raw in reader:
            rows.append(
                {
                    key: int(raw.get(key, OPTIONAL_NUMERIC_DEFAULTS.get(key)), 16)
                    if key == "path_signature"
                    else int(raw.get(key, OPTIONAL_NUMERIC_DEFAULTS.get(key)))
                    for key in NUMERIC_FIELDS
                }
            )
    return rows


def logical_key(row: dict[str, int]) -> tuple[int, int, int, int, int]:
    return (
        row["flow_id"],
        row["orig_src"],
        row["orig_dst"],
        row["tag_id"],
        row["channel_id"],
    )


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_jct_us(path: Path) -> float | None:
    if not path.exists():
        return None
    for line in reversed(path.read_text(errors="replace").splitlines()):
        for field in reversed(line.split(",")):
            try:
                return float(field.strip())
            except ValueError:
                continue
    return None


def summarize_run(run_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    metric_path = run_dir / "stripe_metrics.csv"
    rows = read_rows(metric_path)
    by_flow: dict[
        tuple[int, int, int, int, int], list[dict[str, int]]
    ] = defaultdict(list)
    for row in rows:
        by_flow[logical_key(row)].append(row)

    flow_rows: list[dict[str, object]] = []
    for key, stripes in sorted(by_flow.items()):
        path_counts = Counter(row["path_signature"] for row in stripes)
        source_nic_counts = Counter(row["source_nic"] for row in stripes)
        destination_nic_counts = Counter(
            row["destination_nic"] for row in stripes
        )
        fcts = [float(row["fct_ns"]) for row in stripes]
        fct_p50 = percentile(fcts, 0.50)
        declared_stripes = max(row["stripe_count"] for row in stripes)
        unique_paths = len(path_counts)
        lane_paths: dict[int, list[dict[str, int]]] = defaultdict(list)
        if any(row["dynamic_chunk"] for row in stripes):
            for row in stripes:
                lane_paths[row["source_nic_ordinal_hint"]].append(row)
        path_changes = 0
        path_change_opportunities = 0
        for lane in lane_paths.values():
            ordered_lane = sorted(lane, key=lambda row: row["stripe_index"])
            path_changes += sum(
                current["path_signature"] != previous["path_signature"]
                for previous, current in zip(ordered_lane, ordered_lane[1:])
            )
            path_change_opportunities += max(0, len(ordered_lane) - 1)
        flow_rows.append(
            {
                "flow_id": key[0],
                "orig_src": key[1],
                "orig_dst": key[2],
                "tag_id": key[3],
                "channel_id": key[4],
                "stripes": len(stripes),
                "declared_stripes": declared_stripes,
                "complete": int(len(stripes) == declared_stripes),
                "dynamic_chunks": sum(
                    row["dynamic_chunk"] for row in stripes
                ),
                "bytes": sum(row["bytes"] for row in stripes),
                "unique_paths": unique_paths,
                "candidate_count_max": max(
                    row["candidate_count"] for row in stripes
                ),
                "path_diversity": unique_paths / len(stripes),
                "path_changes": path_changes,
                "path_change_opportunities": path_change_opportunities,
                "path_change_ratio": path_changes / path_change_opportunities
                if path_change_opportunities
                else None,
                "dominant_path_share": max(path_counts.values()) / len(stripes),
                "unique_source_nics": len(source_nic_counts),
                "source_nic_entropy": normalized_entropy(
                    source_nic_counts.values()
                ),
                "unique_destination_nics": len(destination_nic_counts),
                "destination_nic_entropy": normalized_entropy(
                    destination_nic_counts.values()
                ),
                "fct_p50_ns": fct_p50,
                "fct_p95_ns": percentile(fcts, 0.95),
                "fct_max_ns": max(fcts),
                "flow_completion_span_ns": max(
                    row["finish_ns"] for row in stripes
                )
                - min(row["start_ns"] for row in stripes),
                "slowest_to_median_fct": max(fcts) / fct_p50
                if fct_p50
                else None,
                "cnp_count": sum(row["cnp_count"] for row in stripes),
                "nic_reassignments": sum(
                    row["nic_reassignments"] for row in stripes
                ),
            }
        )

    source_nic_bytes: Counter[tuple[int, int]] = Counter()
    destination_nic_bytes: Counter[tuple[int, int]] = Counter()
    for row in rows:
        source_nic_bytes[(row["physical_src"], row["source_nic"])] += row[
            "bytes"
        ]
        destination_nic_bytes[
            (row["physical_dst"], row["destination_nic"])
        ] += row["bytes"]

    source_values = list(source_nic_bytes.values())
    destination_values = list(destination_nic_bytes.values())
    fcts = [float(row["fct_ns"]) for row in rows]
    summary: dict[str, object] = {
        "run_dir": str(run_dir.resolve()),
        "jct_us": read_jct_us(run_dir / "EndToEnd.csv"),
        "stripes": len(rows),
        "dynamic_chunks": sum(row["dynamic_chunk"] for row in rows),
        "logical_flows": len(flow_rows),
        "incomplete_flows": sum(
            int(not row["complete"]) for row in flow_rows
        ),
        "bytes": sum(row["bytes"] for row in rows),
        "source_nic_keys": len(source_nic_bytes),
        "source_nic_max_mean_ratio": max(source_values)
        / statistics.mean(source_values)
        if source_values
        else None,
        "source_nic_bytes_cov": statistics.pstdev(source_values)
        / statistics.mean(source_values)
        if len(source_values) > 1 and statistics.mean(source_values)
        else 0.0 if source_values else None,
        "destination_nic_keys": len(destination_nic_bytes),
        "destination_nic_max_mean_ratio": max(destination_values)
        / statistics.mean(destination_values)
        if destination_values
        else None,
        "destination_nic_bytes_cov": statistics.pstdev(destination_values)
        / statistics.mean(destination_values)
        if len(destination_values) > 1 and statistics.mean(destination_values)
        else 0.0 if destination_values else None,
        "unique_paths_mean": mean(
            float(row["unique_paths"]) for row in flow_rows
        ),
        "path_diversity_mean": mean(
            float(row["path_diversity"])
            for row in flow_rows
        ),
        "path_change_ratio_mean": mean(
            float(row["path_change_ratio"])
            for row in flow_rows
            if row["path_change_ratio"] is not None
        ),
        "dominant_path_share_mean": mean(
            float(row["dominant_path_share"]) for row in flow_rows
        ),
        "source_nic_entropy_mean": mean(
            float(row["source_nic_entropy"])
            for row in flow_rows
            if row["source_nic_entropy"] is not None
        ),
        "destination_nic_entropy_mean": mean(
            float(row["destination_nic_entropy"])
            for row in flow_rows
            if row["destination_nic_entropy"] is not None
        ),
        "stripe_fct_p50_ns": percentile(fcts, 0.50),
        "stripe_fct_p95_ns": percentile(fcts, 0.95),
        "stripe_fct_p99_ns": percentile(fcts, 0.99),
        "flow_completion_span_p50_ns": percentile(
            [float(row["flow_completion_span_ns"]) for row in flow_rows],
            0.50,
        ),
        "flow_completion_span_p95_ns": percentile(
            [float(row["flow_completion_span_ns"]) for row in flow_rows],
            0.95,
        ),
        "flow_completion_span_p99_ns": percentile(
            [float(row["flow_completion_span_ns"]) for row in flow_rows],
            0.99,
        ),
        "slowest_to_median_fct_mean": mean(
            float(row["slowest_to_median_fct"])
            for row in flow_rows
            if row["slowest_to_median_fct"] is not None
        ),
        "cnp_count": sum(row["cnp_count"] for row in rows),
        "nic_reassignments": sum(row["nic_reassignments"] for row in rows),
        "source_nic_hint_fallbacks": sum(
            row["source_nic_hint_fallback"] for row in rows
        ),
    }
    return summary, flow_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        nargs="+",
        type=Path,
        help="run directories containing stripe_metrics.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("stripe_summary.csv"),
        help="combined run-level CSV (default: stripe_summary.csv)",
    )
    parser.add_argument(
        "--no-flow-output",
        action="store_true",
        help="do not write stripe_flow_metrics.csv in each run directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summaries: list[dict[str, object]] = []
    for run_dir in args.run_dirs:
        summary, flow_rows = summarize_run(run_dir)
        summaries.append(summary)
        if not args.no_flow_output:
            write_csv(run_dir / "stripe_flow_metrics.csv", flow_rows)
    write_csv(args.output, summaries)
    print(f"wrote {len(summaries)} run summaries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
