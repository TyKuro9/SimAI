#!/usr/bin/env python3
"""
从 256 Dense baseline 拓扑生成半速版本：
非 NVSwitch 链路带宽减半，GPU↔NVSwitch (NVLink) 保持不变。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "mytopo"
OUT_DIR = ROOT / "mytopo" / "256-half"

TOPO_FILES = [
    "Meta_Topo_256g_8gps_400Gbps_A100",
    "AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100",
    "DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
    "Zcube_n16_k2_256g_8gps_200Gbps_H100",
    "RailOnly_256g_8gps_p16a0.5_400Gbps_H100",
    "ROFT_256g_8gps_p16a0.5_400Gbps_H100",
]

BANDWIDTH_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(Gbps|Mbps|Kbps|bps)$",
    re.IGNORECASE,
)


def ParseBandwidth(bw: str) -> tuple[float, str]:
    match = BANDWIDTH_RE.match(bw.strip())
    if not match:
        raise ValueError(f"无法解析带宽: {bw!r}")
    return float(match.group(1)), match.group(2)


def FormatBandwidth(value: float, unit: str) -> str:
    if abs(value - round(value)) < 1e-9:
        value_str = str(int(round(value)))
    else:
        value_str = f"{value:g}"
    return f"{value_str}{unit}"


def HalveBandwidth(bw: str) -> str:
    value, unit = ParseBandwidth(bw)
    return FormatBandwidth(value / 2.0, unit)


def IsNvSwitchLink(src: int, dst: int, nvsw_ids: set[int]) -> bool:
    return src in nvsw_ids or dst in nvsw_ids


def ProcessTopo(src_path: Path, dst_path: Path) -> dict:
    lines = src_path.read_text().splitlines()
    if len(lines) < 3:
        raise ValueError(f"拓扑文件过短: {src_path}")

    header_parts = lines[0].split()
    if len(header_parts) < 6:
        raise ValueError(f"header 格式错误: {src_path}")

    total_nodes = int(header_parts[0])
    nvswitch_count = int(header_parts[2])
    other_switch_count = int(header_parts[3])
    link_count = int(header_parts[4])

    switch_ids = [int(x) for x in lines[1].split()]
    if len(switch_ids) < nvswitch_count:
        raise ValueError(f"switch 行 NVSwitch 数量不足: {src_path}")

    nvsw_ids = set(switch_ids[:nvswitch_count])
    gpu_count = total_nodes - nvswitch_count - other_switch_count

    out_lines = [lines[0], lines[1]]
    nvsw_unchanged = 0
    halved = 0
    non_nvsw_bandwidths: list[tuple[str, str]] = []

    for raw in lines[2:]:
        parts = raw.split()
        if len(parts) < 5:
            raise ValueError(f"链路行格式错误: {raw!r} in {src_path}")

        src = int(parts[0])
        dst = int(parts[1])
        bw = parts[2]
        latency = parts[3]
        error_rate = parts[4]

        if IsNvSwitchLink(src, dst, nvsw_ids):
            new_bw = bw
            nvsw_unchanged += 1
        else:
            new_bw = HalveBandwidth(bw)
            halved += 1
            non_nvsw_bandwidths.append((bw, new_bw))

        out_lines.append(f"{src} {dst} {new_bw} {latency} {error_rate}")

    if len(out_lines) - 2 != link_count:
        raise ValueError(
            f"链路数不一致: header={link_count}, actual={len(out_lines) - 2} in {src_path}"
        )

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text("\n".join(out_lines) + "\n")

    return {
        "file": src_path.name,
        "gpu_count": gpu_count,
        "nvswitch_count": nvswitch_count,
        "link_count": link_count,
        "nvsw_unchanged": nvsw_unchanged,
        "halved": halved,
        "sample_halved": non_nvsw_bandwidths[:3],
    }


def VerifyHalving(src_path: Path, dst_path: Path) -> None:
    src_lines = src_path.read_text().splitlines()
    dst_lines = dst_path.read_text().splitlines()

    header = src_lines[0].split()
    nvswitch_count = int(header[2])
    switch_ids = [int(x) for x in src_lines[1].split()]
    nvsw_ids = set(switch_ids[:nvswitch_count])

    for src_line, dst_line in zip(src_lines[2:], dst_lines[2:]):
        src_parts = src_line.split()
        dst_parts = dst_line.split()
        if src_parts[0:2] != dst_parts[0:2]:
            raise ValueError(f"连接关系变化: {src_line} -> {dst_line}")
        if src_parts[3:] != dst_parts[3:]:
            raise ValueError(f"时延/error_rate 变化: {src_line} -> {dst_line}")

        src_bw = src_parts[2]
        dst_bw = dst_parts[2]
        s = int(src_parts[0])
        d = int(src_parts[1])

        if IsNvSwitchLink(s, d, nvsw_ids):
            if src_bw != dst_bw:
                raise ValueError(f"NVSwitch 链路带宽被修改: {src_line} -> {dst_line}")
        else:
            expected = HalveBandwidth(src_bw)
            if dst_bw != expected:
                raise ValueError(
                    f"非 NVSwitch 链路未正确减半: {src_bw} -> {dst_bw}, 期望 {expected}"
                )


def Main() -> int:
    print(f"源目录: {SRC_DIR}")
    print(f"输出目录: {OUT_DIR}")
    print()

    summaries = []
    for name in TOPO_FILES:
        src = SRC_DIR / name
        if not src.is_file():
            print(f"Error: 源拓扑不存在: {src}", file=sys.stderr)
            return 1

        dst = OUT_DIR / name
        summary = ProcessTopo(src, dst)
        VerifyHalving(src, dst)
        summaries.append(summary)

        print(f"[OK] {name}")
        print(f"     GPU={summary['gpu_count']}, NVSwitch={summary['nvswitch_count']}, "
              f"links={summary['link_count']}")
        print(f"     NVSwitch 链路保持: {summary['nvsw_unchanged']}, "
              f"减半: {summary['halved']}")
        if summary["sample_halved"]:
            samples = ", ".join(f"{a}->{b}" for a, b in summary["sample_halved"])
            print(f"     示例: {samples}")
        print()

    print(f"全部 {len(summaries)} 套半速拓扑已写入 {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
