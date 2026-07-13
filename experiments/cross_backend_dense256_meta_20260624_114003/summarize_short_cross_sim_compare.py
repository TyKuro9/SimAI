#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path


def first_number(value):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value.strip())
    return float(match.group(0)) if match else ""


def parse_wall_and_rss(log_path):
    wall = ""
    rss_kb = ""
    exit_code = ""
    finished = False
    packet_level = ""
    if not log_path.exists():
        return wall, rss_kb, exit_code, finished, packet_level
    for line in log_path.read_text(errors="replace").splitlines():
        if "Elapsed (wall clock) time" in line:
            wall = line.rsplit(": ", 1)[-1].strip()
        elif "Maximum resident set size" in line:
            rss_kb = line.rsplit(":", 1)[-1].strip()
        elif line.startswith("EXIT:"):
            exit_code = line.split(":", 1)[1].strip()
        elif "all passes finished" in line or "workload stats for the job scheduled" in line:
            finished = True
        elif "packet_level=" in line:
            match = re.search(r"packet_level=(\d+)", line)
            if match:
                packet_level = match.group(1)
    return wall, rss_kb, exit_code, finished, packet_level


def count_lines(path):
    if not path.exists():
        return 0
    with path.open(errors="replace") as f:
        return sum(1 for _ in f)


def parse_endtoend(csv_path):
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return {
            "rows": 0,
            "total_time": "",
            "exposed": "",
            "comp": "",
            "dp": "",
            "tp": "",
        }
    with csv_path.open(newline="") as f:
        rows = list(csv.reader(f))
    summary = rows[1] if len(rows) > 1 else []
    return {
        "rows": len(rows),
        "total_time": first_number(summary[9]) if len(summary) > 9 else "",
        "exposed": first_number(summary[8]) if len(summary) > 8 else "",
        "comp": first_number(summary[7]) if len(summary) > 7 else "",
        "dp": first_number(summary[1]) if len(summary) > 1 else "",
        "tp": first_number(summary[3]) if len(summary) > 3 else "",
    }


def fmt(value):
    if value == "" or value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main():
    if len(sys.argv) != 2:
        print("usage: summarize_short_cross_sim_compare.py <output-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    cases = [
        {
            "case": "FlowSim",
            "dir": root / "flowsim",
            "model": "flow/chunk/link sharing",
            "route": "fixed precomputed path per src-dst",
        },
        {
            "case": "htsim ECMP",
            "dir": root / "htsim_ecmp",
            "model": "packet RoCE",
            "route": "stable per-flow ECMP",
        },
        {
            "case": "htsim spray_rr",
            "dir": root / "htsim_spray_rr",
            "model": "packet RoCE",
            "route": "deterministic per-packet RR spray",
        },
        {
            "case": "NS-3 ECMP",
            "dir": root / "ns3_ecmp",
            "model": "packet/QP/protocol",
            "route": "switch-side ECMP",
        },
    ]
    rows = []
    for case in cases:
        out_dir = case["dir"]
        e2e = parse_endtoend(out_dir / "EndToEnd.csv")
        wall, rss_kb, exit_code, finished, packet_level = parse_wall_and_rss(out_dir / "run.log")
        row = {
            **case,
            **e2e,
            "status": "complete" if e2e["rows"] > 1 and exit_code == "0" else "missing_or_incomplete",
            "exit_code": exit_code,
            "finished_marker": int(finished),
            "packet_level": packet_level,
            "fct_lines": count_lines(out_dir / "fct.txt"),
            "ns3_fct_lines": count_lines(out_dir / "ns3_aux" / "short_fct.txt"),
            "wall": wall,
            "rss_kb": rss_kb,
        }
        rows.append(row)

    fields = [
        "case",
        "status",
        "exit_code",
        "finished_marker",
        "model",
        "route",
        "packet_level",
        "rows",
        "total_time",
        "exposed",
        "comp",
        "dp",
        "tp",
        "fct_lines",
        "ns3_fct_lines",
        "wall",
        "rss_kb",
        "dir",
    ]
    with (root / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    with (root / "summary.md").open("w") as f:
        f.write("# Short Dense256 Meta Cross-Simulator Summary\n\n")
        f.write("| Case | Status | Model | Route | Rows | Total time | Exposed comm | DP | TP | FCT rows | Wall | RSS KB |\n")
        f.write("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |\n")
        for row in rows:
            fct_rows = row["fct_lines"] or row["ns3_fct_lines"]
            f.write(
                "| "
                + " | ".join(
                    [
                        row["case"],
                        row["status"],
                        row["model"],
                        row["route"],
                        str(row["rows"]),
                        fmt(row["total_time"]),
                        fmt(row["exposed"]),
                        fmt(row["dp"]),
                        fmt(row["tp"]),
                        str(fct_rows),
                        row["wall"],
                        row["rss_kb"],
                    ]
                )
                + " |\n"
            )
        f.write("\n## Notes\n\n")
        f.write("- This is a short/capped sanity matrix, not a replacement for the full dense workload.\n")
        f.write("- Use it to check directionality and whether each backend is producing comparable upper-stack reports.\n")
        f.write("- The full route-isolation conclusion still needs the long htsim ECMP and htsim spray_rr runs to finish.\n")

    print(root / "summary.csv")
    print(root / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
