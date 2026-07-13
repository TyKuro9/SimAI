#!/usr/bin/env python3
"""Analyze targeted NS3 monitor logs by topology link category."""

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
DEFAULT_INPUT = ROOT / "experiments" / "fault_tolerance" / "targeted_monitor_mismatch_retry"
DEFAULT_OUTPUT = DEFAULT_INPUT

TOPOLOGY_ORDER = ["Meta", "Zcube", "RO", "DeepSeek", "ROFT"]
LINK_CATEGORY_ORDER = ["local_nvswitch", "gpu_switch", "switch_switch", "other", "unmapped"]
PAIR_CATEGORY_ORDER = [
    "same_server",
    "cross_server_same_rail",
    "cross_server_cross_rail",
]

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}
COLORS = {
    "local_nvswitch": "#5477C4",
    "gpu_switch": "#71B436",
    "switch_switch": "#CC6F47",
    "other": "#7A828F",
    "unmapped": "#C5CAD3",
}


def use_chart_theme() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": TOKENS["surface"],
            "savefig.facecolor": TOKENS["surface"],
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial"],
            "xtick.color": TOKENS["muted"],
            "ytick.color": TOKENS["muted"],
            "text.color": TOKENS["ink"],
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def add_header(fig: plt.Figure, ax: plt.Axes, title: str, subtitle: str) -> None:
    title = textwrap.fill(title, width=82, break_long_words=False)
    subtitle = textwrap.fill(subtitle, width=118, break_long_words=False)
    fig.subplots_adjust(top=0.82)
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
    )
    fig.text(
        left,
        0.925,
        subtitle,
        ha="left",
        va="top",
        fontsize=9,
        color=TOKENS["muted"],
    )


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["left"].set_color(TOKENS["axis"])
    ax.spines["bottom"].set_color(TOKENS["axis"])
    ax.tick_params(axis="both", labelsize=8.5, length=0)


def parse_gbps(value: str) -> float:
    text = str(value).strip().lower()
    if text.endswith("gbps"):
        return float(text[:-4])
    if text.endswith("mbps"):
        return float(text[:-4]) / 1000.0
    if text.endswith("kbps"):
        return float(text[:-4]) / 1_000_000.0
    if text.endswith("bps"):
        return float(text[:-3]) / 1_000_000_000.0
    return float(text)


def parse_node_id(token: str) -> int:
    text = str(token).strip()
    if text.startswith("0b"):
        body = text[2:]
        node_hex = body[:-2] if len(body) > 2 else body
        return int(node_hex, 16)
    return int(text, 0)


def topology_sort_key(topology: str) -> int:
    try:
        return TOPOLOGY_ORDER.index(topology)
    except ValueError:
        return len(TOPOLOGY_ORDER)


def monitor_path(run_dir: Path, stem: str) -> Path:
    expected = run_dir / f"{stem}.csv"
    if expected.exists():
        return expected
    legacy = run_dir / f"{stem}nf"
    if legacy.exists():
        return legacy
    return expected


def parse_topology(path: Path) -> dict[str, object]:
    with path.open() as f:
        header = f.readline().split()
        if len(header) < 6:
            raise ValueError(f"invalid topology header: {path}")
        node_count = int(header[0])
        gpus_per_server = int(header[1])
        nvswitch_count = int(header[2])
        switch_count = int(header[3])
        link_count = int(header[4])
        switch_ids = [int(x) for x in f.readline().split()]
        node_types = [0] * node_count
        for sid in switch_ids[:nvswitch_count]:
            node_types[sid] = 2
        for sid in switch_ids[nvswitch_count : nvswitch_count + switch_count]:
            node_types[sid] = 1

        port_counts = [0] * node_count
        port_to_neighbor: dict[tuple[int, int], int] = {}
        bandwidth_gbps: dict[tuple[int, int], float] = {}
        edges = []
        for _ in range(link_count):
            line = f.readline()
            if not line:
                break
            parts = line.split()
            if len(parts) < 3:
                continue
            src, dst = int(parts[0]), int(parts[1])
            bw = parse_gbps(parts[2])
            port_counts[src] += 1
            port_counts[dst] += 1
            port_to_neighbor[(src, port_counts[src])] = dst
            port_to_neighbor[(dst, port_counts[dst])] = src
            bandwidth_gbps[(src, dst)] = bw
            bandwidth_gbps[(dst, src)] = bw
            edges.append((src, dst, bw))
    return {
        "node_count": node_count,
        "gpu_count": node_count - nvswitch_count - switch_count,
        "gpus_per_server": gpus_per_server,
        "nvswitch_count": nvswitch_count,
        "switch_count": switch_count,
        "node_types": node_types,
        "port_to_neighbor": port_to_neighbor,
        "bandwidth_gbps": bandwidth_gbps,
        "edges": edges,
    }


def node_type_name(topo: dict[str, object], node: int) -> str:
    node_types = topo["node_types"]
    if node < 0 or node >= len(node_types):
        return "unknown"
    value = node_types[node]
    if value == 0:
        return "gpu"
    if value == 1:
        return "switch"
    if value == 2:
        return "nvswitch"
    return "unknown"


def link_category(topo: dict[str, object], src: int | None, dst: int | None) -> str:
    if src is None or dst is None:
        return "unmapped"
    src_type = node_type_name(topo, src)
    dst_type = node_type_name(topo, dst)
    if src_type == "nvswitch" or dst_type == "nvswitch":
        return "local_nvswitch"
    if src_type == "switch" and dst_type == "switch":
        return "switch_switch"
    if {src_type, dst_type} == {"gpu", "switch"}:
        return "gpu_switch"
    return "other"


def pair_category(src: int, dst: int, gpus_per_server: int) -> str:
    if src // gpus_per_server == dst // gpus_per_server:
        return "same_server"
    if src % gpus_per_server == dst % gpus_per_server:
        return "cross_server_same_rail"
    return "cross_server_cross_rail"


def pct(series: pd.Series, percentile: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return float("nan")
    return float(np.percentile(values, percentile))


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(errors="replace") as f:
        return sum(1 for _ in f)


def add_port_mapping(frame: pd.DataFrame, topo: dict[str, object]) -> pd.DataFrame:
    if frame.empty:
        return frame
    port_to_neighbor = topo["port_to_neighbor"]
    frame = frame.copy()
    frame["node_id"] = pd.to_numeric(frame["node_id"], errors="coerce").astype("Int64")
    frame["port_id"] = pd.to_numeric(frame["port_id"], errors="coerce").astype("Int64")
    frame["neighbor"] = [
        port_to_neighbor.get((int(node), int(port)))
        if pd.notna(node) and pd.notna(port)
        else None
        for node, port in zip(frame["node_id"], frame["port_id"])
    ]
    frame["link_category"] = [
        link_category(topo, int(node) if pd.notna(node) else None, neighbor)
        for node, neighbor in zip(frame["node_id"], frame["neighbor"])
    ]
    return frame


def summarize_bw(run: pd.Series, topo: dict[str, object]) -> pd.DataFrame:
    path = monitor_path(Path(run["ns3_run_dir"]), "bw")
    if not path.exists():
        return pd.DataFrame()
    bw = pd.read_csv(path, skipinitialspace=True)
    if bw.empty:
        return pd.DataFrame()
    bw = add_port_mapping(bw, topo)
    bw["bandwidth"] = pd.to_numeric(bw["bandwidth"], errors="coerce")
    rows = []
    for category, part in bw.groupby("link_category", dropna=False):
        total_by_time = part.groupby("time")["bandwidth"].sum()
        rows.append(
            {
                "topology": run["topology"],
                "rate": run["rate"],
                "seed": run["seed"],
                "link_category": category,
                "samples": len(part),
                "active_ports": part[["node_id", "port_id"]].drop_duplicates().shape[0],
                "p50_port_bw": pct(part["bandwidth"], 50),
                "p95_port_bw": pct(part["bandwidth"], 95),
                "max_port_bw": float(part["bandwidth"].max()),
                "p95_total_bw_by_time": pct(total_by_time, 95),
                "max_total_bw_by_time": float(total_by_time.max()),
            }
        )
    return pd.DataFrame(rows)


def summarize_qlen(run: pd.Series, topo: dict[str, object]) -> pd.DataFrame:
    path = monitor_path(Path(run["ns3_run_dir"]), "qlen")
    if not path.exists():
        return pd.DataFrame()
    qlen = pd.read_csv(path, skipinitialspace=True)
    if qlen.empty:
        return pd.DataFrame()
    qlen = qlen.rename(columns={"sw_id": "node_id"})
    qlen = add_port_mapping(qlen, topo)
    qlen["q_len"] = pd.to_numeric(qlen["q_len"], errors="coerce")
    qlen["port_len"] = pd.to_numeric(qlen["port_len"], errors="coerce")
    per_port = (
        qlen.groupby(["time", "node_id", "port_id", "link_category"], dropna=False)
        .agg({"q_len": "max", "port_len": "max"})
        .reset_index()
    )
    rows = []
    for category, part in per_port.groupby("link_category", dropna=False):
        rows.append(
            {
                "topology": run["topology"],
                "rate": run["rate"],
                "seed": run["seed"],
                "link_category": category,
                "samples": len(part),
                "active_ports": part[["node_id", "port_id"]].drop_duplicates().shape[0],
                "p95_q_len": pct(part["q_len"], 95),
                "max_q_len": float(part["q_len"].max()),
                "p95_port_len": pct(part["port_len"], 95),
                "max_port_len": float(part["port_len"].max()),
            }
        )
    return pd.DataFrame(rows)


def summarize_qp_monitor(run: pd.Series, stem: str, value_col: str) -> pd.DataFrame:
    path = monitor_path(Path(run["ns3_run_dir"]), stem)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, skipinitialspace=True)
    if frame.empty:
        return pd.DataFrame()
    gpus_per_server = int(parse_topology(Path(run["topology_file"]))["gpus_per_server"])
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame["pair_category"] = [
        pair_category(int(src), int(dst), gpus_per_server)
        for src, dst in zip(frame["src"], frame["dst"])
    ]
    rows = []
    for category, part in frame.groupby("pair_category", dropna=False):
        rows.append(
            {
                "topology": run["topology"],
                "rate": run["rate"],
                "seed": run["seed"],
                "monitor": stem,
                "pair_category": category,
                "samples": len(part),
                "active_qps": part[["src", "dst", "sport", "dport"]]
                .drop_duplicates()
                .shape[0],
                f"p95_{value_col}": pct(part[value_col], 95),
                f"max_{value_col}": float(part[value_col].max()),
            }
        )
    return pd.DataFrame(rows)


def summarize_send(run: pd.Series) -> pd.DataFrame:
    path = Path(run["ns3_run_dir"]) / "send.txt"
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    topo = parse_topology(Path(run["topology_file"]))
    rows = []
    with path.open(errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 7:
                continue
            src = parse_node_id(parts[0])
            dst = parse_node_id(parts[1])
            rows.append(
                {
                    "src": src,
                    "dst": dst,
                    "size": int(float(parts[4])),
                    "start_time": float(parts[5]),
                    "duration": float(parts[6]),
                    "pair_category": pair_category(src, dst, int(topo["gpus_per_server"])),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    out = []
    for category, part in frame.groupby("pair_category", dropna=False):
        out.append(
            {
                "topology": run["topology"],
                "rate": run["rate"],
                "seed": run["seed"],
                "pair_category": category,
                "send_lines": len(part),
                "p95_duration": pct(part["duration"], 95),
                "max_duration": float(part["duration"].max()),
                "total_bytes": int(part["size"].sum()),
            }
        )
    return pd.DataFrame(out)


def summarize_pfc(run: pd.Series, topo: dict[str, object]) -> pd.DataFrame:
    path = Path(run["ns3_run_dir"]) / "pfc.txt"
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    rows = []
    port_to_neighbor = topo["port_to_neighbor"]
    with path.open(errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5:
                continue
            node = int(parts[1])
            port = int(parts[3])
            neighbor = port_to_neighbor.get((node, port))
            rows.append(
                {
                    "topology": run["topology"],
                    "rate": run["rate"],
                    "seed": run["seed"],
                    "node": node,
                    "node_type": int(parts[2]),
                    "port": port,
                    "event_type": int(parts[4]),
                    "link_category": link_category(topo, node, neighbor),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    return (
        frame.groupby(
            ["topology", "rate", "seed", "node_type", "event_type", "link_category"],
            dropna=False,
        )
        .size()
        .reset_index(name="events")
    )


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def concat_nonempty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    return pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()


def plot_bw(bw: pd.DataFrame, output_dir: Path) -> None:
    if bw.empty:
        return
    use_chart_theme()
    data = bw.copy()
    data["topology_order"] = data["topology"].map(topology_sort_key)
    data["category_order"] = data["link_category"].map(
        lambda x: LINK_CATEGORY_ORDER.index(x)
        if x in LINK_CATEGORY_ORDER
        else len(LINK_CATEGORY_ORDER)
    )
    data = data.sort_values(["topology_order", "category_order"])
    pivot = data.pivot_table(
        index="topology",
        columns="link_category",
        values="max_total_bw_by_time",
        aggfunc="max",
    ).reindex(TOPOLOGY_ORDER)
    pivot = pivot[[c for c in LINK_CATEGORY_ORDER if c in pivot.columns]]
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    bottom = np.zeros(len(pivot))
    x = np.arange(len(pivot))
    for category in pivot.columns:
        values = pivot[category].fillna(0).to_numpy(dtype=float)
        ax.bar(
            x,
            values,
            bottom=bottom,
            width=0.58,
            label=category,
            color=COLORS.get(category, "#7A828F"),
        )
        bottom += values
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index)
    ax.set_ylabel("Peak aggregate monitored BW")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    add_header(
        fig,
        ax,
        "NS3 monitored bandwidth is dominated by different link classes per topology",
        "Values are peak aggregate BW by sampled time bucket, grouped by reconstructed topology port category.",
    )
    clean_axes(ax)
    fig.savefig(output_dir / "targeted_monitor_peak_bw_by_link_category.png", dpi=220, bbox_inches="tight")
    fig.savefig(output_dir / "targeted_monitor_peak_bw_by_link_category.svg", bbox_inches="tight")
    plt.close(fig)


def plot_qlen(qlen: pd.DataFrame, output_dir: Path) -> None:
    if qlen.empty:
        return
    use_chart_theme()
    data = qlen.copy()
    data["topology_order"] = data["topology"].map(topology_sort_key)
    data["category_order"] = data["link_category"].map(
        lambda x: LINK_CATEGORY_ORDER.index(x)
        if x in LINK_CATEGORY_ORDER
        else len(LINK_CATEGORY_ORDER)
    )
    data = data.sort_values(["topology_order", "category_order"])
    pivot = data.pivot_table(
        index="topology",
        columns="link_category",
        values="max_port_len",
        aggfunc="max",
    ).reindex(TOPOLOGY_ORDER)
    pivot = pivot[[c for c in LINK_CATEGORY_ORDER if c in pivot.columns]]
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    width = 0.18
    x = np.arange(len(pivot))
    offsets = np.linspace(-width * (len(pivot.columns) - 1) / 2, width * (len(pivot.columns) - 1) / 2, len(pivot.columns))
    for offset, category in zip(offsets, pivot.columns):
        values = pivot[category].fillna(0).to_numpy(dtype=float) / 1_000_000
        ax.bar(
            x + offset,
            values,
            width=width,
            label=category,
            color=COLORS.get(category, "#7A828F"),
        )
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index)
    ax.set_ylabel("Peak port queue (MB)")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    add_header(
        fig,
        ax,
        "NS3 queue pressure exposes where PXN/failure traffic accumulates",
        "Queue values are per reconstructed output port; QLen rows are deduplicated across queues before aggregation.",
    )
    clean_axes(ax)
    fig.savefig(output_dir / "targeted_monitor_peak_queue_by_link_category.png", dpi=220, bbox_inches="tight")
    fig.savefig(output_dir / "targeted_monitor_peak_queue_by_link_category.svg", bbox_inches="tight")
    plt.close(fig)


def build_overview(
    summary: pd.DataFrame,
    bw: pd.DataFrame,
    qlen: pd.DataFrame,
    send: pd.DataFrame,
    pfc: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, run in summary.iterrows():
        topo = run["topology"]
        rate = run["rate"]
        seed = run["seed"]
        ns3_run_dir = Path(run["ns3_run_dir"])
        bw_run = bw[(bw["topology"] == topo) & (bw["rate"] == rate) & (bw["seed"] == seed)]
        qlen_run = qlen[
            (qlen["topology"] == topo) & (qlen["rate"] == rate) & (qlen["seed"] == seed)
        ]
        send_run = send[
            (send["topology"] == topo) & (send["rate"] == rate) & (send["seed"] == seed)
        ]
        pfc_run = pfc[
            (pfc["topology"] == topo) & (pfc["rate"] == rate) & (pfc["seed"] == seed)
        ] if not pfc.empty else pd.DataFrame()
        rows.append(
            {
                "topology": topo,
                "rate": rate,
                "seed": seed,
                "flowsim_jct": run.get("flowsim_jct"),
                "ns3_jct": run.get("ns3_jct"),
                "ns3_over_flowsim_jct": float(run["ns3_jct"]) / float(run["flowsim_jct"])
                if str(run.get("flowsim_jct")) != "missing"
                and str(run.get("ns3_jct")) != "missing"
                else np.nan,
                "ns3_fct_lines": run.get("ns3_fct_lines"),
                "ns3_send_lines": run.get("ns3_send_lines"),
                "actual_ns3_qlen_lines": count_lines(monitor_path(ns3_run_dir, "qlen")),
                "actual_ns3_bw_lines": count_lines(monitor_path(ns3_run_dir, "bw")),
                "actual_ns3_rate_lines": count_lines(monitor_path(ns3_run_dir, "rate")),
                "actual_ns3_cnp_lines": count_lines(monitor_path(ns3_run_dir, "cnp")),
                "actual_ns3_pfc_lines": count_lines(ns3_run_dir / "pfc.txt"),
                "bw_categories": int(bw_run["link_category"].nunique()) if not bw_run.empty else 0,
                "max_local_nvswitch_bw": category_value(
                    bw_run, "local_nvswitch", "max_total_bw_by_time"
                ),
                "max_gpu_switch_bw": category_value(
                    bw_run, "gpu_switch", "max_total_bw_by_time"
                ),
                "max_switch_switch_bw": category_value(
                    bw_run, "switch_switch", "max_total_bw_by_time"
                ),
                "max_local_nvswitch_queue": category_value(
                    qlen_run, "local_nvswitch", "max_port_len"
                ),
                "max_gpu_switch_queue": category_value(
                    qlen_run, "gpu_switch", "max_port_len"
                ),
                "max_switch_switch_queue": category_value(
                    qlen_run, "switch_switch", "max_port_len"
                ),
                "pfc_events": int(pfc_run["events"].sum()) if not pfc_run.empty else 0,
                "send_same_server": pair_value(send_run, "same_server", "send_lines"),
                "send_cross_server_same_rail": pair_value(
                    send_run, "cross_server_same_rail", "send_lines"
                ),
                "send_cross_server_cross_rail": pair_value(
                    send_run, "cross_server_cross_rail", "send_lines"
                ),
            }
        )
    return pd.DataFrame(rows)


def category_value(frame: pd.DataFrame, category: str, column: str) -> float:
    if frame.empty or column not in frame:
        return float("nan")
    part = frame[frame["link_category"] == category]
    if part.empty:
        return 0.0
    return float(part[column].max())


def pair_value(frame: pd.DataFrame, category: str, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    part = frame[frame["pair_category"] == category]
    if part.empty:
        return 0
    return int(part[column].sum())


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    summary_path = input_dir / "targeted_fct_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    summary = pd.read_csv(summary_path)

    bw_frames = []
    qlen_frames = []
    rate_frames = []
    cnp_frames = []
    send_frames = []
    pfc_frames = []
    for _, row in summary.iterrows():
        topo = parse_topology(Path(row["topology_file"]))
        bw_frames.append(summarize_bw(row, topo))
        qlen_frames.append(summarize_qlen(row, topo))
        rate_frames.append(summarize_qp_monitor(row, "rate", "curr_rate"))
        cnp_frames.append(summarize_qp_monitor(row, "cnp", "cnp_number"))
        send_frames.append(summarize_send(row))
        pfc_frames.append(summarize_pfc(row, topo))

    bw = concat_nonempty(bw_frames)
    qlen = concat_nonempty(qlen_frames)
    rate = concat_nonempty(rate_frames)
    cnp = concat_nonempty(cnp_frames)
    send = concat_nonempty(send_frames)
    pfc = concat_nonempty(pfc_frames)
    overview = build_overview(summary, bw, qlen, send, pfc)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_frame(bw, output_dir / "targeted_monitor_bw_summary.csv")
    write_frame(qlen, output_dir / "targeted_monitor_qlen_summary.csv")
    write_frame(rate, output_dir / "targeted_monitor_rate_summary.csv")
    write_frame(cnp, output_dir / "targeted_monitor_cnp_summary.csv")
    write_frame(send, output_dir / "targeted_monitor_send_summary.csv")
    write_frame(pfc, output_dir / "targeted_monitor_pfc_summary.csv")
    write_frame(overview, output_dir / "targeted_monitor_overview.csv")
    plot_bw(bw, output_dir)
    plot_qlen(qlen, output_dir)
    print(output_dir / "targeted_monitor_overview.csv")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze targeted NS3 monitor logs")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
