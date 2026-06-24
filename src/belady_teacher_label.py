from __future__ import annotations

from typing import Any

import pandas as pd

from .data import FEATURE_COLUMNS, TARGET_COLUMN, build_training_frame, calculate_next_distance

BELADY_TEACHER_LABEL_COLUMN = TARGET_COLUMN
BELADY_LABEL_STRATEGY = "belady_next_access_distance_teacher"


def validate_rawml_belady_schema(training_frame: pd.DataFrame) -> None:
    """Validate that RawML uses D_t^+(x) as label, not as input feature."""
    missing_feature_columns = [
        feature_column
        for feature_column in FEATURE_COLUMNS
        if feature_column not in training_frame.columns
    ]
    if missing_feature_columns:
        raise ValueError(f"Missing RawML feature columns: {missing_feature_columns}")

    if BELADY_TEACHER_LABEL_COLUMN not in training_frame.columns:
        raise ValueError(
            f"Missing Belady teacher label column: {BELADY_TEACHER_LABEL_COLUMN}"
        )

    if BELADY_TEACHER_LABEL_COLUMN in FEATURE_COLUMNS:
        raise ValueError(
            f"{BELADY_TEACHER_LABEL_COLUMN} is D_t^+(x), the Belady teacher label. "
            "It must not be part of FEATURE_COLUMNS."
        )


def calculate_belady_teacher_label(
    cache_item: str,
    current_index: int,
    position_lookup: dict[str, list[int]],
    trace_length: int,
) -> int:
    """Compute D_t^+(x), the next-access-distance label used by Belady/OPT.

    This function is a semantic wrapper around the existing next-distance helper.
    It makes the supervised target explicit: RawML learns to approximate the
    Belady/OPT future distance, while online prediction still receives only
    history-based features.
    """
    return calculate_next_distance(
        cache_item=cache_item,
        current_index=current_index,
        position_lookup=position_lookup,
        trace_length=trace_length,
    )


def build_belady_teacher_training_frame(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    max_training_rows: int,
) -> pd.DataFrame:
    """Build RawML data with history features and Belady/OPT teacher labels.

    Existing feature extraction already creates the target column
    `target_next_distance`. This wrapper validates and documents that the target
    is D_t^+(x), the next access distance used by Belady/OPT.
    """
    training_frame = build_training_frame(
        request_trace=request_trace,
        cache_size=cache_size,
        recent_window_size=recent_window_size,
        max_training_rows=max_training_rows,
    )
    validate_rawml_belady_schema(training_frame)
    training_frame.attrs["label_strategy"] = BELADY_LABEL_STRATEGY
    training_frame.attrs["label_column"] = BELADY_TEACHER_LABEL_COLUMN
    training_frame.attrs["feature_columns"] = list(FEATURE_COLUMNS)
    return training_frame


def describe_belady_teacher_frame(training_frame: pd.DataFrame) -> dict[str, Any]:
    """Return lightweight metadata for reproducibility logs."""
    validate_rawml_belady_schema(training_frame)
    return {
        "label_strategy": BELADY_LABEL_STRATEGY,
        "label_column": BELADY_TEACHER_LABEL_COLUMN,
        "feature_columns": list(FEATURE_COLUMNS),
        "num_rows": int(len(training_frame)),
        "target_min": float(training_frame[BELADY_TEACHER_LABEL_COLUMN].min()),
        "target_mean": float(training_frame[BELADY_TEACHER_LABEL_COLUMN].mean()),
        "target_max": float(training_frame[BELADY_TEACHER_LABEL_COLUMN].max()),
    }
