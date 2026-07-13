#!/usr/bin/env python3
"""Run 256-GPU FlowSim JCT sweeps over random link failure probability."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
FAULT_SCRIPT = ROOT / "scripts" / "fault_tolerance_experiments.py"
FLOWSIM_BIN = Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim")
DEFAULT_WORKLOAD = (
    ROOT
    / "my_workloads"
    / "H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt"
)

TOPOLOGIES: Sequence[Tuple[str, str]] = (
    ("Meta", "Meta_Topo_256g_8gps_400Gbps_A100"),
    ("HPN", "AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100"),
    ("DeepSeek", "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800"),
    ("Zcube", "Zcube_n16_k2_256g_8gps_200Gbps_H100"),
    ("RO", "RailOnly_256g_8gps_p16a0.5_400Gbps_H100"),
    ("ROFT", "ROFT_256g_8gps_p16a0.5_400Gbps_H100"),
)

BASELINE_RESULT_DIRS = {
    "Meta": ROOT / "experiments" / "flowsim_results" / "256" / "MetaMoE",
    "HPN": ROOT / "experiments" / "flowsim_results" / "256" / "HPNMoE",
    "DeepSeek": ROOT / "experiments" / "flowsim_results" / "256" / "DeepSeekMoE",
    "Zcube": ROOT / "experiments" / "flowsim_results" / "256" / "ZcubeMoE",
    "RO": ROOT / "experiments" / "flowsim_results" / "256" / "ROMoE",
    "ROFT": ROOT / "experiments" / "flowsim_results" / "256" / "ROFTMoE",
}


def load_fault_module():
    spec = importlib.util.spec_from_file_location("fault_tolerance_experiments", FAULT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {FAULT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fault = load_fault_module()


def probability_grid(max_percent: int) -> List[float]:
    return [i / 100.0 for i in range(max_percent + 1)]


def parse_topology_filter(names: str) -> List[str]:
    if not names:
        return [name for name, _ in TOPOLOGIES]
    wanted = [item.strip() for item in names.split(",") if item.strip()]
    known = {name for name, _ in TOPOLOGIES}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(f"unknown topology names: {', '.join(unknown)}")
    return wanted


def parse_seeds(seeds: str, num_seeds: int, random_seed: int) -> List[int]:
    if seeds:
        return [int(item.strip()) for item in seeds.split(",") if item.strip()]
    return [random_seed + i for i in range(num_seeds)]


def run_flowsim(
    flowsim_bin: Path,
    workload: Path,
    topology: Path,
    output_dir: Path,
    threads: int,
    env: Dict[str, str],
    resume: bool,
) -> Optional[float]:
    end_to_end = output_dir / "EndToEnd.csv"
    if resume and end_to_end.exists() and end_to_end.stat().st_size > 0:
        return fault.read_total_time(end_to_end)

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(flowsim_bin),
        "-t",
        str(threads),
        "-w",
        str(workload),
        "-n",
        str(topology),
        "-o",
        str(output_dir) + "/",
    ]
    with (output_dir / "run.log").open("w") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False, env=env)
    return fault.read_total_time(end_to_end)


def scale_rate(rate: str, probability: float) -> str:
    if not rate.endswith("Gbps"):
        raise ValueError(f"unsupported bandwidth unit: {rate}")
    gbps = float(rate[:-4])
    return f"{gbps * (1.0 - probability):.6g}Gbps"


def write_error_probability_topology(topology, probability: float, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    impacted = 0
    with out_path.open("w") as f:
        f.write(
            f"{topology.total_nodes} {topology.gpus_per_server} "
            f"{topology.nvswitch_count} {topology.switch_count} "
            f"{topology.link_count} {topology.gpu_type}\n"
        )
        f.write(" ".join(str(x) for x in topology.switch_ids))
        f.write("\n")
        for link in topology.links:
            if topology.is_inter_server_link(link):
                impacted += 1
                f.write(
                    f"{link.src} {link.dst} {scale_rate(link.bandwidth, probability)} "
                    f"{link.latency} {probability:.6g}\n"
                )
            else:
                f.write(link.raw)
                f.write("\n")
    return impacted


def write_raw(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "topology",
        "error_probability",
        "error_probability_percent",
        "seed",
        "jct_raw",
        "jct_seconds",
        "impacted_links",
        "impacted_link_ratio",
        "connectivity_ratio",
        "generated_topology",
        "run_dir",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    groups: Dict[Tuple[str, float], List[Dict[str, object]]] = {}
    for row in rows:
        groups.setdefault((str(row["topology"]), float(row["error_probability"])), []).append(row)

    out_rows: List[Dict[str, object]] = []
    for (topology, probability), group_rows in sorted(groups.items()):
        jcts = [float(row["jct_seconds"]) for row in group_rows if row["jct_seconds"] != "missing"]
        impacted = [float(row["impacted_links"]) for row in group_rows]
        connectivity = [
            float(row["connectivity_ratio"])
            for row in group_rows
            if row["connectivity_ratio"] != "missing"
        ]
        out_rows.append(
            {
                "topology": topology,
                "error_probability": probability,
                "error_probability_percent": probability * 100.0,
                "num_seeds": len(group_rows),
                "jct_seconds_mean": mean(jcts) if jcts else "missing",
                "jct_seconds_std": pstdev(jcts) if len(jcts) > 1 else (0.0 if jcts else "missing"),
                "impacted_links_mean": mean(impacted) if impacted else "missing",
                "connectivity_ratio_mean": mean(connectivity) if connectivity else "missing",
            }
        )

    fields = [
        "topology",
        "error_probability",
        "error_probability_percent",
        "num_seeds",
        "jct_seconds_mean",
        "jct_seconds_std",
        "impacted_links_mean",
        "connectivity_ratio_mean",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)


def plot_summary(summary_csv: Path, output_png: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows: List[Dict[str, str]] = []
    with summary_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))

    by_topology: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        if row["jct_seconds_mean"] == "missing":
            continue
        by_topology.setdefault(row["topology"], []).append(row)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    for topology, topo_rows in by_topology.items():
        topo_rows.sort(key=lambda row: float(row["error_probability_percent"]))
        x = [float(row["error_probability_percent"]) for row in topo_rows]
        y = [float(row["jct_seconds_mean"]) for row in topo_rows]
        yerr = [float(row["jct_seconds_std"]) for row in topo_rows]
        ax.plot(x, y, marker="o", linewidth=1.8, markersize=4, label=topology)
        if any(value > 0 for value in yerr):
            lower = [max(0.0, value - err) for value, err in zip(y, yerr)]
            upper = [value + err for value, err in zip(y, yerr)]
            ax.fill_between(x, lower, upper, alpha=0.12)

    ax.set_xlabel("Error probability (%)")
    ax.set_ylabel("JCT (s)")
    ax.legend(title="Topology", frameon=False, ncols=2)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220)
    plt.close(fig)


def run(args: argparse.Namespace) -> None:
    if not args.workload.exists():
        raise SystemExit(f"workload not found: {args.workload}")
    if not args.flowsim_bin.exists() or not os.access(args.flowsim_bin, os.X_OK):
        raise SystemExit(f"FlowSim binary not executable: {args.flowsim_bin}")

    use_existing_baseline = args.workload.resolve() == DEFAULT_WORKLOAD.resolve()
    selected = set(parse_topology_filter(args.topologies))
    seeds = parse_seeds(args.seeds, args.num_seeds, args.random_seed)
    probabilities = probability_grid(args.max_error_percent)
    out_root = args.output_dir
    generated_root = out_root / "generated_topologies"
    rows: List[Dict[str, object]] = []
    raw_csv = out_root / "jct_by_error_probability_raw.csv"
    summary_csv = out_root / "jct_by_error_probability_summary.csv"

    env = os.environ.copy()
    env["FLOWSIM_WRITE_FCT"] = "0"
    env.setdefault("FLOWSIM_PROGRESS", "0")

    for topology_name, topology_file in TOPOLOGIES:
        if topology_name not in selected:
            continue
        topology_path = ROOT / "mytopo" / topology_file
        topology = fault.parse_topology(topology_path)
        baseline_lengths = fault.shortest_path_lengths(topology, set())

        for probability in probabilities:
            for seed in seeds:
                if probability == 0.0:
                    failed_keys = set()
                    impacted_links = 0
                    impacted_link_ratio = 0.0
                    failed_topology = topology_path
                else:
                    failed_topology = (
                        generated_root
                        / topology_name
                        / f"p{int(round(probability * 100)):02d}_seed{seed}.topo"
                    )
                    if args.error_model == "bandwidth_scale":
                        failed_keys = set()
                        impacted_links = write_error_probability_topology(
                            topology, probability, failed_topology
                        )
                        eligible = fault.eligible_inter_server_links(topology)
                        impacted_link_ratio = impacted_links / len(eligible) if eligible else 0.0
                    else:
                        failed_keys = fault.sample_failed_links(topology, probability, seed)
                        fault.write_topology(topology, failed_keys, failed_topology)
                        impacted_links = len(failed_keys)
                        eligible = fault.eligible_inter_server_links(topology)
                        impacted_link_ratio = impacted_links / len(eligible) if eligible else 0.0

                run_dir = (
                    out_root
                    / "runs"
                    / topology_name
                    / f"p{int(round(probability * 100)):02d}"
                    / f"seed{seed}"
                )
                print(
                    f"[FlowSim] topology={topology_name} "
                    f"error_probability={probability:.2f} seed={seed}"
                )
                if probability == 0.0 and use_existing_baseline:
                    baseline_dir = BASELINE_RESULT_DIRS[topology_name]
                    total_time = fault.read_total_time(baseline_dir / "EndToEnd.csv")
                    run_dir_for_row = baseline_dir
                else:
                    total_time = run_flowsim(
                        args.flowsim_bin,
                        args.workload,
                        failed_topology,
                        run_dir,
                        args.threads,
                        env,
                        args.resume,
                    )
                    run_dir_for_row = run_dir
                metrics = fault.topology_metrics(
                    topology, failed_keys, baseline_lengths, args.workload_name
                )
                rows.append(
                    {
                        "topology": topology_name,
                        "error_probability": probability,
                        "error_probability_percent": probability * 100.0,
                        "seed": seed,
                        "jct_raw": total_time if total_time is not None else "missing",
                        "jct_seconds": total_time / 1_000_000.0
                        if total_time is not None
                        else "missing",
                        "impacted_links": impacted_links,
                        "impacted_link_ratio": impacted_link_ratio,
                        "connectivity_ratio": metrics["connectivity_ratio"],
                        "generated_topology": str(failed_topology),
                        "run_dir": str(run_dir_for_row),
                    }
                )
                write_raw(raw_csv, rows)
                write_summary(summary_csv, rows)

    plot_summary(summary_csv, out_root / "jct_by_error_probability.png")
    print(f"wrote {raw_csv}")
    print(f"wrote {summary_csv}")
    print(f"wrote {out_root / 'jct_by_error_probability.png'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "fault_tolerance_256_flowsim")
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--workload-name", default="Mixtral-8x7B-MoE-256")
    parser.add_argument("--flowsim-bin", type=Path, default=FLOWSIM_BIN)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--max-error-percent", type=int, default=15)
    parser.add_argument("--num-seeds", type=int, default=1)
    parser.add_argument("--random-seed", type=int, default=1)
    parser.add_argument("--seeds", default="")
    parser.add_argument("--topologies", default="", help="comma-separated subset")
    parser.add_argument(
        "--error-model",
        choices=["bandwidth_scale", "link_failure"],
        default="bandwidth_scale",
    )
    parser.add_argument("--resume", action="store_true", default=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
