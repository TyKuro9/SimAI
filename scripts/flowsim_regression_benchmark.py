#!/usr/bin/env python3
import argparse
import csv
import statistics
from pathlib import Path


def ParseFctFile(fct_path: Path):
    values = []
    with fct_path.open("r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split()
            if len(parts) < 8:
                continue
            values.append(int(parts[6]))
    if not values:
        raise RuntimeError(f"empty fct data: {fct_path}")
    values.sort()
    return values


def Percentile(sorted_values, ratio: float):
    index = min(len(sorted_values) - 1, max(0, int(ratio * (len(sorted_values) - 1))))
    return float(sorted_values[index])


def ReadRuntime(runtime_file: Path):
    content = runtime_file.read_text(encoding="utf-8").strip().split()
    if len(content) < 1:
        raise RuntimeError(f"invalid runtime file: {runtime_file}")
    return float(content[0])


def AggregateThreadMetrics(records):
    runtime_list = [item["runtime_sec"] for item in records]
    p50_list = [item["p50_ns"] for item in records]
    p95_list = [item["p95_ns"] for item in records]
    p99_list = [item["p99_ns"] for item in records]
    return {
        "runtime_median_sec": statistics.median(runtime_list),
        "runtime_stdev_sec": statistics.pstdev(runtime_list) if len(runtime_list) > 1 else 0.0,
        "p50_median_ns": statistics.median(p50_list),
        "p95_median_ns": statistics.median(p95_list),
        "p99_median_ns": statistics.median(p99_list),
    }


def Main():
    parser = argparse.ArgumentParser(description="FlowSim parallel regression metrics")
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--threads", required=True, nargs="+", type=int)
    parser.add_argument("--repeats", required=True, type=int)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--baseline-thread", default=1, type=int)
    parser.add_argument("--consistency-threshold", default=0.05, type=float)
    args = parser.parse_args()

    thread_runs = {}
    for thread in args.threads:
        run_records = []
        for repeat in range(1, args.repeats + 1):
            run_dir = args.input_root / f"t{thread}" / f"r{repeat}"
            fct_values = ParseFctFile(run_dir / "fct.txt")
            run_records.append(
                {
                    "runtime_sec": ReadRuntime(run_dir / "runtime.txt"),
                    "p50_ns": Percentile(fct_values, 0.50),
                    "p95_ns": Percentile(fct_values, 0.95),
                    "p99_ns": Percentile(fct_values, 0.99),
                }
            )
        thread_runs[thread] = run_records

    baseline_summary = AggregateThreadMetrics(thread_runs[args.baseline_thread])
    baseline_runtime = baseline_summary["runtime_median_sec"]

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "threads",
                "runtime_median_sec",
                "runtime_stdev_sec",
                "speedup_vs_baseline",
                "p50_median_ns",
                "p95_median_ns",
                "p99_median_ns",
                "correctness_ok",
                "reproducibility_ok",
            ]
        )

        for thread in sorted(thread_runs.keys()):
            summary = AggregateThreadMetrics(thread_runs[thread])
            speedup = baseline_runtime / summary["runtime_median_sec"]
            p99_delta_ratio = abs(summary["p99_median_ns"] - baseline_summary["p99_median_ns"]) / max(
                baseline_summary["p99_median_ns"], 1.0
            )
            correctness_ok = p99_delta_ratio <= args.consistency_threshold

            run_p99 = [item["p99_ns"] for item in thread_runs[thread]]
            reproducibility_ratio = (statistics.pstdev(run_p99) / max(statistics.mean(run_p99), 1.0)) if len(run_p99) > 1 else 0.0
            reproducibility_ok = reproducibility_ratio <= args.consistency_threshold

            writer.writerow(
                [
                    thread,
                    f"{summary['runtime_median_sec']:.6f}",
                    f"{summary['runtime_stdev_sec']:.6f}",
                    f"{speedup:.4f}",
                    f"{summary['p50_median_ns']:.2f}",
                    f"{summary['p95_median_ns']:.2f}",
                    f"{summary['p99_median_ns']:.2f}",
                    int(correctness_ok),
                    int(reproducibility_ok),
                ]
            )


if __name__ == "__main__":
    Main()
