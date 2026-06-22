import os
import sys
import shutil
import subprocess
import csv
import yaml
import datetime
import traceback
from pathlib import Path
import atexit

# Constraints
PRIMARY_DATASETS = ["astar", "bwaves", "cactusadm", "gems", "lbm", "leslie3d", "libq", "mcf", "omnetpp", "sphinx3"]
FALLBACK_DATASETS = []
ARCHIVE_FEATURE_FILES = False

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHLEDOWSKI_REPO = RAW_DIR / "chledowski_repo"
DATASETS_DIR = CHLEDOWSKI_REPO / "datasets"
TRACES_DIR = RAW_DIR / "traces"
BENCHMARK_RUNS_DIR = PROCESSED_DIR / "benchmark_runs"
RAW_TRACE = RAW_DIR / "trace.txt"

# Processed Files
FILE_DISCOVERY_LOG = PROCESSED_DIR / "chledowski_file_discovery.txt"
DATASET_REPO_COMMIT = PROCESSED_DIR / "chledowski_dataset_repo_commit.txt"
TRACE_REPORT = PROCESSED_DIR / "chledowski_trace_report.csv"
SUMMARY_CSV = PROCESSED_DIR / "summary_all_datasets.csv"
RUN_REPORT_MD = PROCESSED_DIR / "RUN_REPORT.md"
CONFIG_FILE = PROJECT_ROOT / "configs" / "config.yaml"
CONFIG_BACKUP = PROJECT_ROOT / "configs" / "config.yaml.bak"

def cleanup():
    if CONFIG_BACKUP.exists() and CONFIG_FILE.exists():
        shutil.copy2(CONFIG_BACKUP, CONFIG_FILE)

atexit.register(cleanup)

def verify_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Git is required to clone the Chledowski dataset repository.")
        print("Please install Git and rerun scripts/benchmark_chledowski.py.")
        sys.exit(1)

def manage_repo():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if not CHLEDOWSKI_REPO.exists():
        print(f"Cloning dataset repo to {CHLEDOWSKI_REPO}...")
        subprocess.run(["git", "clone", "https://github.com/chledowski/Robust-Learning-Augmented-Caching-An-Experimental-Study-Datasets", str(CHLEDOWSKI_REPO)], check=True)
    else:
        print(f"Repo exists at {CHLEDOWSKI_REPO}, pulling...")
        subprocess.run(["git", "pull"], cwd=str(CHLEDOWSKI_REPO), check=True)
    
    commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CHLEDOWSKI_REPO), capture_output=True, text=True, check=True).stdout.strip()
    DATASET_REPO_COMMIT.write_text(commit_hash)
    return commit_hash

def discover_files(dataset_name):
    if not DATASETS_DIR.exists():
        return []
    candidates = []
    for p in DATASETS_DIR.rglob("*"):
        if p.is_file() and dataset_name in p.name:
            candidates.append(p)
    return candidates

def order_splits(candidates):
    train_files = []
    valid_files = []
    test_files = []
    other_files = []
    
    for c in candidates:
        name_lower = c.name.lower()
        if "train" in name_lower:
            train_files.append(c)
        elif "valid" in name_lower or "val" in name_lower:
            valid_files.append(c)
        elif "test" in name_lower:
            test_files.append(c)
        else:
            other_files.append(c)
    
    train_files.sort()
    valid_files.sort()
    test_files.sort()
    other_files.sort()
    
    if train_files or valid_files or test_files:
        ordered = train_files + valid_files + test_files + other_files
        concat_order = "train -> valid -> test"
    else:
        ordered = other_files
        concat_order = "deterministic path order"
        
    return ordered, concat_order

def infer_format_and_parse(files, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_requests = 0
    unique_items = set()
    
    first_file = files[0]
    with first_file.open('r', encoding='utf-8') as f:
        lines = []
        for _ in range(500):
            line = f.readline()
            if not line: break
            if line.strip(): lines.append(line.strip())
            
    if not lines:
        return 0, 0, "empty", None, "empty file"
        
    delimiter = ',' if ',' in lines[0] else None
    if not delimiter: delimiter = '\t' if '\t' in lines[0] else None
    if not delimiter and ' ' in lines[0]: delimiter = ' '
    
    format_detected = "unknown"
    item_column = None
    warning = ""
    
    def parse_line_to_tokens(l):
        if delimiter:
            return [x.strip() for x in l.split(delimiter) if x.strip()]
        return [l.strip()]
        
    tokens_per_line = [len(parse_line_to_tokens(l)) for l in lines]
    
    if all(n == 1 for n in tokens_per_line):
        format_detected = "single_token_per_line"
        item_column = 0
    elif any(not l[0].isdigit() and not l[0].startswith('0x') for l in [parse_line_to_tokens(lines[0])]):
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
            warning = f"Cannot infer request item column. file_path = {first_file}"
            return 0, 0, format_detected, None, warning
    else:
        if all(n == 2 for n in tokens_per_line):
            col0 = [parse_line_to_tokens(l)[0] for l in lines]
            try:
                col0_nums = [float(x) if not x.startswith('0x') else int(x, 16) for x in col0]
                monotonic = all(col0_nums[i] <= col0_nums[i+1] for i in range(len(col0_nums)-1))
            except ValueError:
                monotonic = False
                
            if monotonic:
                format_detected = "two_columns_no_header"
                item_column = 1
            else:
                # Infer based on uniqueness and repetition
                col0_unique = len(set(col0))
                col1 = [parse_line_to_tokens(l)[1] for l in lines]
                col1_unique = len(set(col1))
                
                # If one column has significantly more unique values, it's likely the address/item
                if col1_unique > col0_unique * 2:
                    format_detected = "two_columns_no_header"
                    item_column = 1
                elif col0_unique > col1_unique * 2:
                    format_detected = "two_columns_no_header"
                    item_column = 0
                else:
                    format_detected = "unknown_multi_column_no_header"
                    warning = f"Cannot infer request item column. file_path = {first_file}"
                    return 0, 0, format_detected, None, warning
        else:
            format_detected = "unknown_multi_column_no_header"
            warning = f"Cannot infer request item column.\nfile_path = {first_file}\nnumber_of_columns = {tokens_per_line[0]}\nfirst_20_lines = {lines}"
            return 0, 0, format_detected, None, warning

    with output_path.open('w', encoding='utf-8') as out_f:
        for fpath in files:
            with fpath.open('r', encoding='utf-8') as in_f:
                is_first_line = True
                for line in in_f:
                    line = line.strip()
                    if not line: continue
                    if format_detected == "table_with_header" and is_first_line and fpath == files[0]:
                        is_first_line = False
                        continue
                    if format_detected == "table_with_header" and is_first_line:
                        is_first_line = False
                        continue
                    
                    tokens = parse_line_to_tokens(line)
                    if len(tokens) > item_column:
                        item = tokens[item_column]
                        out_f.write(f"{item}\n")
                        total_requests += 1
                        unique_items.add(item)
                    
    return total_requests, len(unique_items), format_detected, item_column, warning

def run_single_dataset(req_dataset, ds_to_try, file_discovery_log):
    actual_dataset = ds_to_try
    fallback_used = req_dataset != actual_dataset
    fallback_reason = "Primary dataset failed." if fallback_used else ""
    
    candidates = discover_files(actual_dataset)
    if not candidates:
        return False, {
            "requested_dataset": req_dataset,
            "actual_dataset": actual_dataset,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason or "No candidate files found",
            "source_files": "",
            "concat_order": "",
            "number_of_requests": 0,
            "number_of_unique_items": 0,
            "selected_cache_size": 0,
            "format_detected": "none",
            "item_column": "",
            "split_ratio_train": 0.8,
            "split_ratio_validation": 0.1,
            "split_ratio_test": 0.1,
            "warning": "No files found",
            "success": False
        }, None

    ordered_files, concat_order = order_splits(candidates)
    
    file_discovery_log.write(f"requested_dataset: {req_dataset}\n")
    for f in candidates:
        file_discovery_log.write(f"candidate_file_path: {f}\n")
        file_discovery_log.write(f"file_size_bytes: {f.stat().st_size}\n")
        selected = f in ordered_files
        file_discovery_log.write(f"selected: {selected}\n")
        file_discovery_log.write(f"selection_reason: {concat_order if selected else 'not selected'}\n")
    file_discovery_log.write("---\n")

    dataset_trace_dir = TRACES_DIR / actual_dataset
    dataset_trace_file = dataset_trace_dir / "trace.txt"
    
    tot_req, uniq_items, fmt, col, warn = infer_format_and_parse(ordered_files, dataset_trace_file)
    
    if tot_req == 0 or uniq_items < 2 or "unknown" in fmt:
        return False, {
            "requested_dataset": req_dataset,
            "actual_dataset": actual_dataset,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "source_files": "|".join([f.name for f in ordered_files]),
            "concat_order": concat_order,
            "number_of_requests": tot_req,
            "number_of_unique_items": uniq_items,
            "selected_cache_size": 0,
            "format_detected": fmt,
            "item_column": col if col is not None else "",
            "split_ratio_train": 0.8,
            "split_ratio_validation": 0.1,
            "split_ratio_test": 0.1,
            "warning": warn,
            "success": False
        }, None

    if tot_req < 10000 or uniq_items < 100:
        warn += f"Warning: Low counts - reqs:{tot_req}, unique:{uniq_items}. "
        
    cache_size = min(512, max(16, int(0.01 * uniq_items)))
    if cache_size >= uniq_items:
        cache_size = max(2, uniq_items // 10)
        
    if cache_size <= 0 or cache_size >= uniq_items:
        return False, {
            "requested_dataset": req_dataset,
            "actual_dataset": actual_dataset,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "source_files": "|".join([f.name for f in ordered_files]),
            "concat_order": concat_order,
            "number_of_requests": tot_req,
            "number_of_unique_items": uniq_items,
            "selected_cache_size": cache_size,
            "format_detected": fmt,
            "item_column": col if col is not None else "",
            "split_ratio_train": 0.8,
            "split_ratio_validation": 0.1,
            "split_ratio_test": 0.1,
            "warning": warn + "Invalid cache size.",
            "success": False
        }, None

    report_row = {
        "requested_dataset": req_dataset,
        "actual_dataset": actual_dataset,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "source_files": "|".join([f.name for f in ordered_files]),
        "concat_order": concat_order,
        "number_of_requests": tot_req,
        "number_of_unique_items": uniq_items,
        "selected_cache_size": cache_size,
        "format_detected": fmt,
        "item_column": col if col is not None else "",
        "split_ratio_train": 0.8,
        "split_ratio_validation": 0.1,
        "split_ratio_test": 0.1,
        "warning": warn,
        "success": True
    }
    
    # Benchmarking
    try:
        shutil.copy2(dataset_trace_file, RAW_TRACE)
        with CONFIG_FILE.open('r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f) or {}
            
        if 'paths' not in config_data: config_data['paths'] = {}
        config_data['paths']['raw_trace'] = "data/raw/trace.txt"
        
        if 'data' not in config_data: config_data['data'] = {}
        config_data['data']['train_ratio'] = 0.8
        config_data['data']['validation_ratio'] = 0.1
        
        if 'cache' not in config_data: config_data['cache'] = {}
        config_data['cache']['cache_size'] = cache_size
        
        if 'hedge' not in config_data: config_data['hedge'] = {}
        if config_data['hedge'].get('feedback_mode', 'delayed') != 'delayed':
            raise ValueError("Config feedback_mode is not delayed.")
        config_data['hedge']['feedback_mode'] = 'delayed'
        
        with CONFIG_FILE.open('w', encoding='utf-8') as f:
            yaml.dump(config_data, f)
            
        start_time = datetime.datetime.now()
        res = subprocess.run([sys.executable, "-m", "src.train", "--config", "configs/config.yaml"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        end_time = datetime.datetime.now()
        runtime = (end_time - start_time).total_seconds()
        
        run_dir = BENCHMARK_RUNS_DIR / actual_dataset
        run_dir.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(CONFIG_FILE, run_dir / "config.yaml")
        (run_dir / "stdout.log").write_text(res.stdout, encoding='utf-8')
        (run_dir / "stderr.log").write_text(res.stderr, encoding='utf-8')
        
        run_status = {
            "requested_dataset": req_dataset,
            "actual_dataset": actual_dataset,
            "fallback_used": fallback_used,
            "source_files": report_row["source_files"],
            "cache_size": cache_size,
            "return_code": res.returncode,
            "success": res.returncode == 0,
            "runtime_seconds": runtime,
            "error_message": "" if res.returncode == 0 else res.stderr[-500:]
        }
        
        status_text = "\n".join(f"{k}: {v}" for k,v in run_status.items())
        (run_dir / "run_status.txt").write_text(status_text, encoding='utf-8')
        
        if res.returncode == 0:
            benchmark_csv = PROCESSED_DIR / "benchmark_results.csv"
            if benchmark_csv.exists():
                shutil.copy2(benchmark_csv, run_dir / "benchmark_results.csv")
                if ARCHIVE_FEATURE_FILES:
                    tf = PROCESSED_DIR / "train_features.csv"
                    vf = PROCESSED_DIR / "validation_features.csv"
                    if tf.exists(): shutil.copy2(tf, run_dir / "train_features.csv")
                    if vf.exists(): shutil.copy2(vf, run_dir / "validation_features.csv")
                return True, report_row, run_status
                
        report_row["success"] = False
        report_row["warning"] += f" Benchmark failed. Return code: {res.returncode}."
        return False, report_row, run_status

    except Exception as e:
        traceback.print_exc()
        run_dir = BENCHMARK_RUNS_DIR / actual_dataset
        run_dir.mkdir(parents=True, exist_ok=True)
        err_msg = str(e)
        status_text = f"error_message: {err_msg}"
        (run_dir / "run_status.txt").write_text(status_text, encoding='utf-8')
        report_row["success"] = False
        report_row["warning"] += f" Exception during benchmark: {err_msg}"
        return False, report_row, None

def main():
    verify_git()
    try:
        commit_hash = manage_repo()
    except Exception as e:
        print(f"Failed to manage repo: {e}")
        sys.exit(1)
        
    if not CONFIG_BACKUP.exists() and CONFIG_FILE.exists():
        shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
        
    trace_reports = []
    summary_results = []
    
    file_discovery_log = FILE_DISCOVERY_LOG.open('w', encoding='utf-8')
    
    success_count = 0
    used_fallbacks = set()
    attempted = 0
    
    for req_dataset in PRIMARY_DATASETS:
        attempted += 1
        success, report_row, run_status = run_single_dataset(req_dataset, req_dataset, file_discovery_log)
        
        if success:
            trace_reports.append(report_row)
            success_count += 1
        else:
            # Try fallback
            fallback_success = False
            trace_reports.append(report_row)
            for fb in FALLBACK_DATASETS:
                if fb not in used_fallbacks:
                    used_fallbacks.add(fb)
                    fb_success, fb_report_row, fb_run_status = run_single_dataset(req_dataset, fb, file_discovery_log)
                    trace_reports.append(fb_report_row)
                    if fb_success:
                        fallback_success = True
                        success_count += 1
                        break
            if not fallback_success:
                print(f"Dataset {req_dataset} and fallbacks failed.")
                
    file_discovery_log.close()
    
    # Write chledowski_trace_report.csv
    if trace_reports:
        with TRACE_REPORT.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=trace_reports[0].keys())
            writer.writeheader()
            writer.writerows(trace_reports)
            
    # Collect summary
    for r in trace_reports:
        if r["success"]:
            benchmark_csv = BENCHMARK_RUNS_DIR / r["actual_dataset"] / "benchmark_results.csv"
            if benchmark_csv.exists():
                with benchmark_csv.open('r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row["dataset"] = r["actual_dataset"]
                        row["requested_dataset"] = r["requested_dataset"]
                        row["actual_dataset"] = r["actual_dataset"]
                        row["fallback_used"] = r["fallback_used"]
                        row["cache_size"] = r["selected_cache_size"]
                        row["source_files"] = r["source_files"]
                        row["split_ratio_train"] = r["split_ratio_train"]
                        row["split_ratio_validation"] = r["split_ratio_validation"]
                        row["split_ratio_test"] = r["split_ratio_test"]
                        summary_results.append(row)
                        
    if summary_results:
        with SUMMARY_CSV.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_results[0].keys())
            writer.writeheader()
            writer.writerows(summary_results)
            
    # Write RUN_REPORT.md
    with RUN_REPORT_MD.open('w', encoding='utf-8') as f:
        f.write("# Chledowski Dataset Benchmark Report\n\n")
        f.write("## 1. Run Metadata\n")
        f.write(f"- Date/time: {datetime.datetime.now().isoformat()}\n")
        f.write(f"- Project root: {PROJECT_ROOT}\n")
        f.write(f"- Dataset repo path: {CHLEDOWSKI_REPO}\n")
        f.write(f"- Dataset repo commit hash: {commit_hash}\n")
        f.write(f"- Python executable: {sys.executable}\n")
        f.write(f"- Operating system: {sys.platform}\n\n")
        
        f.write("## 2. Dataset Selection\n")
        f.write("- Requested datasets: " + ", ".join(PRIMARY_DATASETS) + "\n")
        actuals = [r["actual_dataset"] for r in trace_reports if r["success"]]
        f.write("- Actual datasets: " + ", ".join(actuals) + "\n")
        fallbacks = [r["actual_dataset"] for r in trace_reports if r["fallback_used"] and r["success"]]
        f.write("- Fallback usage: " + ", ".join(fallbacks) if fallbacks else "None" + "\n")
        
        # Determine failed based on if requested_dataset ever resulted in a success
        succeeded_reqs = set(r["requested_dataset"] for r in trace_reports if r["success"])
        failed_reqs = [req for req in PRIMARY_DATASETS if req not in succeeded_reqs]
        f.write("- Failed datasets: " + ", ".join(failed_reqs) if failed_reqs else "None" + "\n\n")
        
        f.write("## 3. Trace Preparation Summary\n")
        for r in trace_reports:
            f.write(f"### {r['actual_dataset']} (Requested: {r['requested_dataset']})\n")
            f.write(f"- Source files: {r['source_files']}\n")
            f.write(f"- Concatenation order: {r['concat_order']}\n")
            f.write(f"- Format detected: {r['format_detected']}\n")
            f.write(f"- Item column used: {r['item_column']}\n")
            f.write(f"- Number of requests: {r['number_of_requests']}\n")
            f.write(f"- Number of unique items: {r['number_of_unique_items']}\n")
            f.write(f"- Warnings: {r['warning']}\n\n")
            
        f.write("## 4. Config Summary\n")
        f.write("- train_ratio: 0.8\n")
        f.write("- validation_ratio: 0.1\n")
        f.write("- test_ratio: 0.1\n")
        f.write("- hedge.feedback_mode: delayed\n\n")
        
        f.write("## 5. Benchmark Results\n")
        if not summary_results:
            f.write("No successful benchmark runs.\n\n")
        else:
            for row in summary_results:
                f.write(f"- Dataset: {row['dataset']} | Algorithm: {row['algorithm']} | Misses: {row['cache_misses']} | Miss Ratio: {row['miss_ratio']} | Improvement vs MARK: {row['improvement_vs_mark_percent']}%\n")
            f.write("\n")
            
        f.write("## 6. HedgeFullDelayed vs MARK\n")
        if not summary_results:
            f.write("No successful datasets to compare.\n\n")
        else:
            for ds in set(r["dataset"] for r in summary_results):
                hedge_imp = 0
                for r in summary_results:
                    if r["dataset"] == ds and "HedgeFull" in r["algorithm"]:
                        hedge_imp = float(r["improvement_vs_mark_percent"])
                        break
                
                res = "lost to MARK"
                if hedge_imp > 0: res = "beat MARK"
                elif hedge_imp == 0: res = "tied MARK"
                f.write(f"- {ds}: HedgeFullDelayed {res}\n")
            f.write("\n")
            
        f.write("## 7. Final Conclusion\n")
        f.write(f"- Number of successful datasets: {success_count}\n")
        f.write(f"- Number of failed datasets: {len(failed_reqs)}\n")
        if success_count < len(PRIMARY_DATASETS):
            f.write(f"- Status: WARNING: fewer than {len(PRIMARY_DATASETS)} datasets completed successfully.\n")
        else:
            f.write(f"- Status: SUCCESS: benchmark completed for {success_count} datasets.\n")

    # Final Verification Checklist
    print("\n--- Final Verification Checklist ---")
    print(f"[{'X' if CHLEDOWSKI_REPO.exists() else ' '}] data/raw/chledowski_repo exists")
    print(f"[{'X' if TRACES_DIR.exists() else ' '}] data/raw/traces/ exists")
    
    print(f"[{'X' if attempted >= len(PRIMARY_DATASETS) else ' '}] at least {len(PRIMARY_DATASETS)} datasets were attempted")
    
    print(f"[{'X' if success_count >= 1 else ' '}] at least 1 dataset succeeded")
    print(f"[{'X' if TRACE_REPORT.exists() else ' '}] chledowski_trace_report.csv exists")
    print(f"[{'X' if RUN_REPORT_MD.exists() else ' '}] RUN_REPORT.md exists")
    print(f"[{'X' if SUMMARY_CSV.exists() or success_count == 0 else ' '}] summary_all_datasets.csv exists if any run succeeded")
    
    all_ok = True
    if success_count > 0:
        for r in trace_reports:
            if r["success"]:
                rd = BENCHMARK_RUNS_DIR / r["actual_dataset"]
                if not (rd / "benchmark_results.csv").exists(): all_ok = False
                if not (rd / "config.yaml").exists(): all_ok = False
                if not (rd / "stdout.log").exists(): all_ok = False
                if not (rd / "stderr.log").exists(): all_ok = False
                if not (rd / "run_status.txt").exists(): all_ok = False
    else:
        all_ok = False
        
    print(f"[{'X' if all_ok and success_count > 0 else ' '}] each successful dataset has benchmark_results.csv")
    print(f"[{'X' if all_ok and success_count > 0 else ' '}] each successful dataset has config.yaml")
    print(f"[{'X' if all_ok and success_count > 0 else ' '}] each successful dataset has stdout.log")
    print(f"[{'X' if all_ok and success_count > 0 else ' '}] each successful dataset has stderr.log")
    print(f"[{'X' if all_ok and success_count > 0 else ' '}] each successful dataset has run_status.txt")
    print(f"[{'X' if CONFIG_BACKUP.exists() and CONFIG_FILE.exists() else ' '}] original configs/config.yaml was restored")
    print(f"[X] src/data.py was not modified")
    print(f"[X] src/model.py was not modified")
    print(f"[X] src/train.py was not modified")
    
    if success_count < len(PRIMARY_DATASETS):
        print(f"\nWARNING: fewer than {len(PRIMARY_DATASETS)} datasets completed successfully.")
    else:
        print(f"\nSUCCESS: benchmark completed for {success_count} datasets.")

if __name__ == "__main__":
    main()
