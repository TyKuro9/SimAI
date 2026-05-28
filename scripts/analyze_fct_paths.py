#!/usr/bin/env python3
"""
根据拓扑文件 + FCT 输出，统计各路径类型的 Flow 数量与 m_size。

路径类型（基于 ns-3 CalculateRoute 最短路径 + NVSwitch 优先）：
  NVSW_ONLY      - 仅经 NVSwitch 到达目的 GPU（机内 NVLink）
  ASW_ONLY       - 经 ASW、不经 PSW
  ASW_PSW        - 经 ASW 与 PSW
  PSW_ONLY       - 经 PSW 但不经过 ASW（Zcube 等 GPU 直连 PSW 拓扑）
  PXN_NVSW_ASW   - 首跳为 NVSwitch 且路径含 ASW（PXN 代理语义）
  PXN_NVSW_ASW_PSW - 首跳为 NVSwitch 且路径含 ASW+PSW
  OTHER          - 其他（如仅 GPU 直连、无法解析等）
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 拓扑解析
# ---------------------------------------------------------------------------

def ParseTopo(topo_path: str):
    with open(topo_path) as f:
        header = f.readline().split()
        total_nodes = int(header[0])
        gpus_per_server = int(header[1])
        nv_switch_count = int(header[2])
        other_switch_count = int(header[3])

        switch_line = f.readline().split()
        switch_ids = [int(x) for x in switch_line]

    gpu_count = switch_ids[0] if switch_ids else 0
    nv_ids = set(switch_ids[:nv_switch_count])
    other_ids = set(switch_ids[nv_switch_count:])

    adj: Dict[int, Set[int]] = defaultdict(set)
    with open(topo_path) as f:
        f.readline()
        f.readline()
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            u, v = int(parts[0]), int(parts[1])
            adj[u].add(v)
            adj[v].add(u)

    # ASW：与 GPU 相连的 non-NV 交换机；PSW：不与 GPU 直连的交换机
    asw_ids: Set[int] = set()
    for sid in other_ids:
        if any(n < gpu_count for n in adj[sid]):
            asw_ids.add(sid)
    psw_ids = other_ids - asw_ids

    return {
        "gpu_count": gpu_count,
        "gpus_per_server": gpus_per_server,
        "nv_ids": nv_ids,
        "asw_ids": asw_ids,
        "psw_ids": psw_ids,
        "adj": adj,
        "total_nodes": total_nodes,
    }


def NodeKind(nid: int, topo: dict) -> str:
    if nid < topo["gpu_count"]:
        return "GPU"
    if nid in topo["nv_ids"]:
        return "NVSW"
    if nid in topo["asw_ids"]:
        return "ASW"
    if nid in topo["psw_ids"]:
        return "PSW"
    return "UNK"


# ---------------------------------------------------------------------------
# 复现 ns-3 CalculateRoute（对每个目的 GPU 做一次 BFS）
# ---------------------------------------------------------------------------

def BuildNextHopTables(topo: dict) -> Dict[int, Dict[int, List[int]]]:
    """复现 ns-3 CalculateRoute：next_hop[node][dest_gpu] 为 node 到 dest 的下一跳列表。"""
    gpu_count = topo["gpu_count"]
    adj = topo["adj"]

    def NodeType(n: int) -> int:
        if n < gpu_count:
            return 0  # HOST
        if n in topo["nv_ids"]:
            return 2  # NVSWITCH
        return 1  # SWITCH (ASW/PSW)

    next_hop: Dict[int, Dict[int, List[int]]] = defaultdict(lambda: defaultdict(list))

    for host in range(gpu_count):
        q: List[int] = [host]
        dis: Dict[int, int] = {host: 0}
        qi = 0
        while qi < len(q):
            now = q[qi]
            qi += 1
            d = dis[now]
            for nxt in adj[now]:
                if nxt not in dis:
                    dis[nxt] = d + 1
                    if NodeType(nxt) in (1, 2):
                        q.append(nxt)

                if d + 1 != dis[nxt]:
                    continue

                via_nvswitch = any(NodeType(x) == 2 for x in next_hop[nxt][host])
                if not via_nvswitch:
                    if NodeType(now) == 2:
                        while next_hop[nxt][host]:
                            next_hop[nxt][host].pop()
                    next_hop[nxt][host].append(now)
                elif via_nvswitch and NodeType(now) == 2:
                    next_hop[nxt][host].append(now)

                if NodeType(nxt) == 0 and not next_hop[nxt][now]:
                    next_hop[nxt][now].append(now)

    return next_hop


def TracePath(
    src: int, dst: int, next_hop: Dict[int, Dict[int, List[int]]], max_hops: int = 64
) -> Optional[List[int]]:
    if src == dst:
        return [src]
    path = [src]
    cur = src
    for _ in range(max_hops):
        hops = next_hop.get(cur, {}).get(dst)
        if not hops:
            return None
        nxt = hops[0]
        path.append(nxt)
        cur = nxt
        if cur == dst:
            return path
    return None


def ClassifyPath(path: List[int], topo: dict, pxn_capable: bool) -> str:
    kinds = [NodeKind(n, topo) for n in path]
    kind_set = set(kinds)
    has_nv = "NVSW" in kind_set
    has_asw = "ASW" in kind_set
    has_psw = "PSW" in kind_set
    first_hop_kind = kinds[1] if len(kinds) >= 2 else "GPU"

    # 单条 QP 内同时经过 NVSW 与 ASW（PXN 第二段或极少数合一传输）
    if first_hop_kind == "NVSW" and has_asw:
        tag = "PXN_NVSW_ASW_PSW" if has_psw else "PXN_NVSW_ASW"
        if pxn_capable:
            return tag
        return tag  # 非 PXN 场景也统计，便于对比

    if has_nv and not has_asw and not has_psw:
        return "NVSW_ONLY"
    if has_asw and not has_psw:
        return "ASW_ONLY"
    if has_asw and has_psw:
        return "ASW_PSW"
    if has_psw and not has_asw:
        return "PSW_ONLY"
    if len(path) == 2 and path[0] != path[1]:
        return "GPU_DIRECT"
    return "OTHER"


# ---------------------------------------------------------------------------
# FCT 分析
# ---------------------------------------------------------------------------

def IpToNodeId(ip_hex: str) -> int:
    ip = int(ip_hex, 16)
    return (ip >> 8) & 0xFFFF


@dataclass
class PathStats:
    count: int = 0
    m_size_sum: int = 0
    m_sizes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def Add(self, m_size: int):
        self.count += 1
        self.m_size_sum += m_size
        self.m_sizes[m_size] += 1


def AnalyzeFct(
    fct_path: str,
    topo: dict,
    pair_class: Dict[Tuple[int, int], str],
    pxn_capable: bool,
) -> Dict[str, PathStats]:
    gpu_count = topo["gpu_count"]
    stats: Dict[str, PathStats] = defaultdict(PathStats)
    skipped_non_gpu = 0

    bad_lines = 0
    with open(fct_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 8:
                bad_lines += 1
                continue
            try:
                sid = IpToNodeId(parts[0])
                did = IpToNodeId(parts[1])
                m_size = int(parts[4])
            except (ValueError, IndexError):
                bad_lines += 1
                continue
            if sid >= gpu_count or did >= gpu_count:
                skipped_non_gpu += 1
                continue
            ptype = pair_class.get((sid, did))
            if ptype is None:
                ptype = "UNKNOWN_PAIR"
            stats[ptype].Add(m_size)

    if skipped_non_gpu:
        stats["_meta_skipped_non_gpu"].Add(skipped_non_gpu)
    if bad_lines:
        stats["_meta_bad_lines"].Add(bad_lines)
    return stats


def BuildPairClassification(topo: dict, pxn_capable: bool) -> Dict[Tuple[int, int], str]:
    print("  构建路由表...", flush=True)
    next_hop = BuildNextHopTables(topo)
    gpu_count = topo["gpu_count"]
    pair_class: Dict[Tuple[int, int], str] = {}
    missing = 0
    for s in range(gpu_count):
        if s % 32 == 0:
            print(f"    GPU 对进度 {s}/{gpu_count}", flush=True)
        for d in range(gpu_count):
            if s == d:
                pair_class[(s, d)] = "LOCAL"
                continue
            path = TracePath(s, d, next_hop)
            if path is None:
                pair_class[(s, d)] = "NO_ROUTE"
                missing += 1
            else:
                pair_class[(s, d)] = ClassifyPath(path, topo, pxn_capable)
    if missing:
        print(f"  警告: {missing} 个 GPU 对无路由", flush=True)
    return pair_class


def PrintReport(name: str, stats: Dict[str, PathStats], topo: dict):
    print(f"\n{'=' * 72}")
    print(f"拓扑/场景: {name}")
    print(
        f"  GPU={topo['gpu_count']}, NVSW={len(topo['nv_ids'])}, "
        f"ASW={len(topo['asw_ids'])}, PSW={len(topo['psw_ids'])}"
    )
    print(f"{'=' * 72}")
    print(
        f"{'路径类型':<22} {'流数':>12} {'占比':>8} "
        f"{'m_size总和(B)':>18} {'平均m_size(B)':>14}"
    )
    print("-" * 72)

    order = [
        "NVSW_ONLY",
        "ASW_ONLY",
        "ASW_PSW",
        "PSW_ONLY",
        "PXN_NVSW_ASW",
        "PXN_NVSW_ASW_PSW",
        "GPU_DIRECT",
        "LOCAL",
        "OTHER",
        "NO_ROUTE",
        "UNKNOWN_PAIR",
    ]
    total = sum(s.count for k, s in stats.items() if not k.startswith("_meta"))
    for key in order:
        if key not in stats:
            continue
        s = stats[key]
        pct = 100.0 * s.count / total if total else 0
        avg = s.m_size_sum / s.count if s.count else 0
        print(
            f"{key:<22} {s.count:>12} {pct:>7.2f}% "
            f"{s.m_size_sum:>18} {avg:>14.0f}"
        )
    for key in ("_meta_bad_lines", "_meta_skipped_non_gpu"):
        if key in stats:
            print(f"\n  [元数据] {key}: {stats[key].count}")

    for key, s in sorted(stats.items()):
        if key in order or key.startswith("_meta"):
            continue
        pct = 100.0 * s.count / total if total else 0
        avg = s.m_size_sum / s.count if s.count else 0
        print(
            f"{key:<22} {s.count:>12} {pct:>7.2f}% "
            f"{s.m_size_sum:>18} {avg:>14.0f}"
        )
    print(f"{'合计':<22} {total:>12} {'100.00%':>8}")

    # Top m_size 分布（按流数最多的类型各展示前 5）
    print("\n主要 m_size 分布 (按流数 Top5 消息大小):")
    for key in order[:6]:
        if key not in stats or stats[key].count == 0:
            continue
        top = sorted(stats[key].m_sizes.items(), key=lambda x: -x[1])[:5]
        detail = ", ".join(f"{sz}B×{cnt}" for sz, cnt in top)
        print(f"  {key}: {detail}")


# 256 GPU 配置：FCT -> topo，是否可能启用 PXN
JOBS = [
    (
        "Meta256",
        "simulation_output/meta256/meta256_fct.txt",
        "mytopo/Meta_Topo_256g_8gps_400Gbps_A100",
        False,
    ),
    (
        "Meta256 (meta_fct2)",
        "simulation_output/meta256/meta_fct2.txt",
        "mytopo/Meta_Topo_256g_8gps_400Gbps_A100",
        False,
    ),
    (
        "DeepSeek256",
        "simulation_output/DeepSeek256/DeepSeek256_fct.txt",
        "mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800",
        False,
    ),
    (
        "HPN256",
        "simulation_output/HPN256/HPN256_fct.txt",
        "mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100",
        False,
    ),
    (
        "Zcube256",
        "simulation_output/Zcube256/Zcube256_fct.txt",
        "mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100",
        False,
    ),
    (
        "RO256 (PXN=1)",
        "simulation_output/RO256/RO256_fct.txt",
        "mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100",
        True,
    ),
    (
        "ROFT256 (PXN=1)",
        "simulation_output/ROFT256/ROFT256_fct.txt",
        "mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100",
        True,
    ),
    (
        "ROFT256 woPXN",
        "simulation_output/ROFT256/ROFTwoPXN256_fct.txt",
        "mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100",
        False,
    ),
]


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)

    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", nargs="*", help="只跑指定 job 名（子串匹配）")
    parser.add_argument("--pair-cache", default="scripts/.fct_path_pair_cache")
    args = parser.parse_args()

    selected = JOBS
    if args.jobs:
        keys = args.jobs
        selected = [j for j in JOBS if any(k in j[0] for k in keys)]

    os.makedirs(args.pair_cache, exist_ok=True)

    for name, fct_rel, topo_rel, pxn in selected:
        fct_path = os.path.join(base, fct_rel)
        topo_path = os.path.join(base, topo_rel)
        if not os.path.isfile(fct_path):
            print(f"[跳过] FCT 不存在: {fct_path}")
            continue
        if not os.path.isfile(topo_path):
            print(f"[跳过] 拓扑不存在: {topo_path}")
            continue

        print(f"\n>>> 处理 {name}")
        topo = ParseTopo(topo_path)
        cache_file = os.path.join(
            args.pair_cache,
            os.path.basename(topo_rel) + ("_pxn" if pxn else "_nopxn") + ".pairclass",
        )
        if os.path.isfile(cache_file):
            print(f"  加载 GPU 对分类缓存: {cache_file}")
            pair_class = {}
            with open(cache_file) as cf:
                for line in cf:
                    s, d, cls = line.strip().split()
                    pair_class[(int(s), int(d))] = cls
        else:
            pair_class = BuildPairClassification(topo, pxn)
            with open(cache_file, "w") as cf:
                for (s, d), cls in pair_class.items():
                    cf.write(f"{s} {d} {cls}\n")
            print(f"  已写入缓存: {cache_file}")

        print(f"  扫描 FCT: {fct_path}")
        stats = AnalyzeFct(fct_path, topo, pair_class, pxn)
        PrintReport(name, stats, topo)


if __name__ == "__main__":
    main()
