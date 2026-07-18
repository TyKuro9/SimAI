#!/usr/bin/env python3

import csv
import re
import sys
from pathlib import Path


ROOT = Path("/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2")
DEFAULT_RESULTS = (
    ROOT / "experiments/flowsim_spray/adaptive_dense_1024_ga6_gapfix_20260718"
)
NS3_RESULTS = (
    ROOT / "experiments/ns3_spray/adaptive_1024_dense_ga6_20260717/jct_results.csv"
)
ORDER = ("ROFT", "Zcube", "DeepSeek", "Meta", "HPN", "RO")
JCT_RE = re.compile(r"all passes finished at time:\s*(\d+)")


def read_key_values(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def main() -> int:
    results = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RESULTS
    ns3 = {}
    with NS3_RESULTS.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["status"] == "success":
                ns3[row["topology"]] = float(row["jct_us"])

    rows = []
    for topology in ORDER:
        run_dir = results / topology
        log_path = run_dir / "run.log"
        match = JCT_RE.search(log_path.read_text(errors="replace")) if log_path.exists() else None
        timing = read_key_values(run_dir / "timing.txt")
        flowsim_jct = int(match.group(1)) / 1000.0 if match else None
        ns3_jct = ns3.get(topology)
        error = (
            abs(flowsim_jct - ns3_jct) / ns3_jct * 100.0
            if flowsim_jct is not None and ns3_jct is not None
            else None
        )
        rows.append(
            {
                "topology": topology,
                "status": "success" if (run_dir / "COMPLETE").exists() else "incomplete",
                "flowsim_jct_us": flowsim_jct,
                "ns3_jct_us": ns3_jct,
                "abs_error_pct": error,
                "wall_seconds": float(timing["wall_seconds"]) if "wall_seconds" in timing else None,
                "max_rss_kb": int(timing["max_rss_kb"]) if "max_rss_kb" in timing else None,
            }
        )

    summary_path = results / "summary.csv"
    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    comparable = [row for row in rows if row["abs_error_pct"] is not None]
    mape = (
        sum(row["abs_error_pct"] for row in comparable) / len(comparable)
        if comparable
        else None
    )
    readme = [
        "# FlowSim 1024-GPU Adaptive Spray Validation",
        "",
        "- Workload: GPT-22B Dense, TP=8, PP=4, EP=1, GA=6",
        "- Topologies: 1024-GPU 12.8 Tbps set",
        "- Routing: `spray_adaptive`, width=4, path pool=64, max extra hops=2",
        "- Transport: `ns3_cc`, 9000 B payload + 48 B header",
        "- PXN/NVLS: disabled",
        "",
        "| Topology | Status | FlowSim JCT (us) | ns-3 JCT (us) | Error | Wall (s) | RSS (GiB) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        fmt = lambda value, digits=3: "n/a" if value is None else f"{value:.{digits}f}"
        rss_gib = row["max_rss_kb"] / 1024 / 1024 if row["max_rss_kb"] else None
        error_text = "n/a" if row["abs_error_pct"] is None else f"{row['abs_error_pct']:.3f}%"
        readme.append(
            f"| {row['topology']} | {row['status']} | {fmt(row['flowsim_jct_us'])} | "
            f"{fmt(row['ns3_jct_us'])} | {error_text} | {fmt(row['wall_seconds'], 2)} | "
            f"{fmt(rss_gib, 2)} |"
        )
    if mape is not None:
        readme.extend(["", f"Comparable-topology MAPE: `{mape:.3f}%`."])
    (results / "README.md").write_text("\n".join(readme) + "\n")

    print(summary_path)
    print(results / "README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
