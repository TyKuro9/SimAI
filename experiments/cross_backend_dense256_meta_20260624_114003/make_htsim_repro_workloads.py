#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
SOURCE = (
    ROOT
    / "my_workloads"
    / "H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt"
)
OUT_DIR = EXP / "diagnostic_workloads"


def read_workload(path):
    lines = path.read_text().splitlines()
    if len(lines) < 2:
        raise RuntimeError(f"invalid workload: {path}")
    header = lines[0]
    declared = int(lines[1])
    rows = [line for line in lines[2:] if line.strip()]
    if declared != len(rows):
        raise RuntimeError(
            f"workload declares {declared} layers but contains {len(rows)} rows"
        )
    return header, rows


def write_workload(name, header, rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.txt"
    path.write_text("\n".join([header, str(len(rows)), *rows]) + "\n")
    return path


def capped_rows(rows, cap_bytes):
    capped = []
    for row in rows:
        fields = row.split("\t")
        for idx in (4, 7, 10):
            if idx < len(fields):
                try:
                    value = int(fields[idx])
                except ValueError:
                    continue
                if value > cap_bytes:
                    fields[idx] = str(cap_bytes)
        capped.append("\t".join(fields))
    return capped


def main():
    header, rows = read_workload(SOURCE)
    core = rows[:7]
    payload = rows[7:]

    outputs = {
        "dense256_fullsize_layernorm_only": [rows[3]],
        "dense256_fullsize_layernorm_embedding": [rows[3], rows[4]],
        "dense256_fullsize_core7": core,
        "dense256_fullsize_prefix10": rows[:10],
        "dense256_fullsize_core_plus_tail64": core + payload[-64:],
        "dense256_cap64m_core7": capped_rows(core, 64 * 1024 * 1024),
        "dense256_cap256m_core7": capped_rows(core, 256 * 1024 * 1024),
    }
    for name, subset in outputs.items():
        path = write_workload(name, header, subset)
        print(f"{name}\t{len(subset)}\t{path}")


if __name__ == "__main__":
    main()
