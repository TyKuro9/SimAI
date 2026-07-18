#!/usr/bin/env python3
"""Tests for matched 1024-GPU spray result comparison."""

from __future__ import annotations

import unittest

from scripts.compare_ns3_spray_1024_ga6 import build_comparison, result_status


class SprayComparisonTest(unittest.TestCase):
    def test_result_status_preserves_failed_return_code(self) -> None:
        self.assertEqual(
            result_status({"status": "failed", "return_code": "-11"}),
            "failed(-11)",
        )

    def test_failed_side_marks_pair_failed(self) -> None:
        baseline = [
            {
                "workload_kind": "MoE",
                "topology": "Zcube",
                "policy": "spray_adaptive",
                "status": "success",
                "return_code": "0",
                "jct_us": "1000",
            }
        ]
        dynamic = [
            {
                "workload_kind": "MoE",
                "topology": "Zcube",
                "policy": "spray_dynamic_chunk",
                "status": "failed",
                "return_code": "-11",
                "jct_us": "missing",
            }
        ]

        row = build_comparison(
            baseline,
            dynamic,
            "spray_adaptive",
            "spray_dynamic_chunk",
            [("MoE", "Zcube")],
        )[0]

        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["baseline_status"], "success")
        self.assertEqual(row["dynamic_status"], "failed(-11)")


if __name__ == "__main__":
    unittest.main()
