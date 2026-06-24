# RawML Belady teacher label

RawML should learn the next-access-distance label `target_next_distance`, denoted D_t^+(x). This is the same future signal that Belady/OPT uses when it is available offline.

The valid training scheme is:

- Features: history-only online features such as recency, frequency, recent frequency, average inter-arrival, and cache age.
- Label: `target_next_distance = D_t^+(x)` computed inside the train or validation split.
- Online prediction: RawML predicts the next distance from history-only features and evicts the item with the largest predicted distance.
- Fallback: Hedge combines RawML with LRU, LFU, and MARK. If RawML is weak on a trace segment, Hedge can reduce its weight and rely more on the classic experts.

The label must not be inserted into `FEATURE_COLUMNS`, because that would leak future information into online prediction.
