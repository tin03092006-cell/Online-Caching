from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from .belady_teacher_label import (
    BELADY_LABEL_STRATEGY,
    build_belady_teacher_training_frame,
    describe_belady_teacher_frame,
)
from .data import TARGET_COLUMN, TraceSplits, load_config, load_request_trace, save_processed_frame, split_trace
from .model import CacheRunResult, count_belady_misses, run_mark_cache
from .rawml_belady_model import BeladyTeacherRawMLPredictor
from .all_expert_soft import run_hedge_full_cache, select_best_hedge_learning_rate


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train RawML on Belady/OPT next-distance labels and benchmark Hedge fallback."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/belady_teacher.yaml"),
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


def build_optional_validation_frame(
    validation_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    max_training_rows: int,
) -> pd.DataFrame | None:
    try:
        return build_belady_teacher_training_frame(
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
                "rawml_label_strategy": BELADY_LABEL_STRATEGY,
            }
        )
    return pd.DataFrame(result_rows)


def run_pipeline(config: dict[str, Any], project_root: Path) -> None:
    seed = int(config["seed"])
    set_seed(seed)

    cache_size = int(config["cache"]["cache_size"])
    if cache_size <= 0:
        raise ValueError("cache.cache_size must be a positive integer.")

    if str(config["hedge"]["feedback_mode"]) != "delayed":
        raise ValueError("hedge.feedback_mode must be 'delayed'.")

    recent_window_size = int(config["data"]["recent_window_size"])
    max_training_rows = int(config["data"]["max_training_rows"])
    processed_dir = resolve_project_path(project_root, config["paths"]["processed_dir"])

    trace_splits = load_trace_splits_from_config(config, project_root)

    training_frame = build_belady_teacher_training_frame(
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

    save_processed_frame(training_frame, processed_dir / "train_features_belady_teacher.csv")
    if validation_frame is not None:
        save_processed_frame(
            validation_frame,
            processed_dir / "validation_features_belady_teacher.csv",
        )

    predictor = BeladyTeacherRawMLPredictor(model_config=config["model"], seed=seed)
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
    save_processed_frame(results_frame, processed_dir / "benchmark_results_belady_teacher.csv")

    training_meta = {
        "selected_hedge_learning_rate": selected_hedge_learning_rate,
        "validation_mae": validation_mae,
        "rawml_label_strategy": BELADY_LABEL_STRATEGY,
        "training_frame": describe_belady_teacher_frame(training_frame),
        "feature_importance": predictor.feature_importance_dict(),
    }
    with open(
        processed_dir / "training_metadata_belady_teacher.json",
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(training_meta, metadata_file, indent=2)

    print("\nRawML label strategy:")
    print(BELADY_LABEL_STRATEGY)
    print("\nSelected Hedge learning rate:")
    print(selected_hedge_learning_rate)
    if validation_mae is not None:
        print("\nRawML validation MAE against D_t^+(x):")
        print(round(validation_mae, 6))
    print("\nBenchmark results:")
    print(results_frame.to_string(index=False))


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config = load_config(resolve_project_path(project_root, str(args.config)))
    run_pipeline(config=config, project_root=project_root)


if __name__ == "__main__":
    main()
