#!/usr/bin/env python3
"""Plot FlowSim fault-tolerance JCT curves with matplotlib.

This version is intended for the local Topo plotting environment and exports
PNG/SVG/PDF figures in a dark style matching the provided reference chart.
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
DEFAULT_RESULTS = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "flowsim_256_alltoall_p01_p15_s10_chain"
)
DEFAULT_OUTPUT = DEFAULT_RESULTS / "plots"

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


def load_plot_frame(results_dir: Path) -> pd.DataFrame:
    baseline = pd.read_csv(results_dir / "baseline_jct.csv")
    summary = pd.read_csv(results_dir / "random_link_failure_summary.csv")

    base_rows = baseline.rename(
        columns={"normal_jct": "mean", "normal_jct_std": "std"}
    )[["topology", "mean"]].copy()
    base_rows["rate_pct"] = 0.0
    base_rows["std"] = 0.0

    fault_rows = summary.rename(
        columns={
            "link_failure_probability": "rate_pct",
            "failed_jct_mean": "mean",
            "failed_jct_std": "std",
        }
    )[["topology", "rate_pct", "mean", "std"]].copy()
    fault_rows["rate_pct"] = fault_rows["rate_pct"] * 100.0

    df = pd.concat([base_rows, fault_rows], ignore_index=True)
    df = df[df["topology"].isin(ORDER)].copy()
    df["topology"] = pd.Categorical(df["topology"], categories=ORDER, ordered=True)
    return df.sort_values(["topology", "rate_pct"])


def style_axis(ax, bg: str, fg: str, axis: str) -> None:
    ax.set_facecolor(bg)
    for side in ["left", "right", "top", "bottom"]:
        ax.spines[side].set_color(axis)
        ax.spines[side].set_linewidth(1.2)
    ax.tick_params(colors=fg, labelsize=23, width=1.2, length=5)
    ax.grid(False)


def draw_chart(
    df: pd.DataFrame,
    *,
    output_dir: Path,
    prefix: str,
    scale: float,
    y_label: str,
    y_max: float | None,
) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"

    fig, ax = plt.subplots(figsize=(14.13, 7.52), dpi=100, facecolor=bg)
    style_axis(ax, bg, fg, axis)

    for topology in ORDER:
        part = df[df["topology"] == topology].sort_values("rate_pct")
        if part.empty:
            continue
        x = part["rate_pct"].to_numpy(dtype=float)
        y = part["mean"].to_numpy(dtype=float) / scale
        std = part["std"].to_numpy(dtype=float) / scale
        color = COLORS[topology]
        ax.fill_between(x, np.maximum(0, y - std), y + std, color=color, alpha=0.14, linewidth=0)
        ax.plot(
            x,
            y,
            color=color,
            marker=MARKERS[topology],
            markersize=9.2,
            markeredgewidth=1.4,
            linewidth=2.3,
            label=LABELS[topology],
        )

    ax.set_xlim(0, 15)
    ax.set_xticks(np.arange(0, 16, 1))
    ax.set_xlabel("Link failure percentage (%)", fontsize=27, color=fg)
    ax.set_ylabel(y_label, fontsize=27, color=fg)

    if y_max is None:
        plotted_max = 0.0
        for topology in ORDER:
            part = df[df["topology"] == topology]
            if not part.empty:
                plotted_max = max(
                    plotted_max,
                    float(((part["mean"] + part["std"]) / scale).max()),
                )
        y_max = np.ceil(plotted_max / 50.0) * 50.0
        y_step = 50.0
    else:
        y_step = 0.25
    ax.set_ylim(0, y_max)
    ax.set_yticks(np.arange(0, y_max + y_step / 2, y_step))
    if y_step < 1:
        ax.set_yticklabels([f"{v:.2f}" for v in ax.get_yticks()], color=fg)

    legend = ax.legend(
        title="Topology",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=23,
        title_fontsize=24,
        handlelength=2.0,
        labelspacing=0.42,
    )
    legend.get_title().set_color(fg)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts():
        text.set_color(fg)

    fig.subplots_adjust(left=0.145, right=0.675, bottom=0.145, top=0.96)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(output_dir / f"{prefix}.{ext}", facecolor=bg, edgecolor=bg)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot fault tolerance with matplotlib")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prefix", default="flowsim_fault_tolerance")
    parser.add_argument("--scaled-scale", type=float, default=200.0)
    parser.add_argument("--scaled-y-max", type=float, default=2.0)
    parser.add_argument("--raw-y-label", default="FlowSim JCT")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    df = load_plot_frame(args.results_dir)
    draw_chart(
        df,
        output_dir=args.output_dir,
        prefix=f"{args.prefix}_jct_scaled_mpl",
        scale=args.scaled_scale,
        y_label="JCT (s)",
        y_max=args.scaled_y_max,
    )
    draw_chart(
        df,
        output_dir=args.output_dir,
        prefix=f"{args.prefix}_jct_raw_mpl",
        scale=1.0,
        y_label=args.raw_y_label,
        y_max=None,
    )
    print(args.output_dir / f"{args.prefix}_jct_scaled_mpl.png")
    print(args.output_dir / f"{args.prefix}_jct_raw_mpl.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
