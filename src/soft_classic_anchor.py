from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

from .data import OnlineFeatureState
from .model import (
    CacheRunResult,
    PendingExpertVote,
    RawMLPredictor,
    choose_weighted_eviction,
    normalize_expert_weights,
    propose_expert_evictions,
    store_pending_feedback,
)


ACTIVE_EXPERTS = ("LRU", "LFU", "MARK", "RawML")
ANCHOR_EXPERTS = ("LRU", "LFU")
RECENT_LOSS_WINDOW_SIZE = 512
SOFT_ANCHOR_MARGIN = 0.01
SOFT_ANCHOR_MIN_FEEDBACK_COUNT = 8
SOFT_ANCHOR_BOOST = 1.75
RAW_ML_COMPETITIVE_MARGIN = 0.02
RAW_ML_COMPETITIVE_BOOST = 1.25


@dataclass
class RecentExpertLossTracker:
    max_window_size: int
    losses: dict[str, deque[float]]

    @classmethod
    def create(cls, max_window_size: int) -> "RecentExpertLossTracker":
        return cls(
            max_window_size=max_window_size,
            losses={
                expert_name: deque(maxlen=max_window_size)
                for expert_name in ACTIVE_EXPERTS
            },
        )

    def add_loss(self, expert_name: str, loss: float) -> None:
        if expert_name in self.losses:
            self.losses[expert_name].append(loss)

    def feedback_count(self, expert_name: str) -> int:
        return len(self.losses.get(expert_name, ()))

    def is_ready(self, expert_name: str) -> bool:
        return self.feedback_count(expert_name) >= SOFT_ANCHOR_MIN_FEEDBACK_COUNT

    def mean_loss(self, expert_name: str) -> float:
        expert_losses = self.losses.get(expert_name)
        if not expert_losses:
            return float("inf")
        return sum(expert_losses) / len(expert_losses)

    def ready_experts(self) -> list[str]:
        return [expert_name for expert_name in ACTIVE_EXPERTS if self.is_ready(expert_name)]

    def best_anchor_expert(self) -> str | None:
        ready_anchor_experts = [
            expert_name
            for expert_name in ANCHOR_EXPERTS
            if self.is_ready(expert_name)
        ]
        if not ready_anchor_experts:
            return None

        return min(
            ready_anchor_experts,
            key=lambda expert_name: (self.mean_loss(expert_name), expert_name),
        )

    def should_boost_anchor(self, anchor_expert: str) -> bool:
        ready_experts = self.ready_experts()
        if not ready_experts:
            return False

        anchor_loss = self.mean_loss(anchor_expert)
        best_loss = min(self.mean_loss(expert_name) for expert_name in ready_experts)
        return anchor_loss <= best_loss + SOFT_ANCHOR_MARGIN


def build_soft_expert_weights(
    expert_weights: dict[str, float],
    recent_loss_tracker: RecentExpertLossTracker,
) -> dict[str, float]:
    adjusted_weights = dict(expert_weights)
    anchor_expert = recent_loss_tracker.best_anchor_expert()

    if anchor_expert is None or not recent_loss_tracker.should_boost_anchor(anchor_expert):
        return adjusted_weights

    adjusted_weights[anchor_expert] *= SOFT_ANCHOR_BOOST

    raw_ml_loss = recent_loss_tracker.mean_loss("RawML")
    anchor_loss = recent_loss_tracker.mean_loss(anchor_expert)
    if (
        recent_loss_tracker.is_ready("RawML")
        and raw_ml_loss <= anchor_loss + RAW_ML_COMPETITIVE_MARGIN
    ):
        adjusted_weights["RawML"] *= RAW_ML_COMPETITIVE_BOOST

    return adjusted_weights


def choose_soft_classic_anchored_eviction(
    expert_votes: dict[str, str],
    expert_weights: dict[str, float],
    recent_loss_tracker: RecentExpertLossTracker,
) -> str:
    adjusted_weights = build_soft_expert_weights(
        expert_weights=expert_weights,
        recent_loss_tracker=recent_loss_tracker,
    )
    return choose_weighted_eviction(
        expert_votes=expert_votes,
        expert_weights=adjusted_weights,
    )


def apply_observed_feedback_with_losses(
    pending_feedback: defaultdict[str, list[PendingExpertVote]],
    expert_weights: dict[str, float],
    observed_item: str,
    current_index: int,
    hedge_learning_rate: float,
) -> list[tuple[str, float]]:
    observed_votes = pending_feedback.pop(observed_item, [])
    observed_losses: list[tuple[str, float]] = []

    for pending_vote in observed_votes:
        feedback_delay = current_index - pending_vote.decision_index
        expert_loss = 1.0 / (1.0 + float(feedback_delay))
        expert_weights[pending_vote.expert_name] *= math.exp(
            -hedge_learning_rate * expert_loss
        )
        observed_losses.append((pending_vote.expert_name, expert_loss))

    if observed_votes:
        normalize_expert_weights(expert_weights)

    return observed_losses


def create_initial_expert_weights() -> dict[str, float]:
    return {expert_name: 1.0 for expert_name in ACTIVE_EXPERTS}


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
    recent_loss_tracker = RecentExpertLossTracker.create(RECENT_LOSS_WINDOW_SIZE)
    pending_feedback: defaultdict[str, list[PendingExpertVote]] = defaultdict(list)
    cache_items: set[str] = set()
    marked_items: set[str] = set()
    cache_misses = 0
    trace_length = len(request_trace)

    for current_index, request_item in enumerate(request_trace):
        observed_losses = apply_observed_feedback_with_losses(
            pending_feedback=pending_feedback,
            expert_weights=expert_weights,
            observed_item=request_item,
            current_index=current_index,
            hedge_learning_rate=hedge_learning_rate,
        )
        for expert_name, expert_loss in observed_losses:
            recent_loss_tracker.add_loss(expert_name, expert_loss)

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
                evicted_item = choose_soft_classic_anchored_eviction(
                    expert_votes=expert_votes,
                    expert_weights=expert_weights,
                    recent_loss_tracker=recent_loss_tracker,
                )
                store_pending_feedback(
                    expert_votes=expert_votes,
                    pending_feedback=pending_feedback,
                    current_index=current_index,
                )
                cache_items.remove(evicted_item)
                marked_items.discard(evicted_item)
                feature_state.cache_insert_times.pop(evicted_item, None)
                feature_state.cache_access_counts.pop(evicted_item, None)

            cache_items.add(request_item)
            feature_state.cache_insert_times[request_item] = current_index
            feature_state.cache_access_counts[request_item] = 0

        marked_items.add(request_item)
        feature_state.update_after_request(
            request_item=request_item,
            current_index=current_index,
        )

    return CacheRunResult(
        algorithm_name=f"HedgeFullDelayedSoftClassicAnchor(eta={hedge_learning_rate})",
        cache_misses=cache_misses,
        total_requests=trace_length,
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
