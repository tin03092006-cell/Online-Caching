# AI Agent Task Spec: Fix Benchmark Logic and Parallelize Dataset Runs

This file is written for an AI coding agent. The agent must modify the repository automatically while preserving the intended experimental goal.

The benchmark goal is strictly:

```text
HedgeFullDelayed vs Belady/OPT vs MARK
```

Do **not** add standalone benchmark baselines for LRU, LFU, FIFO, or RawML. They are internal experts inside HedgeFullDelayed only.

---

## 0. Non-negotiable requirements

The agent must implement the following without changing the scientific meaning of the benchmark.

### Must preserve

1. Benchmark output must contain exactly these main algorithms:

```text
Belady/OPT
MARK
HedgeFullDelayed
```

2. HedgeFullDelayed may still use internal experts:

```text
LRU
LFU
FIFO
MARK
RawML
```

3. `Belady/OPT` remains the offline optimum baseline on the test trace.
4. `MARK` remains the online baseline.
5. `HedgeFullDelayed` remains the proposed algorithm.
6. The code must run locally on CPU.
7. Benchmarking multiple datasets must run in parallel to maximize CPU usage.
8. `configs/config.yaml` must not be modified during benchmark execution.
9. Every dataset run must be isolated in its own run directory.
10. Old benchmark results must not be reused unless metadata proves that they match the current code/config/dataset.

---

## 1. High-level target behavior

After implementation, this command should work:

```bash
python scripts/benchmark_chledowski.py --jobs auto --force
```

Expected behavior:

1. Prepare all Chledowski datasets.
2. Create one isolated run directory per dataset:

```text
data/processed/benchmark_runs/<dataset>/
```

3. For each dataset, write run-local files only:

```text
data/processed/benchmark_runs/<dataset>/config.yaml
data/processed/benchmark_runs/<dataset>/trace.txt
# or, if official split mode is used:
data/processed/benchmark_runs/<dataset>/train_trace.txt
data/processed/benchmark_runs/<dataset>/validation_trace.txt
data/processed/benchmark_runs/<dataset>/test_trace.txt
```

4. Run datasets concurrently with CPU parallelism.
5. Write per-dataset results:

```text
data/processed/benchmark_runs/<dataset>/benchmark_results.csv
data/processed/benchmark_runs/<dataset>/train_features.csv
data/processed/benchmark_runs/<dataset>/validation_features.csv
data/processed/benchmark_runs/<dataset>/stdout.log
data/processed/benchmark_runs/<dataset>/stderr.log
data/processed/benchmark_runs/<dataset>/run_status.txt
data/processed/benchmark_runs/<dataset>/metadata.json
```

6. Write global reports:

```text
data/processed/chledowski_trace_report.csv
data/processed/summary_all_datasets.csv
data/processed/run_status_all_datasets.csv
data/processed/RUN_REPORT.md
```

7. `git diff configs/config.yaml` must be empty after benchmark execution.

---

## 2. Required code changes

## 2.1 Fix MARK expert side effect inside HedgeFullDelayed

### Current problem

In `src/model.py`, `choose_mark_eviction(...)` mutates `marked_items` by clearing it when all cache items are marked.

That is correct for standalone MARK, but dangerous inside HedgeFullDelayed because `propose_expert_evictions(...)` calls MARK only to ask for a vote. The vote must not mutate the actual Hedge state unless the algorithm explicitly intends that.

### Required implementation

Refactor MARK logic into explicit stateful and pure operations.

Acceptable minimal implementation:

```python
def choose_mark_eviction(
    cache_items: set[str],
    marked_items: set[str],
    random_generator: random.Random,
    *,
    mutate_phase: bool = True,
) -> str:
    unmarked_items = sorted(cache_items - marked_items)

    if not unmarked_items:
        if mutate_phase:
            marked_items.clear()
            unmarked_items = sorted(cache_items)
        else:
            unmarked_items = sorted(cache_items)

    return random_generator.choice(unmarked_items)
```

Then:

- standalone `run_mark_cache(...)` should call with `mutate_phase=True`;
- `propose_expert_evictions(...)` should call with `mutate_phase=False`, or use a copied MARK state.

Better implementation:

Create a `MarkExpertState` object with explicit methods:

```python
class MarkExpertState:
    def propose_eviction(...): ...
    def observe_request(...): ...
    def observe_eviction(...): ...
```

### Acceptance criteria

Add a test or assertable behavior:

```python
before = set(marked_items)
choose_mark_eviction(cache_items, marked_items, rng, mutate_phase=False)
assert marked_items == before
```

Standalone MARK behavior must remain unchanged.

---

## 2.2 Stop mutating `configs/config.yaml`

### Current problem

`scripts/benchmark_chledowski.py` rewrites the real project config while benchmarking each dataset.

This is not allowed.

### Required implementation

The benchmark script must create a fresh per-dataset config file:

```text
data/processed/benchmark_runs/<dataset>/config.yaml
```

The per-dataset config must set:

```yaml
paths:
  raw_trace: data/processed/benchmark_runs/<dataset>/trace.txt
  processed_dir: data/processed/benchmark_runs/<dataset>
```

If official split mode is implemented, use:

```yaml
paths:
  train_trace: data/processed/benchmark_runs/<dataset>/train_trace.txt
  validation_trace: data/processed/benchmark_runs/<dataset>/validation_trace.txt
  test_trace: data/processed/benchmark_runs/<dataset>/test_trace.txt
  processed_dir: data/processed/benchmark_runs/<dataset>
```

Then call:

```bash
python -m src.train --config data/processed/benchmark_runs/<dataset>/config.yaml
```

### Acceptance criteria

After running the benchmark:

```bash
git diff -- configs/config.yaml configs/config.yaml.bak
```

must be empty.

Remove the need for `CONFIG_BACKUP` and `atexit` cleanup.

---

## 2.3 Fix dataset split handling

### Current problem

The script orders files as:

```text
train -> valid -> test -> other
```

then concatenates them into one trace, and `src.train` splits that trace again by ratio. This can corrupt official train/validation/test boundaries.

### Required implementation

Add split modes:

```bash
--split-mode auto
--split-mode official
--split-mode ratio
```

Default:

```bash
--split-mode auto
```

### Behavior

#### `official`

Use detected train/valid/test files directly.

Do not split again by ratio.

Create:

```text
train_trace.txt
validation_trace.txt
test_trace.txt
```

#### `ratio`

Concatenate valid request files into one trace:

```text
trace.txt
```

Then let `src.train` split by configured ratios.

#### `auto`

If train/valid/test files are confidently detected, use `official`.

Otherwise use `ratio`.

### Required change in `src.train`

Add support for explicit split files.

Suggested function:

```python
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
```

Then `run_pipeline(...)` must call this function instead of always loading one raw trace and splitting it.

### Acceptance criteria

The report must include:

```text
split_mode
train_trace_source_files
validation_trace_source_files
test_trace_source_files
```

For official split mode, the report must not claim that ratio split was used.

---

## 2.4 Make split ratio and cache-size selection explicit

### Current problem

`configs/config.yaml` contains:

```yaml
train_ratio: 0.6
validation_ratio: 0.2
cache_size: 100
```

But the benchmark script currently overrides split ratios and cache size.

### Required implementation

Add CLI/config options:

```bash
--train-ratio 0.8
--validation-ratio 0.1
--cache-mode ratio
--cache-ratio 0.01
--min-cache-size 16
--max-cache-size 512
--fixed-cache-size 100
```

Default benchmark behavior can remain:

```text
train_ratio = 0.8
validation_ratio = 0.1
cache_mode = ratio
cache_ratio = 0.01
min_cache_size = 16
max_cache_size = 512
```

But it must be explicit in:

- per-dataset `config.yaml`;
- `metadata.json`;
- `chledowski_trace_report.csv`;
- `RUN_REPORT.md`.

### Acceptance criteria

The user must be able to see exactly why a dataset got a given cache size.

Example report fields:

```text
cache_mode
cache_ratio
min_cache_size
max_cache_size
selected_cache_size
```

---

## 2.5 Prevent stale result reuse

### Current problem

The script skips a dataset if `benchmark_results.csv` and `run_status.txt` already exist.

This is unsafe.

### Required implementation

Create one `metadata.json` per dataset run.

It must include at least:

```json
{
  "project_commit": "...",
  "dataset_commit": "...",
  "script_hash": "...",
  "src_hash": "...",
  "config_hash": "...",
  "trace_hashes": {
    "train": "...",
    "validation": "...",
    "test": "..."
  },
  "dataset": "...",
  "split_mode": "...",
  "cache_mode": "...",
  "selected_cache_size": 123,
  "seed": 42,
  "model": {...},
  "hedge": {...}
}
```

Skip only if:

1. `benchmark_results.csv` exists;
2. `run_status.txt` indicates success;
3. `metadata.json` exists;
4. all current metadata fields match the previous metadata.

Add CLI:

```bash
--force
```

If `--force` is passed, rerun all datasets regardless of metadata.

### Acceptance criteria

Changing any of these must force rerun:

- `src/model.py`;
- `src/data.py`;
- `src/train.py`;
- `scripts/benchmark_chledowski.py`;
- dataset commit;
- selected cache size;
- split mode;
- model params;
- Hedge candidate learning rates.

---

## 2.6 Pin external dataset repo

### Current problem

The script uses latest dataset repo state via `git pull`.

### Required implementation

Add CLI:

```bash
--dataset-ref <commit-or-branch-or-tag>
```

Behavior:

- If `--dataset-ref` is provided, checkout exactly that ref.
- If not provided, current behavior may use default branch, but the report must say it is unpinned.

Suggested logic:

```bash
git fetch --all
git checkout <dataset-ref>
```

### Acceptance criteria

The final report must include:

```text
dataset_ref_requested
dataset_commit_used
```

---

## 2.7 Harden file discovery and parsing

### Current problem

Dataset file discovery uses substring matching:

```python
dataset_name in p.name
```

Parser format is inferred from the first file and reused for all files.

### Required implementation

Add a dataset file descriptor structure:

```python
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
```

Validation requirements:

1. Only include files that can be parsed as request traces.
2. Reject metadata/stat/report files.
3. Detect split from filename only when confident:

```text
train
valid
validation
val
test
```

4. Validate every selected file, not only the first one.
5. Write file-discovery details to:

```text
data/processed/chledowski_file_discovery.txt
```

### Acceptance criteria

For each dataset, `chledowski_trace_report.csv` must include:

```text
source_files
rejected_files
format_detected_per_file
parsed_rows_per_file
skipped_rows_per_file
warning
```

---

## 2.8 Fix Markdown report formatting bugs

### Current problem

The script uses conditional expressions inside string concatenation, which can produce malformed lines.

### Required implementation

Replace expressions like:

```python
f.write("- Fallback usage: " + ", ".join(fallbacks) if fallbacks else "None" + "\n")
```

with:

```python
fallback_text = ", ".join(fallbacks) if fallbacks else "None"
f.write(f"- Fallback usage: {fallback_text}\n")
```

Do the same for failed datasets and any similar report logic.

### Acceptance criteria

`RUN_REPORT.md` must always contain labels:

```text
- Fallback usage: ...
- Failed datasets: ...
```

regardless of whether the corresponding list is empty.

---

## 3. CPU parallelism requirement

The benchmark must run multiple datasets in parallel to maximize CPU usage.

### 3.1 Add `--jobs`

Add CLI option:

```bash
--jobs auto
--jobs 1
--jobs 2
--jobs 4
...
```

Default:

```text
auto
```

Suggested behavior:

```python
if jobs == "auto":
    max_workers = os.cpu_count() or 1
else:
    max_workers = int(jobs)
```

Because each dataset run is a separate Python subprocess and the current ML model is scikit-learn `GradientBoostingRegressor`, dataset-level multiprocessing is the right way to use CPU cores.

### 3.2 Avoid CPU oversubscription

When launching each subprocess, set environment variables:

```python
env = os.environ.copy()
env.setdefault("OMP_NUM_THREADS", "1")
env.setdefault("MKL_NUM_THREADS", "1")
env.setdefault("OPENBLAS_NUM_THREADS", "1")
env.setdefault("NUMEXPR_NUM_THREADS", "1")
env.setdefault("VECLIB_MAXIMUM_THREADS", "1")
```

Reason:

- We parallelize across datasets.
- Each dataset process should not also spawn many BLAS/OpenMP threads.
- This prevents CPU oversubscription and unstable runtimes.

### 3.3 Use isolated subprocesses

Do not run all datasets inside the same Python process.

Use one subprocess per dataset:

```bash
python -m src.train --config data/processed/benchmark_runs/<dataset>/config.yaml
```

This ensures:

- independent outputs;
- independent logs;
- no shared mutable global trace path;
- easier failure isolation;
- easier parallel execution.

### 3.4 Recommended orchestration

Use `concurrent.futures.ThreadPoolExecutor` to orchestrate subprocesses.

Reason:

- The heavy computation happens in subprocesses.
- Threads only wait for subprocess completion.
- This avoids pickling large data structures.

Suggested structure:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [
        executor.submit(run_dataset_subprocess, dataset_job)
        for dataset_job in dataset_jobs
    ]

    for future in as_completed(futures):
        run_status = future.result()
        run_statuses.append(run_status)
```

### 3.5 Logging during parallel run

Each dataset must write separate logs:

```text
stdout.log
stderr.log
run_status.txt
```

The global console output should show compact status only:

```text
[START] xalanc
[DONE] xalanc success=True runtime=123.45s
[FAIL] mcf return_code=1
```

Avoid interleaving full subprocess output in the main terminal.

### 3.6 Acceptance criteria for parallelism

The following must work:

```bash
python scripts/benchmark_chledowski.py --jobs 1 --force
python scripts/benchmark_chledowski.py --jobs 2 --force
python scripts/benchmark_chledowski.py --jobs auto --force
```

For the same seed, dataset-level results must be identical regardless of `--jobs`, except for ordering in logs.

The final CSV files must be sorted deterministically by dataset and algorithm.

---

## 4. Required report outputs

## 4.1 `chledowski_trace_report.csv`

Must include at least:

```text
requested_dataset
actual_dataset
success
split_mode
source_files
rejected_files
number_of_requests_train
number_of_requests_validation
number_of_requests_test
number_of_unique_items_train
number_of_unique_items_validation
number_of_unique_items_test
cache_mode
cache_ratio
min_cache_size
max_cache_size
selected_cache_size
format_detected
item_column
warning
```

## 4.2 `summary_all_datasets.csv`

Must include benchmark rows only for:

```text
Belady/OPT
MARK
HedgeFullDelayed
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
```

## 4.3 `run_status_all_datasets.csv`

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

## 4.4 `RUN_REPORT.md`

Must include:

```text
1. Run Metadata
2. Dataset Repository Metadata
3. Parallelism Settings
4. Dataset Preparation Summary
5. Config Summary
6. Benchmark Results
7. HedgeFullDelayed vs MARK
8. Failed Datasets
9. Reproducibility Metadata
10. Final Conclusion
```

The report must clearly say:

```text
Standalone baselines: Belady/OPT, MARK
Proposed algorithm: HedgeFullDelayed
Internal experts: LRU, LFU, FIFO, MARK, RawML
```

---

## 5. Determinism and reproducibility requirements

The same command should produce identical benchmark numbers when run twice with:

- same project commit;
- same dataset commit;
- same config;
- same seed;
- same split mode;
- same cache-size rule.

Parallel execution must not change benchmark numbers.

Required deterministic ordering:

1. Sort datasets by `PRIMARY_DATASETS` order.
2. Sort files within each split by path.
3. Sort final CSV rows by:

```text
dataset, algorithm
```

4. Sort report dataset sections by `PRIMARY_DATASETS` order.

---

## 6. Suggested implementation order for the AI agent

Follow this exact order.

### Step 1 — Refactor MARK vote side effect

Modify `src/model.py` so MARK expert vote inside HedgeFullDelayed cannot mutate shared actual MARK state accidentally.

Run a small local sanity check.

### Step 2 — Add explicit split-file support to `src.train`

Add support for:

```yaml
paths.train_trace
paths.validation_trace
paths.test_trace
```

Keep backward compatibility with:

```yaml
paths.raw_trace
```

### Step 3 — Rewrite benchmark script to use per-dataset run directories

Remove config mutation and backup/restore logic.

Every dataset gets its own:

```text
config.yaml
trace files
processed outputs
logs
metadata.json
```

### Step 4 — Add metadata-based skip and `--force`

Do not trust existing result files unless metadata matches.

### Step 5 — Add dataset-level parallel execution

Implement `--jobs` and run dataset subprocesses concurrently.

Set BLAS/OpenMP thread env vars to `1` per subprocess.

### Step 6 — Harden parser and file discovery

Validate every selected file.

Reject suspicious files.

Write detailed discovery logs.

### Step 7 — Fix reports

Fix Markdown formatting bugs.

Add global `run_status_all_datasets.csv`.

Ensure deterministic sorting.

### Step 8 — Run verification commands

Run:

```bash
python scripts/benchmark_chledowski.py --jobs 1 --force
python scripts/benchmark_chledowski.py --jobs 2 --force
```

If full benchmark is too slow, test first with two datasets using:

```bash
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 2 --force
```

If `--datasets` does not exist yet, add it.

---

## 7. Required CLI options

Add these to `scripts/benchmark_chledowski.py`:

```bash
--datasets xalanc,mcf
--jobs auto
--force
--dataset-ref <commit-or-tag>
--split-mode auto|official|ratio
--cache-mode ratio|fixed
--cache-ratio 0.01
--min-cache-size 16
--max-cache-size 512
--fixed-cache-size 100
--train-ratio 0.8
--validation-ratio 0.1
--timeout-seconds 3600
```

Defaults:

```text
--datasets all PRIMARY_DATASETS
--jobs auto
--split-mode auto
--cache-mode ratio
--cache-ratio 0.01
--min-cache-size 16
--max-cache-size 512
--train-ratio 0.8
--validation-ratio 0.1
--timeout-seconds 3600
```

---

## 8. Tests / sanity checks the agent must add or manually run

At minimum, manually verify these conditions.

### Test 1 — Config is not mutated

Before:

```bash
git diff -- configs/config.yaml configs/config.yaml.bak
```

Run benchmark.

After:

```bash
git diff -- configs/config.yaml configs/config.yaml.bak
```

Expected: empty diff.

### Test 2 — MARK vote purity

Calling MARK vote inside Hedge must not clear actual `marked_items` unless the standalone MARK algorithm explicitly starts a new phase.

### Test 3 — Parallel result consistency

Run the same small dataset set twice:

```bash
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 1 --force
python scripts/benchmark_chledowski.py --datasets xalanc,mcf --jobs 2 --force
```

Expected:

```text
same cache_misses
same miss_ratio
same selected eta
same selected cache_size
```

### Test 4 — No stale reuse after code change

Change a source file or metadata-relevant config.

Run without `--force`.

Expected:

```text
script reruns affected datasets
```

### Test 5 — Explicit skip only when metadata matches

Run twice without changing anything:

```bash
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1
python scripts/benchmark_chledowski.py --datasets xalanc --jobs 1
```

Expected second run:

```text
skipped_due_to_cache=True
```

### Test 6 — Final summary contains only intended benchmark algorithms

Check `summary_all_datasets.csv`.

Allowed algorithms:

```text
Belady/OPT
MARK
HedgeFullDelayed(...)
```

Do not include standalone LRU/LFU/FIFO/RawML rows.

---

## 9. Do not do these things

The agent must not:

1. Add LRU/LFU/FIFO/RawML as standalone benchmark baselines.
2. Modify `configs/config.yaml` during benchmark execution.
3. Use one global `data/raw/trace.txt` for parallel dataset runs.
4. Let different datasets write to the same `processed_dir` simultaneously.
5. Reuse old results only because `benchmark_results.csv` exists.
6. Use unpinned dataset input without reporting that it is unpinned.
7. Print full subprocess logs into the shared parallel console.
8. Make parallelism change benchmark numbers.

---

## 10. Final acceptance checklist

The implementation is accepted only if all are true:

```text
[ ] HedgeFullDelayed benchmark still compares only against Belady/OPT and MARK.
[ ] LRU/LFU/FIFO/RawML remain internal experts only.
[ ] MARK expert vote inside Hedge has no unintended state mutation.
[ ] Official train/valid/test splits are not accidentally concatenated and split again.
[ ] Ratio split mode still works for datasets without official splits.
[ ] configs/config.yaml is never modified by the benchmark script.
[ ] Each dataset has an isolated run directory.
[ ] Each dataset has its own config, trace files, logs, metadata, and outputs.
[ ] --jobs auto uses CPU cores by running datasets in parallel.
[ ] Per-subprocess BLAS/OpenMP thread env vars are limited to avoid oversubscription.
[ ] Existing results are reused only when metadata matches.
[ ] --force reruns all selected datasets.
[ ] Dataset repo commit is recorded, and --dataset-ref can pin it.
[ ] chledowski_trace_report.csv is written.
[ ] summary_all_datasets.csv is written.
[ ] run_status_all_datasets.csv is written.
[ ] RUN_REPORT.md is correctly formatted.
[ ] Final CSV/report ordering is deterministic.
[ ] Running with --jobs 1 and --jobs 2 gives the same benchmark numbers.
```
