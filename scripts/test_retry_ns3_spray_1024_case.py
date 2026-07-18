#!/usr/bin/env python3
"""Tests for safe 1024-GPU spray retry result merging."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.retry_ns3_spray_1024_case import ROW_INVARIANTS, merge_retry


def result_row(status: str, return_code: str, jct_us: str) -> dict[str, str]:
    row = {
        "workload_kind": "MoE",
        "topology": "Zcube",
        "policy": "spray_dynamic_chunk",
        "status": status,
        "return_code": return_code,
        "jct_us": jct_us,
    }
    for field in ROW_INVARIANTS:
        row.setdefault(field, f"same-{field}")
    return row


class SprayRetryMergeTest(unittest.TestCase):
    def test_successful_retry_atomically_replaces_failed_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authoritative_path = root / "jct_results.csv"
            retry_dir = root / "retry"
            retry_dir.mkdir()
            failed = result_row("failed", "-11", "missing")
            success = result_row("success", "0", "1234.5")

            merge_retry(
                authoritative_path,
                [failed],
                [success],
                ("MoE", "Zcube", "spray_dynamic_chunk"),
                retry_dir,
            )

            with authoritative_path.open(newline="") as input_file:
                merged = list(csv.DictReader(input_file))
            self.assertEqual(merged[0]["status"], "success")
            self.assertEqual(merged[0]["jct_us"], "1234.5")
            record = json.loads((retry_dir / "merge_record.json").read_text())
            self.assertEqual(record["previous_return_code"], "-11")

    def test_mismatched_retry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            failed = result_row("failed", "-11", "missing")
            success = result_row("success", "0", "1234.5")
            success["binary_sha256"] = "different"

            with self.assertRaises(SystemExit):
                merge_retry(
                    Path(directory) / "jct_results.csv",
                    [failed],
                    [success],
                    ("MoE", "Zcube", "spray_dynamic_chunk"),
                    Path(directory),
                )


if __name__ == "__main__":
    unittest.main()
