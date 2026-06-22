# Benchmark Agent Instructions

Run benchmark for the `classic-anchor-no-fifo` branch.

This branch uses the Classic-Anchored Hedge variant with FIFO removed from the main expert set.

Main expert set:

```text
LRU + LFU + MARK + RawML
```

FIFO is intentionally not used as a main expert in this branch. Keep FIFO only for ablation or noisy-expert experiments.

## 1. Checkout branch

```bash
git fetch origin
git checkout classic-anchor-no-fifo
git pull origin classic-anchor-no-fifo
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
summary file contains Belady/OPT, LRU, LFU, MARK, HedgeFullDelayedClassicAnchorNoFIFO
```

Then compare total cache misses and miss ratio across algorithms.
