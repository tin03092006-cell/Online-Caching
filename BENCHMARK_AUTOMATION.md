# Benchmark Automation

Branch: `all-expert-soft-clean`

```bash
git fetch origin
git checkout all-expert-soft-clean
git pull origin all-expert-soft-clean
python -m pip install -r requirements.txt
python scripts/benchmark_chledowski.py --datasets all --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b --force
python scripts/quick_eval_lru_lfu_from_processed.py
```

Check:

```text
data/processed/summary_all_datasets.csv
data/processed/summary_all_datasets_with_lru_lfu.csv
data/processed/RUN_REPORT.md
```

Success:

```text
failed datasets = 0
algorithm contains HedgeFullDelayedAllExpertSoft
compare total misses vs MARK/LRU/LFU/SoftClassicAnchor
```
