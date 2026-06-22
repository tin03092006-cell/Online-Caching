# Chledowski Dataset Benchmark Report

## 1. Run Metadata
- Date/time: 2026-06-22T15:23:33.244330
- Project root: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project
- Dataset repo path: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project\data\raw\chledowski_repo
- Dataset repo commit hash: 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
- Python executable: C:\Users\LENOVO\Documents\hedge_cache_delayed_feedback_project\hedge_cache_minimal_project\.venv\Scripts\python.exe
- Operating system: win32

## 2. Dataset Selection
- Requested datasets: astar, bwaves, cactusadm, gems, lbm, leslie3d, libq, mcf, omnetpp, sphinx3, xalanc, bzip, milc
- Actual datasets: astar, bwaves, cactusadm, gems, lbm, leslie3d, libq, mcf, omnetpp, sphinx3, xalanc, bzip, milc
None
None

## 3. Trace Preparation Summary
### astar (Requested: astar)
- Source files: astar_train.csv|astar_valid.csv|astar_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 1442560
- Number of unique items: 5189
- Warnings: 

### bwaves (Requested: bwaves)
- Source files: bwaves_train.csv|bwaves_valid.csv|bwaves_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 712960
- Number of unique items: 217510
- Warnings: 

### cactusadm (Requested: cactusadm)
- Source files: cactusadm_train.csv|cactusadm_valid.csv|cactusadm_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 277440
- Number of unique items: 135314
- Warnings: 

### gems (Requested: gems)
- Source files: gems_train.csv|gems_valid.csv|gems_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 904320
- Number of unique items: 440361
- Warnings: 

### lbm (Requested: lbm)
- Source files: lbm_train.csv|lbm_valid.csv|lbm_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 977600
- Number of unique items: 769820
- Warnings: 

### leslie3d (Requested: leslie3d)
- Source files: leslie3d_train.csv|leslie3d_valid.csv|leslie3d_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 895040
- Number of unique items: 43492
- Warnings: 

### libq (Requested: libq)
- Source files: libq_train.csv|libq_valid.csv|libq_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 724800
- Number of unique items: 16375
- Warnings: 

### mcf (Requested: mcf)
- Source files: mcf_train.csv|mcf_valid.csv|mcf_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 3706880
- Number of unique items: 861171
- Warnings: 

### omnetpp (Requested: omnetpp)
- Source files: omnetpp_train.csv|omnetpp_valid.csv|omnetpp_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 694400
- Number of unique items: 23366
- Warnings: 

### sphinx3 (Requested: sphinx3)
- Source files: sphinx3_train.csv|sphinx3_valid.csv|sphinx3_test.csv
- Concatenation order: train -> valid -> test
- Format detected: two_columns_no_header
- Item column used: 1
- Number of requests: 410880
- Number of unique items: 6530
- Warnings: 

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
- Dataset: astar | Algorithm: Belady/OPT | Misses: 140235 | Miss Ratio: 0.9721259427684117 | Improvement vs MARK: 2.779992374085757%
- Dataset: astar | Algorithm: MARK | Misses: 144245 | Miss Ratio: 0.9999237466725821 | Improvement vs MARK: 0.0%
- Dataset: astar | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 143551 | Miss Ratio: 0.9951128549245786 | Improvement vs MARK: 0.48112586224825815%
- Dataset: bwaves | Algorithm: Belady/OPT | Misses: 67834 | Miss Ratio: 0.9514418761220825 | Improvement vs MARK: 4.855812387791741%
- Dataset: bwaves | Algorithm: MARK | Misses: 71296 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: bwaves | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 71296 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: cactusadm | Algorithm: Belady/OPT | Misses: 21801 | Miss Ratio: 0.7857915224913494 | Improvement vs MARK: 21.42084775086505%
- Dataset: cactusadm | Algorithm: MARK | Misses: 27744 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: cactusadm | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 26034 | Miss Ratio: 0.9383650519031141 | Improvement vs MARK: 6.163494809688581%
- Dataset: gems | Algorithm: Belady/OPT | Misses: 81455 | Miss Ratio: 0.9007320417551309 | Improvement vs MARK: 7.652627402074712%
- Dataset: gems | Algorithm: MARK | Misses: 88205 | Miss Ratio: 0.9753737615003538 | Improvement vs MARK: 0.0%
- Dataset: gems | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 87996 | Miss Ratio: 0.9730626326963907 | Improvement vs MARK: 0.2369480188197948%
- Dataset: lbm | Algorithm: Belady/OPT | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: lbm | Algorithm: MARK | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: lbm | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: leslie3d | Algorithm: Belady/OPT | Misses: 71585 | Miss Ratio: 0.7997966571326421 | Improvement vs MARK: 15.324106931629997%
- Dataset: leslie3d | Algorithm: MARK | Misses: 84540 | Miss Ratio: 0.9445387915623883 | Improvement vs MARK: 0.0%
- Dataset: leslie3d | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 81066 | Miss Ratio: 0.9057248838040758 | Improvement vs MARK: 4.1092973740241305%
- Dataset: libq | Algorithm: Belady/OPT | Misses: 71832 | Miss Ratio: 0.9910596026490066 | Improvement vs MARK: 0.8940397350993378%
- Dataset: libq | Algorithm: MARK | Misses: 72480 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: libq | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 72480 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0%
- Dataset: mcf | Algorithm: Belady/OPT | Misses: 216366 | Miss Ratio: 0.5836876294889503 | Improvement vs MARK: 32.88187960268763%
- Dataset: mcf | Algorithm: MARK | Misses: 322366 | Miss Ratio: 0.8696423946823204 | Improvement vs MARK: 0.0%
- Dataset: mcf | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 234101 | Miss Ratio: 0.631531098929558 | Improvement vs MARK: 27.380368897464376%
- Dataset: omnetpp | Algorithm: Belady/OPT | Misses: 55123 | Miss Ratio: 0.7938220046082949 | Improvement vs MARK: 19.55782561109084%
- Dataset: omnetpp | Algorithm: MARK | Misses: 68525 | Miss Ratio: 0.9868231566820277 | Improvement vs MARK: 0.0%
- Dataset: omnetpp | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 66283 | Miss Ratio: 0.9545362903225807 | Improvement vs MARK: 3.2717986136446555%
- Dataset: sphinx3 | Algorithm: Belady/OPT | Misses: 37759 | Miss Ratio: 0.918978777258567 | Improvement vs MARK: 8.099885608586657%
- Dataset: sphinx3 | Algorithm: MARK | Misses: 41087 | Miss Ratio: 0.9999756619937694 | Improvement vs MARK: 0.0%
- Dataset: sphinx3 | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 38975 | Miss Ratio: 0.948573792834891 | Improvement vs MARK: 5.14031202083384%
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
- astar: HedgeFullDelayed beat MARK
- bwaves: HedgeFullDelayed tied MARK
- milc: HedgeFullDelayed tied MARK
- leslie3d: HedgeFullDelayed beat MARK
- lbm: HedgeFullDelayed tied MARK
- mcf: HedgeFullDelayed beat MARK
- gems: HedgeFullDelayed beat MARK
- sphinx3: HedgeFullDelayed beat MARK
- omnetpp: HedgeFullDelayed beat MARK
- cactusadm: HedgeFullDelayed beat MARK
- xalanc: HedgeFullDelayed beat MARK
- libq: HedgeFullDelayed tied MARK
- bzip: HedgeFullDelayed beat MARK

## 7. Final Conclusion
- Number of successful datasets: 13
- Number of failed datasets: 0
- Status: SUCCESS: benchmark completed for 13 datasets.
