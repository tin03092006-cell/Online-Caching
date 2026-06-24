from __future__ import annotations

import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import benchmark_chledowski as base
from src.raw_trace_processing import write_trace_manifest

INTEGRATED_CODE_PATHS = [
    "src/train_all_policies.py",
    "src/classic_policies.py",
    "src/all_expert_soft.py",
    "src/raw_trace_processing.py",
    "scripts/benchmark_chledowski_all_policies.py",
]


def get_integrated_code_hashes() -> dict[str, str]:
    """Hash all files that can affect the integrated benchmark output."""
    hashes = base.get_code_hashes()
    for relative_path in INTEGRATED_CODE_PATHS:
        path = base.PROJECT_ROOT / relative_path
        if path.exists():
            hashes[relative_path] = base.hash_file(path)
    return hashes


def algorithm_rank(algorithm_name: str) -> int:
    if algorithm_name == "Belady/OPT":
        return 0
    if algorithm_name == "LRU":
        return 1
    if algorithm_name == "LFU":
        return 2
    if algorithm_name == "MARK":
        return 3
    if algorithm_name.startswith("HedgeFullDelayed"):
        return 4
    return 99


def prepared_trace_paths(run_dir: Path) -> list[Path]:
    official_paths = [
        run_dir / "train_trace.txt",
        run_dir / "validation_trace.txt",
        run_dir / "test_trace.txt",
    ]
    if all(path.exists() for path in official_paths):
        return official_paths
    raw_path = run_dir / "trace.txt"
    return [raw_path] if raw_path.exists() else []


def validate_prepared_traces_for_result(result: dict) -> dict:
    if not result.get("success"):
        return result

    run_dir = base.BENCHMARK_RUNS_DIR / result["dataset"]
    trace_paths = prepared_trace_paths(run_dir)
    if not trace_paths:
        result["success"] = False
        result["return_code"] = -1
        result["error_message"] = "No prepared trace file found after dataset processing."
        base.write_run_status_file(run_dir / "run_status.txt", result)
        return result

    manifest_path = run_dir / "trace_manifest.json"
    try:
        stats = write_trace_manifest(trace_paths, manifest_path)
        result["trace_manifest"] = str(manifest_path)
        result["trace_manifest_num_files"] = len(stats)
        base.write_run_status_file(run_dir / "run_status.txt", result)
    except Exception as exc:
        result["success"] = False
        result["return_code"] = -1
        result["error_message"] = f"Prepared trace validation failed: {exc}"
        base.write_run_status_file(run_dir / "run_status.txt", result)
    return result


def process_dataset_with_trace_validation(
    dataset: str,
    args,
    commit_hash: str,
    code_hashes: dict[str, str],
    project_commit: str,
    base_config: dict,
) -> dict:
    result = base.process_dataset(
        dataset,
        args,
        commit_hash,
        code_hashes,
        project_commit,
        base_config,
    )
    return validate_prepared_traces_for_result(result)


def build_summary_all_policies(
    results: list[dict],
    datasets: list[str],
    base_config: dict,
) -> list[dict]:
    summary_results = []
    for result in results:
        if not result["success"]:
            continue
        benchmark_csv = base.BENCHMARK_RUNS_DIR / result["dataset"] / "benchmark_results.csv"
        if not benchmark_csv.exists():
            continue
        with benchmark_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["dataset"] = result["dataset"]
                row["split_mode"] = result["split_mode"]
                row["seed"] = base_config.get("seed", 42)
                row["selected_cache_size"] = result["trace_report_info"]["selected_cache_size"]
                summary_results.append(row)

    summary_results.sort(
        key=lambda row: (
            datasets.index(row["dataset"]) if row["dataset"] in datasets else 999,
            algorithm_rank(str(row["algorithm"])),
            str(row["algorithm"]),
        )
    )
    return summary_results


def write_run_report_all_policies(
    args,
    commit_hash: str,
    project_commit: str,
    project_dirty: bool,
    trace_reports: list[dict],
    summary_results: list[dict],
    results: list[dict],
    datasets: list[str],
) -> None:
    with base.RUN_REPORT_MD.open("w", encoding="utf-8") as f:
        f.write("# Chledowski Dataset Benchmark Report\n\n")
        f.write("## 1. Run Metadata\n")
        f.write(f"- project_commit: {project_commit}\n")
        f.write(f"- project_dirty: {project_dirty}\n")
        f.write(f"- dataset_ref_requested: {args.dataset_ref or 'unpinned'}\n")
        f.write(f"- dataset_commit_used: {commit_hash}\n")
        f.write(f"- jobs: {args.jobs}\n")
        f.write("- integrated_online_algorithms: Belady/OPT, LRU, LFU, MARK, HedgeFullDelayedAllExpertSoft\n")
        f.write("- prepared_trace_manifest: trace_manifest.json is written inside each successful dataset run directory\n\n")

        f.write("## 2. Dataset Preparation Summary\n")
        for report in trace_reports:
            f.write(f"### {report['requested_dataset']}\n")
            f.write(f"- split_mode actual per dataset: {report['split_mode']}\n")
            f.write(f"- source_files: {report['source_files']}\n")
            f.write(f"- warning: {report['warning']}\n\n")

        f.write("## 3. Config Summary\n")
        f.write(
            f"- cache_size rule: {args.cache_mode} "
            f"(ratio: {args.cache_ratio}, fixed: {args.fixed_cache_size})\n"
        )
        f.write("- standalone baselines are computed inside the main src.train run.\n")
        f.write("- dataset-level parallelism is controlled by --jobs; each worker limits BLAS threads to 1.\n\n")

        f.write("## 4. Benchmark Results\n")
        f.write("Standalone baselines: Belady/OPT, LRU, LFU, MARK\n")
        f.write("Proposed algorithm: HedgeFullDelayedAllExpertSoft\n")
        f.write("Internal experts: LRU, LFU, MARK, RawML\n\n")
        for row in summary_results:
            f.write(
                f"- Dataset: {row['dataset']} | Algorithm: {row['algorithm']} | "
                f"Misses: {row['cache_misses']} | Miss Ratio: {row['miss_ratio']} | "
                f"Improvement vs MARK: {row['improvement_vs_mark_percent']}% | "
                f"Eta: {row.get('selected_hedge_learning_rate', '')} | "
                f"MAE: {row.get('validation_mae', '')}\n"
            )
        f.write("\n")

        f.write("## 5. HedgeFullDelayed vs MARK\n")
        base.write_mark_comparison(summary_results, datasets, f)
        f.write("\n")

        f.write("## 6. Failed Datasets\n")
        failed = [result["dataset"] for result in results if not result["success"]]
        f.write(f"- Failed datasets: {', '.join(failed) if failed else 'None'}\n\n")

        f.write("## 7. Final Conclusion\n")
        success_count = sum(1 for result in results if result["success"])
        f.write(f"- Number of successful datasets: {success_count}\n")
        f.write(f"- Number of failed datasets: {len(failed)}\n")
        if success_count < len(datasets):
            f.write(f"- Status: WARNING: fewer than {len(datasets)} datasets completed successfully.\n")
        else:
            f.write(f"- Status: SUCCESS: benchmark completed for {success_count} datasets.\n")


def main() -> None:
    args = base.parse_args()
    base.verify_git()
    commit_hash = base.manage_repo(args.dataset_ref)
    code_hashes = get_integrated_code_hashes()
    project_commit = base.get_project_commit()
    project_dirty = base.get_project_dirty()

    base_config_path = base.resolve_project_path(args.base_config)
    with base_config_path.open("r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)

    datasets = (
        base.PRIMARY_DATASETS
        if args.datasets == "all"
        else [dataset.strip() for dataset in args.datasets.split(",") if dataset.strip()]
    )
    max_workers = (os.cpu_count() or 1) if args.jobs == "auto" else int(args.jobs)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {
            executor.submit(
                process_dataset_with_trace_validation,
                dataset,
                args,
                commit_hash,
                code_hashes,
                project_commit,
                base_config,
            ): dataset
            for dataset in datasets
        }
        for future in as_completed(future_to_dataset):
            dataset = future_to_dataset[future]
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"[FAIL] {dataset} Unhandled worker exception: {exc}")
                trace_info = base.make_trace_report_info(
                    dataset,
                    False,
                    args.split_mode,
                    [],
                    warning=f"Unhandled worker exception: {exc}",
                )
                results.append(
                    {
                        "dataset": dataset,
                        "success": False,
                        "return_code": -1,
                        "runtime_seconds": 0.0,
                        "config_path": "",
                        "metadata_path": "",
                        "stdout_log": "",
                        "stderr_log": "",
                        "error_message": f"Unhandled worker exception: {exc}",
                        "skipped_due_to_cache": False,
                        "split_mode": args.split_mode,
                        "discovery_records": [],
                        "trace_report_info": trace_info,
                    }
                )

    results.sort(key=lambda item: datasets.index(item["dataset"]) if item["dataset"] in datasets else 999)
    trace_reports = [result["trace_report_info"] for result in results if result.get("trace_report_info")]
    base.write_trace_report(trace_reports)
    summary_results = build_summary_all_policies(results, datasets, base_config)
    base.write_summary(summary_results)
    base.write_run_status_summary(results)
    write_run_report_all_policies(
        args,
        commit_hash,
        project_commit,
        project_dirty,
        trace_reports,
        summary_results,
        results,
        datasets,
    )


if __name__ == "__main__":
    main()
