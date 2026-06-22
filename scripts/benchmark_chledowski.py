import argparse
import copy
import csv
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import yaml

PRIMARY_DATASETS = [
    "astar",
    "bwaves",
    "cactusadm",
    "gems",
    "lbm",
    "leslie3d",
    "libq",
    "mcf",
    "omnetpp",
    "sphinx3",
    "xalanc",
    "bzip",
    "milc",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHLEDOWSKI_REPO = RAW_DIR / "chledowski_repo"
DATASETS_DIR = CHLEDOWSKI_REPO / "datasets"
BENCHMARK_RUNS_DIR = PROCESSED_DIR / "benchmark_runs"

FILE_DISCOVERY_LOG = PROCESSED_DIR / "chledowski_file_discovery.txt"
DATASET_REPO_COMMIT = PROCESSED_DIR / "chledowski_dataset_repo_commit.txt"
TRACE_REPORT = PROCESSED_DIR / "chledowski_trace_report.csv"
SUMMARY_CSV = PROCESSED_DIR / "summary_all_datasets.csv"
RUN_STATUS_CSV = PROCESSED_DIR / "run_status_all_datasets.csv"
RUN_REPORT_MD = PROCESSED_DIR / "RUN_REPORT.md"


@dataclass(frozen=True)
class DatasetFile:
    path: Path
    split: str
    format_detected: str
    item_column: int | None
    parsed_rows: int
    skipped_rows: int
    unique_items: int
    warning: str


@dataclass(frozen=True)
class TraceExtractionResult:
    output_path: Path
    parsed_rows: int
    skipped_rows: int
    unique_items: set[str]
    trace_hash: str


def parse_args():
    parser = argparse.ArgumentParser(description="Automated Benchmark Script")
    parser.add_argument("--datasets", type=str, default="all")
    parser.add_argument("--jobs", type=str, default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dataset-ref", type=str, default="")
    parser.add_argument("--base-config", type=str, default="configs/config.yaml")
    parser.add_argument("--split-mode", choices=["auto", "official", "ratio"], default="auto")
    parser.add_argument("--cache-mode", choices=["ratio", "fixed"], default="ratio")
    parser.add_argument("--cache-ratio", type=float, default=0.01)
    parser.add_argument("--min-cache-size", type=int, default=16)
    parser.add_argument("--max-cache-size", type=int, default=512)
    parser.add_argument("--fixed-cache-size", type=int, default=100)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    return parser.parse_args()


def verify_git() -> None:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Git is required.")
        sys.exit(1)


def get_project_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def get_project_dirty() -> bool:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return bool(status)
    except Exception:
        return True


def manage_repo(dataset_ref: str) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not CHLEDOWSKI_REPO.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/chledowski/Robust-Learning-Augmented-Caching-An-Experimental-Study-Datasets",
                str(CHLEDOWSKI_REPO),
            ],
            check=True,
        )
    else:
        subprocess.run(["git", "fetch", "--all"], cwd=str(CHLEDOWSKI_REPO), check=True)

    if dataset_ref:
        subprocess.run(["git", "checkout", dataset_ref], cwd=str(CHLEDOWSKI_REPO), check=True)
    else:
        subprocess.run(["git", "pull"], cwd=str(CHLEDOWSKI_REPO), check=False)

    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(CHLEDOWSKI_REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    DATASET_REPO_COMMIT.write_text(commit_hash, encoding="utf-8")
    return commit_hash


def hash_file(filepath: Path) -> str:
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_code_hashes() -> dict[str, str]:
    hashes = {}
    for relative_path in [
        "src/model.py",
        "src/train.py",
        "src/data.py",
        "src/classic_anchor.py",
        "scripts/benchmark_chledowski.py",
    ]:
        path = PROJECT_ROOT / relative_path
        if path.exists():
            hashes[relative_path] = hash_file(path)
    return hashes


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def parse_tokens(line: str, delimiter: str | None) -> list[str]:
    if delimiter is None:
        return [line.strip()]
    return [part.strip() for part in line.split(delimiter) if part.strip()]


def infer_format_and_parse(file_path: Path) -> DatasetFile:
    try:
        with file_path.open("r", encoding="utf-8") as f:
            sample_lines = [f.readline().strip() for _ in range(500)]
        sample_lines = [line for line in sample_lines if line]
    except Exception as exc:
        return DatasetFile(file_path, "other", "error", None, 0, 0, 0, str(exc))

    if not sample_lines:
        return DatasetFile(file_path, "other", "empty", None, 0, 0, 0, "empty file")

    first_line = sample_lines[0]
    delimiter = "," if "," in first_line else ("\t" if "\t" in first_line else (" " if " " in first_line else None))
    tokenized_sample = [parse_tokens(line, delimiter) for line in sample_lines]
    token_counts = [len(tokens) for tokens in tokenized_sample]

    format_detected = "unknown"
    item_column = None
    warning = ""

    if all(count == 1 for count in token_counts):
        format_detected = "single_token_per_line"
        item_column = 0
    elif tokenized_sample and any(not token.startswith(("0x", "0X")) and not token[:1].isdigit() for token in tokenized_sample[0]):
        format_detected = "table_with_header"
        header = tokenized_sample[0]
        priorities = [
            "item_id",
            "object_id",
            "key",
            "page_id",
            "block_id",
            "address",
            "addr",
            "memory_address",
            "request",
            "request_key",
            "id",
        ]
        for priority in priorities:
            for index, column_name in enumerate(header):
                if priority == column_name.lower():
                    item_column = index
                    break
            if item_column is not None:
                break
        if item_column is None:
            warning = "Cannot infer request item column."
    elif all(count == 2 for count in token_counts):
        first_column = [tokens[0] for tokens in tokenized_sample]
        second_column = [tokens[1] for tokens in tokenized_sample]
        try:
            first_values = [float(x) if not x.startswith(("0x", "0X")) else int(x, 16) for x in first_column]
            monotonic = all(first_values[i] <= first_values[i + 1] for i in range(len(first_values) - 1))
        except ValueError:
            monotonic = False

        format_detected = "two_columns_no_header"
        if monotonic or len(set(second_column)) > len(set(first_column)) * 2:
            item_column = 1
        elif len(set(first_column)) > len(set(second_column)) * 2:
            item_column = 0
        else:
            item_column = 1
    else:
        warning = "Cannot infer request item column."

    parsed_rows = 0
    skipped_rows = 0
    unique_items = set()
    if item_column is not None:
        with file_path.open("r", encoding="utf-8") as f:
            skip_header = format_detected == "table_with_header"
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if skip_header:
                    skip_header = False
                    continue
                tokens = parse_tokens(line, delimiter)
                if len(tokens) > item_column:
                    unique_items.add(tokens[item_column])
                    parsed_rows += 1
                else:
                    skipped_rows += 1

    name_lower = file_path.name.lower()
    split = "other"
    if "train" in name_lower:
        split = "train"
    elif "valid" in name_lower or "val" in name_lower:
        split = "validation"
    elif "test" in name_lower:
        split = "test"

    if parsed_rows == 0 and not warning:
        warning = "No rows parsed."

    return DatasetFile(
        path=file_path,
        split=split,
        format_detected=format_detected,
        item_column=item_column,
        parsed_rows=parsed_rows,
        skipped_rows=skipped_rows,
        unique_items=len(unique_items),
        warning=warning,
    )


def discover_dataset_files(dataset_name: str) -> list[DatasetFile]:
    if not DATASETS_DIR.exists():
        return []

    rejected_words = ["readme", "summary", "stats", "stat", "metadata", "report", "result", "log", "png", "jpg", "pdf", "json", "yaml", "yml"]
    blocked_exts = {".md", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".pdf"}
    allowed_exts = {".txt", ".csv", ".tsv", ".trace", ".dat"}
    discovered = []

    for path in DATASETS_DIR.rglob("*"):
        if not path.is_file() or dataset_name not in path.name:
            continue
        lower_name = path.name.lower()
        ext = path.suffix.lower()
        if any(word in lower_name for word in rejected_words):
            continue
        if ext in blocked_exts:
            continue
        if ext and ext not in allowed_exts:
            continue
        parsed_file = infer_format_and_parse(path)
        if parsed_file.parsed_rows > 0 and parsed_file.item_column is not None:
            discovered.append(parsed_file)

    discovered.sort(key=lambda item: item.path)
    return discovered


def extract_trace(dataset_files: list[DatasetFile], output_path: Path) -> TraceExtractionResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_rows = 0
    skipped_rows = 0
    unique_items = set()

    with output_path.open("w", encoding="utf-8") as out_f:
        for dataset_file in dataset_files:
            first_line = ""
            with dataset_file.path.open("r", encoding="utf-8") as in_f:
                for line in in_f:
                    if line.strip():
                        first_line = line.strip()
                        break
            delimiter = "," if "," in first_line else ("\t" if "\t" in first_line else (" " if " " in first_line else None))

            with dataset_file.path.open("r", encoding="utf-8") as in_f:
                skip_header = dataset_file.format_detected == "table_with_header"
                for line in in_f:
                    line = line.strip()
                    if not line:
                        continue
                    if skip_header:
                        skip_header = False
                        continue
                    tokens = parse_tokens(line, delimiter)
                    if dataset_file.item_column is not None and len(tokens) > dataset_file.item_column:
                        item = tokens[dataset_file.item_column]
                        out_f.write(f"{item}\n")
                        unique_items.add(item)
                        parsed_rows += 1
                    else:
                        skipped_rows += 1

    return TraceExtractionResult(output_path, parsed_rows, skipped_rows, unique_items, hash_file(output_path))


def make_trace_report_info(
    dataset: str,
    success: bool,
    split_mode: str,
    source_files: list[DatasetFile],
    train_reqs: int = 0,
    valid_reqs: int = 0,
    test_reqs: int = 0,
    train_uniq: int = 0,
    valid_uniq: int = 0,
    test_uniq: int = 0,
    cache_mode: str = "ratio",
    cache_ratio: float = 0.01,
    min_cache: int = 16,
    max_cache: int = 512,
    selected_cache: int = 0,
    warning: str = "",
) -> dict:
    return {
        "requested_dataset": dataset,
        "actual_dataset": dataset,
        "success": success,
        "split_mode": split_mode,
        "source_files": "|".join(file.path.name for file in source_files),
        "rejected_files": "",
        "number_of_requests_train": train_reqs,
        "number_of_requests_validation": valid_reqs,
        "number_of_requests_test": test_reqs,
        "number_of_unique_items_train": train_uniq,
        "number_of_unique_items_validation": valid_uniq,
        "number_of_unique_items_test": test_uniq,
        "cache_mode": cache_mode,
        "cache_ratio": cache_ratio,
        "min_cache_size": min_cache,
        "max_cache_size": max_cache,
        "selected_cache_size": selected_cache,
        "format_detected_per_file": "|".join(f"{file.path.name}:{file.format_detected}" for file in source_files),
        "item_column_per_file": "|".join(f"{file.path.name}:{file.item_column}" for file in source_files),
        "parsed_rows_per_file": "|".join(f"{file.path.name}:{file.parsed_rows}" for file in source_files),
        "skipped_rows_per_file": "|".join(f"{file.path.name}:{file.skipped_rows}" for file in source_files),
        "unique_items_per_file": "|".join(f"{file.path.name}:{file.unique_items}" for file in source_files),
        "warning": warning,
    }


def previous_run_succeeded(run_status_file: Path) -> bool:
    if not run_status_file.exists():
        return False
    text = run_status_file.read_text(encoding="utf-8")
    return "success: True" in text and "return_code: 0" in text


def write_run_status_file(run_status_file: Path, run_status: dict) -> None:
    run_status_file.parent.mkdir(parents=True, exist_ok=True)
    with run_status_file.open("w", encoding="utf-8") as f:
        for key, value in run_status.items():
            if key not in {"trace_report_info", "discovery_records"}:
                f.write(f"{key}: {value}\n")


def process_dataset(dataset: str, args, commit_hash: str, code_hashes: dict[str, str], project_commit: str, base_config: dict) -> dict:
    run_dir = BENCHMARK_RUNS_DIR / dataset
    prepared_dir = run_dir / "_prepared"
    run_status_file = run_dir / "run_status.txt"
    metadata_file = run_dir / "metadata.json"
    stdout_file = run_dir / "stdout.log"
    stderr_file = run_dir / "stderr.log"

    source_files = discover_dataset_files(dataset)
    if not source_files:
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_info = make_trace_report_info(dataset, False, args.split_mode, [], warning="No valid trace files found")
        run_status = {
            "dataset": dataset,
            "success": False,
            "return_code": -1,
            "runtime_seconds": 0.0,
            "config_path": "",
            "metadata_path": str(metadata_file),
            "stdout_log": str(stdout_file),
            "stderr_log": str(stderr_file),
            "error_message": "No valid trace files found",
            "skipped_due_to_cache": False,
            "split_mode": args.split_mode,
            "discovery_records": [],
            "trace_report_info": trace_info,
        }
        write_run_status_file(run_status_file, run_status)
        return run_status

    train_files = [file for file in source_files if file.split == "train"]
    validation_files = [file for file in source_files if file.split == "validation"]
    test_files = [file for file in source_files if file.split == "test"]
    other_files = [file for file in source_files if file.split == "other"]

    has_official_split = bool(train_files and validation_files and test_files)
    actual_split_mode = args.split_mode
    if actual_split_mode == "auto":
        actual_split_mode = "official" if has_official_split else "ratio"

    if prepared_dir.exists():
        shutil.rmtree(prepared_dir)
    prepared_dir.mkdir(parents=True, exist_ok=False)

    if actual_split_mode == "official" and has_official_split:
        train_result = extract_trace(train_files, prepared_dir / "train_trace.txt")
        validation_result = extract_trace(validation_files, prepared_dir / "validation_trace.txt")
        test_result = extract_trace(test_files, prepared_dir / "test_trace.txt")
        total_unique_items = len(train_result.unique_items | validation_result.unique_items | test_result.unique_items)
        train_reqs, valid_reqs, test_reqs = train_result.parsed_rows, validation_result.parsed_rows, test_result.parsed_rows
        train_uniq, valid_uniq, test_uniq = len(train_result.unique_items), len(validation_result.unique_items), len(test_result.unique_items)
        trace_hashes = {
            "train": train_result.trace_hash,
            "validation": validation_result.trace_hash,
            "test": test_result.trace_hash,
        }
    else:
        actual_split_mode = "ratio"
        ordered_files = train_files + validation_files + test_files + other_files
        raw_result = extract_trace(ordered_files, prepared_dir / "trace.txt")
        total_unique_items = len(raw_result.unique_items)
        train_reqs = int(raw_result.parsed_rows * args.train_ratio)
        valid_reqs = int(raw_result.parsed_rows * args.validation_ratio)
        test_reqs = raw_result.parsed_rows - train_reqs - valid_reqs
        train_uniq = int(total_unique_items * args.train_ratio)
        valid_uniq = int(total_unique_items * args.validation_ratio)
        test_uniq = total_unique_items - train_uniq - valid_uniq
        trace_hashes = {"raw": raw_result.trace_hash}

    if args.cache_mode == "fixed":
        selected_cache_size = args.fixed_cache_size
    else:
        selected_cache_size = min(args.max_cache_size, max(args.min_cache_size, int(args.cache_ratio * total_unique_items)))
        if selected_cache_size >= total_unique_items and total_unique_items > 0:
            selected_cache_size = max(2, total_unique_items // 10)

    config_dict = copy.deepcopy(base_config)
    config_dict["paths"]["processed_dir"] = str(run_dir)
    config_dict["data"]["train_ratio"] = args.train_ratio
    config_dict["data"]["validation_ratio"] = args.validation_ratio
    config_dict["cache"]["cache_size"] = selected_cache_size
    config_dict["hedge"]["feedback_mode"] = "delayed"

    if actual_split_mode == "official" and has_official_split:
        config_dict["paths"]["train_trace"] = str(run_dir / "train_trace.txt")
        config_dict["paths"]["validation_trace"] = str(run_dir / "validation_trace.txt")
        config_dict["paths"]["test_trace"] = str(run_dir / "test_trace.txt")
    else:
        config_dict["paths"]["raw_trace"] = str(run_dir / "trace.txt")

    base_config_path = resolve_project_path(args.base_config)
    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()
    metadata = {
        "project_commit": project_commit,
        "project_dirty": get_project_dirty(),
        "dataset_commit": commit_hash,
        "dataset_ref_requested": args.dataset_ref or "unpinned",
        "code_hashes": code_hashes,
        "config_hash": config_hash,
        "base_config_path": str(base_config_path),
        "base_config_hash": hash_file(base_config_path),
        "dataset_source_file_hashes": {str(file.path): hash_file(file.path) for file in source_files},
        "trace_hashes": trace_hashes,
        "dataset": dataset,
        "split_mode": actual_split_mode,
        "cache_mode": args.cache_mode,
        "cache_ratio": args.cache_ratio,
        "min_cache_size": args.min_cache_size,
        "max_cache_size": args.max_cache_size,
        "fixed_cache_size": args.fixed_cache_size,
        "selected_cache_size": selected_cache_size,
        "seed": config_dict.get("seed", 42),
        "model": config_dict["model"],
        "hedge": config_dict["hedge"],
    }

    trace_report_info = make_trace_report_info(
        dataset=dataset,
        success=False,
        split_mode=actual_split_mode,
        source_files=source_files,
        train_reqs=train_reqs,
        valid_reqs=valid_reqs,
        test_reqs=test_reqs,
        train_uniq=train_uniq,
        valid_uniq=valid_uniq,
        test_uniq=test_uniq,
        cache_mode=args.cache_mode,
        cache_ratio=args.cache_ratio,
        min_cache=args.min_cache_size,
        max_cache=args.max_cache_size,
        selected_cache=selected_cache_size,
    )

    if not args.force and metadata_file.exists() and (run_dir / "benchmark_results.csv").exists():
        try:
            old_metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if old_metadata == metadata and previous_run_succeeded(run_status_file):
                trace_report_info["success"] = True
                print(f"[DONE] {dataset} (skipped_due_to_cache)")
                shutil.rmtree(prepared_dir)
                return {
                    "dataset": dataset,
                    "success": True,
                    "return_code": 0,
                    "runtime_seconds": 0.0,
                    "config_path": str(run_dir / "config.yaml"),
                    "metadata_path": str(metadata_file),
                    "stdout_log": str(stdout_file),
                    "stderr_log": str(stderr_file),
                    "error_message": "",
                    "skipped_due_to_cache": True,
                    "split_mode": actual_split_mode,
                    "discovery_records": [],
                    "trace_report_info": trace_report_info,
                }
        except Exception:
            pass

    run_dir.mkdir(parents=True, exist_ok=True)
    for item in run_dir.iterdir():
        if item == prepared_dir:
            continue
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

    for item in prepared_dir.iterdir():
        shutil.move(str(item), str(run_dir / item.name))
    shutil.rmtree(prepared_dir)

    with (run_dir / "config.yaml").open("w", encoding="utf-8") as config_file:
        yaml.safe_dump(config_dict, config_file)
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    env["VECLIB_MAXIMUM_THREADS"] = "1"
    env["PYTHONHASHSEED"] = str(config_dict.get("seed", 42))

    print(f"[START] {dataset}")
    start_time = datetime.datetime.now()
    error_message = ""

    with stdout_file.open("w", encoding="utf-8") as out_f, stderr_file.open("w", encoding="utf-8") as err_f:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.train", "--config", str(run_dir / "config.yaml")],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=out_f,
                stderr=err_f,
                timeout=args.timeout_seconds,
            )
            return_code = result.returncode
            success = return_code == 0
        except subprocess.TimeoutExpired:
            return_code = -1
            success = False
            error_message = "Subprocess timeout"
            err_f.write(error_message)
        except Exception as exc:
            return_code = -1
            success = False
            error_message = f"Subprocess exception: {exc}"
            err_f.write(error_message)

    runtime_seconds = (datetime.datetime.now() - start_time).total_seconds()
    trace_report_info["success"] = success
    if success:
        print(f"[DONE] {dataset} success=True runtime={runtime_seconds:.2f}s")
    else:
        print(f"[FAIL] {dataset} return_code={return_code}")
        if not error_message and stderr_file.exists():
            error_message = stderr_file.read_text(encoding="utf-8")[-2000:]

    run_status = {
        "dataset": dataset,
        "success": success,
        "return_code": return_code,
        "runtime_seconds": runtime_seconds,
        "config_path": str(run_dir / "config.yaml"),
        "metadata_path": str(metadata_file),
        "stdout_log": str(stdout_file),
        "stderr_log": str(stderr_file),
        "error_message": error_message,
        "skipped_due_to_cache": False,
        "split_mode": actual_split_mode,
        "discovery_records": [],
        "trace_report_info": trace_report_info,
    }
    write_run_status_file(run_status_file, run_status)
    return run_status


def write_trace_report(trace_reports: list[dict]) -> None:
    if not trace_reports:
        return
    with TRACE_REPORT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=trace_reports[0].keys())
        writer.writeheader()
        writer.writerows(trace_reports)


def build_summary(results: list[dict], datasets: list[str], base_config: dict) -> list[dict]:
    summary_results = []
    for result in results:
        if not result["success"]:
            continue
        benchmark_csv = BENCHMARK_RUNS_DIR / result["dataset"] / "benchmark_results.csv"
        if not benchmark_csv.exists():
            continue
        with benchmark_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["algorithm"] in ["Belady/OPT", "MARK"] or row["algorithm"].startswith("HedgeFullDelayed"):
                    row["dataset"] = result["dataset"]
                    row["split_mode"] = result["split_mode"]
                    row["seed"] = base_config.get("seed", 42)
                    row["selected_cache_size"] = result["trace_report_info"]["selected_cache_size"]
                    summary_results.append(row)

    summary_results.sort(key=lambda row: (datasets.index(row["dataset"]) if row["dataset"] in datasets else 999, row["algorithm"]))
    return summary_results


def write_summary(summary_results: list[dict]) -> None:
    fieldnames = [
        "dataset",
        "algorithm",
        "cache_misses",
        "total_requests",
        "miss_ratio",
        "empirical_competitive_ratio",
        "improvement_vs_mark_percent",
        "selected_cache_size",
        "split_mode",
        "seed",
        "selected_hedge_learning_rate",
        "validation_mae",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary_results)


def write_run_status_summary(results: list[dict]) -> None:
    fieldnames = [
        "dataset",
        "success",
        "return_code",
        "runtime_seconds",
        "config_path",
        "metadata_path",
        "stdout_log",
        "stderr_log",
        "error_message",
        "skipped_due_to_cache",
    ]
    with RUN_STATUS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def write_mark_comparison(summary_results: list[dict], datasets: list[str], output_file) -> None:
    dataset_set = {row["dataset"] for row in summary_results}
    for dataset in [item for item in datasets if item in dataset_set]:
        hedge_improvement = 0.0
        for row in summary_results:
            if row["dataset"] == dataset and row["algorithm"].startswith("HedgeFullDelayed"):
                hedge_improvement = float(row["improvement_vs_mark_percent"])
                break
        result_text = "lost to MARK" if hedge_improvement < 0 else ("beat MARK" if hedge_improvement > 0 else "tied MARK")
        output_file.write(f"- {dataset}: HedgeFullDelayed {result_text}\n")


def write_run_report(args, commit_hash: str, project_commit: str, project_dirty: bool, trace_reports: list[dict], summary_results: list[dict], results: list[dict], datasets: list[str]) -> None:
    with RUN_REPORT_MD.open("w", encoding="utf-8") as f:
        f.write("# Chledowski Dataset Benchmark Report\n\n")
        f.write("## 1. Run Metadata\n")
        f.write(f"- project_commit: {project_commit}\n")
        f.write(f"- project_dirty: {project_dirty}\n")
        f.write(f"- dataset_ref_requested: {args.dataset_ref or 'unpinned'}\n")
        f.write(f"- dataset_commit_used: {commit_hash}\n")
        f.write(f"- jobs: {args.jobs}\n\n")

        f.write("## 2. Dataset Preparation Summary\n")
        for report in trace_reports:
            f.write(f"### {report['requested_dataset']}\n")
            f.write(f"- split_mode actual per dataset: {report['split_mode']}\n")
            f.write(f"- source_files: {report['source_files']}\n")
            f.write(f"- warning: {report['warning']}\n\n")

        f.write("## 3. Config Summary\n")
        f.write(f"- cache_size rule: {args.cache_mode} (ratio: {args.cache_ratio}, fixed: {args.fixed_cache_size})\n\n")

        f.write("## 4. Benchmark Results\n")
        f.write("Standalone baselines: Belady/OPT, MARK\n")
        f.write("Proposed algorithm: HedgeFullDelayedClassicAnchor\n")
        f.write("Internal experts: LRU, LFU, MARK, RawML\n\n")
        for row in summary_results:
            f.write(
                f"- Dataset: {row['dataset']} | Algorithm: {row['algorithm']} | Misses: {row['cache_misses']} | "
                f"Miss Ratio: {row['miss_ratio']} | Improvement vs MARK: {row['improvement_vs_mark_percent']}% | "
                f"Eta: {row.get('selected_hedge_learning_rate', '')} | MAE: {row.get('validation_mae', '')}\n"
            )
        f.write("\n")

        f.write("## 5. HedgeFullDelayed vs MARK\n")
        write_mark_comparison(summary_results, datasets, f)
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
    args = parse_args()
    verify_git()
    commit_hash = manage_repo(args.dataset_ref)
    code_hashes = get_code_hashes()
    project_commit = get_project_commit()
    project_dirty = get_project_dirty()

    base_config_path = resolve_project_path(args.base_config)
    with base_config_path.open("r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)

    datasets = PRIMARY_DATASETS if args.datasets == "all" else [dataset.strip() for dataset in args.datasets.split(",") if dataset.strip()]
    max_workers = os.cpu_count() or 1 if args.jobs == "auto" else int(args.jobs)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {
            executor.submit(process_dataset, dataset, args, commit_hash, code_hashes, project_commit, base_config): dataset
            for dataset in datasets
        }
        for future in as_completed(future_to_dataset):
            dataset = future_to_dataset[future]
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"[FAIL] {dataset} Unhandled worker exception: {exc}")
                trace_info = make_trace_report_info(dataset, False, args.split_mode, [], warning=f"Unhandled worker exception: {exc}")
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
    write_trace_report(trace_reports)
    summary_results = build_summary(results, datasets, base_config)
    write_summary(summary_results)
    write_run_status_summary(results)
    write_run_report(args, commit_hash, project_commit, project_dirty, trace_reports, summary_results, results, datasets)


if __name__ == "__main__":
    main()
