# Hedge Cache: Integrated All-Policies Benchmark

Dự án triển khai pipeline **Online Caching** tăng cường Machine Learning. Pipeline hiện tại chạy đồng thời các thuật toán `Belady/OPT`, `LRU`, `LFU`, `MARK` và `HedgeFullDelayedAllExpertSoft` trong một lần benchmark.

## 1. Kiến trúc thuật toán cốt lõi

`HedgeFullDelayedAllExpertSoft` kết hợp bốn expert:

- `LRU`: evict item có lần truy cập gần nhất xa nhất.
- `LFU`: evict item có cache-local frequency nhỏ nhất, tie-break bằng last access và item ID.
- `MARK`: randomized marking policy, phụ thuộc seed.
- `RawML`: Gradient Boosting Regressor dự đoán `target_next_distance` để xấp xỉ tín hiệu Belady/OPT.

Hedge dùng weighted voting trên đề xuất eviction của các expert. Score của một item là tổng trọng số của các expert vote cho item đó. Feedback là delayed counterfactual proxy loss.

## 2. Cài đặt môi trường

Khuyến nghị Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Chạy benchmark tích hợp

```bash
python scripts/benchmark_chledowski_all_policies.py --datasets all --jobs auto --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b --force
```

Ghi chú:

- Không cần chạy `scripts/quick_eval_lru_lfu_from_processed.py` nữa.
- `--jobs auto` chạy song song theo dataset trên CPU.
- Mỗi worker giới hạn BLAS/OpenMP thread về 1 để tránh oversubscribe CPU.

Kết quả chính:

```text
data/processed/summary_all_datasets.csv
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
data/processed/run_status_all_datasets.csv
```

Mỗi dataset run còn có:

```text
data/processed/benchmark_runs/<dataset>/benchmark_results.csv
data/processed/benchmark_runs/<dataset>/trace_manifest.json
data/processed/benchmark_runs/<dataset>/stdout.log
data/processed/benchmark_runs/<dataset>/stderr.log
```

## 4. Cấu trúc thư mục chính

- `src/data.py`: feature extraction và label `target_next_distance`.
- `src/model.py`: Belady/OPT, MARK, RawML và hàm chọn eviction của expert.
- `src/classic_policies.py`: standalone LRU/LFU runners.
- `src/all_expert_soft.py`: HedgeFullDelayedAllExpertSoft.
- `src/train_all_policies.py`: pipeline train/evaluate tích hợp toàn bộ thuật toán.
- `src/train.py`: entrypoint trỏ tới `train_all_policies`.
- `scripts/benchmark_chledowski_all_policies.py`: benchmark nhiều dataset, có CPU parallel.
- `automation_benchmark.md`: hướng dẫn ngắn cho IDE AI agent tự chạy benchmark.

## 5. Chạy một trace thủ công

Đặt trace tại `data/raw/trace.txt`, sau đó chạy:

```bash
python -m src.train --config configs/config.yaml
```

Output sẽ nằm trong `data/processed/`.
