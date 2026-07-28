#!/usr/bin/env python3

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate disjoint dynamic-chunk path pairs and windows."
    )
    parser.add_argument("stripe_metrics", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.stripe_metrics.open(newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    rows = [row for row in all_rows if int(row["dynamic_chunk"]) != 0]

    flow_rows: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    hop_chunks: Counter[int] = Counter()
    hop_bytes: Counter[int] = Counter()
    window_mismatches = 0
    member_mismatches = 0

    for row in rows:
        key = (row["orig_src"], row["orig_dst"], row["flow_id"])
        flow_rows[key].append(row)
        hop = int(row["path_hops"])
        hop_chunks[hop] += 1
        hop_bytes[hop] += int(row["bytes"])
        worker = int(row["worker_ordinal"])
        member = int(row["path_pair_member"])
        if worker % 2 != member:
            member_mismatches += 1
        rtt_ns = int(row["actual_path_rtt_ns"])
        expected_window = math.ceil(rtt_ns * 25)
        if int(row["actual_path_window_bytes"]) != expected_window:
            window_mismatches += 1

    pair_types: Counter[str] = Counter()
    invalid_pairs = 0
    incomplete_flows = 0
    worker_path_changes = 0
    source_nic_changes = 0

    for group in flow_rows.values():
        expected_chunks = int(group[0]["stripe_count"])
        stripe_indices = {int(row["stripe_index"]) for row in group}
        if len(group) != expected_chunks or stripe_indices != set(
            range(expected_chunks)
        ):
            incomplete_flows += 1

        member_hops: dict[int, set[int]] = defaultdict(set)
        worker_hops: dict[int, set[int]] = defaultdict(set)
        worker_nics: dict[int, set[int]] = defaultdict(set)
        for row in group:
            member = int(row["path_pair_member"])
            worker = int(row["worker_ordinal"])
            hop = int(row["path_hops"])
            member_hops[member].add(hop)
            worker_hops[worker].add(hop)
            worker_nics[worker].add(int(row["source_nic"]))

        if any(len(hops) != 1 for hops in worker_hops.values()):
            worker_path_changes += 1
        if any(len(nics) != 1 for nics in worker_nics.values()):
            source_nic_changes += 1

        member_pattern = sorted(
            next(iter(hops))
            for member, hops in sorted(member_hops.items())
            if len(hops) == 1
        )
        if len(member_hops) != 2 or any(
            len(hops) != 1 for hops in member_hops.values()
        ):
            invalid_pairs += 1
            pair_types["invalid"] += 1
        elif member_pattern == [2, 4]:
            pair_types["2+4"] += 1
        elif member_pattern == [3, 3]:
            pair_types["3+3"] += 1
        else:
            invalid_pairs += 1
            pair_types["invalid"] += 1

    total_bytes = sum(hop_bytes.values())
    summary = {
        "non_fabric_rows_ignored": len(all_rows) - len(rows),
        "rows": len(rows),
        "logical_flows": len(flow_rows),
        "pair_types": dict(sorted(pair_types.items())),
        "hop_chunks": dict(sorted(hop_chunks.items())),
        "hop_bytes": dict(sorted(hop_bytes.items())),
        "hop_byte_share": {
            str(hop): bytes_count / total_bytes if total_bytes else 0
            for hop, bytes_count in sorted(hop_bytes.items())
        },
        "invalid_pairs": invalid_pairs,
        "incomplete_flows": incomplete_flows,
        "worker_path_changes": worker_path_changes,
        "source_nic_changes": source_nic_changes,
        "member_mismatches": member_mismatches,
        "window_mismatches": window_mismatches,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")

    failed = any(
        summary[field]
        for field in (
            "invalid_pairs",
            "incomplete_flows",
            "worker_path_changes",
            "source_nic_changes",
            "member_mismatches",
            "window_mismatches",
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
