#!/usr/bin/env python3
"""Validate DP-only NS3 FCT logs and plot logical-flow CDFs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence


TOPOLOGIES = ("Zcube", "DeepSeek", "ROFT")
POLICIES = ("spray_dual_table", "spray_adaptive")
TOPOLOGY_STYLE = {
    "Zcube": {"color": "#1976D2", "linestyle": "-"},
    "DeepSeek": {"color": "#F28E2B", "linestyle": "--"},
    "ROFT": {"color": "#D62728", "linestyle": "-."},
}
POLICY_LABELS = {
    "spray_dual_table": "Equal-path dual-table spray",
    "spray_adaptive": "Path-aware adaptive spray",
}


def percentile(ordered: list[int], quantile: float) -> float:
    if not ordered:
        raise ValueError("cannot compute a percentile of an empty sample")
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return (
        ordered[lower] * (upper - position)
        + ordered[upper] * (position - lower)
    )


def read_jct(results_path: Path) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], float] = {}
    if not results_path.exists():
        return values
    with results_path.open(newline="") as input_file:
        for row in csv.DictReader(input_file):
            if row.get("status") != "success" or not row.get("jct_us"):
                continue
            values[(row["topology"], row["policy"])] = float(row["jct_us"])
    return values


def parse_dp_fct(
    path: Path, dp_group_count: int
) -> tuple[list[int], dict[str, int | float]]:
    # A spray operation completes only when its slowest physical stripe does.
    logical_max_fct: dict[tuple[int, int, int], int] = {}
    logical_stripes: dict[tuple[int, int, int], int] = {}
    physical_records = 0
    malformed_records = 0
    non_dp_records = 0
    self_records = 0

    with path.open(errors="replace") as input_file:
        for line_number, line in enumerate(input_file, 1):
            fields = line.split()
            if len(fields) != 14:
                malformed_records += 1
                continue
            try:
                fct_ns = int(fields[6])
                original_src = int(fields[8])
                original_dst = int(fields[9])
                flow_id = int(fields[13])
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: invalid FCT row") from error

            physical_records += 1
            if original_src == original_dst:
                self_records += 1
                continue
            if original_src % dp_group_count != original_dst % dp_group_count:
                non_dp_records += 1
                continue

            key = (flow_id, original_src, original_dst)
            previous = logical_max_fct.get(key)
            if previous is None or fct_ns > previous:
                logical_max_fct[key] = fct_ns
            logical_stripes[key] = logical_stripes.get(key, 0) + 1

    if malformed_records:
        raise ValueError(f"{path}: found {malformed_records} malformed FCT rows")
    if non_dp_records or self_records:
        raise ValueError(
            f"{path}: DP filter validation failed: non_dp={non_dp_records}, "
            f"self={self_records}"
        )
    if not logical_max_fct:
        raise ValueError(f"{path}: no logical DP flows found")

    logical_fcts = sorted(logical_max_fct.values())
    stripe_counts = sorted(logical_stripes.values())
    metrics: dict[str, int | float] = {
        "physical_records": physical_records,
        "logical_flows": len(logical_fcts),
        "dp_group_count": dp_group_count,
        "stripe_count_min": stripe_counts[0],
        "stripe_count_p50": percentile(stripe_counts, 0.50),
        "stripe_count_p95": percentile(stripe_counts, 0.95),
        "stripe_count_max": stripe_counts[-1],
        "fct_p50_us": percentile(logical_fcts, 0.50) / 1_000.0,
        "fct_p90_us": percentile(logical_fcts, 0.90) / 1_000.0,
        "fct_p95_us": percentile(logical_fcts, 0.95) / 1_000.0,
        "fct_p99_us": percentile(logical_fcts, 0.99) / 1_000.0,
        "fct_max_us": logical_fcts[-1] / 1_000.0,
    }
    return logical_fcts, metrics


def cdf_points(
    ordered_ns: list[int], max_points: int
) -> list[tuple[float, float]]:
    count = len(ordered_ns)
    if count <= max_points:
        indices = range(count)
    else:
        indices = sorted(
            {
                round(index * (count - 1) / (max_points - 1))
                for index in range(max_points)
            }
        )
    return [
        (ordered_ns[index] / 1_000.0, (index + 1) / count)
        for index in indices
    ]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def configure_axis(axis: object) -> None:
    from matplotlib.ticker import LogFormatterMathtext

    axis.set_xscale("log", base=2)
    axis.xaxis.set_major_formatter(LogFormatterMathtext(base=2))
    axis.set_ylim(0.0, 1.03)
    axis.set_xlabel("DP logical-flow FCT (us)")
    axis.set_ylabel("CDF")
    axis.grid(True, which="major", color="#D7DCE2", linestyle="--", linewidth=0.8)
    axis.grid(True, which="minor", color="#ECEFF2", linestyle=":", linewidth=0.5)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_policy(
    output_dir: Path,
    policy: str,
    series: dict[tuple[str, str], list[tuple[float, float]]],
) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    for topology in TOPOLOGIES:
        points = series[(topology, policy)]
        axis.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            label=topology,
            linewidth=2.2,
            **TOPOLOGY_STYLE[topology],
        )
    configure_axis(axis)
    axis.set_title(
        "DP Flow Completion Time CDF\n"
        f"GPT-22B Dense, 1024 GPUs, GA=6, {POLICY_LABELS[policy]}"
    )
    axis.legend(title="Topology", frameon=True, loc="lower right")
    stem = output_dir / f"dp_fct_cdf_{policy}"
    figure.savefig(stem.with_suffix(".png"), dpi=240, facecolor="white")
    figure.savefig(stem.with_suffix(".pdf"), facecolor="white")
    plt.close(figure)


def plot_combined(
    output_dir: Path,
    series: dict[tuple[str, str], list[tuple[float, float]]],
) -> None:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        1, 2, figsize=(12.6, 4.5), sharey=True, constrained_layout=True
    )
    for axis, policy in zip(axes, POLICIES):
        for topology in TOPOLOGIES:
            points = series[(topology, policy)]
            axis.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                label=topology,
                linewidth=2.1,
                **TOPOLOGY_STYLE[topology],
            )
        configure_axis(axis)
        axis.set_title(POLICY_LABELS[policy])
    axes[1].set_ylabel("")
    axes[1].legend(title="Topology", frameon=True, loc="lower right")
    figure.suptitle("DP FCT CDF - GPT-22B Dense, 1024 GPUs, GA=6", fontsize=14)
    stem = output_dir / "dp_fct_cdf_policy_comparison"
    figure.savefig(stem.with_suffix(".png"), dpi=240, facecolor="white")
    figure.savefig(stem.with_suffix(".pdf"), facecolor="white")
    plt.close(figure)


def write_report(path: Path, summary_rows: list[dict[str, object]]) -> None:
    lines = [
        "# NS3 DP FCT Comparison",
        "",
        "Workload: GPT-22B Dense, 1024 GPUs, GA=6. PXN is disabled.",
        "Each logical DP flow groups physical spray stripes by "
        "`(flow_id, original_src, original_dst)`; its FCT is the maximum stripe FCT.",
        "The parser validates every logged pair against the simulator's DP grouping rule.",
        "",
        "| Policy | Topology | JCT (us) | DP flows | FCT p50 (us) | p90 | p95 | p99 | max | Stripes p50 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["policy"]),
                    str(row["topology"]),
                    f"{float(row['jct_us']):.3f}",
                    str(row["logical_flows"]),
                    f"{float(row['fct_p50_us']):.3f}",
                    f"{float(row['fct_p90_us']):.3f}",
                    f"{float(row['fct_p95_us']):.3f}",
                    f"{float(row['fct_p99_us']):.3f}",
                    f"{float(row['fct_max_us']):.3f}",
                    f"{float(row['stripe_count_p50']):.1f}",
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--workload", default="Dense")
    parser.add_argument("--max-cdf-points", type=int, default=5000)
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="wait up to this many seconds for all six successful runs",
    )
    parser.add_argument("--poll-seconds", type=int, default=60)
    return parser


def wait_for_results(
    input_dir: Path, workload: str, wait_seconds: int, poll_seconds: int
) -> None:
    deadline = time.monotonic() + wait_seconds
    expected = {(topology, policy) for topology in TOPOLOGIES for policy in POLICIES}
    previous_ready = -1
    while True:
        successful = read_jct(input_dir / "jct_results.csv")
        ready = {
            key
            for key in expected
            if key in successful
            and (
                input_dir
                / workload
                / key[0]
                / key[1]
                / "fct.txt"
            ).exists()
            and (
                input_dir
                / workload
                / key[0]
                / key[1]
                / "fct.txt"
            ).stat().st_size
            > 0
        }
        if ready == expected:
            print("all six DP-FCT runs are ready", flush=True)
            return
        if len(ready) != previous_ready:
            print(
                f"waiting for DP-FCT runs: ready={len(ready)}/{len(expected)}",
                flush=True,
            )
            previous_ready = len(ready)
        if wait_seconds == 0 or time.monotonic() >= deadline:
            missing = sorted(expected - ready)
            raise SystemExit(f"DP-FCT runs are incomplete: {missing}")
        time.sleep(poll_seconds)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    input_dir = args.input_dir.resolve()
    if args.wait_seconds < 0 or args.poll_seconds < 1:
        raise SystemExit("wait seconds must be non-negative and poll seconds positive")
    manifest = json.loads((input_dir / "manifest.json").read_text())
    if manifest.get("record_mode") != "dp-fct":
        raise SystemExit("manifest is not a DP-FCT experiment")
    if args.max_cdf_points < 2:
        raise SystemExit("--max-cdf-points must be at least 2")
    try:
        dp_group_count = int(
            manifest["workloads"][args.workload]["dp_group_count"]
        )
    except KeyError as error:
        raise SystemExit(f"missing workload metadata: {error}") from error

    wait_for_results(
        input_dir,
        args.workload,
        args.wait_seconds,
        args.poll_seconds,
    )
    jct = read_jct(input_dir / "jct_results.csv")
    output_dir = input_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []
    cdf_rows: list[dict[str, object]] = []
    series: dict[tuple[str, str], list[tuple[float, float]]] = {}

    for policy in POLICIES:
        for topology in TOPOLOGIES:
            key = (topology, policy)
            fct_path = input_dir / args.workload / topology / policy / "fct.txt"
            if not fct_path.exists() or fct_path.stat().st_size == 0:
                raise SystemExit(f"missing FCT output: {fct_path}")
            if key not in jct:
                raise SystemExit(f"missing successful JCT result: {topology}/{policy}")
            logical_fcts, metrics = parse_dp_fct(fct_path, dp_group_count)
            points = cdf_points(logical_fcts, args.max_cdf_points)
            series[key] = points
            summary_rows.append(
                {
                    "policy": policy,
                    "topology": topology,
                    "jct_us": jct[key],
                    **metrics,
                    "fct_path": str(fct_path),
                }
            )
            cdf_rows.extend(
                {
                    "policy": policy,
                    "topology": topology,
                    "fct_us": fct_us,
                    "cdf": cdf,
                }
                for fct_us, cdf in points
            )

    write_csv(output_dir / "dp_fct_summary.csv", summary_rows)
    write_csv(output_dir / "dp_fct_cdf_points.csv", cdf_rows)
    write_report(output_dir / "dp_fct_report.md", summary_rows)
    for policy in POLICIES:
        plot_policy(output_dir, policy, series)
    plot_combined(output_dir, series)
    print(f"wrote DP FCT plots and summaries to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
