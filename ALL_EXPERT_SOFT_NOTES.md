# All-Expert Soft Hedge

Use all four experts symmetrically:

```text
LRU, LFU, MARK, RawML
```

Decision rule:

```text
adjusted_weight(e) = hedge_weight(e) * exp(-beta * recent_loss(e))
```

Current beta:

```text
ALL_EXPERT_SOFT_BETA = 2.0
```

Goal:

```text
avoid hard anchoring to LRU/LFU
let every expert compete by recent online performance
```
