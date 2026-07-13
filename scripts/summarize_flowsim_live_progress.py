#!/usr/bin/env python3
"""Summarize a running FlowSim fault sweep from its CSV outputs."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def markdown_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    widths = {
        header: max(len(header), *(len(str(row.get(header, ""))) for row in rows))
        for header in headers
    }
    lines = [
        "| " + " | ".join(header.ljust(widths[header]) for header in headers) + " |",
        "| " + " | ".join("-" * widths[header] for header in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)
            + " |"
        )
    return "\n".join(lines)


def fmt_rate(rate: str) -> str:
    try:
        return f"{float(rate) * 100:.0f}%"
    except ValueError:
        return rate


def run(args: argparse.Namespace) -> int:
    sweep_dir = args.sweep_dir
    baseline_rows = read_rows(sweep_dir / "baseline_jct.csv")
    raw_rows = read_rows(sweep_dir / "random_link_failure_raw.csv")
    summary_rows = read_rows(sweep_dir / "random_link_failure_summary.csv")

    total_expected = args.expected_total
    status_counts = Counter(row.get("status", "") for row in raw_rows)
    topology_counts = Counter(row.get("topology", "") for row in raw_rows)
    rate_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in raw_rows:
        rate_counts[(row.get("topology", ""), row.get("link_failure_probability", ""))] += 1

    baseline_table = [
        {
            "Topology": row.get("topology", ""),
            "Baseline JCT": row.get("normal_jct", ""),
        }
        for row in baseline_rows
    ]
    status_table = [
        {"Status": status or "(blank)", "Rows": count}
        for status, count in sorted(status_counts.items())
    ]
    topology_table = [
        {"Topology": topology, "Rows": count}
        for topology, count in sorted(topology_counts.items())
    ]
    rate_table = [
        {"Topology": topology, "Rate": fmt_rate(rate), "Rows": count}
        for (topology, rate), count in sorted(rate_counts.items())
    ]

    completed = len(raw_rows)
    pct = completed / total_expected * 100 if total_expected else 0.0
    lines = [
        "# FlowSim Live Progress",
        "",
        f"Sweep: `{sweep_dir}`",
        f"Raw rows: `{completed}/{total_expected}` (`{pct:.1f}%`)",
        f"Summary rows: `{len(summary_rows)}`",
        "",
        "## Baselines",
        "",
        markdown_table(baseline_table),
        "",
        "## Status",
        "",
        markdown_table(status_table),
        "",
        "## Topology Coverage",
        "",
        markdown_table(topology_table),
        "",
        "## Rate Coverage",
        "",
        markdown_table(rate_table),
    ]
    args.output.write_text("\n".join(lines).rstrip() + "\n")
    print(args.output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sweep_dir", type=Path)
    parser.add_argument("--expected-total", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
