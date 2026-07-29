#!/usr/bin/env python3

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate disjoint dynamic-chunk path pairs and windows."
    )
    parser.add_argument("stripe_metrics", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-dynamic-reassignment",
        action="store_true",
        help=(
            "accept worker path/NIC changes and classify each flow from all "
            "observed chunk paths"
        ),
    )
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
    source_nic_chunks: Counter[int] = Counter()
    source_nic_bytes: Counter[int] = Counter()
    destination_nic_chunks: Counter[int] = Counter()
    worker_nic_chunks: Counter[tuple[int, int]] = Counter()
    window_mismatches = 0
    member_mismatches = 0

    for row in rows:
        key = (row["orig_src"], row["orig_dst"], row["flow_id"])
        flow_rows[key].append(row)
        hop = int(row["path_hops"])
        hop_chunks[hop] += 1
        hop_bytes[hop] += int(row["bytes"])
        worker = int(row["worker_ordinal"])
        source_nic = int(row["source_nic"])
        source_nic_chunks[source_nic] += 1
        source_nic_bytes[source_nic] += int(row["bytes"])
        destination_nic_chunks[int(row["destination_nic"])] += 1
        worker_nic_chunks[(worker, source_nic)] += 1
        member = int(row["path_pair_member"])
        if worker % 2 != member:
            member_mismatches += 1
        rtt_ns = int(row["actual_path_rtt_ns"])
        bottleneck_bps = int(row["actual_path_bottleneck_bps"])
        expected_window = (
            rtt_ns * bottleneck_bps + 7_999_999_999
        ) // 8_000_000_000
        if int(row["actual_path_window_bytes"]) != expected_window:
            window_mismatches += 1

    pair_types: Counter[str] = Counter()
    invalid_pairs = 0
    incomplete_flows = 0
    worker_path_changes = 0
    source_nic_changes = 0
    path_reassignments = 0
    source_nic_reassignments = 0

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
        worker_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
        for row in group:
            member = int(row["path_pair_member"])
            worker = int(row["worker_ordinal"])
            hop = int(row["path_hops"])
            member_hops[member].add(hop)
            worker_hops[worker].add(hop)
            worker_nics[worker].add(int(row["source_nic"]))
            worker_rows[worker].append(row)

        if any(len(hops) != 1 for hops in worker_hops.values()):
            worker_path_changes += 1
        if any(len(nics) != 1 for nics in worker_nics.values()):
            source_nic_changes += 1
        for assigned_rows in worker_rows.values():
            ordered = sorted(
                assigned_rows, key=lambda row: int(row["stripe_index"])
            )
            for previous, current in zip(ordered, ordered[1:]):
                if previous["path_signature"] != current["path_signature"]:
                    path_reassignments += 1
                if previous["source_nic"] != current["source_nic"]:
                    source_nic_reassignments += 1

        if args.allow_dynamic_reassignment:
            observed_hops = {
                int(row["path_hops"]) for row in group
            }
            if observed_hops == {2}:
                pair_types["2-only"] += 1
            elif observed_hops == {4}:
                pair_types["4-only"] += 1
            elif observed_hops == {2, 4}:
                pair_types["2+4"] += 1
            elif observed_hops == {3}:
                pair_types["3+3"] += 1
            else:
                invalid_pairs += 1
                pair_types["invalid"] += 1
        else:
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
            elif member_pattern == [2, 2]:
                pair_types["2+2"] += 1
            elif member_pattern == [2, 4]:
                pair_types["2+4"] += 1
            elif member_pattern == [3, 3]:
                pair_types["3+3"] += 1
            else:
                invalid_pairs += 1
                pair_types["invalid"] += 1

    total_bytes = sum(hop_bytes.values())
    total_source_bytes = sum(source_nic_bytes.values())
    summary = {
        "dynamic_reassignment_allowed": args.allow_dynamic_reassignment,
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
        "path_reassignments": path_reassignments,
        "source_nic_reassignments": source_nic_reassignments,
        "source_nic_chunks": dict(sorted(source_nic_chunks.items())),
        "source_nic_bytes": dict(sorted(source_nic_bytes.items())),
        "source_nic_byte_share": {
            str(nic): bytes_count / total_source_bytes
            if total_source_bytes
            else 0
            for nic, bytes_count in sorted(source_nic_bytes.items())
        },
        "destination_nic_chunks": dict(
            sorted(destination_nic_chunks.items())
        ),
        "worker_nic_chunks": {
            f"{worker}:{nic}": count
            for (worker, nic), count in sorted(worker_nic_chunks.items())
        },
        "member_mismatches": member_mismatches,
        "window_mismatches": window_mismatches,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")

    failure_fields = [
        "invalid_pairs",
        "incomplete_flows",
        "member_mismatches",
        "window_mismatches",
    ]
    if not args.allow_dynamic_reassignment:
        failure_fields.extend(("worker_path_changes", "source_nic_changes"))
    failed = any(summary[field] for field in failure_fields)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
