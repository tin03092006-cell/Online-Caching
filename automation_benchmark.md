# Automation Benchmark Guide

Mục tiêu: hướng dẫn IDE AI agent tự chạy benchmark tích hợp `Belady/OPT`, `LRU`, `LFU`, `MARK`, `HedgeFullDelayedAllExpertSoft` trong một lần chạy.

## 1. Chuẩn bị môi trường

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Chạy benchmark chính

```bash
python scripts/benchmark_chledowski_all_policies.py --datasets all --jobs auto --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b --force
```

Ghi chú:

- `--jobs auto`: dùng nhiều CPU theo số core khả dụng.
- `--force`: chạy lại toàn bộ, không dùng cache cũ.
- Không chạy `quick_eval_lru_lfu_from_processed.py` nữa.

## 3. File kết quả cần kiểm tra

Sau khi chạy xong, kiểm tra:

```text
data/processed/summary_all_datasets.csv
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
data/processed/run_status_all_datasets.csv
data/processed/benchmark_runs/<dataset>/trace_manifest.json
```

## 4. Điều kiện hoàn tất

Benchmark được xem là hoàn tất khi:

- `RUN_REPORT.md` báo 13 dataset success.
- `summary_all_datasets.csv` có đủ các thuật toán: `Belady/OPT`, `LRU`, `LFU`, `MARK`, `HedgeFullDelayed...`.
- Không có dataset fail trong `run_status_all_datasets.csv`.

## 5. Nếu lỗi

Đọc log theo dataset:

```text
data/processed/benchmark_runs/<dataset>/stdout.log
data/processed/benchmark_runs/<dataset>/stderr.log
```

Sửa lỗi code hoặc môi trường, rồi chạy lại lệnh benchmark chính.
