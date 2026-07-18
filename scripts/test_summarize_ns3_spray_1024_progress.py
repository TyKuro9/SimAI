#!/usr/bin/env python3
"""Tests for the monotonic NS3 spray progress counters."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.summarize_ns3_spray_1024_progress import log_progress, workload_shape


class SprayProgressTest(unittest.TestCase):
    def test_workload_shape_counts_nonzero_collectives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workload = Path(directory) / "workload.txt"
            workload.write_text(
                "MODEL all_gpus: 8 checkpoints: 0\n"
                "2\n"
                "first -1 1 ALLGATHER 100 1 NONE 0 1 ALLREDUCE 50 100\n"
                "second -1 1 NONE 0 1 REDUCESCATTER 25 1 NONE 0 100\n"
            )

            self.assertEqual(workload_shape(workload), (2, 3))

    def test_log_progress_counts_events_across_layer_reversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "layer_num is: 0\n"
                "layer_num is: 1\n"
                "layer_num is: 0\n"
            )

            self.assertEqual(log_progress(log), (3, 0))


if __name__ == "__main__":
    unittest.main()
