# benchmark_automation.md

## Mục tiêu

Chạy lại benchmark sau khi sửa 3 lỗi ảnh hưởng trực tiếp đến kết quả:

1. LFU phải dùng `cache_access_counts` theo thời gian item nằm trong cache, không dùng global `access_counts`.
2. MARK expert trong Hedge phải được phép cập nhật phase khi vote, không để `mutate_phase=False` làm MARK expert biến thành random proxy.
3. Hedge weights phải được normalize hoặc dùng log-space để tránh underflow trên trace dài.

Kết quả cuối cùng phải cho biết Hedge sau sửa còn thắng MARK/LFU/LRU hay không.

---

## Yêu cầu tuyệt đối

Không cherry-pick kết quả đẹp.

Không dùng benchmark cũ làm kết luận cuối cùng sau khi sửa code.

Không sửa dataset để làm đẹp kết quả.

Không thay đổi cache size, split ratio, seed nếu không ghi rõ trong report.

---

## Bước 0: Kiểm tra nhánh code

Agent phải chạy trên branch chứa các fix:

```bash
git checkout fix-lfu-mark-weight
```

Kiểm tra trạng thái:

```bash
git status
```

Nếu có thay đổi local chưa commit, ghi rõ vào report.

---

## Bước 1: Kiểm tra implementation đang được benchmark thật sự

Mở các file sau:

```text
src/train.py
src/train_soft.py
src/train_all_expert_soft.py
src/model.py
src/soft_classic_anchor.py
src/all_expert_soft.py
src/data.py
scripts/benchmark_chledowski.py
scripts/quick_eval_lru_lfu_from_processed.py
```

Xác định `python -m src.train` đang gọi implementation nào.

Nếu `src/train.py` đi qua `src/train_all_expert_soft.py`, thì agent phải kiểm tra thêm `src/all_expert_soft.py`.

Implementation được dùng trong benchmark phải thỏa cả 3 điều kiện:

```text
LFU dùng per-cache count, không dùng global access_counts.
MARK expert không dùng mutate_phase=False trong Hedge voting.
Hedge weights được normalize sau feedback update hoặc dùng log-space.
```

Nếu implementation active chưa thỏa 3 điều kiện trên, phải sửa trước khi chạy benchmark.

---

## Bước 2: Kiểm tra nhanh bằng grep

Chạy:

```bash
grep -R "mutate_phase=False" -n src scripts || true
grep -R "access_counts\[cache_item\]" -n src scripts || true
grep -R "cache_access_counts" -n src scripts || true
grep -R "normalize_expert_weights" -n src scripts || true
```

Kỳ vọng:

```text
Không còn mutate_phase=False trong Hedge proposal.
LFU eviction không dùng access_counts[cache_item].
Có cache_access_counts trong LFU và baseline script.
Có normalize_expert_weights hoặc cơ chế log-space tương đương.
```

---

## Bước 3: Cài môi trường

Khuyến nghị dùng Python 3.11.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS/Git Bash:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Bước 4: Kiểm tra compile

Chạy:

```bash
python -m compileall src scripts
```

Nếu lỗi, sửa lỗi trước khi benchmark.

---

## Bước 5: Chạy smoke test nhỏ

Chạy một dataset nhỏ trước:

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

Sau đó chạy baseline LRU/LFU:

```bash
python scripts/quick_eval_lru_lfu_from_processed.py \
  --input-summary data/processed/summary_all_datasets.csv \
  --output-summary data/processed/summary_all_datasets_with_lru_lfu.csv
```

Kiểm tra các file:

```text
data/processed/summary_all_datasets.csv
data/processed/summary_all_datasets_with_lru_lfu.csv
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
```

---

## Bước 6: Chạy full benchmark 13 dataset

Chạy:

```bash
python scripts/benchmark_chledowski.py \
  --datasets all \
  --force \
  --jobs 1 \
  --split-mode ratio \
  --cache-mode ratio \
  --cache-ratio 0.01 \
  --min-cache-size 16 \
  --max-cache-size 512 \
  --timeout-seconds 3600
```

Sau khi xong, chạy thêm LRU/LFU standalone:

```bash
python scripts/quick_eval_lru_lfu_from_processed.py \
  --input-summary data/processed/summary_all_datasets.csv \
  --output-summary data/processed/summary_all_datasets_with_lru_lfu.csv
```

---

## Bước 7: Sinh bảng phân tích Hedge vs MARK/LFU/LRU

Chạy đoạn Python sau từ project root:

```bash
python - <<'PY'
from pathlib import Path
import pandas as pd

processed = Path('data/processed')
input_path = processed / 'summary_all_datasets_with_lru_lfu.csv'
output_csv = processed / 'benchmark_fixed_analysis.csv'
output_md = processed / 'BENCHMARK_FIXED_REPORT.md'

df = pd.read_csv(input_path)
df['algorithm'] = df['algorithm'].astype(str)

rows = []
for dataset, group in df.groupby('dataset', sort=False):
    def first_row(prefix):
        matched = group[group['algorithm'].str.startswith(prefix)]
        return None if matched.empty else matched.iloc[0]

    belady = first_row('Belady/OPT')
    mark = first_row('MARK')
    lru = first_row('LRU')
    lfu = first_row('LFU')
    hedge = first_row('HedgeFullDelayed')

    if belady is None or mark is None or hedge is None:
        continue

    belady_miss = int(belady['cache_misses'])
    mark_miss = int(mark['cache_misses'])
    hedge_miss = int(hedge['cache_misses'])
    lru_miss = None if lru is None else int(lru['cache_misses'])
    lfu_miss = None if lfu is None else int(lfu['cache_misses'])

    mark_gap = mark_miss - belady_miss
    closed_gap = None
    if mark_gap > 0:
        closed_gap = (mark_miss - hedge_miss) / mark_gap * 100.0

    row = {
        'dataset': dataset,
        'belady_misses': belady_miss,
        'mark_misses': mark_miss,
        'lru_misses': lru_miss,
        'lfu_misses': lfu_miss,
        'hedge_misses': hedge_miss,
        'hedge_vs_mark_delta': mark_miss - hedge_miss,
        'hedge_vs_mark_percent': (mark_miss - hedge_miss) / max(mark_miss, 1) * 100.0,
        'closed_gap_to_belady_percent': closed_gap,
        'hedge_vs_lru_delta': None if lru_miss is None else lru_miss - hedge_miss,
        'hedge_vs_lru_percent': None if lru_miss is None else (lru_miss - hedge_miss) / max(lru_miss, 1) * 100.0,
        'hedge_vs_lfu_delta': None if lfu_miss is None else lfu_miss - hedge_miss,
        'hedge_vs_lfu_percent': None if lfu_miss is None else (lfu_miss - hedge_miss) / max(lfu_miss, 1) * 100.0,
    }
    rows.append(row)

analysis = pd.DataFrame(rows)
analysis.to_csv(output_csv, index=False)

hedge_total = int(analysis['hedge_misses'].sum())
mark_total = int(analysis['mark_misses'].sum())
belady_total = int(analysis['belady_misses'].sum())
lru_total = int(analysis['lru_misses'].dropna().sum()) if 'lru_misses' in analysis else 0
lfu_total = int(analysis['lfu_misses'].dropna().sum()) if 'lfu_misses' in analysis else 0

wins_mark = int((analysis['hedge_vs_mark_delta'] > 0).sum())
ties_mark = int((analysis['hedge_vs_mark_delta'] == 0).sum())
losses_mark = int((analysis['hedge_vs_mark_delta'] < 0).sum())

wins_lfu = int((analysis['hedge_vs_lfu_delta'] > 0).sum())
ties_lfu = int((analysis['hedge_vs_lfu_delta'] == 0).sum())
losses_lfu = int((analysis['hedge_vs_lfu_delta'] < 0).sum())

weighted_vs_mark = (mark_total - hedge_total) / max(mark_total, 1) * 100.0
closed_gap_total = None
if mark_total > belady_total:
    closed_gap_total = (mark_total - hedge_total) / (mark_total - belady_total) * 100.0

weighted_vs_lfu = None
if lfu_total > 0:
    weighted_vs_lfu = (lfu_total - hedge_total) / lfu_total * 100.0

lines = []
lines.append('# Fixed Benchmark Report')
lines.append('')
lines.append('## Aggregate')
lines.append('')
lines.append(f'- Belady/OPT total misses: {belady_total:,}')
lines.append(f'- MARK total misses: {mark_total:,}')
lines.append(f'- LRU total misses: {lru_total:,}')
lines.append(f'- LFU total misses: {lfu_total:,}')
lines.append(f'- Hedge total misses: {hedge_total:,}')
lines.append(f'- Hedge weighted improvement vs MARK: {weighted_vs_mark:.4f}%')
if closed_gap_total is not None:
    lines.append(f'- Hedge closed gap to Belady vs MARK: {closed_gap_total:.4f}%')
if weighted_vs_lfu is not None:
    lines.append(f'- Hedge weighted improvement vs LFU: {weighted_vs_lfu:.4f}%')
lines.append('')
lines.append('## Win / Tie / Loss')
lines.append('')
lines.append(f'- Hedge vs MARK: {wins_mark} wins, {ties_mark} ties, {losses_mark} losses')
lines.append(f'- Hedge vs LFU: {wins_lfu} wins, {ties_lfu} ties, {losses_lfu} losses')
lines.append('')
lines.append('## Per-dataset table')
lines.append('')
lines.append(analysis.to_markdown(index=False))

output_md.write_text('\n'.join(lines), encoding='utf-8')
print(f'Saved {output_csv}')
print(f'Saved {output_md}')
PY
```

---

## Bước 8: Kiểm tra kết quả bắt buộc

Agent phải trả lời các câu sau trong `data/processed/BENCHMARK_FIXED_REPORT.md`:

```text
Hedge sau sửa thắng/hòa/thua MARK bao nhiêu dataset?
Hedge sau sửa thắng/hòa/thua LFU bao nhiêu dataset?
Weighted improvement vs MARK là bao nhiêu?
Weighted improvement vs LFU là bao nhiêu?
Dataset nào Hedge thắng mạnh nhất?
Dataset nào Hedge thua hoặc giảm mạnh nhất?
Mcf còn là dataset chi phối tổng improvement không?
Các dataset no-reuse như lbm/libq/milc/bwaves có còn hòa không?
```

---

## Bước 9: Không kết luận quá mức

Nếu Hedge vẫn thắng:

```text
Kết luận đúng: Hedge-style delayed-feedback eviction voting vẫn robust và cải thiện tổng thể.
```

Không viết:

```text
Hedge luôn tốt hơn mọi thuật toán trên mọi dataset.
```

Nếu Hedge thua LFU ở vài dataset:

```text
Kết luận đúng: LFU vẫn là baseline mạnh trên một số workload frequency-stable; Hedge có lợi thế khi workload có locality/phases phức tạp.
```

---

## Output cuối cùng cần nộp lại

Agent phải gửi lại các file sau:

```text
data/processed/summary_all_datasets.csv
data/processed/summary_all_datasets_with_lru_lfu.csv
data/processed/benchmark_fixed_analysis.csv
data/processed/BENCHMARK_FIXED_REPORT.md
data/processed/RUN_REPORT.md
data/processed/chledowski_trace_report.csv
```

Nếu benchmark lỗi ở dataset nào, không được bỏ qua. Phải ghi rõ dataset lỗi, stderr log, và nguyên nhân dự đoán.
