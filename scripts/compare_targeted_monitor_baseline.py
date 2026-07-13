#!/usr/bin/env python3
"""Compare targeted fault monitor results with no-fault baseline monitors."""

from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FAULT = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "targeted_monitor_mismatch_retry"
    / "targeted_monitor_overview.csv"
)
DEFAULT_BASELINE = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "targeted_monitor_baseline"
    / "targeted_monitor_overview.csv"
)
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance"
TOPOLOGY_ORDER = ["Meta", "Zcube", "RO", "DeepSeek"]
COMPARE_COLUMNS = [
    "flowsim_jct",
    "ns3_jct",
    "ns3_fct_lines",
    "ns3_send_lines",
    "max_local_nvswitch_bw",
    "max_gpu_switch_bw",
    "max_switch_switch_bw",
    "max_local_nvswitch_queue",
    "max_gpu_switch_queue",
    "max_switch_switch_queue",
    "pfc_events",
    "send_same_server",
    "send_cross_server_same_rail",
    "send_cross_server_cross_rail",
]


def ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or float(denominator) == 0.0:
        return np.nan
    return float(numerator) / float(denominator)


def build_comparison(fault: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    fault = fault.set_index("topology")
    baseline = baseline.set_index("topology")
    rows = []
    extra_topologies = sorted((set(fault.index) & set(baseline.index)) - set(TOPOLOGY_ORDER))
    for topology in [*TOPOLOGY_ORDER, *extra_topologies]:
        if topology not in fault.index or topology not in baseline.index:
            continue
        row = {"topology": topology}
        for column in COMPARE_COLUMNS:
            fault_value = fault.loc[topology, column]
            baseline_value = baseline.loc[topology, column]
            row[f"{column}_fault"] = fault_value
            row[f"{column}_baseline"] = baseline_value
            row[f"{column}_ratio"] = ratio(fault_value, baseline_value)
        rows.append(row)
    return pd.DataFrame(rows)


def use_chart_theme() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "#FCFCFD",
            "savefig.facecolor": "#FCFCFD",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#D7DBE7",
            "axes.labelcolor": "#1F2430",
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": "#E6E8F0",
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial"],
            "xtick.color": "#6F768A",
            "ytick.color": "#6F768A",
            "text.color": "#1F2430",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def add_header(fig: plt.Figure, ax: plt.Axes, title: str, subtitle: str) -> None:
    title = textwrap.fill(title, width=84, break_long_words=False)
    subtitle = textwrap.fill(subtitle, width=118, break_long_words=False)
    fig.subplots_adjust(top=0.78)
    left = ax.get_position().x0
    fig.text(left, 0.985, title, ha="left", va="top", fontsize=13, fontweight="semibold")
    fig.text(left, 0.925, subtitle, ha="left", va="top", fontsize=9, color="#6F768A")


def plot_ratios(comparison: pd.DataFrame, output_dir: Path) -> None:
    if comparison.empty:
        return
    use_chart_theme()
    metrics = [
        ("ns3_jct_ratio", "JCT"),
        ("ns3_send_lines_ratio", "QP legs"),
        ("max_local_nvswitch_queue_ratio", "NVSwitch queue"),
        ("max_gpu_switch_queue_ratio", "GPU-switch queue"),
        ("max_switch_switch_queue_ratio", "Switch-switch queue"),
    ]
    x = np.arange(len(comparison))
    width = 0.15
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    offsets = np.linspace(-2 * width, 2 * width, len(metrics))
    colors = ["#5477C4", "#71B436", "#CC6F47", "#BD569B", "#7A828F"]
    for offset, (column, label), color in zip(offsets, metrics, colors):
        values = comparison[column].to_numpy(dtype=float)
        ax.bar(x + offset, values, width=width, label=label, color=color)
    ax.axhline(1.0, color="#464C55", linewidth=1.0, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels(comparison["topology"])
    ax.set_ylabel("Fault / baseline ratio")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#D7DBE7")
    ax.tick_params(axis="both", labelsize=8.5, length=0)
    add_header(
        fig,
        ax,
        "Fault monitor ratios expose topology-specific queue amplification",
        "Ratios compare the selected 15% failed sample with the no-fault baseline for the same topology.",
    )
    fig.savefig(output_dir / "targeted_monitor_fault_vs_baseline_ratios.png", dpi=220, bbox_inches="tight")
    fig.savefig(output_dir / "targeted_monitor_fault_vs_baseline_ratios.svg", bbox_inches="tight")
    plt.close(fig)


def run(args: argparse.Namespace) -> int:
    fault = pd.read_csv(args.fault_overview)
    baseline = pd.read_csv(args.baseline_overview)
    comparison = build_comparison(fault, baseline)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "targeted_monitor_fault_vs_baseline.csv"
    comparison.to_csv(out, index=False)
    plot_ratios(comparison, args.output_dir)
    print(out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare fault and baseline monitor summaries")
    parser.add_argument("--fault-overview", type=Path, default=DEFAULT_FAULT)
    parser.add_argument("--baseline-overview", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
