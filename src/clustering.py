from __future__ import annotations

import os

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


def add_clusters(scored: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    clustered = scored.copy()
    cols = [
        "supply_score",
        "demand_score",
        "access_penalty",
        "mismatch_penalty",
        "culture_gap_score",
    ]
    x = StandardScaler().fit_transform(clustered[cols])
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clustered["cluster"] = kmeans.fit_predict(x)
    return clustered
