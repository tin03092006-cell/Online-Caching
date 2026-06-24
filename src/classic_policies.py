from __future__ import annotations

from collections.abc import Callable

from .data import OnlineFeatureState
from .model import CacheRunResult, choose_lfu_eviction, choose_lru_eviction

EvictionFn = Callable[[set[str], OnlineFeatureState], str]


def run_single_policy_cache(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    algorithm_name: str,
    eviction_fn: EvictionFn,
) -> CacheRunResult:
    """Run a deterministic standalone cache policy on one request trace."""
    if cache_size <= 0:
        raise ValueError("cache_size must be positive")

    feature_state = OnlineFeatureState.create(recent_window_size)
    cache_items: set[str] = set()
    cache_misses = 0

    for current_index, request_item in enumerate(request_trace):
        if request_item not in cache_items:
            cache_misses += 1

            if len(cache_items) >= cache_size:
                evicted_item = eviction_fn(
                    cache_items=cache_items,
                    feature_state=feature_state,
                )
                cache_items.remove(evicted_item)
                feature_state.cache_insert_times.pop(evicted_item, None)
                feature_state.cache_access_counts.pop(evicted_item, None)

            cache_items.add(request_item)
            feature_state.cache_insert_times[request_item] = current_index
            feature_state.cache_access_counts[request_item] = 0

        feature_state.update_after_request(
            request_item=request_item,
            current_index=current_index,
        )

    return CacheRunResult(
        algorithm_name=algorithm_name,
        cache_misses=cache_misses,
        total_requests=len(request_trace),
    )


def run_lru_cache(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
) -> CacheRunResult:
    return run_single_policy_cache(
        request_trace=request_trace,
        cache_size=cache_size,
        recent_window_size=recent_window_size,
        algorithm_name="LRU",
        eviction_fn=choose_lru_eviction,
    )


def run_lfu_cache(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
) -> CacheRunResult:
    return run_single_policy_cache(
        request_trace=request_trace,
        cache_size=cache_size,
        recent_window_size=recent_window_size,
        algorithm_name="LFU",
        eviction_fn=choose_lfu_eviction,
    )
