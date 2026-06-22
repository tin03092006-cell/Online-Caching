# Hedge Cache: All Expert Soft Anchor

Dự án này triển khai pipeline cốt lõi cho bài toán **Online Caching** được tăng cường bằng Machine Learning. Phiên bản hiện tại trên nhánh `main` sử dụng thuật toán tối ưu nhất: **`HedgeFullDelayedAllExpertSoft`**.

## 1. Kiến trúc thuật toán cốt lõi

Thuật toán kết hợp sức mạnh của nhiều chuyên gia (experts) khác nhau thông qua cơ chế học máy online (Hedge):
- **Các chuyên gia tham gia:** `LRU`, `LFU`, `MARK`, và `RawML` (Gradient Boosting Regressor).
- **Delayed Feedback:** Loss của một chuyên gia chỉ được cập nhật khi quyết định đẩy (evict) của chuyên gia đó được hệ thống nhìn thấy lại trong tương lai (khi cache miss xảy ra).
- **All Expert Soft Anchor:** Thay vì chỉ chọn ngẫu nhiên một chuyên gia, thuật toán lấy mẫu tỷ lệ (soft sampling) dựa trên trọng số Hedge của *tất cả* các chuyên gia để đưa ra quyết định eviction tập thể tối ưu nhất. Cơ chế này đã đánh bại cả LFU trên các dataset phức tạp (như `mcf`, `xalanc`).

## 2. Cài đặt môi trường

Khuyến nghị sử dụng Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
```

## 3. Chạy tự động Benchmark (Chledowski Datasets)

Dự án cung cấp bộ script tự động tải, tiền xử lý và chạy mô phỏng thuật toán trên các dataset chuẩn.

**Bước 1:** Chạy benchmark trên toàn bộ các dataset (có thể chọn 1 dataset qua `--datasets mcf`):
```bash
python scripts/benchmark_chledowski.py --datasets all --dataset-ref 804cf4ca3ba1a2c59d56dfdb1204a96df246cf2b
```

**Bước 2:** Chạy script đánh giá phụ để bổ sung baseline (LRU/LFU) vào báo cáo cuối cùng:
```bash
python scripts/quick_eval_lru_lfu_from_processed.py
```

Kết quả cuối cùng sẽ được gộp và lưu tại:
- `data/processed/summary_all_datasets.csv`
- `data/processed/RUN_REPORT.md`

## 4. Cấu trúc thư mục

- `src/`: Chứa mã nguồn cốt lõi.
  - `data.py`: Trích xuất feature (recency, frequency, v.v...) và sinh label.
  - `model.py`: Chứa các baseline (Belady/OPT, MARK, LRU, LFU, RawML).
  - `soft_classic_anchor.py`: Thuật toán lõi `HedgeFullDelayedAllExpertSoft`.
  - `train_soft.py`: Pipeline gom nối từ data, model đến simulation.
- `scripts/`: Chứa mã nguồn tự động hóa benchmark.
- `configs/`: Chứa `config.yaml` định nghĩa các hyperparameter (ví dụ: `cache_size`, `candidate_learning_rates`).

## 5. Chỉnh sửa cấu hình thủ công

Nếu bạn không chạy benchmark tự động mà muốn chạy thử nghiệm đơn lẻ, bạn có thể tự chỉnh sửa file `configs/config.yaml` và chạy lệnh sau:

```bash
python -m src.train --config configs/config.yaml
```
Dữ liệu raw test cần được đặt tại `data/raw/trace.txt` (mỗi dòng 1 request). Kết quả sẽ được xuất ra thư mục `data/processed/`.
