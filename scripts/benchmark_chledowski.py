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
import copy
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

@dataclass(frozen=True)
class TraceExtractionResult:
    output_path: Path
    parsed_rows: int
    skipped_rows: int
    unique_items: set
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

def verify_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Git is required.")
        sys.exit(1)

def get_project_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"

def get_project_dirty() -> bool:
    try:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True).stdout.strip()
        return bool(status)
    except Exception:
        return True

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
        subprocess.run(["git", "pull"], cwd=str(CHLEDOWSKI_REPO), check=False)

    commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CHLEDOWSKI_REPO), capture_output=True, text=True, check=True).stdout.strip()
    DATASET_REPO_COMMIT.write_text(commit_hash)
    return commit_hash

def hash_file(filepath: Path) -> str:
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_code_hashes():
    hashes = {}
    for f in ["src/model.py", "src/train.py", "src/data.py", "scripts/benchmark_chledowski.py"]:
        p = PROJECT_ROOT / f
        if p.exists():
            hashes[f] = hash_file(p)
    return hashes

def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path

def write_run_status_file(run_status_file: Path, run_status: dict) -> None:
    run_status_file.parent.mkdir(parents=True, exist_ok=True)
    with run_status_file.open("w", encoding="utf-8") as f:
        for k, v in run_status.items():
            if k not in ["trace_report_info", "discovery_records"]:
                f.write(f"{k}: {v}\n")

def write_metadata_file(metadata_file: Path, metadata: dict) -> None:
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

def reset_run_dir_for_failure(run_dir: Path) -> None:
    if run_dir.exists():
        for item in run_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    run_dir.mkdir(parents=True, exist_ok=True)

def ensure_empty_logs(stdout_file: Path, stderr_file: Path) -> None:
    stdout_file.parent.mkdir(parents=True, exist_ok=True)
    stdout_file.touch()
    stderr_file.touch()

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
                    if not line: continue
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
    rejected_words = ["readme", "summary", "stats", "stat", "metadata", "report", "result", "log", "png", "jpg", "pdf", "json", "yaml", "yml"]
    blocked_exts = {".md", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".pdf"}
    allowed_exts = {".txt", ".csv", ".tsv", ".trace", ".dat"}
    candidates = []
    
    for p in DATASETS_DIR.rglob("*"):
        if not p.is_file() or dataset_name not in p.name:
            continue
        
        lower_name = p.name.lower()
        ext = p.suffix.lower()
        if any(w in lower_name for w in rejected_words):
            candidates.append((p, False, "Contains rejected keyword"))
            continue
            
        if ext in blocked_exts:
            candidates.append((p, False, f"Extension {ext} blocked"))
            continue
            
        if ext and ext not in allowed_exts:
            candidates.append((p, False, f"Extension {ext} not allowed"))
            continue
            
        candidates.append((p, True, ""))
    
    return candidates

def extract_trace(dfiles, output_path) -> TraceExtractionResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_rows = 0
    skipped_rows = 0
    unique_items = set()
    
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
                        val = tokens[dfile.item_column]
                        out_f.write(f"{val}\n")
                        unique_items.add(val)
                        parsed_rows += 1
                    else:
                        skipped_rows += 1

    return TraceExtractionResult(output_path, parsed_rows, skipped_rows, unique_items, hash_file(output_path))

def make_trace_report_info(dataset: str, success: bool, split_mode: str, valid_dfiles: list[DatasetFile], rejected_files_str: str, 
                           train_reqs=0, valid_reqs=0, test_reqs=0, train_uniq=0, valid_uniq=0, test_uniq=0, 
                           cache_mode="ratio", cache_ratio=0.01, min_cache=16, max_cache=512, selected_cache=0, warning=""):
    return {
        "requested_dataset": dataset,
        "actual_dataset": dataset,
        "success": success,
        "split_mode": split_mode,
        "source_files": "|".join(f.path.name for f in valid_dfiles),
        "rejected_files": rejected_files_str,
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
        "format_detected_per_file": "|".join(f"{f.path.name}:{f.format_detected}" for f in valid_dfiles),
        "item_column_per_file": "|".join(f"{f.path.name}:{f.item_column}" for f in valid_dfiles),
        "parsed_rows_per_file": "|".join(f"{f.path.name}:{f.parsed_rows}" for f in valid_dfiles),
        "skipped_rows_per_file": "|".join(f"{f.path.name}:{f.skipped_rows}" for f in valid_dfiles),
        "unique_items_per_file": "|".join(f"{f.path.name}:{f.unique_items}" for f in valid_dfiles),
        "warning": warning
    }

def previous_run_succeeded(run_status_file: Path) -> bool:
    if not run_status_file.exists():
        return False
    text = run_status_file.read_text(encoding="utf-8")
    return "success: True" in text and "return_code: 0" in text

def process_dataset(dataset, args, commit_hash, code_hashes, project_commit, project_dirty, base_config):
    run_dir = BENCHMARK_RUNS_DIR / dataset
    prepared_dir = run_dir / "_prepared"
    run_status_file = run_dir / "run_status.txt"
    metadata_file = run_dir / "metadata.json"
    stdout_file = run_dir / "stdout.log"
    stderr_file = run_dir / "stderr.log"

    candidates = discover_dataset_files(dataset)
    valid_dfiles = []
    rejected_records = []
    discovery_records = []

    for p, allowed, reason in candidates:
        if not allowed:
            rejected_records.append((p, reason))
            discovery_records.append({"dataset": dataset, "path": str(p), "accepted": False, "split": "other", "format_detected": "none", "item_column": None, "parsed_rows": 0, "skipped_rows": 0, "unique_items": 0, "warning": reason})
            continue
        
        dfile = infer_format_and_parse(p)
        if dfile.parsed_rows > 0 and dfile.item_column is not None:
            valid_dfiles.append(dfile)
            discovery_records.append({"dataset": dataset, "path": str(p), "accepted": True, "split": dfile.split, "format_detected": dfile.format_detected, "item_column": dfile.item_column, "parsed_rows": dfile.parsed_rows, "skipped_rows": dfile.skipped_rows, "unique_items": dfile.unique_items, "warning": dfile.warning})
        else:
            rejected_records.append((p, dfile.warning))
            discovery_records.append({"dataset": dataset, "path": str(p), "accepted": False, "split": dfile.split, "format_detected": dfile.format_detected, "item_column": dfile.item_column, "parsed_rows": dfile.parsed_rows, "skipped_rows": dfile.skipped_rows, "unique_items": dfile.unique_items, "warning": dfile.warning})

    valid_dfiles.sort(key=lambda x: x.path)
    rejected_files_str = "|".join(f"{p.name}:{reason}" for p, reason in rejected_records)
    
    if not valid_dfiles:
        reset_run_dir_for_failure(run_dir)
        ensure_empty_logs(stdout_file, stderr_file)
        failure_metadata = {
            "project_commit": project_commit, "dataset_commit": commit_hash,
            "dataset_ref_requested": args.dataset_ref or "unpinned", "code_hashes": code_hashes,
            "dataset": dataset, "split_mode": args.split_mode, "failure_stage": "discovery", "error_message": "No valid trace files found"
        }
        write_metadata_file(metadata_file, failure_metadata)
        trace_info = make_trace_report_info(dataset, False, args.split_mode, [], rejected_files_str, warning="No valid trace files found")
        run_status = {
            "dataset": dataset, "success": False, "error_message": "No valid trace files found", "return_code": -1, "runtime_seconds": 0.0,
            "skipped_due_to_cache": False, "split_mode": args.split_mode, "discovery_records": discovery_records, "trace_report_info": trace_info
        }
        write_run_status_file(run_status_file, run_status)
        return run_status

    train_dfiles = [f for f in valid_dfiles if f.split == "train"]
    valid_split_dfiles = [f for f in valid_dfiles if f.split == "validation"]
    test_dfiles = [f for f in valid_dfiles if f.split == "test"]
    other_dfiles = [f for f in valid_dfiles if f.split == "other"]

    has_official = bool(train_dfiles and valid_split_dfiles and test_dfiles)
    actual_split_mode = args.split_mode
    if actual_split_mode == "auto":
        actual_split_mode = "official" if has_official else "ratio"

    if actual_split_mode == "official" and not has_official:
        reset_run_dir_for_failure(run_dir)
        ensure_empty_logs(stdout_file, stderr_file)
        failure_metadata = {
            "project_commit": project_commit, "dataset_commit": commit_hash,
            "dataset_ref_requested": args.dataset_ref or "unpinned", "code_hashes": code_hashes,
            "dataset": dataset, "split_mode": actual_split_mode, "failure_stage": "split_selection", "error_message": "Official split requested but missing"
        }
        write_metadata_file(metadata_file, failure_metadata)
        trace_info = make_trace_report_info(dataset, False, actual_split_mode, valid_dfiles, rejected_files_str, warning="Official split requested but missing")
        run_status = {
            "dataset": dataset, "success": False, "error_message": "Official split requested but missing", "return_code": -1, "runtime_seconds": 0.0,
            "skipped_due_to_cache": False, "split_mode": actual_split_mode, "discovery_records": discovery_records, "trace_report_info": trace_info
        }
        write_run_status_file(run_status_file, run_status)
        return run_status

    if prepared_dir.exists():
        shutil.rmtree(prepared_dir)
    prepared_dir.mkdir(parents=True, exist_ok=False)

    trace_hashes = {}
    if actual_split_mode == "official":
        train_res = extract_trace(train_dfiles, prepared_dir / "train_trace.txt")
        valid_res = extract_trace(valid_split_dfiles, prepared_dir / "validation_trace.txt")
        test_res = extract_trace(test_dfiles, prepared_dir / "test_trace.txt")
        total_unique_items = len(train_res.unique_items | valid_res.unique_items | test_res.unique_items)
        trace_hashes = {"train": train_res.trace_hash, "validation": valid_res.trace_hash, "test": test_res.trace_hash}
        train_reqs, valid_reqs, test_reqs = train_res.parsed_rows, valid_res.parsed_rows, test_res.parsed_rows
        train_uniq, valid_uniq, test_uniq = len(train_res.unique_items), len(valid_res.unique_items), len(test_res.unique_items)
    else:
        ordered_files = train_dfiles + valid_split_dfiles + test_dfiles + other_dfiles
        raw_res = extract_trace(ordered_files, prepared_dir / "trace.txt")
        total_unique_items = len(raw_res.unique_items)
        trace_hashes = {"raw": raw_res.trace_hash}
        train_reqs = int(raw_res.parsed_rows * args.train_ratio)
        valid_reqs = int(raw_res.parsed_rows * args.validation_ratio)
        test_reqs = raw_res.parsed_rows - train_reqs - valid_reqs
        train_uniq = int(total_unique_items * args.train_ratio)
        valid_uniq = int(total_unique_items * args.validation_ratio)
        test_uniq = total_unique_items - train_uniq - valid_uniq

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

    if actual_split_mode == "official":
        config_dict["paths"]["train_trace"] = str(run_dir / "train_trace.txt")
        config_dict["paths"]["validation_trace"] = str(run_dir / "validation_trace.txt")
        config_dict["paths"]["test_trace"] = str(run_dir / "test_trace.txt")
    else:
        config_dict["paths"]["raw_trace"] = str(run_dir / "trace.txt")

    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()
    
    # base_config is already passed in as a loaded dict, but we should hash the path
    # base_config_path is derived from args.base_config but passed in main
    base_config_path = resolve_project_path(args.base_config)
    base_config_hash = hash_file(base_config_path)

    metadata = {
        "project_commit": project_commit,
        "dataset_commit": commit_hash,
        "dataset_ref_requested": args.dataset_ref or "unpinned",
        "code_hashes": code_hashes,
        "config_hash": config_hash,
        "base_config_path": str(base_config_path),
        "base_config_hash": base_config_hash,
        "dataset_source_file_hashes": {str(dfile.path): hash_file(dfile.path) for dfile in valid_dfiles},
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
        "hedge": config_dict["hedge"]
    }

    trace_report_info = make_trace_report_info(
        dataset, False, actual_split_mode, valid_dfiles, rejected_files_str,
        train_reqs, valid_reqs, test_reqs, train_uniq, valid_uniq, test_uniq,
        args.cache_mode, args.cache_ratio, args.min_cache_size, args.max_cache_size, selected_cache_size
    )

    if not args.force and metadata_file.exists() and (run_dir / "benchmark_results.csv").exists():
        try:
            with open(metadata_file, "r") as mf:
                old_meta = json.load(mf)
            if old_meta == metadata and previous_run_succeeded(run_status_file):
                trace_report_info["success"] = True
                print(f"[DONE] {dataset} (skipped_due_to_cache)")
                shutil.rmtree(prepared_dir)
                return {
                    "dataset": dataset, "success": True, "error_message": "", "return_code": 0, "runtime_seconds": 0.0, "skipped_due_to_cache": True,
                    "split_mode": actual_split_mode, "discovery_records": discovery_records, "trace_report_info": trace_report_info
                }
        except Exception:
            pass

    for item in run_dir.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir() and item.name != "_prepared":
            shutil.rmtree(item)

    for item in prepared_dir.iterdir():
        shutil.move(str(item), str(run_dir / item.name))
    shutil.rmtree(prepared_dir)

    with open(run_dir / "config.yaml", "w") as cf:
        yaml.dump(config_dict, cf)
    with open(metadata_file, "w") as mf:
        json.dump(metadata, mf, indent=2)

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    env["VECLIB_MAXIMUM_THREADS"] = "1"
    env["PYTHONHASHSEED"] = str(config_dict.get("seed", 42))

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
            err_msg = f"Subprocess timeout"
            err_f.write(err_msg)
        except Exception as e:
            return_code = -1
            success = False
            err_msg = f"Subprocess exception: {e}"
            err_f.write(err_msg)

    runtime = (datetime.datetime.now() - start_time).total_seconds()
    
    if success:
        print(f"[DONE] {dataset} success=True runtime={runtime:.2f}s")
    else:
        print(f"[FAIL] {dataset} return_code={return_code}")

    trace_report_info["success"] = success
    if err_msg: trace_report_info["warning"] += f" | {err_msg}"

    run_status = {
        "dataset": dataset, "success": success, "error_message": err_msg, "return_code": return_code, "runtime_seconds": runtime, "skipped_due_to_cache": False,
        "split_mode": actual_split_mode, "discovery_records": discovery_records, "trace_report_info": trace_report_info
    }
    
    with open(run_status_file, "w") as f:
        for k, v in run_status.items():
            if k not in ["trace_report_info", "discovery_records"]:
                f.write(f"{k}: {v}\n")

    return run_status

def main():
    args = parse_args()
    verify_git()
    commit_hash = manage_repo(args.dataset_ref)
    code_hashes = get_code_hashes()
    project_commit = get_project_commit()
    project_dirty = get_project_dirty()

    base_config_path = resolve_project_path(args.base_config)
    with base_config_path.open("r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)

    datasets = PRIMARY_DATASETS if args.datasets == "all" else args.datasets.split(",")
    max_workers = os.cpu_count() or 1 if args.jobs == "auto" else int(args.jobs)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {executor.submit(process_dataset, ds, args, commit_hash, code_hashes, project_commit, project_dirty, base_config): ds for ds in datasets}
        for future in as_completed(future_to_dataset):
            ds = future_to_dataset[future]
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"[FAIL] {ds} Unhandled worker exception")
                run_dir = BENCHMARK_RUNS_DIR / ds
                ensure_empty_logs(run_dir / "stdout.log", run_dir / "stderr.log")
                results.append({
                    "dataset": ds, "success": False, "error_message": f"Unhandled worker exception: {exc}", "return_code": -1, "runtime_seconds": 0.0, "skipped_due_to_cache": False,
                    "split_mode": args.split_mode, "discovery_records": [], "trace_report_info": make_trace_report_info(ds, False, args.split_mode, [], "", warning=f"Unhandled worker exception: {exc}")
                })

    results.sort(key=lambda x: datasets.index(x["dataset"]) if x["dataset"] in datasets else 999)

    discovery_records = []
    for r in results:
        discovery_records.extend(r.get("discovery_records", []))
    if discovery_records:
        with open(FILE_DISCOVERY_LOG, "w", encoding="utf-8") as f:
            for rec in discovery_records:
                f.write(str(rec) + "\n")

    trace_reports = [r.get("trace_report_info") for r in results if r.get("trace_report_info")]
    if trace_reports:
        with open(TRACE_REPORT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=trace_reports[0].keys())
            writer.writeheader()
            writer.writerows(trace_reports)

    summary_results = []
    for r in results:
        if r["success"]:
            benchmark_csv = BENCHMARK_RUNS_DIR / r["dataset"] / "benchmark_results.csv"
            if benchmark_csv.exists():
                with open(benchmark_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["algorithm"] in ["Belady/OPT", "MARK"] or row["algorithm"].startswith("HedgeFullDelayed"):
                            row["dataset"] = r["dataset"]
                            row["split_mode"] = r["split_mode"]
                            row["seed"] = base_config.get("seed", 42)
                            row["selected_cache_size"] = r["trace_report_info"]["selected_cache_size"]
                            summary_results.append(row)

    summary_results.sort(key=lambda x: (datasets.index(x["dataset"]) if x["dataset"] in datasets else 999, x["algorithm"]))
    
    fieldnames = ["dataset", "algorithm", "cache_misses", "total_requests", "miss_ratio", "empirical_competitive_ratio", "improvement_vs_mark_percent", "selected_cache_size", "split_mode", "seed", "selected_hedge_learning_rate", "validation_mae"]
    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(summary_results)

    run_status_keys = ["dataset", "success", "return_code", "runtime_seconds", "config_path", "metadata_path", "stdout_log", "stderr_log", "error_message", "skipped_due_to_cache"]
    with open(RUN_STATUS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=run_status_keys)
        writer.writeheader()
        for r in results:
            run_dir = BENCHMARK_RUNS_DIR / r["dataset"]
            writer.writerow({
                "dataset": r["dataset"], "success": r["success"], "return_code": r["return_code"], "runtime_seconds": r["runtime_seconds"],
                "config_path": str(run_dir / "config.yaml"), "metadata_path": str(run_dir / "metadata.json"), "stdout_log": str(run_dir / "stdout.log"), "stderr_log": str(run_dir / "stderr.log"),
                "error_message": r["error_message"], "skipped_due_to_cache": r["skipped_due_to_cache"]
            })

    with open(RUN_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("# Chledowski Dataset Benchmark Report\n\n")
        f.write("## 1. Run Metadata\n")
        f.write(f"- project_commit: {project_commit}\n")
        f.write(f"- project_dirty: {project_dirty}\n")
        f.write(f"- dataset_ref_requested: {args.dataset_ref or 'unpinned'}\n")
        f.write(f"- dataset_commit_used: {commit_hash}\n")
        f.write(f"- jobs: {args.jobs}\n\n")

        f.write("## 2. Dataset Preparation Summary\n")
        for tr in trace_reports:
            f.write(f"### {tr['requested_dataset']}\n")
            f.write(f"- split_mode actual per dataset: {tr['split_mode']}\n")
            f.write(f"- source_files: {tr['source_files']}\n")
            f.write(f"- rejected_files: {tr['rejected_files']}\n")
            f.write(f"- format_detected_per_file: {tr['format_detected_per_file']}\n")
            f.write(f"- warning: {tr['warning']}\n\n")

        f.write("## 3. Config Summary\n")
        f.write(f"- cache_size rule: {args.cache_mode} (ratio: {args.cache_ratio}, fixed: {args.fixed_cache_size})\n\n")

        f.write("## 4. Benchmark Results\n")
        f.write("Standalone baselines: Belady/OPT, MARK\n")
        f.write("Proposed algorithm: HedgeFullDelayed\n")
        f.write("Internal experts: LRU, LFU, FIFO, MARK, RawML\n\n")
        for row in summary_results:
            f.write(f"- Dataset: {row['dataset']} | Algorithm: {row['algorithm']} | Misses: {row['cache_misses']} | Miss Ratio: {row['miss_ratio']} | Improvement vs MARK: {row['improvement_vs_mark_percent']}% | Eta: {row.get('selected_hedge_learning_rate','')} | MAE: {row.get('validation_mae','')}\n")
        f.write("\n")

        f.write("## 5. HedgeFullDelayed vs MARK\n")
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

        f.write("## 6. Failed Datasets\n")
        failed = [r["dataset"] for r in results if not r["success"]]
        f.write(f"- Failed datasets: {', '.join(failed) if failed else 'None'}\n\n")

        f.write("## 7. Final Conclusion\n")
        success_count = sum(1 for r in results if r["success"])
        f.write(f"- Number of successful datasets: {success_count}\n")
        f.write(f"- Number of failed datasets: {len(failed)}\n")
        if success_count < len(datasets):
            f.write(f"- Status: WARNING: fewer than {len(datasets)} datasets completed successfully.\n")
        else:
            f.write(f"- Status: SUCCESS: benchmark completed for {success_count} datasets.\n")

if __name__ == "__main__":
    main()
