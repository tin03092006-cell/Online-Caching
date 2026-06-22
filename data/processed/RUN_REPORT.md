# Chledowski Dataset Benchmark Report

## 1. Run Metadata
- Date/time: 2026-06-22T12:46:13.965910
- Project root: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project
- Dataset repo path: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project\data\raw\chledowski_repo
- Dataset repo commit hash: 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
- Python executable: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project\.venv\Scripts\python.exe
- Operating system: win32

## 2. Dataset Selection
- Requested datasets: xalanc, bzip, milc
- Actual datasets: xalanc, bzip, milc
None
None

## 3. Trace Preparation Summary
### xalanc (Requested: xalanc)
- Source files: xalanc_train.csv|xalanc_valid.csv|xalanc_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 86400
- Number of unique items: 24182
- Warnings: 

### bzip (Requested: bzip)
- Source files: bzip_train.csv|bzip_valid.csv|bzip_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 209600
- Number of unique items: 35526
- Warnings: 

### milc (Requested: milc)
- Source files: milc_train.csv|milc_valid.csv|milc_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 696000
- Number of unique items: 258588
- Warnings: 

## 4. Config Summary
- train_ratio: 0.8
- validation_ratio: 0.1
- test_ratio: 0.1
- hedge.feedback_mode: delayed

## 5. Benchmark Results
- Dataset: xalanc | Algorithm: Belady/OPT | Misses: 5499 | Miss Ratio: 0.6364583333333333 | Improvement vs MARK: 30.418828293053267%
- Dataset: xalanc | Algorithm: MARK | Misses: 7903 | Miss Ratio: 0.914699074074074 | Improvement vs MARK: 0.0%
- Dataset: xalanc | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 6960 | Miss Ratio: 0.8055555555555556 | Improvement vs MARK: 11.932177654055423%
- Dataset: bzip | Algorithm: Belady/OPT | Misses: 10048 | Miss Ratio: 0.47938931297709925 | Improvement vs MARK: 41.42815505683474%
- Dataset: bzip | Algorithm: MARK | Misses: 17155 | Miss Ratio: 0.8184637404580153 | Improvement vs MARK: 0.0%
- Dataset: bzip | Algorithm: HedgeFullDelayed(eta=0.3) | Misses: 17035 | Miss Ratio: 0.8127385496183206 | Improvement vs MARK: 0.6995045176333431%
- Dataset: milc | Algorithm: Belady/OPT | Misses: 69089 | Miss Ratio: 0.9926580459770115 | Improvement vs MARK: 0.7341954022988506%
- Dataset: milc | Algorithm: MARK | Misses: 69600 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: milc | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 69600 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%

## 6. HedgeFullDelayed vs MARK
- xalanc: HedgeFullDelayed beat MARK
- milc: HedgeFullDelayed tied MARK
- bzip: HedgeFullDelayed beat MARK

## 7. Final Conclusion
- Number of successful datasets: 3
- Number of failed datasets: 0
- Status: SUCCESS: benchmark completed for 3 datasets.
