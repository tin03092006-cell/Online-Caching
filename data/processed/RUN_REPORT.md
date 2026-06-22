# Chledowski Dataset Benchmark Report

## 1. Run Metadata
- project_commit: 41b009e5166a8193d6bab1e86ad64a67ae234540
- project_dirty: True
- dataset_ref_requested: unpinned
- dataset_commit_used: 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
- jobs: auto

## 2. Dataset Preparation Summary
### astar
- split_mode actual per dataset: ratio
- source_files: astar_test.csv|astar_train.csv|astar_valid.csv
- rejected_files: 
- format_detected_per_file: astar_test.csv:two_columns_no_header|astar_train.csv:two_columns_no_header|astar_valid.csv:two_columns_no_header
- warning: 

### bwaves
- split_mode actual per dataset: ratio
- source_files: bwaves_test.csv|bwaves_train.csv|bwaves_valid.csv
- rejected_files: 
- format_detected_per_file: bwaves_test.csv:two_columns_no_header|bwaves_train.csv:two_columns_no_header|bwaves_valid.csv:two_columns_no_header
- warning: 

### cactusadm
- split_mode actual per dataset: ratio
- source_files: cactusadm_test.csv|cactusadm_train.csv|cactusadm_valid.csv
- rejected_files: 
- format_detected_per_file: cactusadm_test.csv:two_columns_no_header|cactusadm_train.csv:two_columns_no_header|cactusadm_valid.csv:two_columns_no_header
- warning: 

### gems
- split_mode actual per dataset: ratio
- source_files: gems_test.csv|gems_train.csv|gems_valid.csv
- rejected_files: 
- format_detected_per_file: gems_test.csv:two_columns_no_header|gems_train.csv:two_columns_no_header|gems_valid.csv:two_columns_no_header
- warning: 

### lbm
- split_mode actual per dataset: ratio
- source_files: lbm_test.csv|lbm_train.csv|lbm_valid.csv
- rejected_files: 
- format_detected_per_file: lbm_test.csv:two_columns_no_header|lbm_train.csv:two_columns_no_header|lbm_valid.csv:two_columns_no_header
- warning: 

### leslie3d
- split_mode actual per dataset: ratio
- source_files: leslie3d_test.csv|leslie3d_train.csv|leslie3d_valid.csv
- rejected_files: 
- format_detected_per_file: leslie3d_test.csv:two_columns_no_header|leslie3d_train.csv:two_columns_no_header|leslie3d_valid.csv:two_columns_no_header
- warning: 

### libq
- split_mode actual per dataset: ratio
- source_files: libq_test.csv|libq_train.csv|libq_valid.csv
- rejected_files: 
- format_detected_per_file: libq_test.csv:two_columns_no_header|libq_train.csv:two_columns_no_header|libq_valid.csv:two_columns_no_header
- warning: 

### mcf
- split_mode actual per dataset: ratio
- source_files: mcf_test.csv|mcf_train.csv|mcf_valid.csv
- rejected_files: 
- format_detected_per_file: mcf_test.csv:two_columns_no_header|mcf_train.csv:two_columns_no_header|mcf_valid.csv:two_columns_no_header
- warning: 

### omnetpp
- split_mode actual per dataset: ratio
- source_files: omnetpp_test.csv|omnetpp_train.csv|omnetpp_valid.csv
- rejected_files: 
- format_detected_per_file: omnetpp_test.csv:two_columns_no_header|omnetpp_train.csv:two_columns_no_header|omnetpp_valid.csv:two_columns_no_header
- warning: 

### sphinx3
- split_mode actual per dataset: ratio
- source_files: sphinx3_test.csv|sphinx3_train.csv|sphinx3_valid.csv
- rejected_files: 
- format_detected_per_file: sphinx3_test.csv:two_columns_no_header|sphinx3_train.csv:two_columns_no_header|sphinx3_valid.csv:two_columns_no_header
- warning: 

### xalanc
- split_mode actual per dataset: ratio
- source_files: xalanc_test.csv|xalanc_train.csv|xalanc_valid.csv
- rejected_files: 
- format_detected_per_file: xalanc_test.csv:two_columns_no_header|xalanc_train.csv:two_columns_no_header|xalanc_valid.csv:two_columns_no_header
- warning: 

### bzip
- split_mode actual per dataset: ratio
- source_files: bzip_test.csv|bzip_train.csv|bzip_valid.csv
- rejected_files: 
- format_detected_per_file: bzip_test.csv:two_columns_no_header|bzip_train.csv:two_columns_no_header|bzip_valid.csv:two_columns_no_header
- warning: 

### milc
- split_mode actual per dataset: ratio
- source_files: milc_test.csv|milc_train.csv|milc_valid.csv
- rejected_files: 
- format_detected_per_file: milc_test.csv:two_columns_no_header|milc_train.csv:two_columns_no_header|milc_valid.csv:two_columns_no_header
- warning: 

## 3. Config Summary
- cache_size rule: ratio (ratio: 0.01, fixed: 100)

## 4. Benchmark Results
Standalone baselines: Belady/OPT, MARK
Proposed algorithm: HedgeFullDelayed
Internal experts: LRU, LFU, FIFO, MARK, RawML

- Dataset: astar | Algorithm: Belady/OPT | Misses: 140235 | Miss Ratio: 0.9721259427684117 | Improvement vs MARK: 2.779992374085757% | Eta: 0.7 | MAE: 9128.985434904534
- Dataset: astar | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 143542 | Miss Ratio: 0.9950504658385093 | Improvement vs MARK: 0.48736524662899927% | Eta: 0.7 | MAE: 9128.985434904534
- Dataset: astar | Algorithm: MARK | Misses: 144245 | Miss Ratio: 0.9999237466725821 | Improvement vs MARK: 0.0% | Eta: 0.7 | MAE: 9128.985434904534
- Dataset: bwaves | Algorithm: Belady/OPT | Misses: 67834 | Miss Ratio: 0.9514418761220825 | Improvement vs MARK: 4.855812387791741% | Eta: 1.0 | MAE: 159258.65731768607
- Dataset: bwaves | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 71296 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 159258.65731768607
- Dataset: bwaves | Algorithm: MARK | Misses: 71296 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 159258.65731768607
- Dataset: cactusadm | Algorithm: Belady/OPT | Misses: 21801 | Miss Ratio: 0.7857915224913494 | Improvement vs MARK: 21.42084775086505% | Eta: 1.0 | MAE: 90560.2746558765
- Dataset: cactusadm | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 26054 | Miss Ratio: 0.9390859284890427 | Improvement vs MARK: 6.091407151095733% | Eta: 1.0 | MAE: 90560.2746558765
- Dataset: cactusadm | Algorithm: MARK | Misses: 27744 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 90560.2746558765
- Dataset: gems | Algorithm: Belady/OPT | Misses: 81455 | Miss Ratio: 0.9007320417551309 | Improvement vs MARK: 7.652627402074712% | Eta: 0.7 | MAE: 262983.7216936585
- Dataset: gems | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 88160 | Miss Ratio: 0.9748761500353857 | Improvement vs MARK: 0.051017516013831414% | Eta: 0.7 | MAE: 262983.7216936585
- Dataset: gems | Algorithm: MARK | Misses: 88205 | Miss Ratio: 0.9753737615003538 | Improvement vs MARK: 0.0% | Eta: 0.7 | MAE: 262983.7216936585
- Dataset: lbm | Algorithm: Belady/OPT | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 646438.1636724814
- Dataset: lbm | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 646438.1636724814
- Dataset: lbm | Algorithm: MARK | Misses: 97760 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 646438.1636724814
- Dataset: leslie3d | Algorithm: Belady/OPT | Misses: 71585 | Miss Ratio: 0.7997966571326421 | Improvement vs MARK: 15.324106931629997% | Eta: 0.7 | MAE: 31174.11023088108
- Dataset: leslie3d | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 82611 | Miss Ratio: 0.9229866821594566 | Improvement vs MARK: 2.281760113555713% | Eta: 0.7 | MAE: 31174.11023088108
- Dataset: leslie3d | Algorithm: MARK | Misses: 84540 | Miss Ratio: 0.9445387915623883 | Improvement vs MARK: 0.0% | Eta: 0.7 | MAE: 31174.11023088108
- Dataset: libq | Algorithm: Belady/OPT | Misses: 71832 | Miss Ratio: 0.9910596026490066 | Improvement vs MARK: 0.8940397350993378% | Eta: 0.1 | MAE: 0.25772133395915886
- Dataset: libq | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 72480 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 0.25772133395915886
- Dataset: libq | Algorithm: MARK | Misses: 72480 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 0.25772133395915886
- Dataset: mcf | Algorithm: Belady/OPT | Misses: 216366 | Miss Ratio: 0.5836876294889503 | Improvement vs MARK: 32.88187960268763% | Eta: 0.7 | MAE: 657182.3138987004
- Dataset: mcf | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 234101 | Miss Ratio: 0.631531098929558 | Improvement vs MARK: 27.380368897464376% | Eta: 0.7 | MAE: 657182.3138987004
- Dataset: mcf | Algorithm: MARK | Misses: 322366 | Miss Ratio: 0.8696423946823204 | Improvement vs MARK: 0.0% | Eta: 0.7 | MAE: 657182.3138987004
- Dataset: omnetpp | Algorithm: Belady/OPT | Misses: 55123 | Miss Ratio: 0.7938220046082949 | Improvement vs MARK: 19.55782561109084% | Eta: 0.3 | MAE: 44070.07399395622
- Dataset: omnetpp | Algorithm: HedgeFullDelayed(eta=0.3) | Misses: 68067 | Miss Ratio: 0.980227534562212 | Improvement vs MARK: 0.6683692083181321% | Eta: 0.3 | MAE: 44070.07399395622
- Dataset: omnetpp | Algorithm: MARK | Misses: 68525 | Miss Ratio: 0.9868231566820277 | Improvement vs MARK: 0.0% | Eta: 0.3 | MAE: 44070.07399395622
- Dataset: sphinx3 | Algorithm: Belady/OPT | Misses: 37759 | Miss Ratio: 0.918978777258567 | Improvement vs MARK: 8.099885608586657% | Eta: 1.0 | MAE: 16159.069855090896
- Dataset: sphinx3 | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 38950 | Miss Ratio: 0.9479653426791277 | Improvement vs MARK: 5.2011585172925745% | Eta: 1.0 | MAE: 16159.069855090896
- Dataset: sphinx3 | Algorithm: MARK | Misses: 41087 | Miss Ratio: 0.9999756619937694 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 16159.069855090896
- Dataset: xalanc | Algorithm: Belady/OPT | Misses: 5499 | Miss Ratio: 0.6364583333333333 | Improvement vs MARK: 30.418828293053267% | Eta: 1.0 | MAE: 48693.025309193996
- Dataset: xalanc | Algorithm: HedgeFullDelayed(eta=1.0) | Misses: 6900 | Miss Ratio: 0.7986111111111112 | Improvement vs MARK: 12.69138301910667% | Eta: 1.0 | MAE: 48693.025309193996
- Dataset: xalanc | Algorithm: MARK | Misses: 7903 | Miss Ratio: 0.914699074074074 | Improvement vs MARK: 0.0% | Eta: 1.0 | MAE: 48693.025309193996
- Dataset: bzip | Algorithm: Belady/OPT | Misses: 10048 | Miss Ratio: 0.47938931297709925 | Improvement vs MARK: 41.42815505683474% | Eta: 0.7 | MAE: 37200.779846835954
- Dataset: bzip | Algorithm: HedgeFullDelayed(eta=0.7) | Misses: 16725 | Miss Ratio: 0.7979484732824428 | Improvement vs MARK: 2.506557854852813% | Eta: 0.7 | MAE: 37200.779846835954
- Dataset: bzip | Algorithm: MARK | Misses: 17155 | Miss Ratio: 0.8184637404580153 | Improvement vs MARK: 0.0% | Eta: 0.7 | MAE: 37200.779846835954
- Dataset: milc | Algorithm: Belady/OPT | Misses: 69089 | Miss Ratio: 0.9926580459770115 | Improvement vs MARK: 0.7341954022988506% | Eta: 0.1 | MAE: 61475.37817081296
- Dataset: milc | Algorithm: HedgeFullDelayed(eta=0.1) | Misses: 69600 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 61475.37817081296
- Dataset: milc | Algorithm: MARK | Misses: 69600 | Miss Ratio: 1.0 | Improvement vs MARK: 0.0% | Eta: 0.1 | MAE: 61475.37817081296

## 5. HedgeFullDelayed vs MARK
- astar: HedgeFullDelayed beat MARK
- bwaves: HedgeFullDelayed tied MARK
- cactusadm: HedgeFullDelayed beat MARK
- gems: HedgeFullDelayed beat MARK
- lbm: HedgeFullDelayed tied MARK
- leslie3d: HedgeFullDelayed beat MARK
- libq: HedgeFullDelayed tied MARK
- mcf: HedgeFullDelayed beat MARK
- omnetpp: HedgeFullDelayed beat MARK
- sphinx3: HedgeFullDelayed beat MARK
- xalanc: HedgeFullDelayed beat MARK
- bzip: HedgeFullDelayed beat MARK
- milc: HedgeFullDelayed tied MARK

## 6. Failed Datasets
- Failed datasets: None

## 7. Final Conclusion
- Number of successful datasets: 13
- Number of failed datasets: 0
- Status: SUCCESS: benchmark completed for 13 datasets.
