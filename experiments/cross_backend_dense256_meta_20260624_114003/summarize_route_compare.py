#!/usr/bin/env python3
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent


CASES = [
    {
        "case": "NS-3 ECMP",
        "path": ROOT / "ns3_rerun_20260624_143409" / "EndToEnd.csv",
        "log": ROOT / "ns3_rerun_20260624_143409" / "run.log",
        "model": "packet/QP/protocol",
        "route": "ECMP",
    },
    {
        "case": "htsim ECMP",
        "path": ROOT / "htsim_ecmp_full_20260626_route_compare" / "EndToEnd.csv",
        "log": ROOT / "htsim_ecmp_full_20260626_route_compare" / "run.log",
        "model": "packet RoCE",
        "route": "stable per-flow ECMP",
    },
    {
        "case": "htsim ns3_ecmp",
        "path": ROOT / "htsim_ns3_ecmp_full_20260702_ns3_ecmp" / "EndToEnd.csv",
        "log": ROOT / "htsim_ns3_ecmp_full_20260702_ns3_ecmp" / "run.log",
        "model": "packet RoCE",
        "route": "per-hop ECMP source-route approximation",
    },
    {
        "case": "htsim ns3_ecmp nofct",
        "path": ROOT / "htsim_ns3_ecmp_full_20260702_ns3_ecmp_nofct" / "EndToEnd.csv",
        "log": ROOT / "htsim_ns3_ecmp_full_20260702_ns3_ecmp_nofct" / "run.log",
        "model": "packet RoCE",
        "route": "per-hop ECMP source-route approximation, FCT output disabled",
    },
    {
        "case": "htsim spray_rr",
        "path": ROOT / "htsim_spray_rr_full_20260626_route_compare" / "EndToEnd.csv",
        "log": ROOT / "htsim_spray_rr_full_20260626_route_compare" / "run.log",
        "model": "packet RoCE",
        "route": "deterministic per-packet RR spray",
    },
    {
        "case": "htsim spray_plb",
        "path": ROOT / "htsim_spray_plb_fixed_20260624_195704" / "EndToEnd.csv",
        "log": ROOT / "htsim_spray_plb_fixed_20260624_195704" / "run.log",
        "model": "packet RoCE",
        "route": "source-side adaptive PLB",
    },
    {
        "case": "FlowSim",
        "path": ROOT / "flowsim" / "EndToEnd.csv",
        "log": ROOT / "flowsim" / "run.log",
        "model": "flow/chunk/link sharing",
        "route": "fixed precomputed path per src-dst",
    },
]


def first_number(value):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value.strip())
    return float(match.group(0)) if match else None


def parse_wall_and_rss(log_path):
    wall = ""
    rss_kb = ""
    if not log_path.exists():
        return wall, rss_kb
    for line in log_path.read_text(errors="replace").splitlines():
        if "Elapsed (wall clock) time" in line:
            wall = line.rsplit(": ", 1)[-1].strip()
        elif "Maximum resident set size" in line:
            rss_kb = line.rsplit(":", 1)[-1].strip()
    return wall, rss_kb


def fct_path_for(case):
    result_dir = case["path"].parent
    if case["case"].startswith("NS-3"):
        return result_dir / "ns3_aux" / "meta_dense_fct.txt"
    return result_dir / "fct.txt"


def count_lines(path):
    if not path.exists():
        return 0
    with path.open(errors="replace") as f:
        return sum(1 for _ in f)


def parse_running_progress(log_path):
    if not log_path.exists():
        return "", ""
    progress = ""
    exit_code = ""
    progress_re = re.compile(
        r"phase:\s*([^,]+).*?phase_progress:\s*([0-9]+/[0-9]+)\s*\(([0-9.]+%)\)"
    )
    for line in log_path.read_text(errors="replace").splitlines():
        if line.startswith("EXIT:"):
            exit_code = line.split(":", 1)[1].strip()
        match = progress_re.search(line)
        if match:
            phase = match.group(1).strip()
            ratio = match.group(2)
            pct = match.group(3)
            eta_match = re.search(r"phase_ETA\s+([0-9]+s)", line)
            eta = f"ETA {eta_match.group(1)}" if eta_match else ""
            progress = f"{phase} {ratio} ({pct})"
            if eta:
                progress += f", {eta}"
    return progress, exit_code


def parse_case(case):
    csv_path = case["path"]
    progress, exit_code = parse_running_progress(case["log"])
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        fct_lines = count_lines(fct_path_for(case))
        if (csv_path.parent / "STOPPED").exists():
            status = "stopped"
        elif exit_code and exit_code != "0":
            status = f"failed:{exit_code}"
        elif progress or fct_lines:
            status = "running"
        else:
            status = "queued_or_missing"
        return {
            **case,
            "status": status,
            "rows": 0,
            "total_time": "",
            "exposed": "",
            "comp": "",
            "dp": "",
            "tp": "",
            "bubble": "",
            "wall": "",
            "rss_kb": "",
            "progress": progress,
            "fct_rows": fct_lines if fct_lines else "",
        }
    with csv_path.open(newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        status = "incomplete"
    else:
        status = "complete"
    summary = rows[1] if len(rows) > 1 else []
    wall, rss_kb = parse_wall_and_rss(case["log"])
    return {
        **case,
        "status": status,
        "rows": len(rows),
        "total_time": first_number(summary[9]) if len(summary) > 9 else "",
        "exposed": first_number(summary[8]) if len(summary) > 8 else "",
        "comp": first_number(summary[7]) if len(summary) > 7 else "",
        "dp": first_number(summary[1]) if len(summary) > 1 else "",
        "tp": first_number(summary[3]) if len(summary) > 3 else "",
        "bubble": first_number(summary[6]) if len(summary) > 6 else "",
        "wall": wall,
        "rss_kb": rss_kb,
        "progress": "complete" if status == "complete" else progress,
        "fct_rows": "",
    }


def fmt(value):
    if value == "" or value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main():
    parsed = [parse_case(case) for case in CASES]
    out_csv = ROOT / "route_compare_summary.csv"
    fields = [
        "case",
        "status",
        "model",
        "route",
        "rows",
        "total_time",
        "exposed",
        "comp",
        "dp",
        "tp",
        "bubble",
        "progress",
        "fct_rows",
        "wall",
        "rss_kb",
        "path",
    ]
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in parsed:
            writer.writerow({field: row.get(field, "") for field in fields})

    out_md = ROOT / "route_compare_summary.md"
    with out_md.open("w") as f:
        f.write("# Dense256 Meta Route Comparison Summary\n\n")
        f.write("| Case | Status | Model | Route | Rows | Progress | FCT rows | Total time | Exposed comm | DP | TP | Wall | RSS KB |\n")
        f.write("| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |\n")
        for row in parsed:
            f.write(
                "| "
                + " | ".join(
                    [
                        row["case"],
                        row["status"],
                        row["model"],
                        row["route"],
                        str(row["rows"]),
                        row["progress"],
                        str(row["fct_rows"]),
                        fmt(row["total_time"]),
                        fmt(row["exposed"]),
                        fmt(row["dp"]),
                        fmt(row["tp"]),
                        row["wall"],
                        row["rss_kb"],
                    ]
                )
                + " |\n"
            )
        f.write("\n## Interpretation Guide\n\n")
        f.write("- NS-3 ECMP vs htsim ns3_ecmp compares NS-3 switch-side ECMP with the htsim per-hop ECMP source-route approximation.\n")
        f.write("- htsim ECMP is the older stable complete-path hash baseline, not switch-side ECMP.\n")
        f.write("- htsim ECMP vs htsim spray_rr isolates stable per-flow routing vs deterministic per-packet spray.\n")
        f.write("- htsim ECMP vs htsim spray_plb isolates stable per-flow routing vs source-side adaptive PLB.\n")
        f.write("- FlowSim should be read as a flow/chunk/link-sharing model with fixed per-src-dst paths, not as packet-level ECMP or Spray.\n")

    print(out_csv)
    print(out_md)


if __name__ == "__main__":
    main()
