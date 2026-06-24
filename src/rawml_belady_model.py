from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from .data import FEATURE_COLUMNS
from .belady_teacher_label import BELADY_TEACHER_LABEL_COLUMN, validate_rawml_belady_schema


class BeladyTeacherRawMLPredictor:
    """RawML predictor trained to approximate Belady/OPT next distance.

    The model learns

        f_theta(history_features) ~= D_t^+(x)

    where D_t^+(x) is the true next-access distance used by Belady/OPT. The
    label is used only during supervised training/evaluation; online eviction
    receives only FEATURE_COLUMNS.
    """

    def __init__(self, model_config: dict[str, Any], seed: int) -> None:
        if model_config["type"] != "gradient_boosting":
            raise ValueError("Only model.type='gradient_boosting' is supported.")

        self.model = GradientBoostingRegressor(
            learning_rate=float(model_config["learning_rate"]),
            n_estimators=int(model_config["n_estimators"]),
            max_depth=int(model_config["max_depth"]),
            random_state=seed,
        )
        self.is_fitted = False
        self.label_column = BELADY_TEACHER_LABEL_COLUMN
        self.feature_columns = list(FEATURE_COLUMNS)

    def fit(self, training_frame: pd.DataFrame) -> None:
        validate_rawml_belady_schema(training_frame)
        feature_frame = training_frame[self.feature_columns]
        target_values = training_frame[self.label_column]
        self.model.fit(feature_frame, target_values)
        self.is_fitted = True

    def predict_distances(self, feature_frame: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError(
                "BeladyTeacherRawMLPredictor must be fitted before prediction."
            )
        missing_feature_columns = [
            feature_column
            for feature_column in self.feature_columns
            if feature_column not in feature_frame.columns
        ]
        if missing_feature_columns:
            raise ValueError(f"Missing RawML feature columns: {missing_feature_columns}")
        return np.asarray(self.model.predict(feature_frame[self.feature_columns]), dtype=float)

    def evaluate_mae(self, evaluation_frame: pd.DataFrame) -> float:
        validate_rawml_belady_schema(evaluation_frame)
        feature_frame = evaluation_frame[self.feature_columns]
        target_values = evaluation_frame[self.label_column]
        predictions = self.predict_distances(feature_frame)
        return float(mean_absolute_error(target_values, predictions))

    def feature_importance_dict(self) -> dict[str, float]:
        if not self.is_fitted:
            raise RuntimeError(
                "BeladyTeacherRawMLPredictor must be fitted before feature importance."
            )
        return {
            feature_name: float(importance)
            for feature_name, importance in zip(
                self.feature_columns,
                self.model.feature_importances_,
                strict=True,
            )
        }
