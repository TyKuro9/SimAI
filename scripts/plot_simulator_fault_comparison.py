#!/usr/bin/env python3
"""Compare FlowSim and NS3 fault-tolerance sweeps.

The main output normalizes each topology by its no-fault baseline, so the two
simulators can be compared by relative JCT degradation instead of raw time
units.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLOWSIM = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "flowsim_256_alltoall_p01_p15_s10_chain"
)
DEFAULT_NS3 = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "compare_flowsim_ns3_pfc_resume_fix"
)

ORDER = ["ROFT", "Zcube", "DeepSeek", "HPN", "Meta", "RO"]
LABELS = {
    "ROFT": "ROFT",
    "Zcube": "ZCube",
    "DeepSeek": "DeepSeek",
    "HPN": "HPN",
    "Meta": "Meta",
    "RO": "Rail-only",
}
COLORS = {
    "ROFT": "#73d2ff",
    "Zcube": "#57ee5a",
    "DeepSeek": "#ff9d8e",
    "HPN": "#f78be8",
    "Meta": "#8b94a4",
    "RO": "#d7d800",
}
MARKERS = {
    "ROFT": "x",
    "Zcube": "<",
    "DeepSeek": ">",
    "HPN": "s",
    "Meta": "p",
    "RO": "o",
}


def load_frame(results_dir: Path, simulator: str) -> pd.DataFrame:
    baseline = pd.read_csv(results_dir / "baseline_jct.csv")
    summary = pd.read_csv(results_dir / "random_link_failure_summary.csv")

    base = baseline.rename(columns={"normal_jct": "jct_mean"})[
        ["topology", "jct_mean"]
    ].copy()
    base["rate_pct"] = 0.0
    base["jct_std"] = 0.0

    faults = summary.rename(
        columns={
            "link_failure_probability": "rate_pct",
            "failed_jct_mean": "jct_mean",
            "failed_jct_std": "jct_std",
        }
    )[["topology", "rate_pct", "jct_mean", "jct_std", "normal_jct_mean"]].copy()
    faults["rate_pct"] = faults["rate_pct"] * 100.0

    base_lookup = baseline.set_index("topology")["normal_jct"].to_dict()
    base["normal_jct_mean"] = base["topology"].map(base_lookup)

    df = pd.concat([base, faults], ignore_index=True)
    df = df[df["topology"].isin(ORDER)].copy()
    df["simulator"] = simulator
    df["jct_factor"] = df["jct_mean"] / df["normal_jct_mean"]
    df["jct_factor_std"] = df["jct_std"] / df["normal_jct_mean"]
    df["topology"] = pd.Categorical(df["topology"], categories=ORDER, ordered=True)
    return df.sort_values(["topology", "rate_pct"])


def style_axis(ax, *, bg: str, fg: str, axis: str) -> None:
    ax.set_facecolor(bg)
    for side in ["left", "right", "top", "bottom"]:
        ax.spines[side].set_color(axis)
        ax.spines[side].set_linewidth(1.1)
    ax.tick_params(colors=fg, labelsize=17, width=1.1, length=5)
    ax.grid(False)


def draw_normalized(df: pd.DataFrame, output_dir: Path, prefix: str) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"

    simulators = ["FlowSim", "NS3"]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(18.0, 7.4),
        dpi=120,
        sharex=True,
        sharey=True,
        facecolor=bg,
    )

    max_y = 1.0
    for ax, simulator in zip(axes, simulators):
        style_axis(ax, bg=bg, fg=fg, axis=axis)
        ax.set_title(simulator, fontsize=24, color=fg, pad=12, fontweight="bold")
        sim_df = df[df["simulator"] == simulator]
        for topology in ORDER:
            part = sim_df[sim_df["topology"] == topology].sort_values("rate_pct")
            if part.empty:
                continue
            x = part["rate_pct"].to_numpy(dtype=float)
            y = part["jct_factor"].to_numpy(dtype=float)
            std = part["jct_factor_std"].to_numpy(dtype=float)
            color = COLORS[topology]
            ax.fill_between(
                x,
                np.maximum(0, y - std),
                y + std,
                color=color,
                alpha=0.12,
                linewidth=0,
            )
            ax.plot(
                x,
                y,
                color=color,
                marker=MARKERS[topology],
                markersize=7.6,
                markeredgewidth=1.2,
                linewidth=2.0,
                label=LABELS[topology],
            )
            max_y = max(max_y, float(np.nanmax(y + std)))
        ax.axhline(1.0, color=axis, linewidth=1.0, alpha=0.45, linestyle="--")
        ax.set_xlim(0, 15)
        ax.set_xticks(np.arange(0, 16, 1))
        ax.set_xlabel("Link failure percentage (%)", fontsize=20, color=fg)

    y_max = max(2.0, np.ceil(max_y * 2.0) / 2.0)
    axes[0].set_ylim(0.5, y_max)
    axes[0].set_yticks(np.arange(0.5, y_max + 0.25, 0.5))
    axes[0].set_ylabel("Normalized JCT (fault / baseline)", fontsize=20, color=fg)

    handles, labels = axes[1].get_legend_handles_labels()
    legend = fig.legend(
        handles,
        labels,
        title="Topology",
        loc="center left",
        bbox_to_anchor=(0.815, 0.52),
        frameon=False,
        fontsize=18,
        title_fontsize=19,
        handlelength=2.0,
        labelspacing=0.48,
    )
    legend.get_title().set_color(fg)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts():
        text.set_color(fg)

    fig.text(
        0.085,
        0.985,
        "Fault tolerance comparison: FlowSim vs NS3",
        ha="left",
        va="top",
        fontsize=24,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.085,
        0.945,
        "256-GPU all-to-all workload; each point is the mean of 10 random link-failure samples, shaded band is one std.",
        ha="left",
        va="top",
        fontsize=13,
        color=fg,
        alpha=0.86,
    )

    fig.subplots_adjust(left=0.08, right=0.77, bottom=0.13, top=0.84, wspace=0.11)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(output_dir / f"{prefix}.{ext}", facecolor=bg, edgecolor=bg)
    plt.close(fig)


def draw_raw_jct(df: pd.DataFrame, output_dir: Path, prefix: str) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"

    simulators = ["FlowSim", "NS3"]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(18.0, 7.4),
        dpi=120,
        sharex=True,
        sharey=True,
        facecolor=bg,
    )

    max_y = 0.0
    for ax, simulator in zip(axes, simulators):
        style_axis(ax, bg=bg, fg=fg, axis=axis)
        ax.set_title(simulator, fontsize=24, color=fg, pad=12, fontweight="bold")
        sim_df = df[df["simulator"] == simulator]
        for topology in ORDER:
            part = sim_df[sim_df["topology"] == topology].sort_values("rate_pct")
            if part.empty:
                continue
            x = part["rate_pct"].to_numpy(dtype=float)
            y = part["jct_mean"].to_numpy(dtype=float)
            std = part["jct_std"].to_numpy(dtype=float)
            color = COLORS[topology]
            ax.fill_between(
                x,
                np.maximum(0, y - std),
                y + std,
                color=color,
                alpha=0.12,
                linewidth=0,
            )
            ax.plot(
                x,
                y,
                color=color,
                marker=MARKERS[topology],
                markersize=7.6,
                markeredgewidth=1.2,
                linewidth=2.0,
                label=LABELS[topology],
            )
            max_y = max(max_y, float(np.nanmax(y + std)))
        ax.set_xlim(0, 15)
        ax.set_xticks(np.arange(0, 16, 1))
        ax.set_xlabel("Link failure percentage (%)", fontsize=20, color=fg)

    y_max = max(50.0, np.ceil(max_y / 50.0) * 50.0)
    axes[0].set_ylim(0, y_max)
    axes[0].set_yticks(np.arange(0, y_max + 1e-9, 50.0))
    axes[0].set_ylabel("JCT (us)", fontsize=20, color=fg)

    handles, labels = axes[1].get_legend_handles_labels()
    legend = fig.legend(
        handles,
        labels,
        title="Topology",
        loc="center left",
        bbox_to_anchor=(0.815, 0.52),
        frameon=False,
        fontsize=18,
        title_fontsize=19,
        handlelength=2.0,
        labelspacing=0.48,
    )
    legend.get_title().set_color(fg)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts():
        text.set_color(fg)

    fig.text(
        0.085,
        0.985,
        "Fault tolerance raw JCT: FlowSim vs NS3",
        ha="left",
        va="top",
        fontsize=24,
        color=fg,
        fontweight="bold",
    )
    fig.text(
        0.085,
        0.945,
        "256-GPU all-to-all workload; each point is the mean of 10 random link-failure samples, shaded band is one std.",
        ha="left",
        va="top",
        fontsize=13,
        color=fg,
        alpha=0.86,
    )

    fig.subplots_adjust(left=0.08, right=0.77, bottom=0.13, top=0.84, wspace=0.11)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(output_dir / f"{prefix}.{ext}", facecolor=bg, edgecolor=bg)
    plt.close(fig)


def write_ratio_csv(df: pd.DataFrame, output_dir: Path) -> Path:
    flow = df[df["simulator"] == "FlowSim"][
        ["topology", "rate_pct", "jct_mean", "jct_factor"]
    ].rename(
        columns={
            "jct_mean": "flowsim_jct_mean",
            "jct_factor": "flowsim_jct_factor",
        }
    )
    ns3 = df[df["simulator"] == "NS3"][
        ["topology", "rate_pct", "jct_mean", "jct_factor"]
    ].rename(
        columns={
            "jct_mean": "ns3_jct_mean",
            "jct_factor": "ns3_jct_factor",
        }
    )
    merged = flow.merge(ns3, on=["topology", "rate_pct"], how="inner")
    merged["ns3_over_flowsim_jct"] = (
        merged["ns3_jct_mean"] / merged["flowsim_jct_mean"]
    )
    merged["ns3_over_flowsim_factor"] = (
        merged["ns3_jct_factor"] / merged["flowsim_jct_factor"]
    )
    merged["factor_delta_ns3_minus_flowsim"] = (
        merged["ns3_jct_factor"] - merged["flowsim_jct_factor"]
    )
    merged["topology"] = pd.Categorical(
        merged["topology"], categories=ORDER, ordered=True
    )
    merged = merged.sort_values(["topology", "rate_pct"])
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "flowsim_ns3_fault_comparison.csv"
    merged.to_csv(out, index=False)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare FlowSim and NS3 fault sweeps")
    parser.add_argument("--flowsim-dir", type=Path, default=DEFAULT_FLOWSIM)
    parser.add_argument("--ns3-dir", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prefix", default="flowsim_vs_ns3_normalized_jct")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    frames = [
        load_frame(args.flowsim_dir, "FlowSim"),
        load_frame(args.ns3_dir, "NS3"),
    ]
    df = pd.concat(frames, ignore_index=True)
    draw_normalized(df, args.output_dir, args.prefix)
    raw_prefix = args.prefix.replace("normalized_jct", "raw_jct")
    if raw_prefix == args.prefix:
        raw_prefix = f"{args.prefix}_raw_jct"
    draw_raw_jct(df, args.output_dir, raw_prefix)
    ratio_csv = write_ratio_csv(df, args.output_dir)
    print(args.output_dir / f"{args.prefix}.png")
    print(args.output_dir / f"{raw_prefix}.png")
    print(ratio_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
