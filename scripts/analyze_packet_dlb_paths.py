#!/usr/bin/env python3

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path


INTEGER_FIELDS = {
    "src_gpu",
    "dst_gpu",
    "src_nic",
    "dst_nic",
    "path_hops",
    "path_signature",
    "considered_packets",
    "selected_packets",
    "selected_bytes",
    "idle_when_considered",
    "busy_when_considered",
    "selected_idle_packets",
    "selected_busy_packets",
    "selected_busy_with_idle_alternative",
    "selected_with_lower_queue_alternative",
    "selected_with_shorter_alternative",
    "candidate_paths_sum",
    "idle_candidates_sum",
    "selected_queue_bytes_sum",
    "selected_reserved_bytes_sum",
    "selected_score_ns_sum",
}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def format_shares(values: Counter[int]) -> str:
    total = sum(values.values())
    return ",".join(
        f"{key}:{100.0 * value / total:.2f}%"
        for key, value in sorted(values.items())
    ) if total else ""


def format_labeled_shares(values: Counter[tuple[int, int]]) -> str:
    total = sum(values.values())
    return ",".join(
        f"hops{hops}->nic{nic}:{100.0 * value / total:.2f}%"
        for (hops, nic), value in sorted(values.items())
    ) if total else ""


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="") as input_file:
        for raw in csv.DictReader(input_file):
            row: dict[str, object] = dict(raw)
            for field in INTEGER_FIELDS:
                row[field] = int(raw[field])
            rows.append(row)
    return rows


def read_jct(run_dir: Path) -> float | None:
    path = run_dir / "EndToEnd.csv"
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open(newline="") as input_file:
        rows = list(csv.reader(input_file))
    if not rows or not rows[-1]:
        return None
    try:
        return float(rows[-1][-1])
    except ValueError:
        return None


def analyze_topology(
    name: str, run_dir: Path
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    rows = load_rows(run_dir / "packet_dlb_paths.csv")
    selected_rows = [row for row in rows if int(row["selected_packets"]) > 0]
    selected_packets = sum(int(row["selected_packets"]) for row in selected_rows)
    selected_bytes = sum(int(row["selected_bytes"]) for row in selected_rows)

    hop_packets: Counter[int] = Counter()
    hop_destination_nic_packets: Counter[tuple[int, int]] = Counter()
    source_nic_bytes: Counter[int] = Counter()
    destination_nic_bytes: Counter[int] = Counter()
    for row in selected_rows:
        packets = int(row["selected_packets"])
        bytes_value = int(row["selected_bytes"])
        hop_packets[int(row["path_hops"])] += packets
        hop_destination_nic_packets[
            (int(row["path_hops"]), int(row["dst_nic"]))
        ] += packets
        source_nic_bytes[int(row["src_nic"])] += bytes_value
        destination_nic_bytes[int(row["dst_nic"])] += bytes_value

    pair_rows: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        pair_rows[(int(row["src_gpu"]), int(row["dst_gpu"]))].append(row)

    per_pair: list[dict[str, object]] = []
    pair_max_path_shares: list[float] = []
    pair_max_destination_nic_shares: list[float] = []
    hop4_candidate_counts: list[float] = []
    hop4_selected_counts: list[float] = []
    hop4_max_path_shares: list[float] = []
    for (source, destination), current_rows in sorted(pair_rows.items()):
        current_selected = [
            row for row in current_rows if int(row["selected_packets"]) > 0
        ]
        packet_total = sum(int(row["selected_packets"]) for row in current_selected)
        path_max_share = max(
            (ratio(int(row["selected_packets"]), packet_total) for row in current_selected),
            default=0.0,
        )
        destination_counts: Counter[int] = Counter()
        current_hops: Counter[int] = Counter()
        for row in current_selected:
            packets = int(row["selected_packets"])
            destination_counts[int(row["dst_nic"])] += packets
            current_hops[int(row["path_hops"])] += packets
        destination_max_share = max(
            (ratio(value, packet_total) for value in destination_counts.values()),
            default=0.0,
        )
        pair_max_path_shares.append(path_max_share)
        pair_max_destination_nic_shares.append(destination_max_share)

        hop4_candidates = [
            row
            for row in current_rows
            if int(row["path_hops"]) == 4 and int(row["considered_packets"]) > 0
        ]
        hop4_selected = [
            row for row in hop4_candidates if int(row["selected_packets"]) > 0
        ]
        hop4_packets = sum(int(row["selected_packets"]) for row in hop4_selected)
        hop4_max_share = max(
            (
                ratio(int(row["selected_packets"]), hop4_packets)
                for row in hop4_selected
            ),
            default=0.0,
        )
        hop4_candidate_counts.append(float(len(hop4_candidates)))
        hop4_selected_counts.append(float(len(hop4_selected)))
        if hop4_packets:
            hop4_max_path_shares.append(hop4_max_share)

        per_pair.append(
            {
                "topology": name,
                "src_gpu": source,
                "dst_gpu": destination,
                "selected_packets": packet_total,
                "selected_paths": len(current_selected),
                "candidate_paths": sum(
                    int(row["considered_packets"]) > 0 for row in current_rows
                ),
                "hop_packet_shares": format_shares(current_hops),
                "max_path_share": path_max_share,
                "destination_nic_shares": format_shares(destination_counts),
                "max_destination_nic_share": destination_max_share,
                "hop4_candidate_paths": len(hop4_candidates),
                "hop4_selected_paths": len(hop4_selected),
                "hop4_max_path_share": hop4_max_share,
            }
        )

    receiver_nic_bytes: dict[int, Counter[int]] = defaultdict(Counter)
    for row in selected_rows:
        receiver_nic_bytes[int(row["dst_gpu"])][int(row["dst_nic"])] += int(
            row["selected_bytes"]
        )
    receiver_max_nic_shares = [
        max(values.values()) / sum(values.values())
        for values in receiver_nic_bytes.values()
        if values and sum(values.values())
    ]

    idle_misses = sum(
        int(row["selected_busy_with_idle_alternative"]) for row in selected_rows
    )
    lower_queue_alternatives = sum(
        int(row["selected_with_lower_queue_alternative"]) for row in selected_rows
    )
    shorter_alternatives = sum(
        int(row["selected_with_shorter_alternative"]) for row in selected_rows
    )
    candidate_rows = [row for row in rows if int(row["considered_packets"]) > 0]
    unselected_candidate_rows = [
        row for row in candidate_rows if int(row["selected_packets"]) == 0
    ]
    hop_rows: list[dict[str, object]] = []
    for hops in sorted(
        {int(row["path_hops"]) for row in candidate_rows}
        | set(hop_packets)
    ):
        current_candidates = [
            row for row in candidate_rows if int(row["path_hops"]) == hops
        ]
        current_selected = [
            row for row in current_candidates if int(row["selected_packets"]) > 0
        ]
        hop_selected_packets = sum(
            int(row["selected_packets"]) for row in current_selected
        )
        hop_destination_counts: Counter[int] = Counter()
        for row in current_selected:
            hop_destination_counts[int(row["dst_nic"])] += int(
                row["selected_packets"]
            )
        hop_rows.append(
            {
                "topology": name,
                "path_hops": hops,
                "candidate_path_rows": len(current_candidates),
                "selected_path_rows": len(current_selected),
                "selected_packets": hop_selected_packets,
                "selected_packet_share": ratio(
                    hop_selected_packets, selected_packets
                ),
                "destination_nic_packet_shares": format_shares(
                    hop_destination_counts
                ),
                "busy_selected_with_idle_alternative_ratio": ratio(
                    sum(
                        int(row["selected_busy_with_idle_alternative"])
                        for row in current_selected
                    ),
                    hop_selected_packets,
                ),
            }
        )

    summary = {
        "topology": name,
        "jct_us": read_jct(run_dir),
        "selected_packets": selected_packets,
        "selected_bytes": selected_bytes,
        "dp_pairs": len(pair_rows),
        "candidate_path_rows": len(candidate_rows),
        "selected_path_rows": len(selected_rows),
        "unselected_candidate_path_ratio": ratio(
            len(unselected_candidate_rows), len(candidate_rows)
        ),
        "hop_packet_shares": format_shares(hop_packets),
        "source_nic_byte_shares": format_shares(source_nic_bytes),
        "destination_nic_byte_shares": format_shares(destination_nic_bytes),
        "hop_destination_nic_packet_shares": format_labeled_shares(
            hop_destination_nic_packets
        ),
        "busy_selected_with_idle_alternative_ratio": ratio(
            idle_misses, selected_packets
        ),
        "selected_with_lower_queue_alternative_ratio": ratio(
            lower_queue_alternatives, selected_packets
        ),
        "selected_with_shorter_alternative_ratio": ratio(
            shorter_alternatives, selected_packets
        ),
        "pair_max_path_share_mean": statistics.mean(pair_max_path_shares),
        "pair_max_path_share_p95": percentile(pair_max_path_shares, 0.95),
        "pair_max_destination_nic_share_mean": statistics.mean(
            pair_max_destination_nic_shares
        ),
        "pair_max_destination_nic_share_p95": percentile(
            pair_max_destination_nic_shares, 0.95
        ),
        "receiver_max_nic_share_mean": statistics.mean(receiver_max_nic_shares),
        "receiver_max_nic_share_p95": percentile(receiver_max_nic_shares, 0.95),
        "hop4_candidate_paths_per_pair_mean": statistics.mean(
            hop4_candidate_counts
        ),
        "hop4_selected_paths_per_pair_mean": statistics.mean(
            hop4_selected_counts
        ),
        "hop4_max_path_share_mean": statistics.mean(hop4_max_path_shares)
        if hop4_max_path_shares
        else 0.0,
    }
    return summary, per_pair, hop_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percent(value: object) -> str:
    return f"{100.0 * float(value):.2f}%"


def write_report(path: Path, summaries: list[dict[str, object]]) -> None:
    lines = [
        "# Packet DLB DP path diagnostics",
        "",
        "| Topology | JCT (us) | Hop packet shares | Destination NIC shares | "
        "Busy chosen with idle alternative | Pair max destination-NIC share |",
        "|---|---:|---|---|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['topology']} | {row['jct_us']} | "
            f"{row['hop_packet_shares']} | {row['destination_nic_byte_shares']} | "
            f"{percent(row['busy_selected_with_idle_alternative_ratio'])} | "
            f"{percent(row['pair_max_destination_nic_share_mean'])} |"
        )
    lines.extend(["", "## Path dispersion", ""])
    for row in summaries:
        lines.extend(
            [
                f"### {row['topology']}",
                "",
                f"- Source NIC byte shares: {row['source_nic_byte_shares']}",
                f"- Hop to destination-NIC packet shares: "
                f"{row['hop_destination_nic_packet_shares']}",
                f"- Mean/P95 maximum path share per DP pair: "
                f"{percent(row['pair_max_path_share_mean'])} / "
                f"{percent(row['pair_max_path_share_p95'])}",
                f"- Mean/P95 maximum destination-NIC share per DP pair: "
                f"{percent(row['pair_max_destination_nic_share_mean'])} / "
                f"{percent(row['pair_max_destination_nic_share_p95'])}",
                f"- Mean/P95 receiver-wide maximum NIC share: "
                f"{percent(row['receiver_max_nic_share_mean'])} / "
                f"{percent(row['receiver_max_nic_share_p95'])}",
                f"- Mean 4-hop candidate/selected paths per pair: "
                f"{float(row['hop4_candidate_paths_per_pair_mean']):.2f} / "
                f"{float(row['hop4_selected_paths_per_pair_mean']):.2f}",
                f"- Busy selected while an idle candidate existed: "
                f"{percent(row['busy_selected_with_idle_alternative_ratio'])}",
                f"- Selected despite a lower-queue candidate: "
                f"{percent(row['selected_with_lower_queue_alternative_ratio'])}",
                f"- Selected while a shorter sampled candidate existed: "
                f"{percent(row['selected_with_shorter_alternative_ratio'])}",
                "",
            ]
        )
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Topology name and run directory as NAME=PATH",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    summaries: list[dict[str, object]] = []
    per_pair: list[dict[str, object]] = []
    per_hop: list[dict[str, object]] = []
    for specification in args.run:
        name, path = specification.split("=", 1)
        summary, pair_rows, hop_rows = analyze_topology(name, Path(path))
        summaries.append(summary)
        per_pair.extend(pair_rows)
        per_hop.extend(hop_rows)

    write_csv(args.output_dir / "summary.csv", summaries)
    write_csv(args.output_dir / "per_pair.csv", per_pair)
    write_csv(args.output_dir / "per_hop.csv", per_hop)
    write_report(args.output_dir / "report.md", summaries)


if __name__ == "__main__":
    main()
