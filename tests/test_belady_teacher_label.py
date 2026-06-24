from __future__ import annotations

import unittest

from src.belady_teacher_label import (
    BELADY_TEACHER_LABEL_COLUMN,
    build_belady_teacher_training_frame,
    calculate_belady_teacher_label,
    validate_rawml_belady_schema,
)
from src.data import FEATURE_COLUMNS, TARGET_COLUMN, build_position_lookup


class BeladyTeacherLabelTest(unittest.TestCase):
    def test_next_distance_matches_belady_teacher_label(self) -> None:
        trace = ["A", "B", "A", "C", "A", "B"]
        position_lookup = build_position_lookup(trace)

        self.assertEqual(
            calculate_belady_teacher_label(
                cache_item="B",
                current_index=1,
                position_lookup=position_lookup,
                trace_length=len(trace),
            ),
            4,
        )
        self.assertEqual(
            calculate_belady_teacher_label(
                cache_item="C",
                current_index=3,
                position_lookup=position_lookup,
                trace_length=len(trace),
            ),
            len(trace) + 1,
        )

    def test_target_is_label_not_feature(self) -> None:
        self.assertEqual(BELADY_TEACHER_LABEL_COLUMN, TARGET_COLUMN)
        self.assertNotIn(TARGET_COLUMN, FEATURE_COLUMNS)

    def test_training_frame_schema(self) -> None:
        trace = ["A", "B", "C", "A", "B", "D", "A", "C", "B", "E"]
        frame = build_belady_teacher_training_frame(
            request_trace=trace,
            cache_size=2,
            recent_window_size=3,
            max_training_rows=20,
        )
        validate_rawml_belady_schema(frame)
        self.assertIn(TARGET_COLUMN, frame.columns)
        for feature_column in FEATURE_COLUMNS:
            self.assertIn(feature_column, frame.columns)


if __name__ == "__main__":
    unittest.main()
