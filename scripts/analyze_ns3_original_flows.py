#!/usr/bin/env python3
"""Analyze NS3 physical-leg logs with original-flow metadata."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "experiments" / "fault_tolerance" / "ns3_original_flow_smoke"
DEFAULT_OUTPUT = DEFAULT_INPUT


def parse_node_id(token: str) -> int:
    text = str(token).strip()
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


def topology_gpus_per_server(path: Path) -> int:
    with path.open() as f:
        header = f.readline().split()
    if len(header) < 2:
        raise ValueError(f"invalid topology header: {path}")
    return int(header[1])


def parse_send(path: Path, *, gpus_per_server: int) -> pd.DataFrame:
    rows = []
    has_metadata = False
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) not in (7, 13):
                raise ValueError(f"invalid send row in {path}:{line_no}: {line!r}")
            physical_src = parse_node_id(parts[0])
            physical_dst = parse_node_id(parts[1])
            if len(parts) == 13:
                has_metadata = True
                original_src = int(parts[7])
                original_dst = int(parts[8])
                leg_kind = parts[9]
                leg_index = int(parts[10])
                leg_count = int(parts[11])
                flow_id = int(parts[12])
            else:
                original_src = physical_src
                original_dst = physical_dst
                leg_kind = "legacy"
                leg_index = 0
                leg_count = 1
                flow_id = line_no
            rows.append(
                {
                    "physical_src": physical_src,
                    "physical_dst": physical_dst,
                    "sport": int(parts[2]),
                    "dport": int(parts[3]),
                    "size": int(float(parts[4])),
                    "start_time": float(parts[5]),
                    "duration": float(parts[6]),
                    "original_src": original_src,
                    "original_dst": original_dst,
                    "leg_kind": leg_kind,
                    "leg_index": leg_index,
                    "leg_count": leg_count,
                    "flow_id": flow_id,
                    "physical_category": pair_category(
                        physical_src, physical_dst, gpus_per_server
                    ),
                    "original_category": pair_category(
                        original_src, original_dst, gpus_per_server
                    ),
                    "has_original_metadata": has_metadata,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["has_original_metadata"] = has_metadata
    return frame


def parse_fct(path: Path, *, gpus_per_server: int) -> pd.DataFrame:
    rows = []
    has_metadata = False
    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) not in (8, 14):
                raise ValueError(f"invalid FCT row in {path}:{line_no}: {line!r}")
            physical_src = parse_node_id(parts[0])
            physical_dst = parse_node_id(parts[1])
            if len(parts) == 14:
                has_metadata = True
                original_src = int(parts[8])
                original_dst = int(parts[9])
                leg_kind = parts[10]
                leg_index = int(parts[11])
                leg_count = int(parts[12])
                flow_id = int(parts[13])
            else:
                original_src = physical_src
                original_dst = physical_dst
                leg_kind = "legacy"
                leg_index = 0
                leg_count = 1
                flow_id = line_no
            rows.append(
                {
                    "physical_src": physical_src,
                    "physical_dst": physical_dst,
                    "sport": int(parts[2]),
                    "dport": int(parts[3]),
                    "size": int(float(parts[4])),
                    "start_time": float(parts[5]),
                    "fct": float(parts[6]),
                    "standalone_fct": float(parts[7]),
                    "original_src": original_src,
                    "original_dst": original_dst,
                    "leg_kind": leg_kind,
                    "leg_index": leg_index,
                    "leg_count": leg_count,
                    "flow_id": flow_id,
                    "physical_category": pair_category(
                        physical_src, physical_dst, gpus_per_server
                    ),
                    "original_category": pair_category(
                        original_src, original_dst, gpus_per_server
                    ),
                    "has_original_metadata": has_metadata,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["has_original_metadata"] = has_metadata
    return frame


def summarize_original_groups(frame: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rows = []
    group_cols = ["original_src", "original_dst", "flow_id"]
    for keys, part in frame.groupby(group_cols, sort=False):
        ordered = part.sort_values(["leg_index", "physical_src", "physical_dst"])
        leg_kinds = ">".join(ordered["leg_kind"].astype(str))
        physical_categories = ">".join(ordered["physical_category"].astype(str))
        rows.append(
            {
                "original_src": keys[0],
                "original_dst": keys[1],
                "flow_id": keys[2],
                "original_category": ordered["original_category"].iloc[0],
                "physical_rows": len(ordered),
                "declared_leg_count": int(ordered["leg_count"].max()),
                "is_split": bool(
                    ordered["leg_kind"].ne("none").any()
                    or int(ordered["leg_count"].max()) > 1
                ),
                "leg_kinds": leg_kinds,
                "physical_categories": physical_categories,
                "has_physical_cross_rail": bool(
                    ordered["physical_category"].eq("cross_server_cross_rail").any()
                ),
                "has_physical_same_rail": bool(
                    ordered["physical_category"].eq("cross_server_same_rail").any()
                ),
                "has_physical_same_server": bool(
                    ordered["physical_category"].eq("same_server").any()
                ),
                "max_value": float(ordered[value_col].max()),
                "sum_value": float(ordered[value_col].sum()),
            }
        )
    return pd.DataFrame(rows)


def pct(values: pd.Series, percentile: float) -> float:
    data = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(data) == 0:
        return float("nan")
    return float(np.percentile(data, percentile))


def build_run_summaries(
    *,
    run: pd.Series,
    frame: pd.DataFrame,
    original: pd.DataFrame,
    source: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    base = {
        "topology": run["topology"],
        "rate": run["rate"],
        "seed": run["seed"],
        "source": source,
        "has_original_metadata": bool(frame["has_original_metadata"].iloc[0]),
    }
    kind_counts = Counter(frame["leg_kind"])
    category_counts = Counter(frame["physical_category"])
    line = {
        **base,
        "physical_rows": len(frame),
        "original_flows": len(original),
        "avg_physical_rows_per_original": len(frame) / len(original)
        if len(original)
        else float("nan"),
        "max_physical_rows_per_original": int(original["physical_rows"].max()),
        "split_original_flows": int(original["is_split"].sum()),
        "direct_original_flows": int((~original["is_split"]).sum()),
        "original_cross_rail_flows": int(
            original["original_category"].eq("cross_server_cross_rail").sum()
        ),
        "original_cross_rail_split_flows": int(
            (
                original["original_category"].eq("cross_server_cross_rail")
                & original["is_split"]
            ).sum()
        ),
        "original_cross_rail_with_physical_cross_rail": int(
            (
                original["original_category"].eq("cross_server_cross_rail")
                & original["has_physical_cross_rail"]
            ).sum()
        ),
        "rows_none": kind_counts.get("none", 0),
        "rows_local": kind_counts.get("local", 0),
        "rows_remote": kind_counts.get("remote", 0),
        "rows_legacy": kind_counts.get("legacy", 0),
        "physical_same_server_rows": category_counts.get("same_server", 0),
        "physical_same_rail_rows": category_counts.get("cross_server_same_rail", 0),
        "physical_cross_rail_rows": category_counts.get("cross_server_cross_rail", 0),
    }
    line_summary = pd.DataFrame([line])

    category_rows = []
    for category, part in original.groupby("original_category", sort=False):
        row = {
            **base,
            "original_category": category,
            "original_flows": len(part),
            "physical_rows": int(part["physical_rows"].sum()),
            "avg_physical_rows_per_original": float(part["physical_rows"].mean()),
            "p95_original_max_value": pct(part["max_value"], 95),
            "max_original_max_value": float(part["max_value"].max()),
            "split_original_flows": int(part["is_split"].sum()),
            "with_physical_cross_rail": int(part["has_physical_cross_rail"].sum()),
            "with_physical_same_rail": int(part["has_physical_same_rail"].sum()),
            "with_physical_same_server": int(part["has_physical_same_server"].sum()),
        }
        category_rows.append(row)
    category_summary = pd.DataFrame(category_rows)

    pattern_rows = []
    for keys, part in original.groupby(
        ["original_category", "leg_kinds", "physical_categories"], sort=False
    ):
        pattern_rows.append(
            {
                **base,
                "original_category": keys[0],
                "leg_kinds": keys[1],
                "physical_categories": keys[2],
                "original_flows": len(part),
                "physical_rows": int(part["physical_rows"].sum()),
            }
        )
    pattern_summary = pd.DataFrame(pattern_rows)
    return line_summary, category_summary, pattern_summary


def empty_group(original_src: int, original_dst: int, original_category: str) -> dict[str, object]:
    return {
        "original_src": original_src,
        "original_dst": original_dst,
        "original_category": original_category,
        "physical_rows": 0,
        "declared_leg_count": 1,
        "is_split": False,
        "has_physical_cross_rail": False,
        "has_physical_same_rail": False,
        "has_physical_same_server": False,
        "max_value": float("-inf"),
        "sum_value": 0.0,
        "legs": [],
    }


def scan_log_file(
    path: Path,
    *,
    source: str,
    gpus_per_server: int,
    run: pd.Series,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    if source not in {"send", "fct"}:
        raise ValueError(source)
    expected_legacy_cols = 7 if source == "send" else 8
    expected_metadata_cols = 13 if source == "send" else 14
    value_index = 6

    has_metadata = False
    physical_rows = 0
    kind_counts: Counter[str] = Counter()
    physical_category_counts: Counter[str] = Counter()
    groups: dict[tuple[int, int, int], dict[str, object]] = {}

    with path.open(errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) not in (expected_legacy_cols, expected_metadata_cols):
                raise ValueError(f"invalid {source} row in {path}:{line_no}: {line!r}")
            physical_src = parse_node_id(parts[0])
            physical_dst = parse_node_id(parts[1])
            if len(parts) == expected_metadata_cols:
                has_metadata = True
                metadata_offset = 7 if source == "send" else 8
                original_src = int(parts[metadata_offset])
                original_dst = int(parts[metadata_offset + 1])
                leg_kind = parts[metadata_offset + 2]
                leg_index = int(parts[metadata_offset + 3])
                leg_count = int(parts[metadata_offset + 4])
                flow_id = int(parts[metadata_offset + 5])
            else:
                original_src = physical_src
                original_dst = physical_dst
                leg_kind = "legacy"
                leg_index = 0
                leg_count = 1
                flow_id = line_no

            value = float(parts[value_index])
            physical_category = pair_category(physical_src, physical_dst, gpus_per_server)
            original_category = pair_category(original_src, original_dst, gpus_per_server)
            key = (original_src, original_dst, flow_id)
            group = groups.setdefault(
                key, empty_group(original_src, original_dst, original_category)
            )
            group["physical_rows"] = int(group["physical_rows"]) + 1
            group["declared_leg_count"] = max(int(group["declared_leg_count"]), leg_count)
            group["is_split"] = bool(group["is_split"]) or leg_kind != "none" or leg_count > 1
            group["has_physical_cross_rail"] = bool(group["has_physical_cross_rail"]) or physical_category == "cross_server_cross_rail"
            group["has_physical_same_rail"] = bool(group["has_physical_same_rail"]) or physical_category == "cross_server_same_rail"
            group["has_physical_same_server"] = bool(group["has_physical_same_server"]) or physical_category == "same_server"
            group["max_value"] = max(float(group["max_value"]), value)
            group["sum_value"] = float(group["sum_value"]) + value
            group["legs"].append((leg_index, physical_src, physical_dst, leg_kind, physical_category))

            physical_rows += 1
            kind_counts[leg_kind] += 1
            physical_category_counts[physical_category] += 1

    base = {
        "topology": run["topology"],
        "rate": run["rate"],
        "seed": run["seed"],
        "source": source,
        "has_original_metadata": has_metadata,
    }
    original_groups = list(groups.values())
    line_rows = [
        {
            **base,
            "physical_rows": physical_rows,
            "original_flows": len(original_groups),
            "avg_physical_rows_per_original": physical_rows / len(original_groups)
            if original_groups
            else float("nan"),
            "max_physical_rows_per_original": max(
                (int(group["physical_rows"]) for group in original_groups), default=0
            ),
            "split_original_flows": sum(bool(group["is_split"]) for group in original_groups),
            "direct_original_flows": sum(
                not bool(group["is_split"]) for group in original_groups
            ),
            "original_cross_rail_flows": sum(
                group["original_category"] == "cross_server_cross_rail"
                for group in original_groups
            ),
            "original_cross_rail_split_flows": sum(
                group["original_category"] == "cross_server_cross_rail"
                and bool(group["is_split"])
                for group in original_groups
            ),
            "original_cross_rail_with_physical_cross_rail": sum(
                group["original_category"] == "cross_server_cross_rail"
                and bool(group["has_physical_cross_rail"])
                for group in original_groups
            ),
            "rows_none": kind_counts.get("none", 0),
            "rows_local": kind_counts.get("local", 0),
            "rows_remote": kind_counts.get("remote", 0),
            "rows_legacy": kind_counts.get("legacy", 0),
            "physical_same_server_rows": physical_category_counts.get("same_server", 0),
            "physical_same_rail_rows": physical_category_counts.get(
                "cross_server_same_rail", 0
            ),
            "physical_cross_rail_rows": physical_category_counts.get(
                "cross_server_cross_rail", 0
            ),
        }
    ]

    by_category: dict[str, list[dict[str, object]]] = {}
    by_pattern: Counter[tuple[str, str, str]] = Counter()
    by_pattern_rows: Counter[tuple[str, str, str]] = Counter()
    for group in original_groups:
        category = str(group["original_category"])
        by_category.setdefault(category, []).append(group)
        ordered = sorted(group["legs"])
        leg_kinds = ">".join(str(leg[3]) for leg in ordered)
        physical_categories = ">".join(str(leg[4]) for leg in ordered)
        pattern_key = (category, leg_kinds, physical_categories)
        by_pattern[pattern_key] += 1
        by_pattern_rows[pattern_key] += int(group["physical_rows"])

    category_rows = []
    for category, groups_in_category in by_category.items():
        max_values = pd.Series([float(group["max_value"]) for group in groups_in_category])
        physical_row_count = sum(int(group["physical_rows"]) for group in groups_in_category)
        category_rows.append(
            {
                **base,
                "original_category": category,
                "original_flows": len(groups_in_category),
                "physical_rows": physical_row_count,
                "avg_physical_rows_per_original": physical_row_count
                / len(groups_in_category),
                "p95_original_max_value": pct(max_values, 95),
                "max_original_max_value": float(max_values.max()),
                "split_original_flows": sum(
                    bool(group["is_split"]) for group in groups_in_category
                ),
                "with_physical_cross_rail": sum(
                    bool(group["has_physical_cross_rail"]) for group in groups_in_category
                ),
                "with_physical_same_rail": sum(
                    bool(group["has_physical_same_rail"]) for group in groups_in_category
                ),
                "with_physical_same_server": sum(
                    bool(group["has_physical_same_server"]) for group in groups_in_category
                ),
            }
        )

    pattern_rows = [
        {
            **base,
            "original_category": key[0],
            "leg_kinds": key[1],
            "physical_categories": key[2],
            "original_flows": value,
            "physical_rows": by_pattern_rows[key],
        }
        for key, value in by_pattern.items()
    ]
    return line_rows, category_rows, pattern_rows


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    summary_path = input_dir / "targeted_fct_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    summary = pd.read_csv(summary_path)

    line_rows = []
    category_rows = []
    pattern_rows = []
    for _, run_row in summary.iterrows():
        run_dir = Path(run_row["ns3_run_dir"])
        gpus_per_server = topology_gpus_per_server(Path(run_row["topology_file"]))
        for source in ["send", "fct"]:
            path = run_dir / f"{source}.txt"
            if not path.exists() or path.stat().st_size == 0:
                continue
            line, category, pattern = scan_log_file(
                path, source=source, gpus_per_server=gpus_per_server, run=run_row
            )
            line_rows.extend(line)
            category_rows.extend(category)
            pattern_rows.extend(pattern)

    output_dir.mkdir(parents=True, exist_ok=True)
    line_summary = pd.DataFrame(line_rows)
    category_summary = pd.DataFrame(category_rows)
    pattern_summary = pd.DataFrame(pattern_rows)
    line_summary.to_csv(output_dir / "ns3_original_flow_line_summary.csv", index=False)
    category_summary.to_csv(
        output_dir / "ns3_original_flow_category_summary.csv", index=False
    )
    pattern_summary.to_csv(
        output_dir / "ns3_original_flow_pattern_summary.csv", index=False
    )
    print(output_dir / "ns3_original_flow_line_summary.csv")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze NS3 original-flow metadata")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
