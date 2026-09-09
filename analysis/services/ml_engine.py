"""
ML signal engine — ported and extended from bot.py:
 - build_pipeline() -> now a voting ensemble of RF, GradientBoosting,
   AdaBoost, XGBoost, LightGBM, Logistic Regression, SVC and MLP
   (soft voting, calibrated), with imputation + scaling + SelectKBest.

One SymbolModel is trained per Deriv market, on that market's own
historical candles, and cached to disk under settings.ML_MODELS_DIR so a
restart doesn't force a full retrain of every market at once.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
from django.conf import settings

# ML libraries are optional for Vercel deployment - degrade gracefully
try:
    import joblib
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import (
        AdaBoostClassifier,
        GradientBoostingClassifier,
        RandomForestClassifier,
        VotingClassifier,
    )
    from sklearn.feature_selection import SelectKBest, f_classif
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logging.warning("sklearn not installed. ML functionality will be disabled.")

from .indicators import NUMERIC_FEATURES, add_technical_indicators

logger = logging.getLogger(__name__)

# XGBoost / LightGBM are optional — degrade gracefully if a host
# doesn't have them installed rather than crashing the whole engine.
try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from lightgbm import LGBMClassifier
    _HAS_LGBM = True
except ImportError:
    _HAS_LGBM = False

LABEL_MOVE_THRESHOLD = 0.015  # predict a >1.5% next-candle move, same as bot.py
MIN_TRAINING_ROWS = 120
CONFIDENCE_THRESHOLD = 0.6  # Lower threshold from 0.75 to catch more signals


def build_sklearn_pipeline() -> Pipeline:
    """Full sklearn ensemble: RF + GB + AdaBoost (+ XGB/LGBM if available)
    + LogisticRegression + SVC + MLP, soft-voting."""
    if not _HAS_SKLEARN:
        raise ImportError("sklearn not installed. ML functionality disabled.")

    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    preprocessor = ColumnTransformer(transformers=[("num", numeric_transformer, NUMERIC_FEATURES)])

    estimators = [
        ("rf", RandomForestClassifier(n_estimators=150, random_state=42)),
        ("gb", GradientBoostingClassifier(n_estimators=100, random_state=42)),
        ("ada", AdaBoostClassifier(n_estimators=100, random_state=42)),
        ("logreg", LogisticRegression(max_iter=1000)),
        ("svc", SVC(probability=True, random_state=42)),
        ("mlp", MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42)),
    ]
    if _HAS_XGB:
        estimators.append(("xgb", XGBClassifier(
            n_estimators=150, use_label_encoder=False, eval_metric="logloss", random_state=42,
        )))
    if _HAS_LGBM:
        estimators.append(("lgbm", LGBMClassifier(n_estimators=150, random_state=42, verbose=-1)))

    ensemble = VotingClassifier(estimators=estimators, voting="soft")
    k = min(15, len(NUMERIC_FEATURES))

    return Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("feature_selection", SelectKBest(score_func=f_classif, k=k)),
        ("model", ensemble),
    ])


def _label_significant_move(df: pd.DataFrame) -> pd.Series:
    return (df["close"].pct_change().shift(-1).abs() > LABEL_MOVE_THRESHOLD).astype(int)


class SymbolModel:
    """Bundles the sklearn ensemble trained for one market."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.sklearn_pipeline: Pipeline | None = None
        self.trained_at: float = 0.0

    # -- persistence ---------------------------------------------------
    def _paths(self):
        root: Path = settings.ML_MODELS_DIR
        root.mkdir(parents=True, exist_ok=True)
        return {
            "sk": root / f"{self.symbol}_sklearn.joblib",
            "meta": root / f"{self.symbol}_meta.joblib",
        }

    def save(self):
        if not _HAS_SKLEARN:
            return
        p = self._paths()
        if self.sklearn_pipeline is not None:
            joblib.dump(self.sklearn_pipeline, p["sk"])
        joblib.dump({"trained_at": self.trained_at}, p["meta"])

    def load_if_fresh(self, max_age_hours: int) -> bool:
        if not _HAS_SKLEARN:
            return False
        p = self._paths()
        if not p["meta"].exists() or not p["sk"].exists():
            return False
        meta = joblib.load(p["meta"])
        age_hours = (time.time() - meta.get("trained_at", 0)) / 3600
        if age_hours > max_age_hours:
            return False
        self.sklearn_pipeline = joblib.load(p["sk"])
        self.trained_at = meta["trained_at"]
        return True

    # -- training --------------------------------------------------------
    def train(self, df: pd.DataFrame) -> bool:
        if not _HAS_SKLEARN:
            logger.info("sklearn not installed. Skipping ML training for %s", self.symbol)
            return False

        df = add_technical_indicators(df)
        if len(df) < MIN_TRAINING_ROWS:
            logger.info("Not enough candles to train %s (%d rows)", self.symbol, len(df))
            return False

        X = df[NUMERIC_FEATURES].fillna(0)
        y = _label_significant_move(df)
        if y.nunique() < 2:
            logger.info("Only one class present for %s, skipping training", self.symbol)
            return False

        # Check if we have enough samples for stratified split
        min_class_count = int(y.value_counts().min())

        # Use stratify only if each class has at least 2 samples
        use_stratify = min_class_count >= 2

        if use_stratify:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
        else:
            logger.warning("Insufficient samples for stratified split on %s (min class: %d), using random split",
                          self.symbol, min_class_count)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        pipeline = build_sklearn_pipeline()
        pipeline.fit(X_train, y_train)
        self.sklearn_pipeline = pipeline

        self.trained_at = time.time()
        self.save()
        logger.info("Trained model for %s on %d rows", self.symbol, len(df))
        return True

    # -- inference --------------------------------------------------------
    def predict_proba_up(self, df_with_indicators: pd.DataFrame) -> float:
        """Probability of an upward significant move, 0..1."""
        if not _HAS_SKLEARN:
            return 0.5  # Neutral probability when ML is disabled

        latest = df_with_indicators[NUMERIC_FEATURES].iloc[[-1]].fillna(0)

        sk_proba = 0.5
        if self.sklearn_pipeline is not None:
            proba = self.sklearn_pipeline.predict_proba(latest)[0]
            classes = list(self.sklearn_pipeline.classes_)
            sk_proba = proba[classes.index(1)] if 1 in classes else proba[-1]

        return float(sk_proba)


class ModelRegistry:
    """In-memory cache of SymbolModel instances, one per market."""

    def __init__(self):
        self._models: dict[str, SymbolModel] = {}

    def get_or_train(self, symbol: str, history_df: pd.DataFrame) -> SymbolModel:
        model = self._models.get(symbol)
        if model is None:
            model = SymbolModel(symbol)
            if model.load_if_fresh(settings.MODEL_RETRAIN_HOURS):
                self._models[symbol] = model
                return model

        if model.sklearn_pipeline is None or self._is_stale(model):
            model.train(history_df)

        self._models[symbol] = model
        return model

    @staticmethod
    def _is_stale(model: SymbolModel) -> bool:
        age_hours = (time.time() - model.trained_at) / 3600
        return age_hours > settings.MODEL_RETRAIN_HOURS


registry = ModelRegistry()
