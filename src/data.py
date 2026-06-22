from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

FEATURE_COLUMNS = [
    "recency",
    "frequency",
    "recent_frequency",
    "average_inter_arrival",
    "cache_age",
]
TARGET_COLUMN = "target_next_distance"


@dataclass(frozen=True)
class TraceSplits:
    train: list[str]
    validation: list[str]
    test: list[str]


@dataclass
class OnlineFeatureState:
    recent_window_size: int
    last_access_times: dict[str, int]
    access_counts: dict[str, int]
    inter_arrival_sums: dict[str, float]
    inter_arrival_counts: dict[str, int]
    cache_insert_times: dict[str, int]
    recent_requests: deque[str]
    recent_access_counts: dict[str, int]

    @classmethod
    def create(cls, recent_window_size: int) -> OnlineFeatureState:
        return cls(
            recent_window_size=recent_window_size,
            last_access_times={},
            access_counts=defaultdict(int),
            inter_arrival_sums=defaultdict(float),
            inter_arrival_counts=defaultdict(int),
            cache_insert_times={},
            recent_requests=deque(),
            recent_access_counts=defaultdict(int),
        )

    def build_item_features(
        self,
        cache_item: str,
        current_index: int,
    ) -> dict[str, float]:
        last_access_time = self.last_access_times.get(cache_item)
        if last_access_time is None:
            recency = float(current_index + 1)
        else:
            recency = float(current_index - last_access_time)

        inter_arrival_count = self.inter_arrival_counts[cache_item]
        if inter_arrival_count == 0:
            average_inter_arrival = recency
        else:
            average_inter_arrival = (
                self.inter_arrival_sums[cache_item] / inter_arrival_count
            )

        cache_insert_time = self.cache_insert_times.get(cache_item, current_index)
        return {
            "recency": recency,
            "frequency": float(self.access_counts[cache_item]),
            "recent_frequency": float(self.recent_access_counts[cache_item]),
            "average_inter_arrival": average_inter_arrival,
            "cache_age": float(current_index - cache_insert_time),
        }

    def update_after_request(
        self,
        request_item: str,
        current_index: int,
    ) -> None:
        last_access_time = self.last_access_times.get(request_item)
        if last_access_time is not None:
            self.inter_arrival_sums[request_item] += current_index - last_access_time
            self.inter_arrival_counts[request_item] += 1

        self.last_access_times[request_item] = current_index
        self.access_counts[request_item] += 1
        self.recent_requests.append(request_item)
        self.recent_access_counts[request_item] += 1

        if len(self.recent_requests) > self.recent_window_size:
            expired_item = self.recent_requests.popleft()
            self.recent_access_counts[expired_item] -= 1


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as config_file:
        config_data = yaml.safe_load(config_file)

    if not isinstance(config_data, dict):
        raise ValueError("configs/config.yaml must contain a YAML mapping.")

    return config_data


def load_request_trace(trace_path: Path) -> list[str]:
    if not trace_path.exists():
        raise FileNotFoundError(
            f"Trace file not found: {trace_path}. "
            "Put your request trace at this path first."
        )

    trace_text = trace_path.read_text(encoding="utf-8")
    request_items = [
        item.strip() for item in re.split(r"[\s,]+", trace_text) if item.strip()
    ]

    if not request_items:
        raise ValueError("The request trace is empty.")

    return request_items


def split_trace(
    request_trace: list[str],
    train_ratio: float,
    validation_ratio: float,
) -> TraceSplits:
    trace_length = len(request_trace)
    train_end_index = int(trace_length * train_ratio)
    validation_end_index = train_end_index + int(trace_length * validation_ratio)

    if train_end_index <= 0 or validation_end_index >= trace_length:
        raise ValueError(
            "Invalid split ratios. Train, validation, and test must be non-empty."
        )

    return TraceSplits(
        train=request_trace[:train_end_index],
        validation=request_trace[train_end_index:validation_end_index],
        test=request_trace[validation_end_index:],
    )


def build_position_lookup(request_trace: list[str]) -> dict[str, list[int]]:
    position_lookup: dict[str, list[int]] = defaultdict(list)
    for current_index, request_item in enumerate(request_trace):
        position_lookup[request_item].append(current_index)
    return dict(position_lookup)


def calculate_next_distance(
    cache_item: str,
    current_index: int,
    position_lookup: dict[str, list[int]],
    trace_length: int,
) -> int:
    item_positions = position_lookup.get(cache_item, [])
    future_position_index = bisect_right(item_positions, current_index)

    if future_position_index >= len(item_positions):
        return trace_length + 1

    return item_positions[future_position_index] - current_index


def choose_lru_item(
    cache_items: set[str],
    last_access_times: dict[str, int],
) -> str:
    return min(
        cache_items,
        key=lambda cache_item: (last_access_times.get(cache_item, -1), cache_item),
    )


def build_training_frame(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    max_training_rows: int,
) -> pd.DataFrame:
    position_lookup = build_position_lookup(request_trace)
    feature_state = OnlineFeatureState.create(recent_window_size)
    cache_items: set[str] = set()
    training_rows: list[dict[str, float]] = []
    trace_length = len(request_trace)

    for current_index, request_item in enumerate(request_trace):
        if len(cache_items) == cache_size and len(training_rows) < max_training_rows:
            for cache_item in sorted(cache_items):
                item_features = feature_state.build_item_features(
                    cache_item=cache_item,
                    current_index=current_index,
                )
                item_features[TARGET_COLUMN] = float(
                    calculate_next_distance(
                        cache_item=cache_item,
                        current_index=current_index,
                        position_lookup=position_lookup,
                        trace_length=trace_length,
                    )
                )
                training_rows.append(item_features)

                if len(training_rows) >= max_training_rows:
                    break

        if request_item not in cache_items:
            if len(cache_items) >= cache_size:
                evicted_item = choose_lru_item(
                    cache_items=cache_items,
                    last_access_times=feature_state.last_access_times,
                )
                cache_items.remove(evicted_item)
                feature_state.cache_insert_times.pop(evicted_item, None)

            cache_items.add(request_item)
            feature_state.cache_insert_times[request_item] = current_index

        feature_state.update_after_request(
            request_item=request_item,
            current_index=current_index,
        )

    if not training_rows:
        raise ValueError(
            "No training rows were created. Reduce cache.cache_size or use a "
            "longer trace."
        )

    return pd.DataFrame(training_rows, columns=[*FEATURE_COLUMNS, TARGET_COLUMN])  # type: ignore[arg-type]


def save_processed_frame(data_frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data_frame.to_csv(output_path, index=False)
