# Benchmark Automation

## Mục tiêu

Chạy lại benchmark sau khi sửa 3 điểm:

1. LFU dùng count trong thời gian item nằm trong cache (`cache_access_counts`).
2. MARK expert trong Hedge được cập nhật phase đúng, không dùng `mutate_phase=False`.
3. Hedge weights được normalize hoặc dùng log-space để tránh underflow.

Mục tiêu cuối: so sánh lại Hedge với MARK, LRU, LFU trên 13 dataset.

---

## Những thứ phải kiểm tra trước khi chạy

Kiểm tra branch:

```bash
git checkout fix-lfu-mark-weight
git pull
git status
```

Kiểm tra entrypoint benchmark:

```bash
grep -R "from .* import main" -n src/train.py src/train_*.py
grep -R "run_hedge_full_cache" -n src/train.py src/train_*.py
```

Xác định `python -m src.train` đang dùng file nào. File đó phải thỏa 3 điều kiện:

```text
LFU không dùng global access_counts để evict.
MARK expert không còn mutate_phase=False.
Weights được normalize sau feedback update hoặc trước weighted vote.
```

Kiểm tra nhanh:

```bash
grep -R "mutate_phase=False" -n src scripts || true
grep -R "access_counts\[cache_item\]" -n src scripts || true
grep -R "cache_access_counts" -n src scripts || true
grep -R "normalize_expert_weights" -n src scripts || true
```

Nếu entrypoint đang dùng `src/all_expert_soft.py`, kiểm tra file này riêng. File đó cũng phải có `cache_access_counts` và `normalize_expert_weights`.

---

## Chạy kiểm tra compile

```bash
python -m compileall src scripts
```

Nếu lỗi, sửa trước khi chạy benchmark.

---

## Chạy smoke test

Smoke test chỉ chạy 1 dataset, nên để `--jobs 1` cho dễ đọc log.

```bash
python scripts/benchmark_chledowski.py \
  --datasets xalanc \
  --force \
  --jobs 1 \
  --split-mode ratio \
  --cache-mode ratio \
  --cache-ratio 0.01 \
  --min-cache-size 16 \
  --max-cache-size 512 \
  --timeout-seconds 3600
```

Sau đó thêm LRU/LFU:

```bash
python scripts/quick_eval_lru_lfu_from_processed.py \
  --input-summary data/processed/summary_all_datasets.csv \
  --output-summary data/processed/summary_all_datasets_with_lru_lfu.csv
```

---

## Chạy full benchmark song song CPU

Full benchmark phải dùng nhiều nhân CPU. Script sẽ chạy song song theo dataset.

Dùng `--jobs auto` để lấy số worker theo số CPU core:

```bash
python scripts/benchmark_chledowski.py \
  --datasets all \
  --force \
  --jobs auto \
  --split-mode ratio \
  --cache-mode ratio \
  --cache-ratio 0.01 \
  --min-cache-size 16 \
  --max-cache-size 512 \
  --timeout-seconds 3600
```

Nếu máy yếu hoặc bị lag, dùng số worker cố định:

```bash
python scripts/benchmark_chledowski.py \
  --datasets all \
  --force \
  --jobs 4 \
  --split-mode ratio \
  --cache-mode ratio \
  --cache-ratio 0.01 \
  --min-cache-size 16 \
  --max-cache-size 512 \
  --timeout-seconds 3600
```

Sau đó thêm LRU/LFU:

```bash
python scripts/quick_eval_lru_lfu_from_processed.py \
  --input-summary data/processed/summary_all_datasets.csv \
  --output-summary data/processed/summary_all_datasets_with_lru_lfu.csv
```

---

## Những kết quả cần báo cáo lại

Từ `summary_all_datasets_with_lru_lfu.csv`, tính và báo cáo:

```text
Hedge thắng/hòa/thua MARK bao nhiêu dataset.
Hedge thắng/hòa/thua LFU bao nhiêu dataset.
Hedge thắng/hòa/thua LRU bao nhiêu dataset.
Weighted improvement của Hedge so với MARK.
Weighted improvement của Hedge so với LFU.
Closed gap to Belady của Hedge so với MARK.
Dataset Hedge thắng mạnh nhất.
Dataset Hedge thua hoặc yếu nhất.
Mcf còn chi phối tổng improvement không.
Các dataset no-reuse như lbm/libq/milc/bwaves còn hòa không.
```

Công thức:

```text
improvement_vs_MARK = (MARK_misses - Hedge_misses) / MARK_misses * 100
improvement_vs_LFU  = (LFU_misses  - Hedge_misses) / LFU_misses  * 100
closed_gap_to_Belady = (MARK_misses - Hedge_misses) / (MARK_misses - Belady_misses) * 100
```

Nếu mẫu số bằng 0 thì ghi `N/A`.

---

## File cần gửi lại

```text
data/processed/summary_all_datasets.csv
data/processed/summary_all_datasets_with_lru_lfu.csv
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
```

Nếu dataset nào lỗi, gửi thêm:

```text
data/processed/benchmark_runs/<dataset>/stderr.log
data/processed/benchmark_runs/<dataset>/stdout.log
```
