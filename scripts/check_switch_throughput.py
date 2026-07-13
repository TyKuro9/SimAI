#!/usr/bin/env python3
"""Check per-switch port throughput in SimAI topology files.

The intended use is to enforce a physical switch ASIC budget without changing
individual link speeds.  By default only ordinary scale-out switches are
checked; NVSwitch nodes are excluded from the budget.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List

from fault_tolerance_experiments import Topology, parse_topology


BW_RE = re.compile(r"^([0-9.]+)\s*([TGMK]?bps)$", re.IGNORECASE)


def bandwidth_to_gbps(value: str) -> float:
    match = BW_RE.match(value.strip())
    if not match:
        raise ValueError(f"unsupported bandwidth value: {value!r}")

    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "tbps":
        return number * 1000.0
    if unit == "gbps":
        return number
    if unit == "mbps":
        return number / 1000.0
    if unit == "kbps":
        return number / 1_000_000.0
    if unit == "bps":
        return number / 1_000_000_000.0
    raise ValueError(f"unsupported bandwidth unit: {unit}")


def checked_switch_ids(topology: Topology, include_nvswitch: bool) -> List[int]:
    ids = set(topology.ordinary_switch_ids)
    if include_nvswitch:
        ids.update(topology.nvswitch_ids)
    return sorted(ids)


def summarize_topology(
    topology: Topology,
    *,
    limit_gbps: float,
    include_nvswitch: bool = False,
) -> Dict[str, object]:
    switch_ids = checked_switch_ids(topology, include_nvswitch)
    loads = {switch_id: 0.0 for switch_id in switch_ids}
    degrees = {switch_id: 0 for switch_id in switch_ids}
    by_peer_type = {
        switch_id: {"gpu": 0.0, "nvswitch": 0.0, "switch": 0.0, "unknown": 0.0}
        for switch_id in switch_ids
    }

    for link in topology.links:
        bw_gbps = bandwidth_to_gbps(link.bandwidth)
        for switch_id, peer in ((link.src, link.dst), (link.dst, link.src)):
            if switch_id not in loads:
                continue
            loads[switch_id] += bw_gbps
            degrees[switch_id] += 1
            by_peer_type[switch_id][topology.node_type(peer)] += bw_gbps

    values = sorted(loads.values())
    if not values:
        raise ValueError(f"no switches selected for {topology.path}")

    over_limit = [
        {
            "switch_id": switch_id,
            "load_gbps": loads[switch_id],
            "degree": degrees[switch_id],
            "peer_split_gbps": by_peer_type[switch_id],
        }
        for switch_id in sorted(loads)
        if loads[switch_id] > limit_gbps + 1e-9
    ]
    max_switch = max(loads, key=loads.get)
    min_switch = min(loads, key=loads.get)

    return {
        "path": str(topology.path),
        "gpu_count": topology.gpu_count,
        "nvswitch_count": topology.nvswitch_count,
        "ordinary_switch_count": len(topology.ordinary_switch_ids),
        "checked_switch_count": len(values),
        "limit_gbps": limit_gbps,
        "min_gbps": values[0],
        "mean_gbps": mean(values),
        "p50_gbps": values[len(values) // 2],
        "max_gbps": values[-1],
        "mean_utilization": mean(values) / limit_gbps if limit_gbps else None,
        "over_limit_count": len(over_limit),
        "max_switch": {
            "switch_id": max_switch,
            "load_gbps": loads[max_switch],
            "degree": degrees[max_switch],
            "peer_split_gbps": by_peer_type[max_switch],
        },
        "min_switch": {
            "switch_id": min_switch,
            "load_gbps": loads[min_switch],
            "degree": degrees[min_switch],
            "peer_split_gbps": by_peer_type[min_switch],
        },
        "over_limit": over_limit,
    }


def print_table(summaries: Iterable[Dict[str, object]]) -> None:
    print(
        "topology,checked_switches,min_gbps,p50_gbps,mean_gbps,max_gbps,"
        "mean_utilization,over_limit"
    )
    for summary in summaries:
        path = Path(str(summary["path"]))
        print(
            f"{path.name},"
            f"{summary['checked_switch_count']},"
            f"{summary['min_gbps']:.0f},"
            f"{summary['p50_gbps']:.0f},"
            f"{summary['mean_gbps']:.1f},"
            f"{summary['max_gbps']:.0f},"
            f"{summary['mean_utilization']:.3f},"
            f"{summary['over_limit_count']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topologies", nargs="+", type=Path)
    parser.add_argument("--limit-gbps", type=float, default=12800.0)
    parser.add_argument(
        "--include-nvswitch",
        action="store_true",
        help="also check NVSwitch nodes; default checks ordinary scale-out switches only",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of CSV-like table")
    parser.add_argument(
        "--fail-on-over-limit",
        action="store_true",
        help="return non-zero when any checked switch exceeds the limit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summaries = [
        summarize_topology(
            parse_topology(path),
            limit_gbps=args.limit_gbps,
            include_nvswitch=args.include_nvswitch,
        )
        for path in args.topologies
    ]

    if args.json:
        print(json.dumps(summaries, indent=2, sort_keys=True))
    else:
        print_table(summaries)

    if args.fail_on_over_limit and any(summary["over_limit_count"] for summary in summaries):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
