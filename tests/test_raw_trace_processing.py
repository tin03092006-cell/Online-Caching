from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.raw_trace_processing import inspect_prepared_trace, read_normalized_trace, trace_sha256


class RawTraceProcessingTest(unittest.TestCase):
    def test_read_normalized_trace_drops_empty_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "trace.txt"
            trace_path.write_text("A\n\n B \nC\n", encoding="utf-8")
            self.assertEqual(read_normalized_trace(trace_path), ["A", "B", "C"])

    def test_inspect_prepared_trace_reports_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "trace.txt"
            trace_path.write_text("A\nB\nA\n", encoding="utf-8")
            stats = inspect_prepared_trace(trace_path)
            self.assertEqual(stats.num_requests, 3)
            self.assertEqual(stats.num_unique_items, 2)
            self.assertEqual(stats.sha256, trace_sha256(["A", "B", "A"]))
            self.assertFalse(stats.has_empty_lines)
            self.assertFalse(stats.has_multitoken_lines)

    def test_inspect_prepared_trace_detects_multitoken_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "trace.txt"
            trace_path.write_text("A\nB C\n", encoding="utf-8")
            stats = inspect_prepared_trace(trace_path)
            self.assertTrue(stats.has_multitoken_lines)


if __name__ == "__main__":
    unittest.main()
