from __future__ import annotations

from . import train_soft
from .all_expert_soft import (
    run_hedge_full_cache,
    select_best_hedge_learning_rate,
)

train_soft.run_hedge_full_cache = run_hedge_full_cache
train_soft.select_best_hedge_learning_rate = select_best_hedge_learning_rate

main = train_soft.main
