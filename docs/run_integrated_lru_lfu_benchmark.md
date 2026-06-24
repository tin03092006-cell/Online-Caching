# Integrated LRU/LFU benchmark workflow

This branch removes the extra waiting step where LRU and LFU were computed later by `scripts/quick_eval_lru_lfu_from_processed.py`.

Use this command instead:

```bash
python scripts/benchmark_chledowski_all_policies.py --datasets all --jobs auto --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
```

What changed:

- `src.train` now points to `src.train_all_policies`.
- A single dataset run writes `benchmark_results.csv` with:
  - `Belady/OPT`
  - `LRU`
  - `LFU`
  - `MARK`
  - `HedgeFullDelayedAllExpertSoft(...)`
- `scripts/benchmark_chledowski_all_policies.py` keeps all these rows in `data/processed/summary_all_datasets.csv`.
- CPU parallelism remains dataset-level via `--jobs`.
- Each worker sets BLAS/OpenMP thread counts to 1 through the existing benchmark environment, so several datasets can run in parallel without each process oversubscribing the CPU.

The old quick script can still be kept for backward compatibility, but it is no longer needed for normal benchmark runs on this branch.
