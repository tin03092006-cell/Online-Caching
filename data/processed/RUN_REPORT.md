# Chledowski Dataset Benchmark Report

## 1. Run Metadata
- project_commit: 55142e0daf2fd7c9dbdc671e4cfac2a303521d87
- project_dirty: True
- dataset_ref_requested: unpinned
- dataset_commit_used: 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
- jobs: 1

## 2. Dataset Preparation Summary
### xalanc
- split_mode actual per dataset: official
- source_files: xalanc_test.csv|xalanc_train.csv|xalanc_valid.csv
- rejected_files: 
- format_detected_per_file: xalanc_test.csv:two_columns_no_header|xalanc_train.csv:two_columns_no_header|xalanc_valid.csv:two_columns_no_header
- warning: 

## 3. Config Summary
- cache_size rule: ratio (ratio: 0.01, fixed: 100)

## 4. Benchmark Results
Standalone baselines: Belady/OPT, MARK
Proposed algorithm: HedgeFullDelayed
Internal experts: LRU, LFU, FIFO, MARK, RawML

- Dataset: xalanc | Algorithm: Belady/OPT | Misses: 5499 | Miss Ratio: 0.6364583333333333 | Improvement vs MARK: 30.418828293053267% | Eta: 1.0 | MAE: 48693.025309193996
- Dataset: xalanc | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 6900 | Miss Ratio: 0.7986111111111112 | Improvement vs MARK: 12.69138301910667% | Eta: 1.0 | MAE: 48693.025309193996
- Dataset: xalanc | Algorithm: MARK | Misses: 7903 | Miss Ratio: 0.914699074074074 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 48693.025309193996

## 5. HedgeFullDelayed vs MARK
- xalanc: HedgeFullDelayed beat MARK

## 6. Failed Datasets
- Failed datasets: None

## 7. Final Conclusion
- Number of successful datasets: 1
- Number of failed datasets: 0
- Status: SUCCESS: benchmark completed for 1 datasets.
