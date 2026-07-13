#!/usr/bin/env python3
"""Analyze targeted FlowSim/NS3 FCT outputs.

Chart contract:
- Question: how do representative mismatch samples differ at the FCT-record level?
- Takeaway: NS3 records physical PXN legs, while FlowSim records original flows; line
  inflation and tail FCT should be interpreted at those different grains.
- Surface: static PNG/SVG files for the local markdown diagnosis.
"""

from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "experiments" / "fault_tolerance" / "targeted_fct_mismatch"
DEFAULT_OUTPUT = DEFAULT_INPUT

TOPOLOGY_ORDER = ["Meta", "Zcube", "RO"]
SIMULATOR_ORDER = ["flowsim", "ns3"]
CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]
CATEGORY_LABELS = {
    "same_server": "Same server",
    "cross_server_same_rail": "Cross-server\nsame rail",
    "cross_server_cross_rail": "Cross-server\ncross rail",
}
SIMULATOR_LABELS = {
    "flowsim": "FlowSim",
    "ns3": "NS3",
}

FONT_FAMILY = ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial", "sans-serif"]
MONO_FONT_FAMILY = ["DejaVu Sans Mono", "Menlo", "Consolas", "monospace"]

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}
NEUTRAL = {
    "light": "#E2E5EA",
    "base": "#C5CAD3",
    "mid": "#7A828F",
    "dark": "#464C55",
}
COLORS = {
    "blue": {"light": "#CEDFFE", "base": "#A3BEFA", "mid": "#5477C4", "dark": "#2E4780"},
    "gold": {"light": "#FFEA8F", "base": "#FFE15B", "mid": "#B8A037", "dark": "#736422"},
    "orange": {"light": "#FFBDA1", "base": "#F0986E", "mid": "#CC6F47", "dark": "#804126"},
    "olive": {"light": "#BEEB96", "base": "#A3D576", "mid": "#71B436", "dark": "#386411"},
    "pink": {"light": "#F5BACC", "base": "#F390CA", "mid": "#BD569B", "dark": "#8A3A6F"},
}
CATEGORY_COLORS = {
    "same_server": COLORS["blue"],
    "cross_server_same_rail": COLORS["gold"],
    "cross_server_cross_rail": COLORS["pink"],
}
SIM_COLORS = {
    "flowsim": COLORS["orange"],
    "ns3": COLORS["blue"],
}


def use_chart_theme() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": TOKENS["surface"],
            "savefig.facecolor": TOKENS["surface"],
            "savefig.edgecolor": "none",
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": FONT_FAMILY,
            "font.monospace": MONO_FONT_FAMILY,
            "xtick.color": TOKENS["muted"],
            "ytick.color": TOKENS["muted"],
            "text.color": TOKENS["ink"],
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def add_chart_header(
    fig: plt.Figure,
    ax: plt.Axes,
    title: str,
    subtitle: str,
    *,
    title_width: int = 78,
    subtitle_width: int = 118,
) -> None:
    title = textwrap.fill(str(title).strip(), width=title_width, break_long_words=False)
    subtitle = textwrap.fill(
        str(subtitle).strip(), width=subtitle_width, break_long_words=False
    )
    if not title or not subtitle:
        raise ValueError("title and subtitle are required")
    title_lines = title.count("\n") + 1
    subtitle_lines = subtitle.count("\n") + 1
    fig.subplots_adjust(
        top=max(0.62, 0.86 - 0.045 * (title_lines - 1) - 0.032 * (subtitle_lines - 1))
    )
    left = ax.get_position().x0
    fig.text(
        left,
        0.985,
        title,
        ha="left",
        va="top",
        fontsize=13,
        fontweight="semibold",
        color=TOKENS["ink"],
        linespacing=1.08,
    )
    fig.text(
        left,
        0.93 - 0.045 * (title_lines - 1),
        subtitle,
        ha="left",
        va="top",
        fontsize=9,
        color=TOKENS["muted"],
        linespacing=1.18,
    )


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(TOKENS["axis"])
    ax.spines["bottom"].set_color(TOKENS["axis"])
    ax.tick_params(axis="both", labelsize=8.5, length=0)


def export_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def parse_node_id(token: str) -> int:
    text = token.strip()
    if text.startswith("0b"):
        body = text[2:]
        node_hex = body[:-2] if len(body) > 2 else body
        return int(node_hex, 16)
    return int(text, 0)


def pair_category(src: int, dst: int, gpus_per_server: int) -> str:
    if src // gpus_per_server == dst // gpus_per_server:
        return "same_server"
    if src % gpus_per_server == dst % gpus_per_server:
        return "cross_server_same_rail"
    return "cross_server_cross_rail"


def parse_fct_file(path: Path, *, gpus_per_server: int) -> pd.DataFrame:
    rows = []
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) < 8:
                raise ValueError(f"invalid FCT row in {path}:{line_no}: {line!r}")
            src = parse_node_id(parts[0])
            dst = parse_node_id(parts[1])
            rows.append(
                {
                    "src": src,
                    "dst": dst,
                    "message_size": int(float(parts[4])),
                    "fct": float(parts[6]),
                    "standalone_fct": float(parts[7]),
                    "category": pair_category(src, dst, gpus_per_server),
                }
            )
    return pd.DataFrame(rows)


def load_targeted_fct(input_dir: Path, *, gpus_per_server: int) -> pd.DataFrame:
    summary_path = input_dir / "targeted_fct_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    targets = pd.read_csv(summary_path)
    frames = []
    for _, target in targets.iterrows():
        for simulator in SIMULATOR_ORDER:
            run_dir = Path(str(target[f"{simulator}_run_dir"]))
            fct_path = run_dir / "fct.txt"
            if not fct_path.exists():
                raise FileNotFoundError(fct_path)
            frame = parse_fct_file(fct_path, gpus_per_server=gpus_per_server)
            frame.insert(0, "simulator", simulator)
            frame.insert(0, "seed", int(target["seed"]))
            frame.insert(0, "rate", float(target["rate"]))
            frame.insert(0, "topology", str(target["topology"]))
            frames.append(frame)
    if not frames:
        raise ValueError(f"no FCT data found in {input_dir}")
    return pd.concat(frames, ignore_index=True)


def summarize_values(values: pd.Series) -> dict[str, float]:
    data = values.to_numpy(dtype=float)
    return {
        "lines": int(len(data)),
        "mean_fct": float(np.mean(data)) if len(data) else np.nan,
        "p50_fct": float(np.percentile(data, 50)) if len(data) else np.nan,
        "p95_fct": float(np.percentile(data, 95)) if len(data) else np.nan,
        "p99_fct": float(np.percentile(data, 99)) if len(data) else np.nan,
        "max_fct": float(np.max(data)) if len(data) else np.nan,
    }


def build_summaries(fct: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overall_rows = []
    for keys, part in fct.groupby(["topology", "rate", "seed", "simulator"], sort=False):
        row = dict(zip(["topology", "rate", "seed", "simulator"], keys))
        row.update(summarize_values(part["fct"]))
        row["mean_standalone"] = float(part["standalone_fct"].mean())
        row["p95_standalone"] = float(np.percentile(part["standalone_fct"], 95))
        overall_rows.append(row)
    overall = pd.DataFrame(overall_rows)

    category_rows = []
    for keys, part in fct.groupby(
        ["topology", "rate", "seed", "simulator", "category"], sort=False
    ):
        row = dict(zip(["topology", "rate", "seed", "simulator", "category"], keys))
        row.update(summarize_values(part["fct"]))
        row["mean_standalone"] = float(part["standalone_fct"].mean())
        row["p95_standalone"] = float(np.percentile(part["standalone_fct"], 95))
        category_rows.append(row)
    category = pd.DataFrame(category_rows)
    totals = overall[["topology", "rate", "seed", "simulator", "lines"]].rename(
        columns={"lines": "total_lines"}
    )
    category = category.merge(totals, on=["topology", "rate", "seed", "simulator"])
    category["share"] = category["lines"] / category["total_lines"]
    category = category.drop(columns=["total_lines"])

    line_inflation_rows = []
    for keys, part in overall.groupby(["topology", "rate", "seed"], sort=False):
        row = dict(zip(["topology", "rate", "seed"], keys))
        lines = part.set_index("simulator")["lines"]
        flow_lines = float(lines.get("flowsim", np.nan))
        ns3_lines = float(lines.get("ns3", np.nan))
        row["flowsim_lines"] = flow_lines
        row["ns3_lines"] = ns3_lines
        row["extra_ns3_lines"] = ns3_lines - flow_lines
        row["ns3_line_ratio"] = ns3_lines / flow_lines if flow_lines else np.nan
        line_inflation_rows.append(row)
    line_inflation = pd.DataFrame(line_inflation_rows)

    return overall, category, line_inflation


def ordered_overall_rows(overall: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for topology in TOPOLOGY_ORDER:
        for simulator in SIMULATOR_ORDER:
            part = overall[
                (overall["topology"] == topology) & (overall["simulator"] == simulator)
            ]
            if not part.empty:
                rows.append(part.iloc[0].to_dict())
    return rows


def plot_line_counts(category: pd.DataFrame, overall: pd.DataFrame, output_dir: Path) -> None:
    use_chart_theme()
    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    rows = ordered_overall_rows(overall)
    y = np.arange(len(rows))
    left = np.zeros(len(rows))
    for category_name in CATEGORY_ORDER:
        values = []
        for row in rows:
            part = category[
                (category["topology"] == row["topology"])
                & (category["simulator"] == row["simulator"])
                & (category["category"] == category_name)
            ]
            values.append(float(part["lines"].iloc[0]) / 1000.0 if not part.empty else 0.0)
        family = CATEGORY_COLORS[category_name]
        bars = ax.barh(
            y,
            values,
            left=left,
            color=family["base"],
            edgecolor=family["dark"],
            linewidth=1.0,
            label=CATEGORY_LABELS[category_name].replace("\n", " "),
        )
        for bar in bars:
            bar.set_linewidth(0.8)
        left += np.asarray(values)

    labels = [
        f"{row['topology']} {SIMULATOR_LABELS[str(row['simulator'])]}" for row in rows
    ]
    totals = [float(row["lines"]) / 1000.0 for row in rows]
    for y_pos, total in zip(y, totals):
        ax.text(
            total + 2.0,
            y_pos,
            f"{total:.1f}k",
            va="center",
            ha="left",
            fontsize=8.5,
            color=TOKENS["muted"],
            fontfamily=MONO_FONT_FAMILY[0],
        )

    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("FCT rows (thousands)")
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    ax.grid(axis="x", color=TOKENS["grid"])
    ax.grid(axis="y", visible=False)
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.02),
        frameon=False,
        ncol=3,
        borderaxespad=0,
        fontsize=8.5,
    )
    ax.set_xlim(0, max(totals) * 1.18)
    clean_axes(ax)
    add_chart_header(
        fig,
        ax,
        "NS3 exposes extra physical PXN FCT rows",
        "Targeted 15% failure samples. FlowSim rows are original all-to-all flows; NS3 rows are physical QP legs, so extra same-server rows indicate PXN decomposition.",
    )
    export_figure(fig, output_dir / "targeted_fct_line_counts.png")


def plot_p95_by_category(category: pd.DataFrame, output_dir: Path) -> None:
    use_chart_theme()
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.8), sharey=True)
    x = np.arange(len(CATEGORY_ORDER))
    width = 0.34
    max_value = float(category["p95_fct"].max())

    for ax, topology in zip(axes, TOPOLOGY_ORDER):
        part = category[category["topology"] == topology]
        for sim_index, simulator in enumerate(SIMULATOR_ORDER):
            values = []
            for category_name in CATEGORY_ORDER:
                point = part[
                    (part["simulator"] == simulator)
                    & (part["category"] == category_name)
                ]
                values.append(float(point["p95_fct"].iloc[0]) if not point.empty else np.nan)
            offset = (sim_index - 0.5) * width
            family = SIM_COLORS[simulator]
            valid_x = x[~np.isnan(values)] + offset
            valid_values = np.asarray(values, dtype=float)[~np.isnan(values)]
            bars = ax.bar(
                valid_x,
                valid_values,
                width=width,
                color=family["base"],
                edgecolor=family["dark"],
                linewidth=1.0,
                hatch="//" if simulator == "flowsim" else None,
                label=SIMULATOR_LABELS[simulator],
            )
            for bar in bars:
                bar.set_linewidth(0.8)
        ax.set_title(topology if topology != "Zcube" else "ZCube", fontsize=10.5)
        ax.set_xticks(x, [CATEGORY_LABELS[c] for c in CATEGORY_ORDER])
        ax.set_ylim(0, max_value * 1.12)
        ax.grid(axis="y", color=TOKENS["grid"])
        ax.grid(axis="x", visible=False)
        clean_axes(ax)
        if ax is axes[0]:
            ax.set_ylabel("p95 FCT output value")
            ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
        else:
            ax.set_ylabel("")

    handles = [
        Patch(
            facecolor=SIM_COLORS["flowsim"]["base"],
            edgecolor=SIM_COLORS["flowsim"]["dark"],
            hatch="//",
            label="FlowSim",
        ),
        Patch(
            facecolor=SIM_COLORS["ns3"]["base"],
            edgecolor=SIM_COLORS["ns3"]["dark"],
            label="NS3",
        ),
    ]
    add_chart_header(
        fig,
        axes[0],
        "Tail FCT differs by simulator grain and topology",
        "p95 values are from fct.txt column 7. FlowSim reports original-flow FCT; NS3 reports physical-leg FCT, so comparisons show model behavior plus logging-grain differences.",
    )
    fig.subplots_adjust(top=0.70, bottom=0.17, wspace=0.20)
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(axes[0].get_position().x0, 0.81),
        frameon=False,
        ncol=2,
        borderaxespad=0,
        fontsize=8.5,
    )
    export_figure(fig, output_dir / "targeted_fct_p95_by_category.png")


def write_outputs(
    *,
    fct: pd.DataFrame,
    overall: pd.DataFrame,
    category: pd.DataFrame,
    line_inflation: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    overall.to_csv(output_dir / "targeted_fct_distribution_summary.csv", index=False)
    category.to_csv(output_dir / "targeted_fct_category_summary.csv", index=False)
    line_inflation.to_csv(output_dir / "targeted_fct_line_inflation_summary.csv", index=False)
    sample_path = output_dir / "targeted_fct_sample_rows.csv"
    fct.sample(min(len(fct), 5000), random_state=0).to_csv(sample_path, index=False)

    plots_dir = output_dir / "plots"
    plot_line_counts(category, overall, plots_dir)
    plot_p95_by_category(category, plots_dir)


def run(args: argparse.Namespace) -> int:
    fct = load_targeted_fct(args.input_dir, gpus_per_server=args.gpus_per_server)
    overall, category, line_inflation = build_summaries(fct)
    write_outputs(
        fct=fct,
        overall=overall,
        category=category,
        line_inflation=line_inflation,
        output_dir=args.output_dir,
    )
    print(f"wrote summaries and plots under {args.output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze targeted mismatch FCT files")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gpus-per-server", type=int, default=8)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
