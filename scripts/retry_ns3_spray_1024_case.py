#!/usr/bin/env python3
"""Retry one failed 1024-GPU spray case and safely merge its result."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ns3_spray_1024_ga6.py"
RESULT_NAME = "jct_results.csv"
ROW_INVARIANTS = (
    "world_size",
    "ga",
    "binary_sha256",
    "workload_sha256",
    "topology_sha256",
    "topology",
    "policy",
    "spray_width",
    "dynamic_chunks",
    "configured_flowlet_gap_ns",
    "configured_flowlet_bytes",
    "configured_flowlet_hysteresis_ns",
    "threads",
    "send_latency",
    "record_mode",
    "dp_size",
    "dp_group_count",
)


def read_json(path: Path) -> dict[str, object]:
    with path.open() as input_file:
        value = json.load(input_file)
    if not isinstance(value, dict):
        raise SystemExit(f"JSON object expected: {path}")
    return value


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as input_file:
        return [dict(row) for row in csv.DictReader(input_file)]


def key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["workload_kind"], row["topology"], row["policy"]


def expected_keys(manifest: dict[str, object]) -> set[tuple[str, str, str]]:
    workloads = (manifest.get("workloads") or {}).keys()
    topologies = (manifest.get("topologies") or {}).keys()
    policies = manifest.get("policies") or []
    return {
        (str(workload), str(topology), str(policy))
        for workload in workloads
        for topology in topologies
        for policy in policies
    }


def value(manifest: dict[str, object], name: str) -> str:
    raw = manifest.get(name)
    if isinstance(raw, bool):
        return "1" if raw else "0"
    return str(raw)


def runner_command(
    manifest: dict[str, object],
    retry_dir: Path,
    workload: str,
    topology: str,
    policy: str,
) -> list[str]:
    return [
        sys.executable,
        str(RUNNER),
        "--binary",
        str(manifest["binary"]),
        "--output-dir",
        str(retry_dir),
        "--workloads",
        workload,
        "--topologies",
        topology,
        "--policies",
        policy,
        "--spray-width",
        value(manifest, "spray_width"),
        "--dynamic-chunks",
        value(manifest, "dynamic_chunks"),
        "--flowlet-gap-ns",
        value(manifest, "flowlet_gap_ns"),
        "--flowlet-bytes",
        value(manifest, "flowlet_bytes"),
        "--flowlet-hysteresis-ns",
        value(manifest, "flowlet_hysteresis_ns"),
        "--threads",
        value(manifest, "threads_per_run"),
        "--parallel-runs",
        "1",
        "--send-latency",
        value(manifest, "send_latency"),
        "--timeout",
        value(manifest, "timeout_seconds"),
        "--record-mode",
        value(manifest, "record_mode"),
    ]


def validate_retry_manifest(
    authoritative: dict[str, object],
    retry: dict[str, object],
    workload: str,
    topology: str,
    policy: str,
) -> None:
    for field in (
        "binary_sha256",
        "spray_width",
        "dynamic_chunks",
        "flowlet_gap_ns",
        "flowlet_bytes",
        "flowlet_hysteresis_ns",
        "threads_per_run",
        "send_latency",
        "pxn",
        "record_mode",
    ):
        if authoritative.get(field) != retry.get(field):
            raise SystemExit(f"retry manifest mismatch: {field}")
    for section, name in (("workloads", workload), ("topologies", topology)):
        authoritative_entry = (authoritative.get(section) or {}).get(name)
        retry_entry = (retry.get(section) or {}).get(name)
        if authoritative_entry != retry_entry:
            raise SystemExit(f"retry manifest mismatch: {section}.{name}")
    if retry.get("policies") != [policy]:
        raise SystemExit("retry manifest has an unexpected policy set")


def wait_for_authoritative_rows(
    result_path: Path,
    expected: set[tuple[str, str, str]],
    poll_seconds: float,
    stable_seconds: float,
    timeout_seconds: float,
) -> list[dict[str, str]]:
    started = time.monotonic()
    stable_since: Optional[float] = None
    observed_mtime: Optional[int] = None
    while True:
        rows = read_rows(result_path)
        current = {key(row) for row in rows}
        mtime = result_path.stat().st_mtime_ns if result_path.exists() else None
        now = time.monotonic()
        if expected.issubset(current):
            if mtime != observed_mtime:
                observed_mtime = mtime
                stable_since = now
            elif stable_since is not None and now - stable_since >= stable_seconds:
                return rows
        else:
            observed_mtime = mtime
            stable_since = None
        if now - started >= timeout_seconds:
            raise SystemExit("timed out waiting for authoritative matrix to settle")
        time.sleep(poll_seconds)


def merge_retry(
    authoritative_path: Path,
    authoritative_rows: list[dict[str, str]],
    retry_rows: list[dict[str, str]],
    target: tuple[str, str, str],
    retry_dir: Path,
) -> None:
    authoritative_index = {key(row): row for row in authoritative_rows}
    retry_index = {key(row): row for row in retry_rows}
    if target not in authoritative_index or target not in retry_index:
        raise SystemExit(f"missing retry target row: {target}")
    previous = authoritative_index[target]
    replacement = retry_index[target]
    if replacement.get("status") != "success" or replacement.get("jct_us") in {
        None,
        "",
        "missing",
    }:
        raise SystemExit("retry did not produce a successful JCT")
    mismatches = [
        field
        for field in ROW_INVARIANTS
        if previous.get(field) != replacement.get(field)
    ]
    if mismatches:
        raise SystemExit("retry row mismatch: " + ", ".join(mismatches))

    authoritative_index[target] = replacement
    merged = [authoritative_index[item] for item in sorted(authoritative_index)]
    fieldnames = list(authoritative_rows[0])
    temporary = authoritative_path.with_suffix(".retry.tmp")
    with temporary.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)
    os.replace(temporary, authoritative_path)
    (retry_dir / "merge_record.json").write_text(
        json.dumps(
            {
                "target": target,
                "previous_status": previous.get("status"),
                "previous_return_code": previous.get("return_code"),
                "replacement_status": replacement.get("status"),
                "replacement_jct_us": replacement.get("jct_us"),
                "authoritative_results": str(authoritative_path),
            },
            indent=2,
        )
        + "\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative-dir", type=Path, required=True)
    parser.add_argument("--retry-dir", type=Path, required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--stable-seconds", type=float, default=120.0)
    parser.add_argument("--merge-timeout-seconds", type=float, default=259200.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    authoritative_dir = args.authoritative_dir.resolve()
    retry_dir = args.retry_dir.resolve()
    manifest = read_json(authoritative_dir / "manifest.json")
    target = (args.workload, args.topology, args.policy)
    if target not in expected_keys(manifest):
        raise SystemExit(f"target is not in authoritative matrix: {target}")
    command = runner_command(
        manifest, retry_dir, args.workload, args.topology, args.policy
    )
    if args.dry_run:
        print(" ".join(command))
        return 0

    retry_dir.mkdir(parents=True, exist_ok=True)
    return_code = subprocess.run(command, cwd=ROOT, check=False).returncode
    if return_code != 0:
        raise SystemExit(f"retry runner failed with return code {return_code}")
    retry_manifest = read_json(retry_dir / "manifest.json")
    validate_retry_manifest(
        manifest, retry_manifest, args.workload, args.topology, args.policy
    )
    authoritative_rows = wait_for_authoritative_rows(
        authoritative_dir / RESULT_NAME,
        expected_keys(manifest),
        args.poll_seconds,
        args.stable_seconds,
        args.merge_timeout_seconds,
    )
    merge_retry(
        authoritative_dir / RESULT_NAME,
        authoritative_rows,
        read_rows(retry_dir / RESULT_NAME),
        target,
        retry_dir,
    )
    print(f"merged successful retry for {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
