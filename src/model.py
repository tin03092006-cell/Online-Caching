from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from .data import (
    FEATURE_COLUMNS,
    OnlineFeatureState,
    build_position_lookup,
    calculate_next_distance,
)


@dataclass(frozen=True)
class CacheRunResult:
    algorithm_name: str
    cache_misses: int
    total_requests: int

    @property
    def miss_ratio(self) -> float:
        return self.cache_misses / self.total_requests


@dataclass(frozen=True)
class PendingExpertVote:
    expert_name: str
    decision_index: int


class RawMLPredictor:
    def __init__(self, model_config: dict[str, Any], seed: int) -> None:
        if model_config["type"] != "gradient_boosting":
            raise ValueError("Only model.type='gradient_boosting' is supported.")

        self.model = GradientBoostingRegressor(
            learning_rate=float(model_config["learning_rate"]),
            n_estimators=int(model_config["n_estimators"]),
            max_depth=int(model_config["max_depth"]),
            random_state=seed,
        )
        self.is_fitted = False

    def fit(self, training_frame: pd.DataFrame) -> None:
        feature_frame = training_frame[FEATURE_COLUMNS]
        target_values = training_frame["target_next_distance"]
        self.model.fit(feature_frame, target_values)
        self.is_fitted = True

    def predict_distances(self, feature_frame: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("RawMLPredictor must be fitted before prediction.")
        return np.asarray(self.model.predict(feature_frame), dtype=float)

    def evaluate_mae(self, evaluation_frame: pd.DataFrame) -> float:
        feature_frame = evaluation_frame[FEATURE_COLUMNS]
        target_values = evaluation_frame["target_next_distance"]
        predictions = self.predict_distances(feature_frame)  # type: ignore[arg-type]
        return mean_absolute_error(target_values, predictions)


def choose_lru_eviction(
    cache_items: set[str],
    feature_state: OnlineFeatureState,
) -> str:
    return min(
        cache_items,
        key=lambda cache_item: (
            feature_state.last_access_times.get(cache_item, -1),
            cache_item,
        ),
    )


def choose_lfu_eviction(
    cache_items: set[str],
    feature_state: OnlineFeatureState,
) -> str:
    return min(
        cache_items,
        key=lambda cache_item: (
            feature_state.access_counts[cache_item],
            feature_state.last_access_times.get(cache_item, -1),
            cache_item,
        ),
    )


def choose_mark_eviction(
    cache_items: set[str],
    marked_items: set[str],
    random_generator: random.Random,
    *,
    mutate_phase: bool = True,
) -> str:
    unmarked_items = sorted(cache_items - marked_items)

    if not unmarked_items:
        if mutate_phase:
            marked_items.clear()
            unmarked_items = sorted(cache_items)
        else:
            unmarked_items = sorted(cache_items)

    return random_generator.choice(unmarked_items)


def choose_raw_ml_eviction(
    cache_items: set[str],
    feature_state: OnlineFeatureState,
    current_index: int,
    predictor: RawMLPredictor,
) -> str:
    ordered_cache_items = sorted(cache_items)
    feature_rows = [
        feature_state.build_item_features(
            cache_item=cache_item,
            current_index=current_index,
        )
        for cache_item in ordered_cache_items
    ]
    feature_frame = pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)  # type: ignore[arg-type]
    predicted_distances = predictor.predict_distances(feature_frame)
    best_item_index = int(np.argmax(predicted_distances))
    return ordered_cache_items[best_item_index]


def count_belady_misses(request_trace: list[str], cache_size: int) -> CacheRunResult:
    position_lookup = build_position_lookup(request_trace)
    cache_items: set[str] = set()
    cache_misses = 0
    trace_length = len(request_trace)

    for current_index, request_item in enumerate(request_trace):
        if request_item in cache_items:
            continue

        cache_misses += 1
        if len(cache_items) < cache_size:
            cache_items.add(request_item)
            continue

        evicted_item = max(
            cache_items,
            key=lambda cache_item: (
                calculate_next_distance(
                    cache_item=cache_item,
                    current_index=current_index,
                    position_lookup=position_lookup,
                    trace_length=trace_length,
                ),
                cache_item,
            ),
        )
        cache_items.remove(evicted_item)
        cache_items.add(request_item)

    return CacheRunResult(
        algorithm_name="Belady/OPT",
        cache_misses=cache_misses,
        total_requests=trace_length,
    )


def run_mark_cache(
    request_trace: list[str],
    cache_size: int,
    seed: int,
    recent_window_size: int,
) -> CacheRunResult:
    random_generator = random.Random(seed)
    feature_state = OnlineFeatureState.create(recent_window_size)
    cache_items: set[str] = set()
    marked_items: set[str] = set()
    cache_misses = 0

    for current_index, request_item in enumerate(request_trace):
        if request_item not in cache_items:
            cache_misses += 1
            if len(cache_items) >= cache_size:
                evicted_item = choose_mark_eviction(
                    cache_items=cache_items,
                    marked_items=marked_items,
                    random_generator=random_generator,
                )
                cache_items.remove(evicted_item)
                marked_items.discard(evicted_item)
                feature_state.cache_insert_times.pop(evicted_item, None)

            cache_items.add(request_item)
            feature_state.cache_insert_times[request_item] = current_index

        marked_items.add(request_item)
        feature_state.update_after_request(
            request_item=request_item,
            current_index=current_index,
        )

    return CacheRunResult(
        algorithm_name="MARK",
        cache_misses=cache_misses,
        total_requests=len(request_trace),
    )


def run_hedge_full_cache(
    request_trace: list[str],
    cache_size: int,
    predictor: RawMLPredictor,
    hedge_learning_rate: float,
    seed: int,
    recent_window_size: int,
) -> CacheRunResult:
    random_generator = random.Random(seed)
    feature_state = OnlineFeatureState.create(recent_window_size)
    expert_weights = create_initial_expert_weights()
    pending_feedback: defaultdict[str, list[PendingExpertVote]] = defaultdict(list)
    cache_items: set[str] = set()
    marked_items: set[str] = set()
    cache_misses = 0
    trace_length = len(request_trace)

    for current_index, request_item in enumerate(request_trace):
        apply_observed_feedback(
            pending_feedback=pending_feedback,
            expert_weights=expert_weights,
            observed_item=request_item,
            current_index=current_index,
            hedge_learning_rate=hedge_learning_rate,
        )

        if request_item not in cache_items:
            cache_misses += 1
            if len(cache_items) >= cache_size:
                expert_votes = propose_expert_evictions(
                    cache_items=cache_items,
                    feature_state=feature_state,
                    marked_items=marked_items,
                    current_index=current_index,
                    predictor=predictor,
                    random_generator=random_generator,
                )
                evicted_item = choose_weighted_eviction(
                    expert_votes=expert_votes,
                    expert_weights=expert_weights,
                )
                store_pending_feedback(
                    expert_votes=expert_votes,
                    pending_feedback=pending_feedback,
                    current_index=current_index,
                )
                cache_items.remove(evicted_item)
                marked_items.discard(evicted_item)
                feature_state.cache_insert_times.pop(evicted_item, None)

            cache_items.add(request_item)
            feature_state.cache_insert_times[request_item] = current_index

        marked_items.add(request_item)
        feature_state.update_after_request(
            request_item=request_item,
            current_index=current_index,
        )

    return CacheRunResult(
        algorithm_name=f"HedgeFullDelayed(eta={hedge_learning_rate})",
        cache_misses=cache_misses,
        total_requests=trace_length,
    )


def propose_expert_evictions(
    cache_items: set[str],
    feature_state: OnlineFeatureState,
    marked_items: set[str],
    current_index: int,
    predictor: RawMLPredictor,
    random_generator: random.Random,
) -> dict[str, str]:
    return {
        "LRU": choose_lru_eviction(cache_items, feature_state),
        "LFU": choose_lfu_eviction(cache_items, feature_state),
        "MARK": choose_mark_eviction(
            cache_items=cache_items,
            marked_items=marked_items,
            random_generator=random_generator,
            mutate_phase=False,
        ),
        "RawML": choose_raw_ml_eviction(
            cache_items=cache_items,
            feature_state=feature_state,
            current_index=current_index,
            predictor=predictor,
        ),
    }


def choose_weighted_eviction(
    expert_votes: dict[str, str],
    expert_weights: dict[str, float],
) -> str:
    total_weight = sum(expert_weights.values())
    item_scores: defaultdict[str, float] = defaultdict(float)

    for expert_name, voted_item in expert_votes.items():
        item_scores[voted_item] += expert_weights[expert_name] / total_weight

    return max(
        item_scores,
        key=lambda cache_item: (item_scores[cache_item], cache_item),
    )


def create_initial_expert_weights() -> dict[str, float]:
    return {
        "LRU": 1.0,
        "LFU": 1.0,
        "MARK": 1.0,
        "RawML": 1.0,
    }


def store_pending_feedback(
    expert_votes: dict[str, str],
    pending_feedback: defaultdict[str, list[PendingExpertVote]],
    current_index: int,
) -> None:
    for expert_name, voted_item in expert_votes.items():
        pending_feedback[voted_item].append(
            PendingExpertVote(
                expert_name=expert_name,
                decision_index=current_index,
            )
        )


def apply_observed_feedback(
    pending_feedback: defaultdict[str, list[PendingExpertVote]],
    expert_weights: dict[str, float],
    observed_item: str,
    current_index: int,
    hedge_learning_rate: float,
) -> None:
    observed_votes = pending_feedback.pop(observed_item, [])

    for pending_vote in observed_votes:
        feedback_delay = current_index - pending_vote.decision_index
        expert_loss = 1.0 / (1.0 + float(feedback_delay))
        expert_weights[pending_vote.expert_name] *= math.exp(
            -hedge_learning_rate * expert_loss
        )


def select_best_hedge_learning_rate(
    validation_trace: list[str],
    cache_size: int,
    predictor: RawMLPredictor,
    candidate_learning_rates: list[float],
    seed: int,
    recent_window_size: int,
) -> float:
    validation_results = [
        run_hedge_full_cache(
            request_trace=validation_trace,
            cache_size=cache_size,
            predictor=predictor,
            hedge_learning_rate=candidate_learning_rate,
            seed=seed,
            recent_window_size=recent_window_size,
        )
        for candidate_learning_rate in candidate_learning_rates
    ]
    best_result_index = int(
        np.argmin([result.cache_misses for result in validation_results])
    )
    return candidate_learning_rates[best_result_index]
