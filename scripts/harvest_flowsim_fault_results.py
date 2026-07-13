#!/usr/bin/env python3
"""Harvest FlowSim fault runs from EndToEnd.csv files and plot averaged JCT.

This is useful when a long resume sweep has produced run outputs but the main
runner's raw CSV has not caught up yet.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


TOPOLOGY_ORDER = ["Meta", "HPN", "DeepSeek", "Zcube", "RO", "ROFT"]
PLOT_ORDER = ["ROFT", "Zcube", "DeepSeek", "HPN", "Meta", "RO"]
LABELS = {
    "ROFT": "ROFT",
    "Zcube": "ZCube",
    "DeepSeek": "DeepSeek",
    "HPN": "HPN",
    "Meta": "Meta",
    "RO": "Rail-only",
}
COLORS = {
    "ROFT": "#74d1ff",
    "Zcube": "#57ea59",
    "DeepSeek": "#ff9d8d",
    "HPN": "#f58be8",
    "Meta": "#8892a2",
    "RO": "#d8d900",
}
MARKERS = {
    "ROFT": "x",
    "Zcube": "tri_left",
    "DeepSeek": "tri_right",
    "HPN": "square",
    "Meta": "pentagon",
    "RO": "circle",
}


def read_total_time(path: Path) -> float | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        row = next(reader, None)
    if not header or not row:
        return None
    try:
        idx = [h.strip() for h in header].index("Total time")
    except ValueError:
        return None
    try:
        return float(row[idx].strip())
    except (ValueError, IndexError):
        return None


def rate_from_label(label: str) -> float:
    if not label.startswith("p"):
        raise ValueError(f"unexpected rate label: {label}")
    return float(label[1:].replace("p", "."))


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_baselines(results_dir: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    with (results_dir / "baseline_jct.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            out[row["topology"]] = float(row["normal_jct"])
    return out


def harvest_rows(results_dir: Path) -> List[Dict[str, object]]:
    baselines = read_baselines(results_dir)
    rows: List[Dict[str, object]] = []
    runs_dir = results_dir / "runs"
    for topology in TOPOLOGY_ORDER:
        topo_dir = runs_dir / topology
        if not topo_dir.exists():
            continue
        for rate_dir in sorted(topo_dir.iterdir()):
            if not rate_dir.is_dir() or not rate_dir.name.startswith("p"):
                continue
            rate = rate_from_label(rate_dir.name)
            for seed_dir in sorted(rate_dir.glob("seed*")):
                if not seed_dir.is_dir():
                    continue
                try:
                    seed = int(seed_dir.name.removeprefix("seed"))
                except ValueError:
                    continue
                jct = read_total_time(seed_dir / "EndToEnd.csv")
                if jct is None:
                    continue
                normal = baselines[topology]
                rows.append(
                    {
                        "topology": topology,
                        "link_failure_probability": rate,
                        "seed": seed,
                        "status": "success",
                        "normal_jct": normal,
                        "failed_jct": jct,
                        "degradation": (jct - normal) / normal if normal else "missing",
                        "run_dir": str(seed_dir),
                    }
                )
    return sorted(
        rows,
        key=lambda r: (
            TOPOLOGY_ORDER.index(str(r["topology"])),
            float(r["link_failure_probability"]),
            int(r["seed"]),
        ),
    )


def summarize(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[tuple[str, float], List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["topology"]), float(row["link_failure_probability"]))].append(row)

    out: List[Dict[str, object]] = []
    for topology in TOPOLOGY_ORDER:
        for rate in [i / 100 for i in range(1, 16)]:
            group = grouped.get((topology, rate), [])
            if not group:
                continue
            jcts = [float(r["failed_jct"]) for r in group]
            normal = float(group[0]["normal_jct"])
            degradations = [float(r["degradation"]) for r in group]
            out.append(
                {
                    "topology": topology,
                    "link_failure_probability": rate,
                    "num_samples": len(group),
                    "num_success": len(group),
                    "normal_jct_mean": normal,
                    "normal_jct_std": 0.0,
                    "failed_jct_mean": statistics.mean(jcts),
                    "failed_jct_std": statistics.pstdev(jcts) if len(jcts) > 1 else 0.0,
                    "degradation_mean": statistics.mean(degradations),
                    "degradation_std": (
                        statistics.pstdev(degradations) if len(degradations) > 1 else 0.0
                    ),
                }
            )
    return out


def marker_svg(kind: str, x: float, y: float, color: str, size: float = 8.5) -> str:
    if kind == "circle":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size/2:.2f}" fill="{color}" stroke="{color}" stroke-width="1.4"/>'
    if kind == "square":
        half = size / 2
        return f'<rect x="{x-half:.2f}" y="{y-half:.2f}" width="{size:.2f}" height="{size:.2f}" fill="{color}" stroke="{color}" stroke-width="1.4"/>'
    if kind == "x":
        half = size / 2
        return (
            f'<path d="M {x-half:.2f} {y-half:.2f} L {x+half:.2f} {y+half:.2f} '
            f'M {x+half:.2f} {y-half:.2f} L {x-half:.2f} {y+half:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="2.0" stroke-linecap="round"/>'
        )
    if kind == "tri_left":
        half = size / 2
        pts = [(x - half, y), (x + half, y - half), (x + half, y + half)]
    elif kind == "tri_right":
        half = size / 2
        pts = [(x + half, y), (x - half, y - half), (x - half, y + half)]
    elif kind == "pentagon":
        radius = size / 2 + 1
        pts = []
        for i in range(5):
            angle = -math.pi / 2 + 2 * math.pi * i / 5
            pts.append((x + math.cos(angle) * radius, y + math.sin(angle) * radius))
    else:
        return marker_svg("circle", x, y, color, size)
    return f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in pts)}" fill="{color}" stroke="{color}" stroke-width="1.2"/>'


def render_svg(summary_rows: Sequence[Dict[str, object]], output_path: Path, *, title: str) -> None:
    width, height = 1413, 752
    bg, fg, axis = "#303846", "#dbe2ef", "#c8d0df"
    plot_x, plot_y, plot_w, plot_h = 216, 58, 740, 626
    legend_x, legend_y = 982, 154

    by_topo: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in summary_rows:
        by_topo[str(row["topology"])].append(row)
    for rows in by_topo.values():
        rows.sort(key=lambda r: float(r["link_failure_probability"]))

    y_max_data = max(float(r["failed_jct_mean"]) + float(r["failed_jct_std"]) for r in summary_rows)
    y_top = max(1000.0, math.ceil(y_max_data / 250.0) * 250.0)
    y_step = 250.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
        '<style>text{font-family:Inter,Segoe UI,Arial,sans-serif;fill:#dbe2ef}.tick{font-size:30px}.axis-label{font-size:36px;font-weight:500}.title{font-size:28px;font-weight:700}.legend-title{font-size:34px;font-weight:700}.legend-text{font-size:32px}</style>',
        f'<text class="title" x="{plot_x}" y="34">{title}</text>',
        f'<rect x="{plot_x}" y="{plot_y}" width="{plot_w}" height="{plot_h}" fill="none" stroke="{axis}" stroke-width="1.4"/>',
    ]

    tick = 0.0
    while tick <= y_top + 1e-9:
        y = plot_y + plot_h - tick / y_top * plot_h
        parts.append(f'<line x1="{plot_x-8}" y1="{y:.2f}" x2="{plot_x}" y2="{y:.2f}" stroke="{axis}" stroke-width="1.4"/>')
        parts.append(f'<text class="tick" x="{plot_x-14}" y="{y+10:.2f}" text-anchor="end">{tick:.0f}</text>')
        tick += y_step

    for pct in range(16):
        x = plot_x + pct / 15.0 * plot_w
        parts.append(f'<line x1="{x:.2f}" y1="{plot_y+plot_h}" x2="{x:.2f}" y2="{plot_y+plot_h+8}" stroke="{axis}" stroke-width="1.4"/>')
        parts.append(f'<text class="tick" x="{x:.2f}" y="{plot_y+plot_h+36}" text-anchor="middle">{pct}</text>')

    parts.append(f'<text class="axis-label" x="{plot_x + plot_w/2:.2f}" y="{height-28}" text-anchor="middle">Link failure percentage (%)</text>')
    parts.append(f'<text class="axis-label" transform="translate(118,{plot_y + plot_h/2:.2f}) rotate(-90)" text-anchor="middle">Mean JCT</text>')

    for topology in PLOT_ORDER:
        rows = by_topo.get(topology, [])
        if not rows:
            continue
        color = COLORS[topology]
        coords = []
        upper = []
        lower = []
        for row in rows:
            x = plot_x + (float(row["link_failure_probability"]) * 100.0) / 15.0 * plot_w
            mean = float(row["failed_jct_mean"])
            std = float(row["failed_jct_std"])
            y = plot_y + plot_h - mean / y_top * plot_h
            y_hi = plot_y + plot_h - (mean + std) / y_top * plot_h
            y_lo = plot_y + plot_h - max(0.0, mean - std) / y_top * plot_h
            coords.append((x, y))
            upper.append((x, y_hi))
            lower.append((x, y_lo))
        band = " ".join(f"{x:.2f},{y:.2f}" for x, y in upper + list(reversed(lower)))
        line = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        parts.append(f'<polygon points="{band}" fill="{color}" opacity="0.14" stroke="none"/>')
        parts.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, y in coords:
            parts.append(marker_svg(MARKERS[topology], x, y, color))

    parts.append(f'<text class="legend-title" x="{legend_x}" y="{legend_y}">Topology</text>')
    for i, topology in enumerate(PLOT_ORDER):
        color = COLORS[topology]
        y = legend_y + 34 + i * 44
        parts.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x+60}" y2="{y}" stroke="{color}" stroke-width="2.7" stroke-linecap="round"/>')
        parts.append(marker_svg(MARKERS[topology], legend_x + 30, y, color, size=9.5))
        parts.append(f'<text class="legend-text" x="{legend_x+84}" y="{y+11}">{LABELS[topology]}</text>')

    parts.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harvest and plot FlowSim fault results")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--required-samples", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = harvest_rows(args.results_dir)
    summary_rows = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "harvested_raw.csv", rows)
    write_csv(args.output_dir / "harvested_summary.csv", summary_rows)

    complete_rows = [
        r for r in summary_rows if int(r["num_success"]) >= args.required_samples
    ]
    write_csv(args.output_dir / "harvested_summary_complete_points.csv", complete_rows)
    if summary_rows:
        render_svg(
            summary_rows,
            args.output_dir / "flowsim_1024_ep4MiB_current_mean_jct.svg",
            title="FlowSim 1024 fault tolerance mean JCT (current harvested samples)",
        )
    if complete_rows:
        render_svg(
            complete_rows,
            args.output_dir / "flowsim_1024_ep4MiB_s30_mean_jct.svg",
            title=f"FlowSim 1024 fault tolerance mean JCT ({args.required_samples} seeds where complete)",
        )

    total_expected = 6 * 15 * args.required_samples
    complete_points = sum(1 for r in summary_rows if int(r["num_success"]) >= args.required_samples)
    print(f"harvested_rows={len(rows)} expected={total_expected}")
    print(f"summary_points={len(summary_rows)} complete_points={complete_points}/90")
    if summary_rows:
        print(args.output_dir / "flowsim_1024_ep4MiB_current_mean_jct.svg")
    if complete_rows:
        print(args.output_dir / "flowsim_1024_ep4MiB_s30_mean_jct.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
