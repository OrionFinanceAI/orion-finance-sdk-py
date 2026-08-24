"""Principal-component analysis of overlapping daily returns."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from orion_finance_sdk_py.stats.series import ReturnSeries


@dataclass(frozen=True)
class PCAResult:
    """Standardized PCA of an overlapping return panel."""

    explained_variance_ratio: np.ndarray
    loadings: pd.DataFrame
    scores: pd.DataFrame


def pca(
    returns: ReturnSeries | pd.DataFrame,
    *,
    n_components: int | None = None,
    standardize: bool = True,
) -> PCAResult:
    """Fit PCA on overlapping contiguous daily returns.

    Requires at least three overlapping rows and two columns. Default
    ``standardize=True`` matches the universe-research notebook
    (``StandardScaler`` then ``PCA``).
    """
    frame = returns.returns if isinstance(returns, ReturnSeries) else returns
    overlap = frame.dropna(how="any")
    if overlap.shape[0] < 3 or overlap.shape[1] < 2:
        raise ValueError("PCA needs at least 3 overlapping observations and 2 assets")
    matrix = overlap.to_numpy(dtype=float)
    if standardize:
        matrix = StandardScaler().fit_transform(matrix)
    k = overlap.shape[1] if n_components is None else n_components
    k = min(k, overlap.shape[0], overlap.shape[1])
    model = PCA(n_components=k)
    scores_arr = model.fit_transform(matrix)
    components = pd.Index([f"PC{i + 1}" for i in range(model.n_components_)])
    loadings = pd.DataFrame(
        model.components_.T,
        index=overlap.columns,
        columns=components,
    )
    scores = pd.DataFrame(scores_arr, index=overlap.index, columns=components)
    return PCAResult(
        explained_variance_ratio=np.asarray(model.explained_variance_ratio_),
        loadings=loadings,
        scores=scores,
    )
