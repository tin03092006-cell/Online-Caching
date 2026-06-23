from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

# This script is intended to be placed in scripts/
# and run from the project root:
#   python scripts/quick_eval_lru_lfu_from_processed.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import OnlineFeatureState, load_request_trace, split_trace
from src.model import choose_lfu_eviction, choose_lru_eviction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Quickly evaluate standalone LRU/LFU on already prepared "
            "data/processed/benchmark_runs traces, then merge rows into a new summary CSV."
        )
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
        help="Path to data/processed.",
    )
    parser.add_argument(
        "--input-summary",
        type=Path,
        default=None,
        help="Existing summary_all_datasets.csv. Defaults to processed-dir/summary_all_datasets.csv.",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=None,
        help=(
            "Output CSV. Defaults to processed-dir/summary_all_datasets_with_lru_lfu.csv. "
            "This script does not overwrite the original summary unless you pass that path explicitly."
        ),
    )
    parser.add_argument(
        "--datasets",
        type=str,
        default="all",
        help="Comma-separated datasets, or all.",
    )
    return parser.parse_args()


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_run_config(run_dir: Path) -> dict:
    config_path = run_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing run config: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_same_test_trace_as_train_pipeline(run_dir: Path, config: dict) -> list[str]:
    paths = config["paths"]

    # Official split mode: src.train reads test_trace directly.
    if "test_trace" in paths:
        test_trace_path = resolve_project_path(paths["test_trace"])
        return load_request_trace(test_trace_path)

    # Ratio split mode: src.train reads raw_trace then split_trace().
    raw_trace_path = resolve_project_path(paths["raw_trace"])
    raw_trace = load_request_trace(raw_trace_path)
    splits = split_trace(
        request_trace=raw_trace,
        train_ratio=float(config["data"]["train_ratio"]),
        validation_ratio=float(config["data"]["validation_ratio"]),
    )
    return splits.test


def run_single_policy_cache(
    request_trace: list[str],
    cache_size: int,
    recent_window_size: int,
    algorithm_name: str,
    eviction_fn: Callable,
) -> dict[str, int | float | str]:
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

    total_requests = len(request_trace)
    return {
        "algorithm": algorithm_name,
        "cache_misses": cache_misses,
        "total_requests": total_requests,
        "miss_ratio": cache_misses / total_requests,
    }


def get_reference_values(summary_df: pd.DataFrame, dataset: str) -> dict[str, float | int | str]:
    dataset_rows = summary_df[summary_df["dataset"] == dataset]
    if dataset_rows.empty:
        raise ValueError(f"Dataset {dataset} is missing from summary CSV.")

    opt_rows = dataset_rows[dataset_rows["algorithm"] == "Belady/OPT"]
    mark_rows = dataset_rows[dataset_rows["algorithm"] == "MARK"]
    hedge_rows = dataset_rows[dataset_rows["algorithm"].astype(str).str.startswith("HedgeFullDelayed")]

    if opt_rows.empty or mark_rows.empty:
        raise ValueError(f"Dataset {dataset} must have Belady/OPT and MARK rows.")

    opt = opt_rows.iloc[0]
    mark = mark_rows.iloc[0]
    hedge = hedge_rows.iloc[0] if not hedge_rows.empty else dataset_rows.iloc[0]

    return {
        "belady_misses": int(opt["cache_misses"]),
        "mark_misses": int(mark["cache_misses"]),
        "selected_cache_size": int(dataset_rows["selected_cache_size"].iloc[0]),
        "split_mode": str(dataset_rows["split_mode"].iloc[0]),
        "seed": int(dataset_rows["seed"].iloc[0]),
        "selected_hedge_learning_rate": hedge.get("selected_hedge_learning_rate", ""),
        "validation_mae": hedge.get("validation_mae", ""),
    }


def enrich_row(
    base_row: dict[str, int | float | str],
    dataset: str,
    refs: dict[str, float | int | str],
) -> dict[str, int | float | str]:
    belady_misses = int(refs["belady_misses"])
    mark_misses = int(refs["mark_misses"])
    cache_misses = int(base_row["cache_misses"])

    return {
        "dataset": dataset,
        "algorithm": base_row["algorithm"],
        "cache_misses": cache_misses,
        "total_requests": int(base_row["total_requests"]),
        "miss_ratio": float(base_row["miss_ratio"]),
        "empirical_competitive_ratio": cache_misses / max(belady_misses, 1),
        "improvement_vs_mark_percent": ((mark_misses - cache_misses) / max(mark_misses, 1)) * 100.0,
        "selected_cache_size": refs["selected_cache_size"],
        "split_mode": refs["split_mode"],
        "seed": refs["seed"],
        "selected_hedge_learning_rate": refs["selected_hedge_learning_rate"],
        "validation_mae": refs["validation_mae"],
    }


def main() -> None:
    args = parse_args()

    processed_dir = args.processed_dir
    benchmark_runs_dir = processed_dir / "benchmark_runs"
    input_summary = args.input_summary or processed_dir / "summary_all_datasets.csv"
    output_summary = args.output_summary or processed_dir / "summary_all_datasets_with_lru_lfu.csv"

    if not input_summary.exists():
        raise FileNotFoundError(f"Missing input summary: {input_summary}")

    summary_df = pd.read_csv(input_summary)

    if args.datasets == "all":
        datasets = list(dict.fromkeys(summary_df["dataset"].astype(str).tolist()))
    else:
        datasets = [x.strip() for x in args.datasets.split(",") if x.strip()]

    new_rows: list[dict[str, int | float | str]] = []

    for dataset in datasets:
        run_dir = benchmark_runs_dir / dataset
        if not run_dir.exists():
            raise FileNotFoundError(f"Missing benchmark run dir: {run_dir}")

        config = load_run_config(run_dir)
        test_trace = load_same_test_trace_as_train_pipeline(run_dir, config)
        cache_size = int(config["cache"]["cache_size"])
        recent_window_size = int(config["data"]["recent_window_size"])

        refs = get_reference_values(summary_df, dataset)

        lru = run_single_policy_cache(
            request_trace=test_trace,
            cache_size=cache_size,
            recent_window_size=recent_window_size,
            algorithm_name="LRU",
            eviction_fn=choose_lru_eviction,
        )
        lfu = run_single_policy_cache(
            request_trace=test_trace,
            cache_size=cache_size,
            recent_window_size=recent_window_size,
            algorithm_name="LFU",
            eviction_fn=choose_lfu_eviction,
        )

        new_rows.append(enrich_row(lru, dataset, refs))
        new_rows.append(enrich_row(lfu, dataset, refs))

        print(
            f"[DONE] {dataset}: "
            f"LRU misses={lru['cache_misses']} "
            f"LFU misses={lfu['cache_misses']} "
            f"total={len(test_trace)} cache={cache_size}"
        )

    # Avoid duplicates if the script is run multiple times.
    cleaned_summary = summary_df[
        ~summary_df["algorithm"].astype(str).isin(["LRU", "LFU"])
    ].copy()

    merged = pd.concat([cleaned_summary, pd.DataFrame(new_rows)], ignore_index=True)

    dataset_order = {dataset: i for i, dataset in enumerate(datasets)}
    algorithm_order = {
        "Belady/OPT": 0,
        "LRU": 1,
        "LFU": 2,
        "MARK": 3,
    }

    def algo_rank(name: str) -> int:
        if str(name).startswith("HedgeFullDelayed"):
            return 4
        return algorithm_order.get(str(name), 99)

    merged["_dataset_rank"] = merged["dataset"].map(lambda x: dataset_order.get(str(x), 999))
    merged["_algorithm_rank"] = merged["algorithm"].map(algo_rank)
    merged = merged.sort_values(["_dataset_rank", "_algorithm_rank", "algorithm"]).drop(
        columns=["_dataset_rank", "_algorithm_rank"]
    )

    output_summary.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_summary, index=False)
    print(f"\nSaved merged summary to: {output_summary}")


if __name__ == "__main__":
    main()
