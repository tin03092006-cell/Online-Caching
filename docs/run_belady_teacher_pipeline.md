# Run Belady teacher RawML pipeline

This branch adds a separate training entry point for RawML trained on the Belady/OPT next-access-distance label.

Run:

```bash
python -m src.train_belady_teacher --config configs/belady_teacher.yaml
```

The pipeline writes:

- `data/processed/train_features_belady_teacher.csv`
- `data/processed/validation_features_belady_teacher.csv`
- `data/processed/benchmark_results_belady_teacher.csv`
- `data/processed/training_metadata_belady_teacher.json`

The target column remains `target_next_distance`. It is D_t^+(x), the next-access-distance label. It is not included in `FEATURE_COLUMNS`.
