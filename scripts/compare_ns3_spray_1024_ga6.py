#!/usr/bin/env python3
"""Validate and compare matched NS3 spray JCT experiment matrices."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_DIR = (
    ROOT / "experiments" / "ns3_spray" / "adaptive_control_1024_ga6_20260718"
)
DEFAULT_DYNAMIC_DIR = (
    ROOT / "experiments" / "ns3_spray" / "dynamic_chunk_1024_ga6_20260718"
)


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"missing manifest: {path}")
    with path.open() as input_file:
        value = json.load(input_file)
    if not isinstance(value, dict):
        raise SystemExit(f"manifest is not an object: {path}")
    return value


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as input_file:
        return [dict(row) for row in csv.DictReader(input_file)]


def nested(manifest: dict[str, object], *keys: str) -> object:
    value: object = manifest
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def comparison_checks(
    baseline: dict[str, object], dynamic: dict[str, object]
) -> list[dict[str, object]]:
    checks: list[tuple[str, tuple[str, ...]]] = [
        ("binary_sha256", ("binary_sha256",)),
        ("spray_width", ("spray_width",)),
        ("dynamic_chunks", ("dynamic_chunks",)),
        ("threads_per_run", ("threads_per_run",)),
        ("send_latency", ("send_latency",)),
        ("pxn", ("pxn",)),
        ("record_mode", ("record_mode",)),
    ]
    workload_names = sorted(
        set((baseline.get("workloads") or {}).keys())
        | set((dynamic.get("workloads") or {}).keys())
    )
    topology_names = sorted(
        set((baseline.get("topologies") or {}).keys())
        | set((dynamic.get("topologies") or {}).keys())
    )
    for name in workload_names:
        for field in ("sha256", "all_gpus", "ga", "ep", "pp"):
            checks.append(
                (f"workloads.{name}.{field}", ("workloads", name, field))
            )
    for name in topology_names:
        checks.append(
            (f"topologies.{name}.sha256", ("topologies", name, "sha256"))
        )
    return [
        {
            "check": name,
            "baseline": nested(baseline, *keys),
            "dynamic": nested(dynamic, *keys),
            "match": nested(baseline, *keys) == nested(dynamic, *keys),
        }
        for name, keys in checks
    ]


def row_index(
    rows: list[dict[str, str]], policy: str
) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if row.get("policy") != policy:
            continue
        key = (row.get("workload_kind", ""), row.get("topology", ""))
        if key in result:
            raise SystemExit(f"duplicate {policy} result: {key}")
        result[key] = row
    return result


def jct(row: Optional[dict[str, str]]) -> Optional[float]:
    if not row or row.get("status") != "success":
        return None
    try:
        value = float(row["jct_us"])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0.0 else None


def build_comparison(
    baseline_rows: list[dict[str, str]],
    dynamic_rows: list[dict[str, str]],
    baseline_policy: str,
    dynamic_policy: str,
    expected_keys: list[tuple[str, str]],
) -> list[dict[str, object]]:
    baseline = row_index(baseline_rows, baseline_policy)
    dynamic = row_index(dynamic_rows, dynamic_policy)
    output: list[dict[str, object]] = []
    for workload, topology in expected_keys:
        baseline_jct = jct(baseline.get((workload, topology)))
        dynamic_jct = jct(dynamic.get((workload, topology)))
        complete = baseline_jct is not None and dynamic_jct is not None
        row: dict[str, object] = {
            "workload_kind": workload,
            "topology": topology,
            "baseline_policy": baseline_policy,
            "dynamic_policy": dynamic_policy,
            "baseline_jct_us": baseline_jct if baseline_jct is not None else "pending",
            "dynamic_jct_us": dynamic_jct if dynamic_jct is not None else "pending",
            "status": "complete" if complete else "pending",
            "delta_us": "pending",
            "delta_pct": "pending",
            "speedup_x": "pending",
            "winner": "pending",
        }
        if complete:
            assert baseline_jct is not None and dynamic_jct is not None
            delta = dynamic_jct - baseline_jct
            row.update(
                {
                    "delta_us": delta,
                    "delta_pct": delta / baseline_jct * 100.0,
                    "speedup_x": baseline_jct / dynamic_jct,
                    "winner": dynamic_policy if delta < 0 else baseline_policy,
                }
            )
        output.append(row)
    return output


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def number(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def geometric_mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return math.exp(sum(math.log(value) for value in values) / len(values))


def write_report(
    path: Path,
    rows: list[dict[str, object]],
    checks: list[dict[str, object]],
) -> None:
    failed_checks = [check for check in checks if not check["match"]]
    complete = [row for row in rows if row["status"] == "complete"]
    lines = [
        "# NS3 1024-GPU GA=6 Dynamic Chunk Comparison",
        "",
        f"Comparable configuration checks: {len(checks) - len(failed_checks)}/{len(checks)} passed.",
        f"Completed A/B cases: {len(complete)}/{len(rows)}.",
        "",
        "Negative delta means `spray_dynamic_chunk` has lower JCT.",
        "",
        "| Workload | Topology | Adaptive JCT (us) | Dynamic JCT (us) | Delta | Speedup | Winner |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        delta = row["delta_pct"]
        delta_text = (
            f"{float(delta):+.3f}%" if isinstance(delta, (float, int)) else str(delta)
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["workload_kind"]),
                    str(row["topology"]),
                    number(row["baseline_jct_us"]),
                    number(row["dynamic_jct_us"]),
                    delta_text,
                    number(row["speedup_x"], 6),
                    str(row["winner"]),
                ]
            )
            + " |"
        )
    if complete:
        lines.extend(["", "## Workload Summary", ""])
        lines.extend(
            [
                "| Workload | Cases | Geomean speedup |",
                "|---|---:|---:|",
            ]
        )
        for workload in sorted({str(row["workload_kind"]) for row in complete}):
            values = [
                float(row["speedup_x"])
                for row in complete
                if row["workload_kind"] == workload
            ]
            mean = geometric_mean(values)
            lines.append(
                f"| {workload} | {len(values)} | {number(mean, 6)} |"
            )
    if failed_checks:
        lines.extend(["", "## Comparability Failures", ""])
        for check in failed_checks:
            lines.append(
                f"- `{check['check']}`: baseline={check['baseline']!r}, "
                f"dynamic={check['dynamic']!r}"
            )
    path.write_text("\n".join(lines) + "\n")


def expected_keys(manifest: dict[str, object]) -> list[tuple[str, str]]:
    workloads = list((manifest.get("workloads") or {}).keys())
    topologies = list((manifest.get("topologies") or {}).keys())
    return [(workload, topology) for workload in workloads for topology in topologies]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--dynamic-dir", type=Path, default=DEFAULT_DYNAMIC_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--baseline-policy", default="spray_adaptive")
    parser.add_argument("--dynamic-policy", default="spray_dynamic_chunk")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--allow-mismatch", action="store_true")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="poll incomplete result matrices at this interval",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=259200.0,
        help="maximum time to wait for complete matrices",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.wait_seconds < 0.0 or args.wait_timeout_seconds <= 0.0:
        raise SystemExit("wait interval must be non-negative and timeout positive")
    baseline_dir = args.baseline_dir.resolve()
    dynamic_dir = args.dynamic_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else dynamic_dir / "comparison"
    )
    baseline_manifest = read_json(baseline_dir / "manifest.json")
    dynamic_manifest = read_json(dynamic_dir / "manifest.json")
    checks = comparison_checks(baseline_manifest, dynamic_manifest)
    failed_checks = [check for check in checks if not check["match"]]
    if failed_checks and not args.allow_mismatch:
        names = ", ".join(str(check["check"]) for check in failed_checks)
        raise SystemExit(f"experiment matrices are not comparable: {names}")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparability.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n"
    )
    keys = expected_keys(dynamic_manifest)
    wait_started = time.monotonic()
    while True:
        rows = build_comparison(
            read_rows(baseline_dir / "jct_results.csv"),
            read_rows(dynamic_dir / "jct_results.csv"),
            args.baseline_policy,
            args.dynamic_policy,
            keys,
        )
        pending = [row for row in rows if row["status"] != "complete"]
        write_csv(output_dir / "jct_comparison.csv", rows)
        write_report(output_dir / "report.md", rows, checks)
        if not pending or args.allow_incomplete or args.wait_seconds == 0.0:
            break
        elapsed = time.monotonic() - wait_started
        if elapsed >= args.wait_timeout_seconds:
            raise SystemExit(
                f"timed out waiting for {len(pending)} incomplete A/B cases"
            )
        labels = ", ".join(
            f"{row['workload_kind']}/{row['topology']}" for row in pending
        )
        print(f"waiting for {len(pending)} A/B cases: {labels}", flush=True)
        time.sleep(min(args.wait_seconds, args.wait_timeout_seconds - elapsed))
    if pending and not args.allow_incomplete:
        labels = ", ".join(
            f"{row['workload_kind']}/{row['topology']}" for row in pending
        )
        raise SystemExit(f"incomplete A/B cases: {labels}")

    print(output_dir / "jct_comparison.csv")
    print(output_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
