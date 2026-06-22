from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from .data import (
    TARGET_COLUMN,
    TraceSplits,
    build_training_frame,
    load_config,
    load_request_trace,
    save_processed_frame,
    split_trace,
)
from .model import (
    CacheRunResult,
    RawMLPredictor,
    count_belady_misses,
    run_mark_cache,
)
from .soft_classic_anchor import (
    run_hedge_full_cache,
    select_best_hedge_learning_rate,
)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and benchmark Soft Classic-Anchored Hedge Full for online caching."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/config.yaml"),
        help="Path to the YAML config file.",
    )
    return parser.parse_args()


def resolve_project_path(project_root: Path, path_text: str) -> Path:
    candidate_path = Path(path_text)
    if candidate_path.is_absolute():
        return candidate_path
    return project_root / candidate_path


def load_trace_splits_from_config(config: dict[str, Any], project_root: Path) -> TraceSplits:
    paths = config["paths"]
    if "train_trace" in paths and "validation_trace" in paths and "test_trace" in paths:
        return TraceSplits(
            train=load_request_trace(resolve_project_path(project_root, paths["train_trace"])),
            validation=load_request_trace(resolve_project_path(project_root, paths["validation_trace"])),
            test=load_request_trace(resolve_project_path(project_root, paths["test_trace"])),
        )

    request_trace = load_request_trace(resolve_project_path(project_root, paths["raw_trace"]))
    return split_trace(
        request_trace=request_trace,
        train_ratio=float(config["data"]["train_ratio"]),
        validation_ratio=float(config["data"]["validation_ratio"]),
    )


def require_positive_cache_size(cache_size: int) -> None:
    if cache_size <= 0:
        raise ValueError("cache.cache_size must be a positive integer.")


def require_delayed_feedback_mode(feedback_mode: str) -> None:
    if feedback_mode != "delayed":
        raise ValueError("hedge.feedback_mode must be 'delayed'.")


def build_optional_validation_frame(
    validation_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    max_training_rows: int,
) -> pd.DataFrame | None:
    try:
        return build_training_frame(
            request_trace=validation_trace,
            cache_size=cache_size,
            recent_window_size=recent_window_size,
            max_training_rows=max_training_rows,
        )
    except ValueError:
        return None


def build_results_frame(
    cache_results: list[CacheRunResult],
    belady_misses: int,
    mark_misses: int,
    selected_hedge_learning_rate: float,
    validation_mae: float | None,
) -> pd.DataFrame:
    result_rows: list[dict[str, float | int | str]] = []

    for cache_result in cache_results:
        competitive_ratio = cache_result.cache_misses / max(belady_misses, 1)
        improvement_vs_mark = (
            (mark_misses - cache_result.cache_misses) / max(mark_misses, 1)
        ) * 100.0
        result_rows.append(
            {
                "algorithm": cache_result.algorithm_name,
                "cache_misses": cache_result.cache_misses,
                "total_requests": cache_result.total_requests,
                "miss_ratio": cache_result.miss_ratio,
                "empirical_competitive_ratio": competitive_ratio,
                "improvement_vs_mark_percent": improvement_vs_mark,
                "selected_hedge_learning_rate": selected_hedge_learning_rate,
                "validation_mae": validation_mae if validation_mae is not None else "",
            }
        )

    return pd.DataFrame(result_rows)


def print_summary(
    results_frame: pd.DataFrame,
    selected_hedge_learning_rate: float,
    validation_mae: float | None,
) -> None:
    print("\nSelected Hedge learning rate:")
    print(selected_hedge_learning_rate)

    if validation_mae is not None:
        print("\nRawML validation MAE:")
        print(round(validation_mae, 6))

    print("\nBenchmark results:")
    print(results_frame.to_string(index=False))


def run_pipeline(config: dict[str, Any], project_root: Path) -> None:
    seed = int(config["seed"])
    set_seed(seed)

    cache_size = int(config["cache"]["cache_size"])
    require_positive_cache_size(cache_size)
    require_delayed_feedback_mode(str(config["hedge"]["feedback_mode"]))

    recent_window_size = int(config["data"]["recent_window_size"])
    max_training_rows = int(config["data"]["max_training_rows"])
    processed_dir = resolve_project_path(project_root, config["paths"]["processed_dir"])

    trace_splits = load_trace_splits_from_config(config, project_root)

    training_frame = build_training_frame(
        request_trace=trace_splits.train,
        cache_size=cache_size,
        recent_window_size=recent_window_size,
        max_training_rows=max_training_rows,
    )
    validation_frame = build_optional_validation_frame(
        validation_trace=trace_splits.validation,
        cache_size=cache_size,
        recent_window_size=recent_window_size,
        max_training_rows=max_training_rows,
    )

    save_processed_frame(training_frame, processed_dir / "train_features.csv")
    if validation_frame is not None:
        save_processed_frame(validation_frame, processed_dir / "validation_features.csv")

    predictor = RawMLPredictor(model_config=config["model"], seed=seed)
    predictor.fit(training_frame)

    validation_mae = None
    if validation_frame is not None and TARGET_COLUMN in validation_frame.columns:
        validation_mae = predictor.evaluate_mae(validation_frame)

    candidate_learning_rates = [
        float(candidate_learning_rate)
        for candidate_learning_rate in config["hedge"]["candidate_learning_rates"]
    ]
    selected_hedge_learning_rate = select_best_hedge_learning_rate(
        validation_trace=trace_splits.validation,
        cache_size=cache_size,
        predictor=predictor,
        candidate_learning_rates=candidate_learning_rates,
        seed=seed,
        recent_window_size=recent_window_size,
    )

    belady_result = count_belady_misses(
        request_trace=trace_splits.test,
        cache_size=cache_size,
    )
    mark_result = run_mark_cache(
        request_trace=trace_splits.test,
        cache_size=cache_size,
        seed=seed,
        recent_window_size=recent_window_size,
    )
    hedge_result = run_hedge_full_cache(
        request_trace=trace_splits.test,
        cache_size=cache_size,
        predictor=predictor,
        hedge_learning_rate=selected_hedge_learning_rate,
        seed=seed,
        recent_window_size=recent_window_size,
    )

    results_frame = build_results_frame(
        cache_results=[belady_result, mark_result, hedge_result],
        belady_misses=belady_result.cache_misses,
        mark_misses=mark_result.cache_misses,
        selected_hedge_learning_rate=selected_hedge_learning_rate,
        validation_mae=validation_mae,
    )
    save_processed_frame(results_frame, processed_dir / "benchmark_results.csv")

    training_meta = {
        "selected_hedge_learning_rate": selected_hedge_learning_rate,
        "validation_mae": validation_mae,
    }
    with open(processed_dir / "training_metadata.json", "w", encoding="utf-8") as f:
        json.dump(training_meta, f, indent=2)

    print_summary(results_frame, selected_hedge_learning_rate, validation_mae)


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(resolve_project_path(project_root, str(args.config)))
    run_pipeline(config=config, project_root=project_root)


if __name__ == "__main__":
    main()
