# AI Agent Final Fix Spec: Remaining Benchmark Automation Issues

Target branch:

```text
feature/benchmark-automation
```

This file is the final focused automation checklist for the issues still remaining after the latest agent changes.

Do not rework the whole benchmark script again. Apply targeted fixes only.

The benchmark goal remains strictly:

```text
HedgeFullDelayed vs Belady/OPT vs MARK
```

Do not add standalone LRU/LFU/FIFO/RawML baselines.

---

## Current status

The branch already correctly implements most of the major requirements:

```text
[OK] MARK vote side effect fixed with mutate_phase=False inside Hedge.
[OK] src.train supports train_trace / validation_trace / test_trace.
[OK] selected_hedge_learning_rate and validation_mae are written by src.train.
[OK] benchmark script supports --base-config.
[OK] metadata contains project_commit, project_dirty, dataset_commit, trace_hashes.
[OK] metadata skip checks old_meta == metadata and previous run success.
[OK] exact unique item sets are used for selected_cache_size.
[OK] CPU thread env vars are assigned directly.
[OK] ThreadPoolExecutor exceptions are caught.
[OK] chledowski_file_discovery.txt is written.
[OK] trace report includes per-file parsing fields.
```

The remaining issues are smaller but still important for benchmark correctness and reproducibility.

---

# 1. Fix metadata field naming and add real dataset source file hashes

## Problem

The current metadata uses:

```python
"source_file_hashes": code_hashes
```

This is incorrect.

`code_hashes` contains hashes of code files:

```text
src/model.py
src/train.py
src/data.py
scripts/benchmark_chledowski.py
```

Those are not dataset source files.

## Required fix

In `scripts/benchmark_chledowski.py`, change metadata from:

```python
"code_hash": code_hashes.get("scripts/benchmark_chledowski.py", ""),
"source_file_hashes": code_hashes,
```

to:

```python
"code_hashes": code_hashes,
"dataset_source_file_hashes": {
    str(dfile.path): hash_file(dfile.path)
    for dfile in valid_dfiles
},
```

Remove the misleading field:

```text
source_file_hashes
```

unless it truly means dataset source file hashes.

## Required metadata shape

Metadata must contain both:

```json
{
  "code_hashes": {
    "src/model.py": "...",
    "src/train.py": "...",
    "src/data.py": "...",
    "scripts/benchmark_chledowski.py": "..."
  },
  "dataset_source_file_hashes": {
    "data/raw/chledowski_repo/.../xalanc_train...": "...",
    "data/raw/chledowski_repo/.../xalanc_test...": "..."
  }
}
```

## Acceptance criteria

```text
[ ] metadata.json no longer has misleading source_file_hashes containing code hashes.
[ ] metadata.json contains code_hashes.
[ ] metadata.json contains dataset_source_file_hashes.
[ ] Changing a selected dataset source file changes metadata and prevents stale skip.
[ ] Changing a code file changes metadata and prevents stale skip.
```

---

# 2. Always write `summary_all_datasets.csv`, even when empty

## Problem

Current script only writes `summary_all_datasets.csv` if `summary_results` is non-empty.

If all datasets fail, an old `summary_all_datasets.csv` from a previous successful run can remain on disk and mislead the user.

## Required fix

Always write `SUMMARY_CSV` with a header.

Current pattern to remove:

```python
if summary_results:
    fieldnames = [...]
    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        ...
```

Replace with:

```python
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

with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(summary_results)
```

## Acceptance criteria

```text
[ ] summary_all_datasets.csv is overwritten every run.
[ ] If all datasets fail, summary_all_datasets.csv exists with only header.
[ ] Stale rows from earlier runs cannot remain.
```

---

# 3. Early failure paths must write per-dataset run_status and metadata

## Problem

Some early failure paths return before writing per-dataset files.

Examples:

```text
No valid trace files found
Official split requested but files not found
```

Global `run_status_all_datasets.csv` may be written, but the per-dataset paths point to files that may not exist or may be stale from a previous run.

## Required fix

Add helper functions:

```python
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
```

For early failure, write minimal metadata such as:

```python
failure_metadata = {
    "project_commit": project_commit,
    "project_dirty": project_dirty,
    "dataset_commit": commit_hash,
    "dataset_ref_requested": args.dataset_ref or "unpinned",
    "code_hashes": code_hashes,
    "dataset": dataset,
    "split_mode": args.split_mode,
    "failure_stage": "discovery" or "split_selection",
    "error_message": "No valid trace files found",
}
```

Then write both:

```text
data/processed/benchmark_runs/<dataset>/run_status.txt
data/processed/benchmark_runs/<dataset>/metadata.json
```

before returning.

## Required behavior for early failure

For every dataset, even failed ones, these paths should exist:

```text
data/processed/benchmark_runs/<dataset>/run_status.txt
data/processed/benchmark_runs/<dataset>/metadata.json
```

`stdout.log` and `stderr.log` are optional for failures that happen before subprocess execution, but if the global `run_status_all_datasets.csv` points to them, create empty files too.

## Acceptance criteria

Run:

```bash
python scripts/benchmark_chledowski.py --datasets does_not_exist --jobs 1 --force
```

Expected:

```text
[ ] script exits normally.
[ ] data/processed/benchmark_runs/does_not_exist/run_status.txt exists.
[ ] data/processed/benchmark_runs/does_not_exist/metadata.json exists.
[ ] run_status_all_datasets.csv contains does_not_exist.
[ ] chledowski_trace_report.csv contains does_not_exist.
[ ] summary_all_datasets.csv exists with only header or no rows for does_not_exist.
```

---

# 4. Clean `_prepared` before extracting traces

## Problem

Current script creates:

```python
prepared_dir.mkdir(parents=True, exist_ok=True)
```

If a previous interrupted run left files in `_prepared`, the next run can move stale files into the final run directory.

## Required fix

Before creating `_prepared`, always remove it:

```python
if prepared_dir.exists():
    shutil.rmtree(prepared_dir)
prepared_dir.mkdir(parents=True, exist_ok=False)
```

This should happen immediately before trace extraction.

## Acceptance criteria

```text
[ ] No stale files from a previous _prepared directory can be moved into run_dir.
[ ] _prepared is always fresh for the current dataset run.
```

---

# 5. Resolve `--base-config` relative to PROJECT_ROOT

## Problem

Current script opens:

```python
with open(args.base_config, "r", encoding="utf-8") as f:
```

and hashes:

```python
base_config_hash = hash_file(Path(args.base_config))
```

This works only if the script is run from the repository root.

## Required fix

Add helper:

```python
def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
```

In `main()`:

```python
base_config_path = resolve_project_path(args.base_config)
with base_config_path.open("r", encoding="utf-8") as f:
    base_config = yaml.safe_load(f)
```

Pass `base_config_path` into `process_dataset(...)` or store it in args if preferred.

In `process_dataset(...)`, compute:

```python
base_config_hash = hash_file(base_config_path)
```

Metadata should store:

```python
"base_config_path": str(base_config_path),
"base_config_hash": base_config_hash,
```

## Acceptance criteria

The script should work from repo root:

```bash
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1 --force
```

and also from another working directory, for example:

```bash
cd ..
python Online-Caching/scripts/benchmark_chledowski.py --datasets xalanc --jobs 1 --force
```

---

# 6. Fix overly broad discovery rejection for `md`

## Problem

The current `rejected_words` includes:

```python
"md"
```

as a substring match. This can reject legitimate trace files whose names happen to contain `md`.

## Required fix

Remove `"md"` from substring rejected words.

Reject Markdown files by extension instead:

```python
blocked_exts = {".md", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".pdf"}
```

Suggested discovery logic:

```python
rejected_name_keywords = [
    "readme",
    "summary",
    "stats",
    "stat",
    "metadata",
    "report",
    "result",
    "log",
]

blocked_exts = {".md", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".pdf"}
allowed_exts = {".txt", ".csv", ".tsv", ".trace", ".dat"}

lower_name = p.name.lower()
ext = p.suffix.lower()

if any(k in lower_name for k in rejected_name_keywords):
    reject
elif ext in blocked_exts:
    reject
elif ext and ext not in allowed_exts:
    reject
else:
    accept
```

## Acceptance criteria

```text
[ ] Markdown files are rejected by .md extension.
[ ] Legitimate trace files are not rejected merely because their filename contains the letters 'md'.
```

---

# 7. Ensure stale per-dataset files do not survive early failure

## Problem

If a dataset succeeded in an earlier run and then fails early in a later run, stale files may remain inside:

```text
data/processed/benchmark_runs/<dataset>/
```

For example:

```text
benchmark_results.csv
train_features.csv
validation_features.csv
```

could remain from the previous run.

## Required fix

For every dataset run, initialize its `run_dir` safely before returning any status.

Recommended helper:

```python
def reset_run_dir_for_failure(run_dir: Path) -> None:
    if run_dir.exists():
        for item in run_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    run_dir.mkdir(parents=True, exist_ok=True)
```

Use this for early failures when the run will not execute `src.train`.

For normal non-skipped reruns, continue to clean run_dir before moving prepared traces.

For metadata skip, do **not** clean run_dir.

## Acceptance criteria

```text
[ ] If a dataset fails early, old benchmark_results.csv from previous runs is removed.
[ ] run_status_all_datasets.csv does not point to stale per-dataset result files.
[ ] Metadata skip still preserves old successful run files only when metadata matches and previous success is true.
```

---

# 8. Keep summary algorithm filtering strict

Do not change this behavior.

Allowed algorithms in `summary_all_datasets.csv`:

```text
Belady/OPT
MARK
HedgeFullDelayed(...)
```

Reject standalone:

```text
LRU
LFU
FIFO
RawML
```

Acceptance criterion:

```text
[ ] summary_all_datasets.csv contains no standalone LRU/LFU/FIFO/RawML rows.
```

---

# 9. Final verification commands

After applying fixes, run at least these commands.

## Failure path test

```bash
python scripts/benchmark_chledowski.py --datasets does_not_exist --jobs 1 --force
```

Expected:

```text
[ ] exits normally.
[ ] run_status_all_datasets.csv exists.
[ ] chledowski_trace_report.csv exists and includes does_not_exist.
[ ] summary_all_datasets.csv exists and has no stale rows.
[ ] data/processed/benchmark_runs/does_not_exist/run_status.txt exists.
[ ] data/processed/benchmark_runs/does_not_exist/metadata.json exists.
```

## Skip test

```bash
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1 --force
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1
```

Expected second run:

```text
[ ] skipped_due_to_cache=True.
```

Then change a selected source dataset file or any source code file.

Expected next run:

```text
[ ] skipped_due_to_cache=False.
```

## Parallel determinism test

```bash
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 1 --force
copy data/processed/summary_all_datasets.csv data/processed/summary_jobs1.csv

python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 2 --force
copy data/processed/summary_all_datasets.csv data/processed/summary_jobs2.csv
```

Compare these columns:

```text
dataset
algorithm
cache_misses
miss_ratio
selected_cache_size
selected_hedge_learning_rate
validation_mae
```

Expected:

```text
[ ] jobs=1 and jobs=2 produce identical benchmark numbers.
```

## Config mutation test

```bash
git diff -- configs/config.yaml configs/config.yaml.bak
```

Expected:

```text
[ ] empty diff.
```

---

# Final acceptance checklist

The branch is ready to merge only if all are true:

```text
[ ] metadata.json has code_hashes.
[ ] metadata.json has dataset_source_file_hashes.
[ ] metadata.json has trace_hashes.
[ ] summary_all_datasets.csv is overwritten every run, even if empty.
[ ] Early failure writes per-dataset run_status.txt.
[ ] Early failure writes per-dataset metadata.json.
[ ] Early failure removes stale per-dataset benchmark files.
[ ] _prepared is cleaned before trace extraction.
[ ] --base-config is resolved relative to PROJECT_ROOT.
[ ] Markdown .md rejection is extension-based, not substring-based.
[ ] summary_all_datasets.csv contains only Belady/OPT, MARK, HedgeFullDelayed.
[ ] configs/config.yaml and configs/config.yaml.bak are unchanged after benchmark.
[ ] jobs=1 and jobs=2 produce identical benchmark numbers.
```

Do not merge `feature/benchmark-automation` into `main` until this checklist passes.
