#!/usr/bin/env python3
"""Derive a smaller-GA SimAI workload while preserving per-layer records."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, Sequence


GA_RE = re.compile(r"\bga:\s*(\d+)\b")
WORLD_SIZE_RE = re.compile(r"\ball_gpus:\s*(\d+)\b")


def record_name(record: str) -> str:
    return record.split("\t", 1)[0]


def derive_workload(
    source: Path,
    destination: Path,
    target_ga: int,
    block_marker: str,
    target_world_size: Optional[int] = None,
) -> tuple[int, int, int]:
    lines = source.read_text().splitlines()
    if len(lines) < 3:
        raise ValueError(f"{source} is not a valid SimAI workload")

    match = GA_RE.search(lines[0])
    if match is None:
        raise ValueError(f"{source} header has no GA field")
    source_ga = int(match.group(1))
    if not 1 <= target_ga <= source_ga:
        raise ValueError(f"target GA must be between 1 and {source_ga}")

    declared_records = int(lines[1])
    records = lines[2:]
    if declared_records != len(records):
        raise ValueError(
            f"declared {declared_records} records but found {len(records)}"
        )

    marker_positions = [
        index
        for index, record in enumerate(records)
        if record_name(record) == block_marker
    ]
    if len(marker_positions) != source_ga:
        raise ValueError(
            f"expected {source_ga} '{block_marker}' records, "
            f"found {len(marker_positions)}"
        )
    if source_ga == 1:
        raise ValueError("a GA=1 source cannot reveal the repeated block size")

    block_size = marker_positions[1] - marker_positions[0]
    expected_positions = [
        marker_positions[0] + index * block_size for index in range(source_ga)
    ]
    if marker_positions != expected_positions:
        raise ValueError("GA block markers are not evenly spaced")

    prefix = records[: marker_positions[0]]
    block_end = marker_positions[-1] + block_size
    if block_end > len(records):
        raise ValueError("last GA block extends beyond the workload")
    suffix = records[block_end:]
    selected_blocks = records[
        marker_positions[0] : marker_positions[0] + target_ga * block_size
    ]
    output_records = prefix + selected_blocks + suffix
    output_header = GA_RE.sub(f"ga: {target_ga}", lines[0], count=1)
    if target_world_size is not None:
        if target_world_size < 1:
            raise ValueError("target world size must be positive")
        if WORLD_SIZE_RE.search(output_header) is None:
            raise ValueError(f"{source} header has no all_gpus field")
        output_header = WORLD_SIZE_RE.sub(
            f"all_gpus: {target_world_size}", output_header, count=1
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "\n".join([output_header, str(len(output_records)), *output_records]) + "\n"
    )
    return source_ga, block_size, len(output_records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--target-ga", type=int, required=True)
    parser.add_argument("--target-world-size", type=int)
    parser.add_argument("--block-marker", default="embedding_layer")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_ga, block_size, records = derive_workload(
        args.source.resolve(),
        args.destination.resolve(),
        args.target_ga,
        args.block_marker,
        args.target_world_size,
    )
    print(
        f"generated {args.destination}: GA {source_ga} -> {args.target_ga}, "
        f"block_size={block_size}, records={records}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
