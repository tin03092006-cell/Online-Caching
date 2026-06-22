# AI Agent Task Spec: Fix Remaining Benchmark Automation Issues

Target branch:

```text
feature/benchmark-automation
```

This file lists the remaining issues that must be fixed before merging the benchmark automation branch.

The current branch already implements the basic structure, but it does **not** yet satisfy all benchmark correctness, reproducibility, and parallel-execution requirements.

Do not change the scientific benchmark goal:

```text
HedgeFullDelayed vs Belady/OPT vs MARK
```

Do **not** add standalone LRU/LFU/FIFO/RawML baselines. They remain internal experts of HedgeFullDelayed only.

---

## 0. Required final outcome

After this task is complete, the following must be true:

```text
[ ] Metadata-based skip does not ignore trace hashes.
[ ] Failed previous runs are never skipped as successful.
[ ] Cache size is computed from exact unique item sets, not from summed per-file unique counts.
[ ] project_commit is written correctly, not "unknown".
[ ] CPU thread-limit environment variables are forced to 1 for each subprocess.
[ ] PYTHONHASHSEED uses the configured seed.
[ ] File discovery log is actually written.
[ ] chledowski_trace_report.csv contains per-file parse details.
[ ] Every failure path returns trace_report_info.
[ ] Exceptions from parallel futures do not crash the whole benchmark.
[ ] selected_hedge_learning_rate is saved in per-dataset and global outputs.
[ ] validation_mae is saved if available.
[ ] Benchmark script reads a base config instead of hard-coding model/data/hedge params.
[ ] configs/config.yaml and configs/config.yaml.bak remain unmodified.
[ ] summary_all_datasets.csv contains only Belady/OPT, MARK, HedgeFullDelayed rows.
```

---

# 1. Fix metadata-based skip

## Current bug

The current implementation removes `trace_hashes` from both old and new metadata before comparison:

```python
old_trace_hashes = old_meta.pop("trace_hashes", {})
current_trace_hashes = metadata.pop("trace_hashes", {})

if old_meta == metadata:
    skip
```

This is wrong. It allows stale benchmark results to be reused even when generated traces differ.

## Required behavior

Skip a dataset only if **all** of these are true:

```text
[ ] --force is not set.
[ ] benchmark_results.csv exists.
[ ] run_status.txt exists.
[ ] previous run_status says success=True and return_code=0.
[ ] metadata.json exists.
[ ] old metadata exactly equals current metadata, including trace_hashes.
```

Never skip a dataset if the previous run failed.

## Required implementation

Add helper functions in `scripts/benchmark_chledowski.py`:

```python
def load_json(path: Path) -> dict:
    ...


def load_previous_run_success(run_status_path: Path) -> bool:
    ...


def metadata_matches(old_metadata: dict, current_metadata: dict) -> bool:
    return old_metadata == current_metadata
```

Do not mutate metadata dictionaries with `.pop()` during comparison.

## Correct flow

The script must compute final metadata before checking skip.

Because final metadata includes generated trace hashes, prepare traces first in a staging area, compute hashes, then decide whether to skip.

Recommended flow inside `process_dataset(...)`:

```text
1. Discover files.
2. Decide split mode.
3. Build run config.
4. Extract traces into a temporary staging directory, for example:
   data/processed/benchmark_runs/<dataset>/_prepared/
5. Compute generated trace hashes from staged traces.
6. Build current metadata including trace_hashes.
7. If not --force and previous metadata matches and previous run succeeded:
      delete _prepared/
      return skipped status.
8. Otherwise:
      clean final run_dir except _prepared/
      move staged traces into final paths.
      write config.yaml.
      write metadata.json.
      run subprocess.
```

Simpler acceptable alternative:

```text
Always clean and regenerate trace files first, then compare metadata. If skip is true, do not rerun src.train. This is acceptable because trace extraction is cheap relative to model training.
```

But do not delete old benchmark results before deciding skip.

## Metadata must include

```json
{
  "project_commit": "...",
  "project_dirty": true,
  "dataset_commit": "...",
  "dataset_ref_requested": "...",
  "code_hash": "...",
  "config_hash": "...",
  "source_file_hashes": {
    "path/to/source/file": "sha256"
  },
  "trace_hashes": {
    "train": "...",
    "validation": "...",
    "test": "..."
  },
  "dataset": "...",
  "split_mode": "...",
  "cache_mode": "...",
  "cache_ratio": 0.01,
  "min_cache_size": 16,
  "max_cache_size": 512,
  "fixed_cache_size": 100,
  "selected_cache_size": 123,
  "seed": 42,
  "model": {...},
  "hedge": {...}
}
```

For ratio split mode, `trace_hashes` may be:

```json
{
  "raw": "..."
}
```

---

# 2. Check run_status before skip

## Current bug

The current code checks `metadata.json` and `benchmark_results.csv`, but does not verify that the previous run succeeded.

## Required implementation

`run_status.txt` must be parsed before skip.

Expected fields:

```text
success: True
return_code: 0
```

Add helper:

```python
def previous_run_succeeded(run_status_file: Path) -> bool:
    if not run_status_file.exists():
        return False
    text = run_status_file.read_text(encoding="utf-8")
    return "success: True" in text and "return_code: 0" in text
```

Better implementation: write `run_status.json` as well, but keep `run_status.txt` for human readability.

Skip only if `previous_run_succeeded(...)` returns `True`.

---

# 3. Compute unique item counts exactly

## Current bug

The current code computes unique counts by summing `unique_items` per file:

```python
unique_train = sum(f.unique_items for f in train_dfiles)
unique_valid = sum(f.unique_items for f in valid_split_dfiles)
unique_test = sum(f.unique_items for f in test_dfiles)
total_uniques = unique_train + unique_valid + unique_test
```

This double-counts items that occur in multiple files or splits.

This directly affects:

```text
selected_cache_size
chledowski_trace_report.csv
RUN_REPORT.md
benchmark results
```

## Required implementation

Modify trace extraction so it returns exact unique item sets.

Add dataclass:

```python
@dataclass(frozen=True)
class TraceExtractionResult:
    output_path: Path
    parsed_rows: int
    skipped_rows: int
    unique_items: set[str]
    trace_hash: str
```

`extract_trace(...)` should return `TraceExtractionResult`.

For official split:

```python
train_result = extract_trace(train_dfiles, train_trace_path)
validation_result = extract_trace(valid_split_dfiles, validation_trace_path)
test_result = extract_trace(test_dfiles, test_trace_path)

unique_train = len(train_result.unique_items)
unique_validation = len(validation_result.unique_items)
unique_test = len(test_result.unique_items)
total_unique_items = len(
    train_result.unique_items
    | validation_result.unique_items
    | test_result.unique_items
)
```

For ratio split:

```python
raw_result = extract_trace(ordered_files, raw_trace_path)
total_unique_items = len(raw_result.unique_items)
```

Use `total_unique_items` to compute cache size.

Do not compute cache size from summed per-file unique counts.

---

# 4. Write real project commit and dirty state

## Current bug

Metadata currently contains:

```python
"project_commit": "unknown"
```

## Required implementation

Add helpers:

```python
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
```

Add both to metadata:

```json
{
  "project_commit": "...",
  "project_dirty": true
}
```

Also include them in `RUN_REPORT.md`.

---

# 5. Force CPU thread limits in subprocess environment

## Current bug

The current implementation uses:

```python
env.setdefault("OMP_NUM_THREADS", "1")
```

This does not override existing environment variables.

If the machine already has `OMP_NUM_THREADS=8`, each dataset subprocess can still use 8 threads, causing CPU oversubscription.

## Required implementation

Replace `setdefault` with direct assignment:

```python
env = os.environ.copy()
env["OMP_NUM_THREADS"] = "1"
env["MKL_NUM_THREADS"] = "1"
env["OPENBLAS_NUM_THREADS"] = "1"
env["NUMEXPR_NUM_THREADS"] = "1"
env["VECLIB_MAXIMUM_THREADS"] = "1"
env["PYTHONHASHSEED"] = str(seed)
```

Do not hard-code `PYTHONHASHSEED` as `0` unless seed is actually `0`.

---

# 6. Actually write `chledowski_file_discovery.txt`

## Current bug

`FILE_DISCOVERY_LOG` is defined but not actually written with detailed discovery results.

## Required behavior

The global discovery log must be written once in the main process after all parallel jobs finish.

Do not let parallel workers write directly to the same file.

Each `process_dataset(...)` should return a list of discovery records.

Example record:

```python
{
    "dataset": dataset,
    "path": str(dfile.path),
    "accepted": True,
    "split": dfile.split,
    "format_detected": dfile.format_detected,
    "item_column": dfile.item_column,
    "parsed_rows": dfile.parsed_rows,
    "skipped_rows": dfile.skipped_rows,
    "unique_items": dfile.unique_items,
    "warning": dfile.warning,
}
```

Main process writes:

```text
data/processed/chledowski_file_discovery.txt
```

Deterministic order:

```text
dataset order follows PRIMARY_DATASETS
files sorted by path
```

---

# 7. Add per-file parse details to trace report

## Current bug

`chledowski_trace_report.csv` currently does not contain enough per-file details.

## Required fields

Add these fields to `trace_report_info`:

```text
source_files
rejected_files
format_detected_per_file
item_column_per_file
parsed_rows_per_file
skipped_rows_per_file
unique_items_per_file
```

Example formatting:

```text
xalanc_train.csv:single_token_per_line|xalanc_test.csv:single_token_per_line
xalanc_train.csv:0|xalanc_test.csv:0
xalanc_train.csv:100000|xalanc_test.csv:20000
```

Do not use only `set(f.format_detected for f in valid_dfiles)` because that loses per-file information.

---

# 8. Every failure path must return `trace_report_info`

## Current bug

Some failure paths return a status dict without `trace_report_info`, so failed datasets may disappear from `chledowski_trace_report.csv`.

## Required implementation

Create helper:

```python
def make_trace_report_info(
    dataset: str,
    success: bool,
    split_mode: str,
    valid_dfiles: list[DatasetFile],
    rejected_dfiles: list[DatasetFile],
    selected_cache_size: int | None = None,
    warning: str = "",
    ...
) -> dict[str, object]:
    ...
```

Every return from `process_dataset(...)` must include:

```python
"trace_report_info": trace_report_info
```

Including:

```text
No valid trace files found
Official split requested but files not found
Subprocess timeout
Subprocess exception
Unexpected internal exception
```

---

# 9. Catch exceptions from parallel futures

## Current bug

Main currently does:

```python
for future in as_completed(futures):
    results.append(future.result())
```

If any worker raises an uncaught exception, the whole benchmark can crash and lose reports.

## Required implementation

Change to:

```python
future_to_dataset = {
    executor.submit(process_dataset, ds, args, commit_hash, code_hash, project_commit, project_dirty): ds
    for ds in datasets
}

for future in as_completed(future_to_dataset):
    ds = future_to_dataset[future]
    try:
        results.append(future.result())
    except Exception as exc:
        results.append(make_failed_run_status(
            dataset=ds,
            error_message=f"Unhandled worker exception: {exc}",
            split_mode=args.split_mode,
        ))
```

The final benchmark must still write:

```text
run_status_all_datasets.csv
RUN_REPORT.md
```

even if one dataset crashes.

---

# 10. Save selected Hedge learning rate and validation MAE

## Current problem

`src.train` prints selected Hedge eta and validation MAE, but does not save them in machine-readable output.

## Required implementation in `src/train.py`

Modify `build_results_frame(...)` to accept:

```python
selected_hedge_learning_rate: float
validation_mae: float | None
```

Add these fields to every row:

```text
selected_hedge_learning_rate
validation_mae
```

Example:

```python
result_rows.append({
    "algorithm": cache_result.algorithm_name,
    "cache_misses": cache_result.cache_misses,
    "total_requests": cache_result.total_requests,
    "miss_ratio": cache_result.miss_ratio,
    "empirical_competitive_ratio": competitive_ratio,
    "improvement_vs_mark_percent": improvement_vs_mark,
    "selected_hedge_learning_rate": selected_hedge_learning_rate,
    "validation_mae": validation_mae if validation_mae is not None else "",
})
```

Also write an optional per-run file:

```text
<processed_dir>/training_metadata.json
```

with:

```json
{
  "selected_hedge_learning_rate": 0.3,
  "validation_mae": 123.456
}
```

## Required implementation in `scripts/benchmark_chledowski.py`

Add these fields to `summary_all_datasets.csv`:

```text
selected_hedge_learning_rate
validation_mae
```

---

# 11. Read base config instead of hard-coding model/data/hedge params

## Current problem

The benchmark script currently hard-codes:

```text
seed = 42
recent_window_size = 128
max_training_rows = 50000
model.learning_rate = 0.05
model.n_estimators = 100
model.max_depth = 3
hedge.candidate_learning_rates = [0.1, 0.3, 0.7, 1.0]
```

This means changes to `configs/config.yaml` may not affect benchmark runs.

## Required implementation

Add CLI:

```bash
--base-config configs/config.yaml
```

Default:

```text
configs/config.yaml
```

Load base config once in main:

```python
with open(args.base_config, "r", encoding="utf-8") as f:
    base_config = yaml.safe_load(f)
```

For each dataset:

```python
config_dict = copy.deepcopy(base_config)
```

Then override only benchmark-specific fields:

```python
config_dict["paths"] = {
    "processed_dir": str(run_dir),
    ... trace paths ...
}
config_dict["data"]["train_ratio"] = args.train_ratio
config_dict["data"]["validation_ratio"] = args.validation_ratio
config_dict["cache"]["cache_size"] = selected_cache_size
config_dict["hedge"]["feedback_mode"] = "delayed"
```

Do not hard-code model params in the script.

Add base config hash to metadata:

```json
{
  "base_config_path": "configs/config.yaml",
  "base_config_hash": "..."
}
```

---

# 12. Strengthen file discovery beyond substring matching

## Current issue

Current discovery still uses:

```python
dataset_name in p.name
```

This may include stats, metadata, backup, or report files.

## Required improvement

Add rejection rules before parsing:

Reject files if name contains obvious metadata/report terms:

```text
readme
summary
stats
stat
metadata
report
result
log
png
jpg
pdf
md
json
yaml
yml
```

Allow likely trace/data extensions only, for example:

```text
.txt
.csv
.tsv
.trace
.dat
```

If the dataset repo has files without extension, allow them only if parser succeeds.

Keep parser validation as final authority, but do not feed obvious non-trace files into parsing.

Record every rejected file in `chledowski_file_discovery.txt` with a reason.

---

# 13. Deterministic and complete reports

## Required updates

### `summary_all_datasets.csv`

Must contain only algorithms:

```text
Belady/OPT
MARK
HedgeFullDelayed(...)
```

Fields:

```text
dataset
algorithm
cache_misses
total_requests
miss_ratio
empirical_competitive_ratio
improvement_vs_mark_percent
selected_cache_size
split_mode
seed
selected_hedge_learning_rate
validation_mae
```

### `run_status_all_datasets.csv`

Must include:

```text
dataset
success
return_code
runtime_seconds
config_path
metadata_path
stdout_log
stderr_log
error_message
skipped_due_to_cache
```

### `RUN_REPORT.md`

Must include:

```text
project_commit
project_dirty
dataset_ref_requested
dataset_commit_used
jobs
split_mode actual per dataset
cache_size rule
failed datasets
```

---

# 14. Verification commands

After implementing fixes, run these commands.

## Small test

```bash
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 1 --force
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 2 --force
```

Compare results:

```text
summary_all_datasets.csv from jobs=1 and jobs=2 must have identical:
- dataset
- algorithm
- cache_misses
- miss_ratio
- selected_cache_size
- selected_hedge_learning_rate
```

## Skip test

Run twice:

```bash
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1 --force
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1
```

Expected second run:

```text
skipped_due_to_cache=True
```

Then change a source file or config value and rerun without `--force`.

Expected:

```text
skipped_due_to_cache=False
```

## Config mutation test

Before and after a benchmark run:

```bash
git diff -- configs/config.yaml configs/config.yaml.bak
```

Expected:

```text
empty diff
```

## Failure path test

Run with a fake dataset:

```bash
python scripts/benchmark_chledowski.py --datasets does_not_exist --jobs 1 --force
```

Expected:

```text
script exits normally
run_status_all_datasets.csv exists
RUN_REPORT.md exists
chledowski_trace_report.csv includes does_not_exist as failed
```

---

# 15. Final acceptance checklist

The agent's work is complete only if all are true:

```text
[ ] No `.pop("trace_hashes")` or any equivalent trace-hash removal during metadata comparison.
[ ] Skip requires previous run success.
[ ] generated trace hashes are in metadata.json.
[ ] source file hashes are in metadata.json.
[ ] project_commit is not hard-coded to unknown when git is available.
[ ] total_unique_items is computed from real item sets.
[ ] selected_cache_size uses exact total_unique_items.
[ ] CPU thread env vars are assigned, not setdefault.
[ ] PYTHONHASHSEED equals configured seed.
[ ] chledowski_file_discovery.txt is written.
[ ] chledowski_trace_report.csv contains failed datasets too.
[ ] chledowski_trace_report.csv has per-file parse details.
[ ] future.result() is wrapped in try/except.
[ ] selected_hedge_learning_rate is saved in benchmark_results.csv and summary_all_datasets.csv.
[ ] validation_mae is saved when available.
[ ] benchmark script loads --base-config instead of hard-coding model params.
[ ] summary_all_datasets.csv contains only Belady/OPT, MARK, HedgeFullDelayed rows.
[ ] configs/config.yaml and configs/config.yaml.bak remain unchanged.
[ ] jobs=1 and jobs=2 produce identical benchmark numbers for the same datasets.
```

Do not merge `feature/benchmark-automation` into `main` until this checklist passes.
