# Minimal Hedge Full for ML-Augmented Online Caching

Dự án tối giản này triển khai pipeline cốt lõi cho bài toán online caching:

```text
HedgeFull = Hedge(LRU, LFU, MARK, RawML)
```

Benchmark chính gồm:

```text
Belady/OPT vs MARK vs HedgeFull
```

## 1. Cài đặt môi trường

Khuyến nghị dùng Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
```

Định dạng code bằng Ruff:

```bash
python -m ruff format src
python -m ruff check src
```

## 2. Chuẩn bị dataset

Bạn cần tự đặt request trace vào:

```text
data/raw/trace.txt
```

Format tối giản: một request item trên một dòng, hoặc các item cách nhau bởi khoảng trắng/dấu phẩy.

Ví dụ:

```text
A
B
C
A
D
B
```

Hoặc:

```text
A B C A D B
```

Không push dữ liệu gốc lên Git. Thư mục `data/raw/` đã được chặn trong `.gitignore`.

## 3. Chỉnh cấu hình

Mọi hyperparameter và path nằm trong:

```text
configs/config.yaml
```

Các giá trị quan trọng nhất cần chỉnh:

```yaml
cache:
  cache_size: 100

data:
  train_ratio: 0.6
  validation_ratio: 0.2
  recent_window_size: 128
  max_training_rows: 50000

hedge:
  candidate_learning_rates: [0.1, 0.3, 0.7, 1.0]
```

Nếu trace nhỏ, hãy giảm `cache.cache_size`, nếu không có thể không tạo được feature train.

## 4. Chạy pipeline

Từ thư mục gốc của project:

```bash
python -m src.train --config configs/config.yaml
```

Sau khi chạy, kết quả được lưu vào:

```text
data/processed/train_features.csv
data/processed/validation_features.csv
data/processed/benchmark_results.csv
```

## 5. Logic đã triển khai

- `src/data.py`
  - Đọc request trace.
  - Chia train/validation/test theo thời gian.
  - Tạo feature cho RawML: `recency`, `frequency`, `recent_frequency`,
    `average_inter_arrival`, `cache_age`.
  - Tạo label `target_next_distance`.

- `src/model.py`
  - RawML predictor bằng `GradientBoostingRegressor` của scikit-learn.
  - Belady/OPT offline baseline.
  - MARK online baseline.
  - Các expert nội bộ: LRU, LFU, MARK, RawML.
  - Hedge Full với delayed feedback. Khi expert đề xuất evict một item,
    quyết định đó được lưu lại. Loss chỉ được cập nhật khi item đó thật sự
    xuất hiện lại trong request stream:

```text
w_i <- w_i * exp(-eta * loss_i)
loss_i = 1 / (1 + feedback_delay)
```

- `src/train.py`
  - Load config.
  - Cố định seed.
  - Train RawML.
  - Chọn eta trên validation.
  - Benchmark trên test.
  - In và lưu kết quả.

## 6. Lưu ý nghiên cứu

Bản này là phiên bản tối giản để có pipeline chạy được. Nó cố ý không chứa logging phức tạp, plotting, notebook, CLI nhiều chế độ, hoặc nhiều model phụ.

Hedge Full trong bản này đã dùng delayed feedback. Trong quá trình benchmark, phần online của Hedge không gọi `next_distance` để cập nhật trọng số. `next_distance` chỉ còn được dùng ở hai nơi hợp lệ: tạo label offline cho RawML trên tập train/validation và tính Belady/OPT làm chuẩn offline.
