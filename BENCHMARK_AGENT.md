# Benchmark Agent Instructions

Run benchmark for the `classic-anchored-hedge` branch.

## 1. Checkout branch

```bash
git fetch origin
git checkout classic-anchored-hedge
git pull origin classic-anchored-hedge
```

## 2. Install requirements

```bash
python -m pip install -r requirements.txt
```

## 3. Run full benchmark

```bash
python scripts/benchmark_chledowski.py --datasets all --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b --force
```

## 4. Add standalone LRU/LFU results

```bash
python scripts/quick_eval_lru_lfu_from_processed.py
```

## 5. Expected outputs

Check these files:

```text
data/processed/summary_all_datasets.csv
data/processed/summary_all_datasets_with_lru_lfu.csv
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
```

## 6. Success criteria

Benchmark is valid if:

```text
failed datasets = 0
summary file contains Belady/OPT, LRU, LFU, MARK, HedgeFullDelayedClassicAnchor
```

Then compare total cache misses and miss ratio across algorithms.
