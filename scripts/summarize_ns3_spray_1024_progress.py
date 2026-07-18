#!/usr/bin/env python3
"""Summarize live progress for matched 1024-GPU NS3 spray matrices."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DYNAMIC_DIR = (
    ROOT / "experiments" / "ns3_spray" / "dynamic_chunk_1024_ga6_20260718"
)
DEFAULT_BASELINE_DIR = (
    ROOT / "experiments" / "ns3_spray" / "adaptive_control_1024_ga6_20260718"
)
LAYER_RE = re.compile(r"layer_num is:\s*(\d+)")


def read_manifest(path: Path) -> dict[str, object]:
    with path.open() as input_file:
        value = json.load(input_file)
    if not isinstance(value, dict):
        raise SystemExit(f"manifest is not an object: {path}")
    return value


def read_result_index(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="") as input_file:
        return {
            (row["workload_kind"], row["topology"], row["policy"]): dict(row)
            for row in csv.DictReader(input_file)
        }


def workload_records(path: Path) -> int:
    lines = path.read_text(errors="replace").splitlines()
    if len(lines) < 2:
        raise SystemExit(f"invalid workload: {path}")
    declared = int(lines[1])
    if declared != len(lines) - 2:
        raise SystemExit(
            f"{path}: declared {declared} records but found {len(lines) - 2}"
        )
    return declared


def parse_start(value: object) -> datetime:
    if not isinstance(value, str):
        raise SystemExit("manifest is missing created_at_utc")
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def format_duration(seconds: object) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "n/a"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def latest_layer(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    matches = LAYER_RE.findall(path.read_text(errors="replace"))
    return int(matches[-1]) if matches else None


def matrix_rows(
    matrix_dir: Path,
    policy: str,
    role: str,
    now: datetime,
) -> list[dict[str, object]]:
    manifest = read_manifest(matrix_dir / "manifest.json")
    started = parse_start(manifest.get("created_at_utc"))
    elapsed = max(0.0, (now - started).total_seconds())
    result_index = read_result_index(matrix_dir / "jct_results.csv")
    rows: list[dict[str, object]] = []
    workloads = manifest.get("workloads") or {}
    topologies = manifest.get("topologies") or {}
    if not isinstance(workloads, dict) or not isinstance(topologies, dict):
        raise SystemExit(f"malformed manifest: {matrix_dir / 'manifest.json'}")
    for workload_name, workload_fields in workloads.items():
        if not isinstance(workload_fields, dict):
            raise SystemExit(f"malformed workload manifest entry: {workload_name}")
        workload_path = Path(str(workload_fields["path"]))
        records = workload_records(workload_path)
        for topology in topologies:
            run_dir = matrix_dir / str(workload_name) / str(topology) / policy
            log_path = run_dir / "run.log"
            layer = latest_layer(log_path)
            progress = min(1.0, (layer + 1) / records) if layer is not None else 0.0
            result = result_index.get(
                (str(workload_name), str(topology), policy), {}
            )
            complete = result.get("status") == "success"
            if complete:
                progress = 1.0
            eta_seconds: object = "n/a"
            if complete:
                eta_seconds = 0.0
            elif progress > 0.0:
                eta_seconds = elapsed * (1.0 - progress) / progress
            log_age_seconds: object = "missing"
            if log_path.exists():
                log_age_seconds = max(
                    0.0,
                    now.timestamp() - log_path.stat().st_mtime,
                )
            rows.append(
                {
                    "role": role,
                    "workload_kind": workload_name,
                    "topology": topology,
                    "policy": policy,
                    "status": "complete" if complete else "running",
                    "latest_layer": layer if layer is not None else "missing",
                    "records": records,
                    "progress_pct": progress * 100.0,
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta_seconds,
                    "log_age_seconds": log_age_seconds,
                    "jct_us": result.get("jct_us", "pending"),
                    "run_dir": str(run_dir),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# NS3 1024-GPU Spray Progress",
        "",
        "ETA extrapolates from the latest workload record index and is only a rough wall-time estimate.",
        "",
        "| Role | Workload | Topology | Layer | Progress | Log age | ETA | JCT (us) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['role']} | {row['workload_kind']} | {row['topology']} | "
            f"{row['latest_layer']} / {int(row['records']) - 1} | "
            f"{float(row['progress_pct']):.1f}% | "
            f"{format_duration(row['log_age_seconds'])} | "
            f"{format_duration(row['eta_seconds'])} | {row['jct_us']} |"
        )
    path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dynamic-dir", type=Path, default=DEFAULT_DYNAMIC_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DYNAMIC_DIR / "comparison",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    rows = matrix_rows(
        args.dynamic_dir.resolve(),
        "spray_dynamic_chunk",
        "dynamic",
        now,
    )
    rows.extend(
        matrix_rows(
            args.baseline_dir.resolve(),
            "spray_adaptive",
            "adaptive",
            now,
        )
    )
    output_dir = args.output_dir.resolve()
    write_csv(output_dir / "progress.csv", rows)
    write_report(output_dir / "progress.md", rows)
    print(output_dir / "progress.csv")
    print(output_dir / "progress.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
