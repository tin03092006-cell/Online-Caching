import argparse
import sys
import shutil
import subprocess
import csv
import yaml
import datetime
import traceback
import os
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

PRIMARY_DATASETS = [
    "astar", "bwaves", "cactusadm", "gems", "lbm", "leslie3d",
    "libq", "mcf", "omnetpp", "sphinx3", "xalanc", "bzip", "milc"
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
    split: str  # train, validation, test, other
    format_detected: str
    item_column: int | None
    parsed_rows: int
    skipped_rows: int
    unique_items: int
    warning: str

def parse_args():
    parser = argparse.ArgumentParser(description="Automated Benchmark Script")
    parser.add_argument("--datasets", type=str, default="all")
    parser.add_argument("--jobs", type=str, default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dataset-ref", type=str, default="")
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

def verify_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Git is required.")
        sys.exit(1)

def manage_repo(dataset_ref):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if not CHLEDOWSKI_REPO.exists():
        subprocess.run(["git", "clone", "https://github.com/chledowski/Robust-Learning-Augmented-Caching-An-Experimental-Study-Datasets", str(CHLEDOWSKI_REPO)], check=True)
    else:
        subprocess.run(["git", "fetch", "--all"], cwd=str(CHLEDOWSKI_REPO), check=True)

    if dataset_ref:
        subprocess.run(["git", "checkout", dataset_ref], cwd=str(CHLEDOWSKI_REPO), check=True)
    else:
        # Default behavior: try to stay on main/master and pull if no ref requested
        subprocess.run(["git", "pull"], cwd=str(CHLEDOWSKI_REPO), check=False)

    commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CHLEDOWSKI_REPO), capture_output=True, text=True, check=True).stdout.strip()
    DATASET_REPO_COMMIT.write_text(commit_hash)
    return commit_hash

def hash_file(filepath):
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_code_hash():
    hasher = hashlib.sha256()
    for f in ["src/model.py", "src/train.py", "src/data.py", "scripts/benchmark_chledowski.py"]:
        p = PROJECT_ROOT / f
        if p.exists():
            hasher.update(p.read_bytes())
    return hasher.hexdigest()

def infer_format_and_parse(file_path: Path):
    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = [f.readline().strip() for _ in range(500)]
            lines = [l for l in lines if l]
    except Exception as e:
        return DatasetFile(file_path, "other", "error", None, 0, 0, 0, str(e))

    if not lines:
        return DatasetFile(file_path, "other", "empty", None, 0, 0, 0, "empty file")

    delimiter = "," if "," in lines[0] else ("\t" if "\t" in lines[0] else (" " if " " in lines[0] else None))
    
    def parse_line_to_tokens(l):
        return [x.strip() for x in l.split(delimiter) if x.strip()] if delimiter else [l.strip()]

    tokens_per_line = [len(parse_line_to_tokens(l)) for l in lines]
    format_detected = "unknown"
    item_column = None
    warning = ""

    if all(n == 1 for n in tokens_per_line):
        format_detected = "single_token_per_line"
        item_column = 0
    elif any(not l[0].isdigit() and not l[0].startswith("0x") for l in [parse_line_to_tokens(lines[0])]):
        format_detected = "table_with_header"
        header = parse_line_to_tokens(lines[0])
        priorities = ["item_id", "object_id", "key", "page_id", "block_id", "address", "addr", "memory_address", "request", "request_key", "id"]
        for p in priorities:
            for idx, col in enumerate(header):
                if p == col.lower():
                    item_column = idx
                    break
            if item_column is not None: break
        if item_column is None:
            format_detected = "unknown_multi_column_no_header"
            warning = "Cannot infer request item column."
    else:
        if all(n == 2 for n in tokens_per_line):
            col0 = [parse_line_to_tokens(l)[0] for l in lines]
            try:
                col0_nums = [float(x) if not x.startswith("0x") else int(x, 16) for x in col0]
                monotonic = all(col0_nums[i] <= col0_nums[i+1] for i in range(len(col0_nums)-1))
            except ValueError:
                monotonic = False

            if monotonic:
                format_detected = "two_columns_no_header"
                item_column = 1
            else:
                col0_unique = len(set(col0))
                col1 = len(set([parse_line_to_tokens(l)[1] for l in lines]))
                if col1 > col0_unique * 2:
                    format_detected = "two_columns_no_header"
                    item_column = 1
                elif col0_unique > col1 * 2:
                    format_detected = "two_columns_no_header"
                    item_column = 0
                else:
                    format_detected = "unknown_multi_column_no_header"
                    warning = "Cannot infer request item column."
        else:
            format_detected = "unknown_multi_column_no_header"
            warning = "Cannot infer request item column."

    parsed_rows = 0
    skipped_rows = 0
    unique_items = set()

    if item_column is not None:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                is_first = format_detected == "table_with_header"
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if is_first:
                        is_first = False
                        continue
                    tokens = parse_line_to_tokens(line)
                    if len(tokens) > item_column:
                        unique_items.add(tokens[item_column])
                        parsed_rows += 1
                    else:
                        skipped_rows += 1
        except Exception as e:
            warning += f" Error while parsing full file: {e}"

    name_lower = file_path.name.lower()
    split = "other"
    if "train" in name_lower: split = "train"
    elif "valid" in name_lower or "val" in name_lower: split = "validation"
    elif "test" in name_lower: split = "test"

    if parsed_rows == 0:
        warning += " No rows parsed."

    return DatasetFile(file_path, split, format_detected, item_column, parsed_rows, skipped_rows, len(unique_items), warning)

def discover_dataset_files(dataset_name):
    if not DATASETS_DIR.exists(): return []
    return [p for p in DATASETS_DIR.rglob("*") if p.is_file() and dataset_name in p.name]

def extract_trace(dfiles, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out_f:
        for dfile in dfiles:
            first_line = ""
            with dfile.path.open("r", encoding="utf-8") as tmp_f:
                for l in tmp_f:
                    if l.strip():
                        first_line = l.strip()
                        break
            if not first_line:
                continue
            delimiter = "," if "," in first_line else ("\t" if "\t" in first_line else (" " if " " in first_line else None))
            
            with dfile.path.open("r", encoding="utf-8") as in_f:
                is_first = dfile.format_detected == "table_with_header"
                for line in in_f:
                    line = line.strip()
                    if not line: continue
                    if is_first:
                        is_first = False
                        continue
                    tokens = [x.strip() for x in line.split(delimiter) if x.strip()] if delimiter else [line.strip()]
                    if len(tokens) > dfile.item_column:
                        out_f.write(f"{tokens[dfile.item_column]}\n")

def process_dataset(dataset, args, commit_hash, code_hash):
    run_dir = BENCHMARK_RUNS_DIR / dataset
    run_status_file = run_dir / "run_status.txt"
    metadata_file = run_dir / "metadata.json"
    stdout_file = run_dir / "stdout.log"
    stderr_file = run_dir / "stderr.log"

    candidates = discover_dataset_files(dataset)
    valid_dfiles = []
    rejected_dfiles = []

    for f in candidates:
        dfile = infer_format_and_parse(f)
        if dfile.parsed_rows > 0 and dfile.item_column is not None:
            valid_dfiles.append(dfile)
        else:
            rejected_dfiles.append(dfile)

    valid_dfiles.sort(key=lambda x: x.path)
    
    if not valid_dfiles:
        return {
            "dataset": dataset,
            "success": False,
            "error_message": "No valid trace files found",
            "return_code": -1,
            "runtime_seconds": 0.0,
            "skipped_due_to_cache": False,
            "source_files": "",
            "rejected_files": "|".join(f.path.name for f in rejected_dfiles),
            "split_mode": args.split_mode
        }

    # Split mode
    train_dfiles = [f for f in valid_dfiles if f.split == "train"]
    valid_split_dfiles = [f for f in valid_dfiles if f.split == "validation"]
    test_dfiles = [f for f in valid_dfiles if f.split == "test"]
    other_dfiles = [f for f in valid_dfiles if f.split == "other"]

    has_official = bool(train_dfiles and valid_split_dfiles and test_dfiles)
    actual_split_mode = args.split_mode
    if actual_split_mode == "auto":
        actual_split_mode = "official" if has_official else "ratio"

    total_reqs_train = 0
    total_reqs_valid = 0
    total_reqs_test = 0
    unique_train = 0
    unique_valid = 0
    unique_test = 0

    if actual_split_mode == "official":
        if not has_official:
            return {
                "dataset": dataset, "success": False, "error_message": "Official split requested but files not found",
                "return_code": -1, "runtime_seconds": 0.0, "skipped_due_to_cache": False,
                "source_files": "|".join(f.path.name for f in valid_dfiles),
                "rejected_files": "|".join(f.path.name for f in rejected_dfiles),
                "split_mode": actual_split_mode
            }
        total_reqs_train = sum(f.parsed_rows for f in train_dfiles)
        total_reqs_valid = sum(f.parsed_rows for f in valid_split_dfiles)
        total_reqs_test = sum(f.parsed_rows for f in test_dfiles)
        # We roughly sum up uniques for trace report
        unique_train = sum(f.unique_items for f in train_dfiles)
        unique_valid = sum(f.unique_items for f in valid_split_dfiles)
        unique_test = sum(f.unique_items for f in test_dfiles)
        total_uniques = unique_train + unique_valid + unique_test
    else:
        ordered_files = train_dfiles + valid_split_dfiles + test_dfiles + other_dfiles
        total_reqs = sum(f.parsed_rows for f in ordered_files)
        total_reqs_train = int(total_reqs * args.train_ratio)
        total_reqs_valid = int(total_reqs * args.validation_ratio)
        total_reqs_test = total_reqs - total_reqs_train - total_reqs_valid
        total_uniques = sum(f.unique_items for f in ordered_files)
        # roughly assign uniques for report
        unique_train = int(total_uniques * args.train_ratio)
        unique_valid = int(total_uniques * args.validation_ratio)
        unique_test = total_uniques - unique_train - unique_valid

    # Cache logic
    if args.cache_mode == "fixed":
        selected_cache_size = args.fixed_cache_size
    else:
        selected_cache_size = min(args.max_cache_size, max(args.min_cache_size, int(args.cache_ratio * total_uniques)))
        if selected_cache_size >= total_uniques and total_uniques > 0:
            selected_cache_size = max(2, total_uniques // 10)

    # Base config
    seed = 42
    config_dict = {
        "seed": seed,
        "paths": {"processed_dir": str(run_dir)},
        "data": {
            "train_ratio": args.train_ratio,
            "validation_ratio": args.validation_ratio,
            "recent_window_size": 128,
            "max_training_rows": 50000
        },
        "cache": {"cache_size": selected_cache_size},
        "model": {
            "type": "gradient_boosting",
            "learning_rate": 0.05,
            "n_estimators": 100,
            "max_depth": 3
        },
        "hedge": {
            "feedback_mode": "delayed",
            "candidate_learning_rates": [0.1, 0.3, 0.7, 1.0]
        }
    }

    if actual_split_mode == "official":
        config_dict["paths"]["train_trace"] = str(run_dir / "train_trace.txt")
        config_dict["paths"]["validation_trace"] = str(run_dir / "validation_trace.txt")
        config_dict["paths"]["test_trace"] = str(run_dir / "test_trace.txt")
    else:
        config_dict["paths"]["raw_trace"] = str(run_dir / "trace.txt")

    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()

    metadata = {
        "project_commit": "unknown", # Can be extracted if project is a git repo
        "dataset_commit": commit_hash,
        "script_hash": code_hash,
        "config_hash": config_hash,
        "dataset": dataset,
        "split_mode": actual_split_mode,
        "cache_mode": args.cache_mode,
        "selected_cache_size": selected_cache_size,
        "seed": seed,
        "model": config_dict["model"],
        "hedge": config_dict["hedge"]
    }

    trace_report_info = {
        "requested_dataset": dataset,
        "actual_dataset": dataset,
        "success": False,
        "split_mode": actual_split_mode,
        "source_files": "|".join(f.path.name for f in valid_dfiles),
        "rejected_files": "|".join(f.path.name for f in rejected_dfiles),
        "number_of_requests_train": total_reqs_train,
        "number_of_requests_validation": total_reqs_valid,
        "number_of_requests_test": total_reqs_test,
        "number_of_unique_items_train": unique_train,
        "number_of_unique_items_validation": unique_valid,
        "number_of_unique_items_test": unique_test,
        "cache_mode": args.cache_mode,
        "cache_ratio": args.cache_ratio,
        "min_cache_size": args.min_cache_size,
        "max_cache_size": args.max_cache_size,
        "selected_cache_size": selected_cache_size,
        "format_detected": "|".join(set(f.format_detected for f in valid_dfiles)),
        "item_column": valid_dfiles[0].item_column if valid_dfiles else "",
        "warning": " | ".join(filter(None, [f.warning for f in valid_dfiles]))
    }

    # Check if we can skip
    if not args.force and metadata_file.exists() and (run_dir / "benchmark_results.csv").exists():
        try:
            with open(metadata_file, "r") as mf:
                old_meta = json.load(mf)
            # Remove trace_hashes for comparison since they are generated after
            old_trace_hashes = old_meta.pop("trace_hashes", {})
            current_trace_hashes = metadata.pop("trace_hashes", {})
            
            if old_meta == metadata:
                trace_report_info["success"] = True
                print(f"[DONE] {dataset} (skipped_due_to_cache)")
                return {
                    "dataset": dataset, "success": True, "error_message": "", "return_code": 0,
                    "runtime_seconds": 0.0, "skipped_due_to_cache": True,
                    "source_files": trace_report_info["source_files"], "rejected_files": trace_report_info["rejected_files"],
                    "split_mode": actual_split_mode, "trace_report_info": trace_report_info
                }
        except Exception:
            pass

    # Clean run dir
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Extract traces
    if actual_split_mode == "official":
        extract_trace(train_dfiles, run_dir / "train_trace.txt")
        extract_trace(valid_split_dfiles, run_dir / "validation_trace.txt")
        extract_trace(test_dfiles, run_dir / "test_trace.txt")
        metadata["trace_hashes"] = {
            "train": hash_file(run_dir / "train_trace.txt"),
            "validation": hash_file(run_dir / "validation_trace.txt"),
            "test": hash_file(run_dir / "test_trace.txt")
        }
    else:
        extract_trace(valid_dfiles, run_dir / "trace.txt")
        metadata["trace_hashes"] = {"raw": hash_file(run_dir / "trace.txt")}

    with open(run_dir / "config.yaml", "w") as cf:
        yaml.dump(config_dict, cf)
        
    with open(metadata_file, "w") as mf:
        json.dump(metadata, mf, indent=2)

    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    env.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    env.setdefault("PYTHONHASHSEED", "0")

    print(f"[START] {dataset}")
    start_time = datetime.datetime.now()
    
    with open(stdout_file, "w") as out_f, open(stderr_file, "w") as err_f:
        try:
            res = subprocess.run(
                [sys.executable, "-m", "src.train", "--config", str(run_dir / "config.yaml")],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=out_f,
                stderr=err_f,
                timeout=args.timeout_seconds
            )
            return_code = res.returncode
            success = (return_code == 0)
            err_msg = ""
        except subprocess.TimeoutExpired:
            return_code = -1
            success = False
            err_msg = f"Timeout after {args.timeout_seconds} seconds"
            err_f.write(err_msg)
        except Exception as e:
            return_code = -1
            success = False
            err_msg = str(e)
            err_f.write(err_msg)

    runtime = (datetime.datetime.now() - start_time).total_seconds()
    
    if success:
        print(f"[DONE] {dataset} success=True runtime={runtime:.2f}s")
    else:
        print(f"[FAIL] {dataset} return_code={return_code}")

    trace_report_info["success"] = success
    if err_msg:
        trace_report_info["warning"] += f" | {err_msg}"

    run_status = {
        "dataset": dataset,
        "success": success,
        "error_message": err_msg,
        "return_code": return_code,
        "runtime_seconds": runtime,
        "skipped_due_to_cache": False,
        "source_files": trace_report_info["source_files"],
        "rejected_files": trace_report_info["rejected_files"],
        "split_mode": actual_split_mode,
        "trace_report_info": trace_report_info
    }
    
    with open(run_status_file, "w") as f:
        for k, v in run_status.items():
            if k != "trace_report_info":
                f.write(f"{k}: {v}\n")

    return run_status

def main():
    args = parse_args()
    verify_git()
    commit_hash = manage_repo(args.dataset_ref)
    code_hash = get_code_hash()

    datasets = PRIMARY_DATASETS if args.datasets == "all" else args.datasets.split(",")
    
    if args.jobs == "auto":
        max_workers = os.cpu_count() or 1
    else:
        max_workers = int(args.jobs)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_dataset, ds, args, commit_hash, code_hash): ds for ds in datasets}
        for future in as_completed(futures):
            results.append(future.result())

    # Sort results deterministically
    results.sort(key=lambda x: datasets.index(x["dataset"]) if x["dataset"] in datasets else 999)

    # Write trace report
    trace_reports = [r.get("trace_report_info") for r in results if r.get("trace_report_info")]
    if trace_reports:
        with open(TRACE_REPORT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=trace_reports[0].keys())
            writer.writeheader()
            writer.writerows(trace_reports)

    # Write summary
    summary_results = []
    for r in results:
        if r["success"]:
            benchmark_csv = BENCHMARK_RUNS_DIR / r["dataset"] / "benchmark_results.csv"
            if benchmark_csv.exists():
                with open(benchmark_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Only keep main algorithms
                        if row["algorithm"] in ["Belady/OPT", "MARK"] or row["algorithm"].startswith("HedgeFullDelayed"):
                            row["dataset"] = r["dataset"]
                            row["split_mode"] = r["split_mode"]
                            row["seed"] = 42 # From config
                            row["selected_cache_size"] = r["trace_report_info"]["selected_cache_size"]
                            summary_results.append(row)

    summary_results.sort(key=lambda x: (datasets.index(x["dataset"]) if x["dataset"] in datasets else 999, x["algorithm"]))
    if summary_results:
        fieldnames = ["dataset", "algorithm", "cache_misses", "total_requests", "miss_ratio", "empirical_competitive_ratio", "improvement_vs_mark_percent", "selected_cache_size", "split_mode", "seed"]
        with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(summary_results)

    # Write run_status_all_datasets
    run_status_keys = ["dataset", "success", "return_code", "runtime_seconds", "config_path", "metadata_path", "stdout_log", "stderr_log", "error_message", "skipped_due_to_cache"]
    with open(RUN_STATUS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=run_status_keys)
        writer.writeheader()
        for r in results:
            run_dir = BENCHMARK_RUNS_DIR / r["dataset"]
            writer.writerow({
                "dataset": r["dataset"],
                "success": r["success"],
                "return_code": r["return_code"],
                "runtime_seconds": r["runtime_seconds"],
                "config_path": str(run_dir / "config.yaml"),
                "metadata_path": str(run_dir / "metadata.json"),
                "stdout_log": str(run_dir / "stdout.log"),
                "stderr_log": str(run_dir / "stderr.log"),
                "error_message": r["error_message"],
                "skipped_due_to_cache": r["skipped_due_to_cache"]
            })

    # Write RUN_REPORT.md
    with open(RUN_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("# Chledowski Dataset Benchmark Report\n\n")
        f.write("## 1. Run Metadata\n")
        f.write(f"- Date/time: {datetime.datetime.now().isoformat()}\n")
        f.write(f"- Project root: {PROJECT_ROOT}\n")
        f.write(f"- Dataset repo path: {CHLEDOWSKI_REPO}\n")
        f.write(f"- Dataset repo commit hash: {commit_hash}\n")
        f.write(f"- Python executable: {sys.executable}\n")
        f.write(f"- Operating system: {sys.platform}\n\n")
        
        f.write("## 2. Dataset Repository Metadata\n")
        f.write(f"- dataset_ref_requested: {args.dataset_ref or 'unpinned'}\n")
        f.write(f"- dataset_commit_used: {commit_hash}\n\n")

        f.write("## 3. Parallelism Settings\n")
        f.write(f"- jobs: {args.jobs}\n\n")

        f.write("## 4. Dataset Preparation Summary\n")
        for tr in trace_reports:
            f.write(f"### {tr['requested_dataset']}\n")
            f.write(f"- source_files: {tr['source_files']}\n")
            f.write(f"- rejected_files: {tr['rejected_files']}\n")
            f.write(f"- format_detected_per_file: {tr['format_detected']}\n")
            f.write(f"- warning: {tr['warning']}\n\n")

        f.write("## 5. Config Summary\n")
        f.write(f"- split_mode: {args.split_mode}\n")
        f.write(f"- cache_mode: {args.cache_mode}\n")
        f.write(f"- cache_ratio: {args.cache_ratio}\n")
        f.write(f"- min_cache_size: {args.min_cache_size}\n")
        f.write(f"- max_cache_size: {args.max_cache_size}\n")
        f.write(f"- train_ratio: {args.train_ratio}\n")
        f.write(f"- validation_ratio: {args.validation_ratio}\n\n")

        f.write("## 6. Benchmark Results\n")
        f.write("Standalone baselines: Belady/OPT, MARK\n")
        f.write("Proposed algorithm: HedgeFullDelayed\n")
        f.write("Internal experts: LRU, LFU, FIFO, MARK, RawML\n\n")
        for row in summary_results:
            f.write(f"- Dataset: {row['dataset']} | Algorithm: {row['algorithm']} | Misses: {row['cache_misses']} | Miss Ratio: {row['miss_ratio']} | Improvement vs MARK: {row['improvement_vs_mark_percent']}%\n")
        f.write("\n")

        f.write("## 7. HedgeFullDelayed vs MARK\n")
        ds_set = set(r["dataset"] for r in summary_results)
        ds_sorted = [ds for ds in datasets if ds in ds_set]
        for ds in ds_sorted:
            hedge_imp = 0
            for r in summary_results:
                if r["dataset"] == ds and "HedgeFullDelayed" in r["algorithm"]:
                    hedge_imp = float(r["improvement_vs_mark_percent"])
                    break
            res = "lost to MARK" if hedge_imp < 0 else ("beat MARK" if hedge_imp > 0 else "tied MARK")
            f.write(f"- {ds}: HedgeFullDelayed {res}\n")
        f.write("\n")

        f.write("## 8. Failed Datasets\n")
        failed = [r["dataset"] for r in results if not r["success"]]
        fallback_text = "None" # Fallbacks removed based on requirements
        f.write(f"- Fallback usage: {fallback_text}\n")
        f.write(f"- Failed datasets: {', '.join(failed) if failed else 'None'}\n\n")

        f.write("## 9. Reproducibility Metadata\n")
        f.write("See metadata.json in each run directory.\n\n")

        f.write("## 10. Final Conclusion\n")
        success_count = sum(1 for r in results if r["success"])
        f.write(f"- Number of successful datasets: {success_count}\n")
        f.write(f"- Number of failed datasets: {len(failed)}\n")
        if success_count < len(datasets):
            f.write(f"- Status: WARNING: fewer than {len(datasets)} datasets completed successfully.\n")
        else:
            f.write(f"- Status: SUCCESS: benchmark completed for {success_count} datasets.\n")

if __name__ == "__main__":
    main()
