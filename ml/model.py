"""Walk-forward training and prediction — the anti-lookahead core.

At each rebalance date in the out-of-sample window we train only on data whose
label window has fully closed **before** that date (a purge/embargo of `horizon`
days), then predict forward-return scores for every stock on that date. The model
never sees the future. Retraining happens periodically for efficiency.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import Ridge

from ml.features import FEATURES


def make_model() -> HistGradientBoostingRegressor:
    """Single gradient-boosted model (the workhorse baseline)."""
    return HistGradientBoostingRegressor(
        max_depth=3,
        learning_rate=0.05,
        max_iter=300,
        l2_regularization=1.0,
        min_samples_leaf=50,
        random_state=42,
    )


class EnsembleModel:
    """Rank-blended ensemble of diverse learners (Qlib DoubleEnsemble philosophy).

    Combines a gradient-booster (boosting), extra-trees (bagging), and ridge
    (linear). Each model's cross-sectional predictions are converted to ranks and
    averaged, so no single model's scale dominates and the blend is robust.
    """

    def __init__(self) -> None:
        self.models = [
            HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.05, max_iter=300,
                l2_regularization=1.0, min_samples_leaf=50, random_state=42,
            ),
            ExtraTreesRegressor(
                n_estimators=300, max_depth=6, min_samples_leaf=50,
                n_jobs=-1, random_state=7,
            ),
            Ridge(alpha=5.0),
        ]

    def fit(self, X: np.ndarray, y: np.ndarray) -> "EnsembleModel":
        for m in self.models:
            m.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        # X is one date's cross-section -> rank each model's output, then average.
        if len(X) == 0:
            return np.array([])
        ranks = [rankdata(m.predict(X)) / len(X) for m in self.models]
        return np.mean(ranks, axis=0)


def make_ensemble() -> EnsembleModel:
    return EnsembleModel()


ModelFactory = Callable[[], object]


def walk_forward_predict(
    data: pd.DataFrame,
    horizon: int,
    oos_frac: float = 0.35,
    rebalance_every: int = 5,
    retrain_every: int = 4,
    model_factory: ModelFactory = make_model,
) -> dict[pd.Timestamp, pd.Series]:
    """Return ``{rebalance_date: Series(symbol -> predicted score)}`` over the OOS window.

    - ``oos_frac``: fraction of history held out for evaluation (last portion).
    - ``rebalance_every``: trading-day gap between rebalances (5 ≈ weekly).
    - ``retrain_every``: refit the model every N rebalances (else reuse).
    """
    dates = data.index.get_level_values("date").unique().sort_values()
    n = len(dates)
    oos_start_idx = int(n * (1 - oos_frac))
    rebal_idxs = range(oos_start_idx, n, rebalance_every)

    preds: dict[pd.Timestamp, pd.Series] = {}
    model = None
    for i, idx in enumerate(rebal_idxs):
        t = dates[idx]
        # Refit periodically on all data whose label window closed before t.
        if model is None or i % retrain_every == 0:
            cutoff_idx = idx - horizon  # purge overlapping labels (embargo = horizon)
            if cutoff_idx <= 0:
                continue
            cutoff_date = dates[cutoff_idx]
            train = data[data.index.get_level_values("date") <= cutoff_date]
            if len(train) < 500:
                continue
            model = model_factory()
            model.fit(train[FEATURES].to_numpy(), train["fwd_ret"].to_numpy())

        if t not in data.index.get_level_values("date"):
            continue
        X_t = data.xs(t, level="date")
        scores = pd.Series(model.predict(X_t[FEATURES].to_numpy()), index=X_t.index)
        preds[t] = scores
    return preds


def feature_importance(data: pd.DataFrame, horizon: int) -> pd.Series:
    """Permutation-free proxy: train on the in-sample portion and report the
    model's split-based importances, for sanity-checking which factors matter.
    """
    dates = data.index.get_level_values("date").unique().sort_values()
    cutoff = dates[int(len(dates) * 0.65)]
    train = data[data.index.get_level_values("date") <= cutoff]
    model = make_model()
    model.fit(train[FEATURES].to_numpy(), train["fwd_ret"].to_numpy())
    # HistGBR has no native importances; use a quick permutation on a sample.
    from sklearn.inspection import permutation_importance

    sample = train.sample(min(5000, len(train)), random_state=0)
    r = permutation_importance(
        model, sample[FEATURES].to_numpy(), sample["fwd_ret"].to_numpy(),
        n_repeats=3, random_state=0,
    )
    return pd.Series(r.importances_mean, index=FEATURES).sort_values(ascending=False)
