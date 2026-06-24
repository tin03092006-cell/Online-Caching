# Final Pipeline: Self-Tuning RawML + Meta-Hedge

Mục tiêu: **tin RawML mặc định**, nhưng mọi tham số fallback đều được tự học online thay vì đặt tay cố định.

## 1. Offline training

```text
Raw trace
↓
Build history-only features cho từng item trong cache
↓
Label Belady: y = D_t^+(x)
↓
Train RawML: f_theta(features) ≈ next-access distance
```

RawML học để xấp xỉ Belady/OPT. Label `D_t^+(x)` chỉ dùng khi train/evaluate, không dùng làm feature online.

## 2. Online experts

Tại mỗi cache miss, các expert cùng đề xuất item để evict:

```text
RawML  → evict item có predicted next distance lớn nhất
LRU    → evict least recently used
LFU    → evict least frequently used trong cache
MARK   → randomized marking expert
```

RawML là expert chính. LRU/LFU/MARK chỉ là phanh an toàn.

## 3. Không chọn một fallback rule cố định

Không dùng một bộ tham số cố định kiểu:

```text
margin = 0.03
window = 512
horizon = 512
min_feedback = 8
eta = 0.7
beta = 2.0
```

Thay vào đó, tạo nhiều fallback rule khác nhau.

Ví dụ:

```text
Rule A: margin=0.01, window=256,  horizon=512,  min_feedback=4,  beta=1.0
Rule B: margin=0.03, window=512,  horizon=1024, min_feedback=8,  beta=2.0
Rule C: margin=0.05, window=1024, horizon=2048, min_feedback=16, beta=4.0
```

Mỗi rule quyết định:

```text
Nếu RawML_recent_loss <= best_classic_loss + margin:
    dùng RawML
Ngược lại:
    fallback về expert classic tốt nhất gần đây
```

## 4. Biến mỗi rule thành một meta-expert

```text
MetaExpert A = RawML + fallback rule A
MetaExpert B = RawML + fallback rule B
MetaExpert C = RawML + fallback rule C
...
```

Mỗi meta-expert tự đưa ra eviction cuối cùng của nó.

## 5. Meta-Hedge tự học tham số tốt nhất

Meta-Hedge giữ trọng số cho từng meta-expert:

```text
w_A, w_B, w_C, ...
```

Khi một meta-expert gây loss lớn:

```text
w_i ← w_i * exp(-eta_meta * loss_i)
```

Khi meta-expert hoạt động tốt, trọng số tương đối của nó được giữ cao hơn.

Eviction cuối cùng:

```text
Lấy weighted vote từ các meta-expert
Evict item có tổng trọng số vote cao nhất
```

## 6. Những tham số được tự học

Các tham số sau không còn chọn tay một giá trị duy nhất:

```text
fallback_margin
recovery_margin
window
feedback_horizon
min_feedback
soft_beta
eta_inner
eta_meta
```

Chúng được đưa vào nhiều rule khác nhau, rồi Meta-Hedge tự chọn rule tốt nhất online.

## 7. Pipeline cuối cùng

```text
Belady label D_t^+(x)
↓
Train RawML
↓
Tạo nhiều fallback rules với nhiều bộ tham số
↓
Mỗi rule = một meta-expert: RawML + fallback controller
↓
Meta-Hedge học online rule nào đáng tin nhất
↓
Eviction cuối cùng = weighted vote của các meta-expert
↓
Benchmark với OPT, LRU, LFU, MARK, RawML, Self-Tuning RawML Meta-Hedge
```

## 8. Lý do hướng này tốt

- Không cần tin một ngưỡng thủ công như `8`, `512`, `0.03`.
- RawML vẫn là trung tâm.
- LRU/LFU/MARK chỉ can thiệp khi một rule học được rằng RawML đang kém.
- Có nền tảng online learning rõ ràng: Hedge over fallback rules.
- Chạy được local CPU, không cần GPU.

## 9. Benchmark cần báo cáo

Báo cáo tối thiểu:

```text
OPT
LRU
LFU
MARK
RawML-only
HedgeFullDelayedAllExpertSoft
Self-Tuning RawML Meta-Hedge
```

Chỉ kết luận rule tự học tốt hơn nếu `Self-Tuning RawML Meta-Hedge` giảm cache misses ổn định trên nhiều dataset, không chỉ thắng một dataset riêng lẻ.
