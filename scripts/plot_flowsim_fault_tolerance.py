#!/usr/bin/env python3
"""Render FlowSim fault-tolerance JCT curves as dark SVG charts.

The plotting code intentionally uses only the Python standard library so it can
run in minimal/offline environments where matplotlib is unavailable.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "flowsim_256_alltoall_p01_p15_s10_chain"
)
DEFAULT_OUTPUT = DEFAULT_RESULTS / "plots"


SERIES_STYLE = {
    "ROFT": {"label": "ROFT", "color": "#74d1ff", "marker": "x"},
    "Zcube": {"label": "ZCube", "color": "#57ea59", "marker": "tri_left"},
    "DeepSeek": {"label": "DeepSeek", "color": "#ff9d8d", "marker": "tri_right"},
    "HPN": {"label": "HPN", "color": "#f58be8", "marker": "square"},
    "Meta": {"label": "Meta", "color": "#8892a2", "marker": "pentagon"},
    "RO": {"label": "Rail-only", "color": "#d8d900", "marker": "circle"},
}
ORDER = ["ROFT", "Zcube", "DeepSeek", "HPN", "Meta", "RO"]


def load_series(results_dir: Path) -> Dict[str, List[Dict[str, float]]]:
    baseline_path = results_dir / "baseline_jct.csv"
    summary_path = results_dir / "random_link_failure_summary.csv"
    baselines: Dict[str, float] = {}
    with baseline_path.open(newline="") as f:
        for row in csv.DictReader(f):
            baselines[row["topology"]] = float(row["normal_jct"])

    grouped: Dict[str, List[Dict[str, float]]] = {
        topo: [{"rate": 0.0, "mean": jct, "std": 0.0}]
        for topo, jct in baselines.items()
    }
    with summary_path.open(newline="") as f:
        for row in csv.DictReader(f):
            topo = row["topology"]
            grouped.setdefault(topo, [])
            grouped[topo].append(
                {
                    "rate": float(row["link_failure_probability"]) * 100.0,
                    "mean": float(row["failed_jct_mean"]),
                    "std": float(row["failed_jct_std"]),
                }
            )
    for points in grouped.values():
        points.sort(key=lambda p: p["rate"])
    return grouped


def nice_y_ticks(y_max: float) -> Tuple[float, List[float]]:
    if y_max <= 2.0:
        top = 2.0
        step = 0.25
    elif y_max <= 4.0:
        top = math.ceil(y_max * 2.0) / 2.0
        step = 0.5
    else:
        top = math.ceil(y_max / 50.0) * 50.0
        step = 50.0
    ticks = []
    value = 0.0
    while value <= top + 1e-9:
        ticks.append(round(value, 6))
        value += step
    return top, ticks


def line_points(
    points: Iterable[Dict[str, float]],
    *,
    x0: float,
    y0: float,
    width: float,
    height: float,
    y_top: float,
    scale: float,
) -> List[Tuple[float, float]]:
    out = []
    for point in points:
        x = x0 + point["rate"] / 15.0 * width
        y = y0 + height - (point["mean"] / scale) / y_top * height
        out.append((x, y))
    return out


def band_polygon(
    points: List[Dict[str, float]],
    *,
    x0: float,
    y0: float,
    width: float,
    height: float,
    y_top: float,
    scale: float,
) -> str:
    upper = []
    lower = []
    for point in points:
        x = x0 + point["rate"] / 15.0 * width
        high = max(0.0, (point["mean"] + point["std"]) / scale)
        low = max(0.0, (point["mean"] - point["std"]) / scale)
        upper.append((x, y0 + height - high / y_top * height))
        lower.append((x, y0 + height - low / y_top * height))
    polygon = upper + list(reversed(lower))
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)


def marker_svg(kind: str, x: float, y: float, color: str, size: float = 8.5) -> str:
    stroke = color
    fill = color
    if kind == "circle":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size/2:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
    if kind == "square":
        half = size / 2
        return f'<rect x="{x-half:.2f}" y="{y-half:.2f}" width="{size:.2f}" height="{size:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
    if kind == "x":
        half = size / 2
        return (
            f'<path d="M {x-half:.2f} {y-half:.2f} L {x+half:.2f} {y+half:.2f} '
            f'M {x+half:.2f} {y-half:.2f} L {x-half:.2f} {y+half:.2f}" '
            f'fill="none" stroke="{stroke}" stroke-width="2.0" stroke-linecap="round"/>'
        )
    if kind == "tri_left":
        half = size / 2
        pts = [(x - half, y), (x + half, y - half), (x + half, y + half)]
        return f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a,b in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
    if kind == "tri_right":
        half = size / 2
        pts = [(x + half, y), (x - half, y - half), (x - half, y + half)]
        return f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a,b in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
    if kind == "pentagon":
        radius = size / 2 + 1
        pts = []
        for i in range(5):
            angle = -math.pi / 2 + 2 * math.pi * i / 5
            pts.append((x + math.cos(angle) * radius, y + math.sin(angle) * radius))
        return f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a,b in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
    return marker_svg("circle", x, y, color, size)


def render_svg(
    grouped: Dict[str, List[Dict[str, float]]],
    *,
    scale: float,
    output_path: Path,
    y_label: str,
) -> None:
    width = 1413
    height = 752
    bg = "#303846"
    fg = "#dbe2ef"
    axis = "#c8d0df"
    muted = "#aeb8c8"

    plot_x = 216
    plot_y = 42
    plot_w = 740
    plot_h = 642
    legend_x = 982
    legend_y = 154

    y_data_max = 0.0
    for topo, points in grouped.items():
        if topo not in SERIES_STYLE:
            continue
        for point in points:
            y_data_max = max(y_data_max, (point["mean"] + point["std"]) / scale)
    y_top, y_ticks = nice_y_ticks(y_data_max)

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
        '<style>',
        'text{font-family:Inter,Segoe UI,Arial,sans-serif;fill:#dbe2ef}',
        '.tick{font-size:32px;fill:#dbe2ef}',
        '.axis-label{font-size:38px;font-weight:500}',
        '.legend-title{font-size:34px;font-weight:700}',
        '.legend-text{font-size:32px}',
        '</style>',
    ]

    # Axes and border.
    parts.append(
        f'<rect x="{plot_x}" y="{plot_y}" width="{plot_w}" height="{plot_h}" '
        f'fill="none" stroke="{axis}" stroke-width="1.4"/>'
    )

    # Y ticks.
    for tick in y_ticks:
        y = plot_y + plot_h - tick / y_top * plot_h
        parts.append(f'<line x1="{plot_x-8}" y1="{y:.2f}" x2="{plot_x}" y2="{y:.2f}" stroke="{axis}" stroke-width="1.6"/>')
        parts.append(
            f'<text class="tick" x="{plot_x-14}" y="{y+11:.2f}" text-anchor="end">{tick:.2f}</text>'
        )

    # X ticks.
    for tick in range(16):
        x = plot_x + tick / 15.0 * plot_w
        parts.append(f'<line x1="{x:.2f}" y1="{plot_y+plot_h}" x2="{x:.2f}" y2="{plot_y+plot_h+8}" stroke="{axis}" stroke-width="1.6"/>')
        parts.append(
            f'<text class="tick" x="{x:.2f}" y="{plot_y+plot_h+36}" text-anchor="middle">{tick}</text>'
        )

    # Axis labels.
    parts.append(
        f'<text class="axis-label" x="{plot_x + plot_w/2:.2f}" y="{height-28}" text-anchor="middle">Link failure percentage (%)</text>'
    )
    parts.append(
        f'<text class="axis-label" transform="translate(126,{plot_y + plot_h/2:.2f}) rotate(-90)" text-anchor="middle">{html.escape(y_label)}</text>'
    )

    # Bands behind lines.
    for topo in ORDER:
        points = grouped.get(topo)
        if not points:
            continue
        style = SERIES_STYLE[topo]
        polygon = band_polygon(points, x0=plot_x, y0=plot_y, width=plot_w, height=plot_h, y_top=y_top, scale=scale)
        parts.append(f'<polygon points="{polygon}" fill="{style["color"]}" opacity="0.14" stroke="none"/>')

    # Lines and markers.
    for topo in ORDER:
        points = grouped.get(topo)
        if not points:
            continue
        style = SERIES_STYLE[topo]
        coords = line_points(points, x0=plot_x, y0=plot_y, width=plot_w, height=plot_h, y_top=y_top, scale=scale)
        d = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        parts.append(
            f'<polyline points="{d}" fill="none" stroke="{style["color"]}" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x, y in coords:
            parts.append(marker_svg(style["marker"], x, y, style["color"]))

    # Legend.
    parts.append(f'<text class="legend-title" x="{legend_x}" y="{legend_y}" text-anchor="start">Topology</text>')
    row_gap = 44
    for i, topo in enumerate(ORDER):
        style = SERIES_STYLE[topo]
        y = legend_y + 34 + i * row_gap
        parts.append(
            f'<line x1="{legend_x}" y1="{y}" x2="{legend_x+60}" y2="{y}" '
            f'stroke="{style["color"]}" stroke-width="2.7" stroke-linecap="round"/>'
        )
        parts.append(marker_svg(style["marker"], legend_x + 30, y, style["color"], size=9.5))
        parts.append(
            f'<text class="legend-text" x="{legend_x+84}" y="{y+11}" text-anchor="start">{html.escape(style["label"])}</text>'
        )

    parts.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts))


def write_html(svg_path: Path, html_path: Path) -> None:
    rel = svg_path.name
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1">',
                "<title>FlowSim fault tolerance JCT</title>",
                '<style>body{margin:0;background:#303846;display:grid;place-items:center;min-height:100vh}img{max-width:100%;height:auto}</style>',
                "</head>",
                "<body>",
                f'<img src="{html.escape(rel)}" alt="FlowSim fault tolerance JCT chart">',
                "</body>",
                "</html>",
            ]
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot FlowSim fault-tolerance JCT curves")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    grouped = load_series(args.results_dir)

    scaled_svg = args.output_dir / "flowsim_fault_tolerance_jct_scaled.svg"
    render_svg(grouped, scale=200.0, output_path=scaled_svg, y_label="JCT (s)")
    write_html(scaled_svg, args.output_dir / "flowsim_fault_tolerance_jct_scaled.html")

    raw_svg = args.output_dir / "flowsim_fault_tolerance_jct_raw.svg"
    render_svg(grouped, scale=1.0, output_path=raw_svg, y_label="FlowSim JCT")
    write_html(raw_svg, args.output_dir / "flowsim_fault_tolerance_jct_raw.html")

    print(scaled_svg)
    print(raw_svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
