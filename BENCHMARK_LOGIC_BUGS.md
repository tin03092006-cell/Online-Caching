# Benchmark Logic Bugs and Experimental Risks

This document lists only logic bugs or experimental-design issues that can directly affect benchmark correctness, benchmark numbers, reproducibility, or interpretation.

It intentionally excludes pure clean-code / clean-architecture comments unless they can change or invalidate the benchmark.

Reviewed scope:

- `src/data.py`
- `src/model.py`
- `src/train.py`
- `scripts/benchmark_chledowski.py`
- `configs/config.yaml` and `configs/config.yaml.bak` where they affect benchmark execution

---

## P0 — Must fix before trusting benchmark

### 1. MARK expert mutates shared state while Hedge is only asking for a vote

**Location**

- `src/model.py`
- `choose_mark_eviction(...)`
- `propose_expert_evictions(...)`
- `run_hedge_full_cache(...)`

**Problem**

`choose_mark_eviction(...)` is not a pure vote function. If all cache items are marked, it calls:

```python
marked_items.clear()
```

But `propose_expert_evictions(...)` calls `choose_mark_eviction(...)` merely to collect the MARK expert's proposed eviction. That call can reset the shared `marked_items` state even when HedgeFullDelayed does not actually follow MARK's eviction vote.

**Why this affects benchmark**

This changes the trajectory of HedgeFullDelayed. The state of MARK inside Hedge can be reset just because MARK was consulted as an expert, not because the final Hedge eviction was MARK's choice.

Therefore, the measured miss count of HedgeFullDelayed may depend on an unintended side effect.

**Expected fix**

Separate MARK proposal from MARK state mutation.

Possible fixes:

1. Make `choose_mark_eviction(...)` pure and return both the proposed item and whether a new phase would start.
2. Give MARK its own expert state object inside Hedge instead of sharing `marked_items` with the actual Hedge cache.
3. At minimum, pass a copied set into the MARK expert vote if the state must not be mutated:

```python
mark_vote = choose_mark_eviction(
    cache_items=cache_items,
    marked_items=set(marked_items),
    random_generator=random_generator,
)
```

However, the cleaner fix is an explicit `MarkExpertState` object.

---

### 2. Chledowski train/valid/test files are concatenated, then split again

**Location**

- `scripts/benchmark_chledowski.py`
- `order_splits(...)`
- `infer_format_and_parse(...)`
- `run_single_dataset(...)`
- `src/train.py::split_trace(...)`

**Problem**

The script discovers dataset files, orders them as:

```text
train -> valid -> test -> other
```

then concatenates them into one `trace.txt`.

After that, `src.train` loads this single trace and splits it again by ratio.

**Why this affects benchmark**

If the external dataset already provides train/valid/test splits, this destroys the official split boundaries.

Possible consequences:

- original validation/test requests can enter training;
- the final test set may not match the dataset's intended test set;
- benchmark numbers become hard to compare with other papers or repos;
- the model may be evaluated on a distribution different from the intended one.

This is one of the most important experimental-validity risks.

**Expected fix**

Do not concatenate official splits and split again.

Use one of these approaches:

```text
Option A:
Use official train file as train,
official valid file as validation,
official test file as test.
```

or:

```text
Option B:
If a dataset has no official split,
concatenate all request files and split by configured ratio.
```

The report must clearly say which mode was used.

---

### 3. Existing benchmark results are reused without checking code/config/dataset hashes

**Location**

- `scripts/benchmark_chledowski.py`
- `run_single_dataset(...)`

**Problem**

If this directory already contains:

```text
data/processed/benchmark_runs/<dataset>/benchmark_results.csv
data/processed/benchmark_runs/<dataset>/run_status.txt
```

then the script skips training and treats the dataset as completed.

It does not verify:

- current project commit;
- current source code content;
- current `configs/config.yaml`;
- current Chledowski dataset commit;
- cache size;
- model hyperparameters;
- Hedge candidate learning rates;
- train/validation/test split mode.

**Why this affects benchmark**

After changing the algorithm, model, config, or dataset, the script may still report old results.

This can completely invalidate a benchmark table.

**Expected fix**

Write a metadata file for every dataset run, for example:

```yaml
project_commit: ...
dataset_commit: ...
config_hash: ...
code_hash: ...
script_hash: ...
cache_size: ...
split_mode: ...
```

Skip only if all metadata match the current run.

A safer default is: do not skip unless the user passes `--resume`.

---

### 4. Benchmark script mutates `configs/config.yaml` in place

**Location**

- `scripts/benchmark_chledowski.py`
- `cleanup(...)`
- `run_single_dataset(...)`

**Problem**

The script copies `configs/config.yaml` to `configs/config.yaml.bak`, then repeatedly rewrites the real `configs/config.yaml` while benchmarking each dataset.

It changes at least:

```yaml
paths.raw_trace
data.train_ratio
data.validation_ratio
cache.cache_size
hedge.feedback_mode
```

**Why this affects benchmark**

This can cause:

- benchmark result depending on the last modified config;
- dirty working tree;
- accidental future runs using benchmark-modified config;
- broken restoration if the process is killed before `atexit` runs;
- stale restore if `config.yaml.bak` was created earlier and no longer matches current config.

**Expected fix**

Never mutate the project config during benchmark.

For each dataset, create a temporary run-specific config:

```text
data/processed/benchmark_runs/<dataset>/config.yaml
```

Then call:

```bash
python -m src.train --config data/processed/benchmark_runs/<dataset>/config.yaml
```

---

### 5. Split ratios differ between config and benchmark script

**Location**

- `configs/config.yaml`
- `scripts/benchmark_chledowski.py`

**Problem**

The default config contains:

```yaml
data:
  train_ratio: 0.6
  validation_ratio: 0.2
```

But the Chledowski script overwrites them with:

```yaml
train_ratio: 0.8
validation_ratio: 0.1
```

and reports `0.8 / 0.1 / 0.1`.

**Why this affects benchmark**

Running:

```bash
python -m src.train --config configs/config.yaml
```

and running:

```bash
python scripts/benchmark_chledowski.py
```

can produce different benchmark results from different splits.

This is not necessarily wrong, but it is currently implicit and easy to misunderstand.

**Expected fix**

Choose one source of truth:

1. The script should read split ratios from config and report them.
2. Or the script should create an explicit per-run benchmark config and say it overrides default config.

---

## P1 — High-impact benchmark risks

### 6. Dataset repository is pulled from latest HEAD, not pinned before running

**Location**

- `scripts/benchmark_chledowski.py`
- `manage_repo(...)`

**Problem**

If the dataset repo already exists, the script runs:

```bash
git pull
```

Then it records the resulting commit hash.

**Why this affects benchmark**

The input dataset may change between two benchmark runs.

Recording the commit after pulling is useful for audit, but it does not guarantee reproducibility unless the benchmark also allows pinning that commit.

**Expected fix**

Add a config/CLI option:

```bash
--dataset-ref <commit-or-tag>
```

Then run:

```bash
git fetch
git checkout <dataset-ref>
```

The report should include the exact dataset commit.

---

### 7. Dataset file discovery uses substring matching only

**Location**

- `scripts/benchmark_chledowski.py`
- `discover_files(dataset_name)`

**Problem**

A file is selected if:

```python
dataset_name in p.name
```

There is no validation of extension, directory, split type, or file schema before selection.

**Why this affects benchmark**

This can accidentally include unrelated files whose names contain the dataset name.

Possible examples:

```text
xalanc_notes.txt
xalanc_stats.csv
old_xalanc_backup.trace
xalanc_metadata.json
```

If such a file is parseable, it may silently pollute the request trace.

**Expected fix**

Use stricter discovery rules:

- allowed extensions;
- known split names;
- expected directory pattern;
- explicit manifest when possible;
- validation of parsed request count and schema per file.

---

### 8. Trace format is inferred from only the first file and first 500 non-empty lines

**Location**

- `scripts/benchmark_chledowski.py`
- `infer_format_and_parse(files, output_path)`

**Problem**

The parser infers delimiter, header, and item column from the first candidate file only, using at most the first 500 non-empty lines.

Then it applies that inferred format to all files.

**Why this affects benchmark**

If later files have:

- a different delimiter;
- a different column order;
- extra header/comment lines;
- malformed rows;
- a different trace format;

then requests can be parsed incorrectly or silently skipped.

This changes trace length, unique item count, selected cache size, and all benchmark miss counts.

**Expected fix**

Validate every file before concatenation.

For each file, report:

```text
format_detected
item_column
parsed_rows
skipped_rows
number_of_unique_items
```

Fail fast if files in the same dataset have incompatible formats.

---

### 9. Parser may reject valid no-header multi-column traces with non-numeric first column

**Location**

- `scripts/benchmark_chledowski.py`
- `infer_format_and_parse(...)`

**Problem**

For multi-column traces, if the first token of the first line is not numeric and not hexadecimal-like, the parser assumes the first line is a header.

If the file is actually no-header but has string IDs in the first column, the parser can misclassify it as a header table and fail to infer the item column.

**Why this affects benchmark**

A valid dataset may be marked as failed or parsed with the wrong column.

This affects which datasets appear in the final summary and may bias the benchmark toward only successfully parsed traces.

**Expected fix**

Separate header detection from data-type detection.

Use stronger checks:

- known header names;
- repeated schema over many rows;
- optional user-specified item column;
- explicit failure message with sample rows.

---

### 10. Training rows are prefix-biased because `max_training_rows` stops collection early

**Location**

- `src/data.py`
- `build_training_frame(...)`
- `configs/config.yaml`

**Problem**

`build_training_frame(...)` stops adding rows once `max_training_rows` is reached.

Since rows are collected sequentially from the beginning of the training trace, large traces train the ML model mostly on the early part of the train split.

**Why this affects benchmark**

If request distribution shifts over time, RawML and therefore HedgeFullDelayed may be trained on a biased prefix of the trace.

This can significantly affect HedgeFullDelayed's miss count.

**Expected fix**

Use one of these:

1. Reservoir sampling over the whole train split.
2. Uniform sampling over decision points.
3. Time-stratified sampling.
4. Increase/report `max_training_rows` and state clearly that the sample is prefix-based.

---

### 11. RawML is trained on LRU-generated cache states but used inside HedgeFullDelayed states

**Location**

- `src/data.py`
- `build_training_frame(...)`
- `src/model.py`
- `choose_raw_ml_eviction(...)`
- `run_hedge_full_cache(...)`

**Problem**

The training frame is generated by simulating a cache that evicts with LRU.

But at benchmark time, RawML is used inside HedgeFullDelayed, whose cache state is generated by the weighted Hedge decisions.

**Why this affects benchmark**

The model is trained on one state distribution but evaluated on another.

This is not automatically a bug, but it can strongly affect the empirical result and must be documented. If the distribution shift is large, RawML expert votes can be poor and may distort Hedge behavior.

**Expected fix**

At minimum, rename/document the training generator as LRU-state-based.

Better options:

1. Generate training rows from several policies, not only LRU.
2. Generate training rows from a warm-up Hedge run.
3. Treat this explicitly as an experimental design choice in the report.

---

### 12. Cache size is selected by script heuristic, not by config

**Location**

- `scripts/benchmark_chledowski.py`
- `run_single_dataset(...)`
- `configs/config.yaml`

**Problem**

The config has:

```yaml
cache:
  cache_size: 100
```

But the Chledowski script overrides cache size per dataset using:

```python
cache_size = min(512, max(16, int(0.01 * uniq_items)))
```

**Why this affects benchmark**

The benchmark result depends on this heuristic, not on the config.

This is acceptable only if the report clearly states that cache size is selected automatically as approximately 1% of unique items, with lower/upper caps.

Otherwise, users may think they benchmarked `cache_size: 100` when they did not.

**Expected fix**

Make cache-size mode explicit:

```yaml
cache:
  mode: ratio
  ratio: 0.01
  min_size: 16
  max_size: 512
```

or:

```yaml
cache:
  mode: fixed
  cache_size: 100
```

The report should include the selected cache size and selection rule.

---

## P2 — Report correctness / auditability issues

### 13. Markdown report has conditional-expression precedence bugs

**Location**

- `scripts/benchmark_chledowski.py`
- RUN_REPORT writing section

**Problem**

Expressions of this form are used:

```python
f.write(
    "- Fallback usage: " + ", ".join(fallbacks) if fallbacks else "None" + "\n"
)
```

and similarly for failed datasets.

Due to Python operator precedence, this does not mean:

```python
f"- Fallback usage: {fallback_text}\n"
```

**Why this affects benchmark**

This may not change the CSV numbers, but it can make the Markdown report misleading or malformed.

For example:

- the label may disappear when there are no fallbacks;
- newline may be missing when fallbacks exist;
- failed dataset summary may be unclear.

**Expected fix**

Use explicit variables:

```python
fallback_text = ", ".join(fallbacks) if fallbacks else "None"
f.write(f"- Fallback usage: {fallback_text}\n")

failed_text = ", ".join(failed_reqs) if failed_reqs else "None"
f.write(f"- Failed datasets: {failed_text}\n\n")
```

---

### 14. Failed run details are not fully propagated into the final report

**Location**

- `scripts/benchmark_chledowski.py`
- `run_single_dataset(...)`
- `main()`

**Problem**

`run_single_dataset(...)` returns `run_status`, including return code, runtime, and error message.

But `main()` mostly uses `report_row` and does not aggregate all `run_status` records into a final machine-readable status table.

**Why this affects benchmark**

When a dataset fails, the final report may not contain enough information to determine whether the failure was due to:

- parser failure;
- training failure;
- subprocess error;
- missing benchmark CSV;
- config issue;
- timeout/hang.

This affects auditability of experimental results.

**Expected fix**

Write a `run_status_all_datasets.csv` with at least:

```text
requested_dataset
actual_dataset
return_code
success
runtime_seconds
error_message
config_path
stdout_log
stderr_log
```

---

### 15. Dataset summary order can be nondeterministic

**Location**

- `scripts/benchmark_chledowski.py`
- RUN_REPORT section `HedgeFullDelayed vs MARK`

**Problem**

The report iterates over:

```python
set(r["dataset"] for r in summary_results)
```

Set iteration order is not guaranteed.

**Why this affects benchmark**

This does not change miss counts, but it makes reports harder to diff across runs.

**Expected fix**

Use:

```python
for ds in sorted(set(r["dataset"] for r in summary_results)):
    ...
```

---

### 16. `git pull` and subprocess execution have no timeout

**Location**

- `scripts/benchmark_chledowski.py`
- `manage_repo(...)`
- `run_single_dataset(...)`

**Problem**

`git pull`, `git clone`, and `python -m src.train` are run without a timeout.

**Why this affects benchmark**

A broken dataset, network issue, or unexpectedly slow run can hang the whole benchmark.

This affects benchmark completion and reproducibility of automated runs.

**Expected fix**

Add explicit timeouts and record timeout failures in `run_status.txt`.

Example:

```python
subprocess.run(..., timeout=3600)
```

---

## Important non-bugs under the current benchmark goal

These are not considered benchmark bugs given the stated goal:

### A. LRU/LFU are not benchmark baselines

The intended benchmark is only:

```text
HedgeFullDelayed vs Belady/OPT vs MARK
```

Therefore, not reporting LRU/LFU/FIFO/RawML as standalone baselines is not a bug.

They are internal experts of HedgeFullDelayed.

### B. Belady/OPT on the test split is expected

`Belady/OPT` uses full future information inside the test trace. That is correct for an offline optimum baseline.

### C. MARK randomness is seeded

MARK uses `random.Random(seed)`, so the current implementation is reproducible for a fixed seed.

---

## Recommended minimal fix order

Fix in this order before relying on final benchmark numbers:

1. Fix MARK expert side effect inside HedgeFullDelayed.
2. Stop mutating `configs/config.yaml`; generate per-dataset temporary configs.
3. Stop reusing old benchmark results unless metadata hashes match.
4. Decide official split handling: use existing dataset splits or ratio split, not both accidentally.
5. Make split ratio and cache-size selection explicit in the report.
6. Pin the external dataset commit.
7. Harden dataset discovery and parser validation.
8. Fix Markdown report precedence bugs.
9. Add `run_status_all_datasets.csv`.
10. Document RawML training-state distribution: currently LRU-generated states.

---

## Bottom line

The benchmark can currently produce numbers, but several implementation details can change or invalidate those numbers:

- HedgeFullDelayed may be affected by unintended MARK expert state mutation.
- Dataset splits may be corrupted by concat-then-resplit.
- Old results may be silently reused.
- Config and cache size are overridden by the benchmark script.
- Dataset inputs are not pinned.
- Parser heuristics may silently select or parse the wrong files.

Until the P0 issues are fixed, the benchmark should be treated as exploratory rather than final experimental evidence.
