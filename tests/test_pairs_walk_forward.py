from __future__ import annotations

import numpy as np
import pandas as pd

from pairs_walk_forward import formation_stats


def test_formation_stats_reports_cointegration_and_finite_half_life():
    rng = np.random.default_rng(7)
    x = np.cumsum(rng.normal(0, 0.01, 500)) + 4.0
    residual = rng.normal(0, 0.01, 500)
    y = 0.3 + 1.2 * x + residual
    frame = pd.DataFrame({"A": np.exp(y), "B": np.exp(x)})

    stats = formation_stats("A-B", frame)

    assert stats.observations == 500
    assert stats.coint_pvalue < 0.05
    assert stats.half_life_bars > 0
