#!/usr/bin/env python3
"""Plot original FlowSim, policy FlowSim, and NS3 fault-tolerance curves."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FT_DIR = ROOT / "experiments" / "fault_tolerance"
DEFAULT_ORIGINAL = FT_DIR / "flowsim_256_alltoall_p01_p15_s10_chain"
DEFAULT_POLICY = FT_DIR / "flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full"
DEFAULT_NS3 = FT_DIR / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix"
DEFAULT_OUTPUT = FT_DIR / "flowsim_crossrail_w03_full_comparison" / "plots"

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


def load_result_dir(results_dir: Path, label: str) -> pd.DataFrame:
    baseline = pd.read_csv(results_dir / "baseline_jct.csv")
    summary = pd.read_csv(results_dir / "random_link_failure_summary.csv")

    base_lookup = baseline.set_index("topology")["normal_jct"].to_dict()
    base = baseline.rename(columns={"normal_jct": "jct_mean"})[
        ["topology", "jct_mean"]
    ].copy()
    base["rate_pct"] = 0.0
    base["jct_std"] = 0.0
    base["num_samples"] = 0
    base["num_success"] = 0
    base["normal_jct_mean"] = base["topology"].map(base_lookup)

    fault = summary.rename(
        columns={
            "link_failure_probability": "rate_pct",
            "failed_jct_mean": "jct_mean",
            "failed_jct_std": "jct_std",
        }
    )[
        [
            "topology",
            "rate_pct",
            "jct_mean",
            "jct_std",
            "normal_jct_mean",
            "num_samples",
            "num_success",
        ]
    ].copy()
    fault["rate_pct"] = fault["rate_pct"] * 100.0

    df = pd.concat([base, fault], ignore_index=True)
    df = df[df["topology"].isin(ORDER)].copy()
    df["series"] = label
    df["jct_factor"] = df["jct_mean"] / df["normal_jct_mean"]
    df["jct_factor_std"] = df["jct_std"] / df["normal_jct_mean"]
    return df


def complete_policy_keys(policy_df: pd.DataFrame, min_samples: int) -> set[tuple[str, float]]:
    complete = policy_df[
        (policy_df["rate_pct"] > 0.0)
        & (policy_df["num_samples"] >= min_samples)
        & (policy_df["num_success"] >= min_samples)
    ]
    return {
        (str(row["topology"]), round(float(row["rate_pct"]), 8))
        for _, row in complete.iterrows()
    }


def filter_to_policy_keys(
    df: pd.DataFrame, keys: set[tuple[str, float]], *, include_baseline: bool
) -> pd.DataFrame:
    topologies = {topology for topology, _ in keys}
    keep = []
    for _, row in df.iterrows():
        topology = str(row["topology"])
        rate_pct = round(float(row["rate_pct"]), 8)
        if include_baseline and rate_pct == 0.0 and topology in topologies:
            keep.append(True)
        else:
            keep.append((topology, rate_pct) in keys)
    return df[keep].copy()


def style_axis(ax, *, bg: str, fg: str, axis: str) -> None:
    ax.set_facecolor(bg)
    for side in ["left", "right", "top", "bottom"]:
        ax.spines[side].set_color(axis)
        ax.spines[side].set_linewidth(1.1)
    ax.tick_params(colors=fg, labelsize=15, width=1.1, length=5)
    ax.grid(False)


def tick_step_for_range(y_max: float) -> float:
    if y_max <= 3.0:
        return 0.5
    if y_max <= 10.0:
        return 1.0
    if y_max <= 50.0:
        return 10.0
    if y_max <= 250.0:
        return 50.0
    return 100.0


def draw_panel_chart(
    df: pd.DataFrame,
    *,
    output_dir: Path,
    prefix: str,
    series_order: list[str],
    metric: str,
    std_metric: str,
    y_label: str,
    title: str,
    y_min: float,
) -> None:
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"

    fig, axes = plt.subplots(
        1,
        len(series_order),
        figsize=(21.0, 7.4),
        dpi=120,
        sharex=True,
        sharey=True,
        facecolor=bg,
    )

    max_y = y_min
    for ax, series in zip(axes, series_order):
        style_axis(ax, bg=bg, fg=fg, axis=axis)
        ax.set_title(series, fontsize=22, color=fg, pad=12, fontweight="bold")
        series_df = df[df["series"] == series]
        for topology in ORDER:
            part = series_df[series_df["topology"] == topology].sort_values("rate_pct")
            if part.empty:
                continue
            x = part["rate_pct"].to_numpy(dtype=float)
            y = part[metric].to_numpy(dtype=float)
            std = part[std_metric].to_numpy(dtype=float)
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
                markersize=7.0,
                markeredgewidth=1.1,
                linewidth=1.9,
                label=LABELS[topology],
            )
            max_y = max(max_y, float(np.nanmax(y + std)))
        ax.set_xlim(0, 15)
        ax.set_xticks(np.arange(0, 16, 1))
        ax.set_xlabel("Link failure percentage (%)", fontsize=18, color=fg)
        if metric == "jct_factor":
            ax.axhline(1.0, color=axis, linewidth=1.0, alpha=0.45, linestyle="--")

    if metric == "jct_factor":
        y_max = max(y_min + 0.5, np.ceil(max_y * 2.0) / 2.0)
        y_step = 0.5
    else:
        y_step = tick_step_for_range(max_y)
        y_max = max(y_min + y_step, np.ceil(max_y / y_step) * y_step)
    axes[0].set_ylim(y_min, y_max)
    axes[0].set_yticks(np.arange(y_min, y_max + y_step / 2.0, y_step))
    axes[0].set_ylabel(y_label, fontsize=18, color=fg)

    handles, labels = axes[-1].get_legend_handles_labels()
    legend = fig.legend(
        handles,
        labels,
        title="Topology",
        loc="center left",
        bbox_to_anchor=(0.86, 0.52),
        frameon=False,
        fontsize=17,
        title_fontsize=18,
        handlelength=2.0,
        labelspacing=0.48,
    )
    legend.get_title().set_color(fg)
    legend.get_title().set_fontweight("bold")
    for text in legend.get_texts():
        text.set_color(fg)

    fig.text(0.055, 0.985, title, ha="left", va="top", fontsize=24, color=fg, fontweight="bold")
    fig.text(
        0.055,
        0.945,
        "256-GPU all-to-all workload; shaded band is one std. Policy panel includes only completed policy rates when requested.",
        ha="left",
        va="top",
        fontsize=13,
        color=fg,
        alpha=0.86,
    )

    fig.subplots_adjust(left=0.065, right=0.82, bottom=0.13, top=0.84, wspace=0.09)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(output_dir / f"{prefix}.{ext}", facecolor=bg, edgecolor=bg)
    plt.close(fig)


def write_joined_csv(df: pd.DataFrame, output_dir: Path, prefix: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{prefix}.csv"
    columns = [
        "series",
        "topology",
        "rate_pct",
        "jct_mean",
        "jct_std",
        "normal_jct_mean",
        "jct_factor",
        "jct_factor_std",
        "num_samples",
        "num_success",
    ]
    result = df[columns].copy()
    result["topology"] = pd.Categorical(result["topology"], categories=ORDER, ordered=True)
    result = result.sort_values(["series", "topology", "rate_pct"])
    result.to_csv(out, index=False)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot original FlowSim, one FlowSim policy, and NS3 fault sweeps"
    )
    parser.add_argument("--original-dir", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--policy-dir", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--ns3-dir", type=Path, default=DEFAULT_NS3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prefix", default="flowsim_policy_vs_ns3")
    parser.add_argument("--policy-series-label", default="w0.3 FlowSim")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--complete-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    original = load_result_dir(args.original_dir, "Original FlowSim")
    policy = load_result_dir(args.policy_dir, args.policy_series_label)
    ns3 = load_result_dir(args.ns3_dir, "NS3")
    series_order = ["Original FlowSim", args.policy_series_label, "NS3"]

    if args.complete_only:
        keys = complete_policy_keys(policy, args.min_samples)
        original = filter_to_policy_keys(original, keys, include_baseline=True)
        policy = filter_to_policy_keys(policy, keys, include_baseline=True)
        ns3 = filter_to_policy_keys(ns3, keys, include_baseline=True)

    df = pd.concat([original, policy, ns3], ignore_index=True)
    df["topology"] = pd.Categorical(df["topology"], categories=ORDER, ordered=True)
    df = df.sort_values(["series", "topology", "rate_pct"])

    csv_path = write_joined_csv(df, args.output_dir, f"{args.prefix}_data")
    draw_panel_chart(
        df,
        output_dir=args.output_dir,
        prefix=f"{args.prefix}_normalized_jct",
        series_order=series_order,
        metric="jct_factor",
        std_metric="jct_factor_std",
        y_label="Normalized JCT (fault / baseline)",
        title="Fault tolerance policy comparison: normalized JCT",
        y_min=0.5,
    )
    draw_panel_chart(
        df,
        output_dir=args.output_dir,
        prefix=f"{args.prefix}_failed_jct",
        series_order=series_order,
        metric="jct_mean",
        std_metric="jct_std",
        y_label="JCT",
        title="Fault tolerance policy comparison: failed JCT",
        y_min=0.0,
    )
    print(args.output_dir / f"{args.prefix}_normalized_jct.png")
    print(args.output_dir / f"{args.prefix}_failed_jct.png")
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
