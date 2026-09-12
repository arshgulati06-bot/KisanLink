#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KisanLink ML Pipeline — Automated Tests
=========================================
Tests for: gap detection, winsorization, APMC normalization,
Pimpalgaon regression, nonexistent market, forecast shape,
evaluation behaviour, and sparse-segment fallback.

Run from project root: python -m pytest tests/test_ml_pipeline.py -v
OR:                    python tests/test_ml_pipeline.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import torch
import pytest

from ml import config
from ml.data_loader import (
    _truncate_at_gap,
    _winsorize_prices,
    get_market_data,
    prepare_context,
    load_combined_data,
)
from ml.evaluator import evaluate_model

# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def combined_df():
    """
    Load the combined dataset ONCE for all tests.

    The historical CSVs are large and gitignored, so a clean checkout will not
    have them. Skip rather than error: these are regression tests against the
    real data, and their absence is an environment fact, not a code failure.
    """
    missing = [p for p in (config.CSV_AGRICULTURE, config.CSV_2022, config.CSV_2026)
               if not os.path.exists(p)]
    if missing:
        pytest.skip(
            "Historical mandi CSVs not present in ml/data/ "
            f"(missing: {', '.join(os.path.basename(m) for m in missing)}). "
            "These regression tests require the real dataset."
        )
    return load_combined_data()


@pytest.fixture(scope="module")
def pimpalgaon_mdf(combined_df):
    """Filtered market data for Tomato/Maharashtra/Nashik/Pimpalgaon."""
    return get_market_data(combined_df, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon")


@pytest.fixture(scope="module")
def pimpalgaon_ctx(pimpalgaon_mdf):
    """Full prepare_context output for Pimpalgaon tomatoes."""
    return prepare_context(pimpalgaon_mdf["data"])


# ===========================================================================
# 1. Gap detection — basic cases
# ===========================================================================

class TestGapDetection:

    def _make_series(self, *segments):
        """Build (prices, dates) from segments like [(price_val, n_days), (gap_days, 0), ...]."""
        prices, dates = [], []
        current = pd.Timestamp("2022-01-01")
        for item in segments:
            if isinstance(item, tuple) and item[1] == 0:
                current += pd.Timedelta(days=item[0])
            else:
                val, n = item
                for _ in range(n):
                    prices.append(float(val))
                    dates.append(current)
                    current += pd.Timedelta(days=1)
        return np.array(prices), pd.DatetimeIndex(dates)

    def test_no_gap(self):
        prices, dates = self._make_series((1000, 50))
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 50
        assert info is None, "No truncation expected when no qualifying gap"

    def test_small_gap_not_truncated(self):
        """A 180-day gap (< 365) must NOT trigger truncation."""
        prices, dates = self._make_series((1000, 50), (180, 0), (2000, 30))
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 80, "Full series expected; 180d < 365d threshold"
        assert info is None

    def test_large_gap_truncates_to_recent(self):
        """A ~900-day gap MUST trigger truncation to the recent segment."""
        prices, dates = self._make_series((500, 50), (900, 0), (5000, 100))
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 100, "Should use only the 100-obs post-gap segment"
        assert info is not None
        # The gap is either 900 or 901 calendar days depending on how the
        # helper stitches consecutive daily dates; either is correct.
        import re
        gap_match = re.search(r"Gap of (\d+) days", info)
        assert gap_match is not None, f"Expected gap description in: {info}"
        assert int(gap_match.group(1)) >= 900, f"Expected gap >= 900 days, got: {info}"
        # All prices in segment should be the high-era value
        assert np.all(p == 5000.0)


    def test_large_gap_but_tiny_latest_segment_falls_back(self):
        """When post-gap segment < min_records, walk to an older gap."""
        # Gap A (1000d) → 200 obs  |  Gap B (800d, more recent) → 5 obs (< 14)
        prices, dates = self._make_series(
            (1000, 10),     # very old era
            (1000, 0),      # gap A = 1000 days
            (2000, 200),    # middle era
            (800, 0),       # gap B = 800 days
            (3000, 5),      # latest era — too short
        )
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        # Must skip tiny 5-obs segment and use 200-obs segment after gap A
        assert len(p) == 205, f"Expected 205 (200+5 after gap A), got {len(p)}"
        assert info is not None

    def test_two_gaps_second_oldest_wins_over_tiny_latest(self):
        """With gaps A and B (B more recent), B→5 obs too small; A→205 obs used."""
        prices, dates = self._make_series(
            (1000, 10),
            (1000, 0),   # gap A = 1000 days
            (2000, 200),
            (800, 0),    # gap B = 800 days
            (3000, 5),   # 5 < 14
        )
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        # Skip tiny B (5 obs), use after A (200+5=205 obs)
        assert len(p) == 205, f"Expected 205, got {len(p)}"
        assert info is not None

    def test_all_segments_truly_tiny_uses_full_series(self):
        """Single qualifying gap with only 10 post-gap obs (< min_records): fall back to full."""
        prices, dates = self._make_series(
            (1000, 50),
            (400, 0),    # gap > 365
            (2000, 10),  # 10 < 14
        )
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 60, f"Expected 60 (full series), got {len(p)}"
        assert info is not None
        assert "full" in info.lower()

    def test_single_observation(self):
        prices = np.array([1000.0])
        dates  = pd.DatetimeIndex(["2022-01-01"])
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 1
        assert info is None


# ===========================================================================
# 2. Winsorization
# ===========================================================================

class TestWinsorization:

    def test_no_effect_on_normal_data(self):
        """Typical mandi prices (Rs. 500–5000) should not be touched."""
        np.random.seed(42)
        prices = np.random.uniform(500, 5000, 200)
        out = _winsorize_prices(prices, k=5.0)
        assert np.array_equal(prices, out), "Normal prices should not be modified"

    def test_caps_extreme_high(self):
        """A single absurd value (Rs. 191 million) must be capped."""
        prices = np.array([1000.0] * 100 + [191_820_849.0])
        out = _winsorize_prices(prices, k=5.0)
        assert out[-1] < 10_000, f"Extreme value must be capped; got {out[-1]}"

    def test_caps_extreme_low(self):
        """A zero or near-zero with otherwise normal data should be capped."""
        prices = np.array([2000.0] * 100 + [0.001])
        out = _winsorize_prices(prices, k=5.0)
        assert out[-1] > 0.0, "Capped value must be >= 0"

    def test_legitimate_high_price_unchanged(self):
        """Rs. 220,000 for exotic flowers (valid high price) should NOT be capped."""
        prices = np.array([200_000.0] * 50 + [220_000.0] * 50)
        out = _winsorize_prices(prices, k=5.0)
        # With k=5: hi = Q3 + max(5*IQR, 5*Q3) = 220k + max(100k, 1100k) = 1.32M
        # All values are <= 220k, well inside the fence. No change expected.
        max_change = np.max(np.abs(out - prices))
        assert max_change < 1, "Legitimate high prices should not be changed at all"

    def test_returns_copy(self):
        """Winsorization must not modify the original array."""
        prices = np.array([1000.0, 999999.0, 1200.0, 1100.0, 900.0])
        orig   = prices.copy()
        _winsorize_prices(prices, k=5.0)
        assert np.array_equal(prices, orig), "Original must not be modified"

    def test_iqr_zero_constant_series_outlier_capped(self):
        """When IQR=0 (all identical prices except one), outlier must still be capped."""
        prices = np.array([1000.0] * 200 + [5_000_000.0])
        out = _winsorize_prices(prices, k=5.0)
        # hi = q3 + max(0, 5*1000) = 1000 + 5000 = 6000
        assert out[-1] <= 6500, f"Expected cap ~6000, got {out[-1]:.0f}"

    def test_too_short_array(self):
        """Arrays with < 4 elements are returned as-is."""
        prices = np.array([1000.0, 2000.0])
        out = _winsorize_prices(prices, k=5.0)
        assert np.array_equal(prices, out)


# ===========================================================================
# 3. APMC suffix normalization
# ===========================================================================

class TestAPMCNormalization:

    def test_pimpalgaon_apmc_resolves(self, combined_df):
        """'Pimpalgaon APMC' must resolve to 'Pimpalgaon'."""
        r = get_market_data(combined_df, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon APMC")
        assert r["source"] != "Insufficient data", "APMC suffix should be stripped"
        assert r["record_count"] > 0

    def test_nonexistent_market_returns_error(self, combined_df):
        """A completely made-up market must return Insufficient data."""
        r = get_market_data(combined_df, "Tomato", "Maharashtra", "Nashik", "FakeMarketXYZ")
        assert r["source"] == "Insufficient data"
        assert "available_markets" in r

    def test_nonexistent_commodity_returns_error(self, combined_df):
        """A made-up commodity must return Insufficient data."""
        r = get_market_data(combined_df, "SomeFakeCommodity123", "Maharashtra", "Nashik", "Pimpalgaon")
        assert r["source"] == "Insufficient data"


# ===========================================================================
# 4. Pimpalgaon regression — prepare_context
# ===========================================================================

class TestPimpalgaonRegression:

    def test_pimpalgaon_returns_data(self, pimpalgaon_mdf):
        assert pimpalgaon_mdf["source"] != "Insufficient data"
        assert pimpalgaon_mdf["record_count"] > 0

    def test_context_tensor_shape(self, pimpalgaon_ctx):
        tensor = pimpalgaon_ctx["context_tensor"]
        assert tensor.ndim == 2
        assert tensor.shape[0] == 1
        assert 1 <= tensor.shape[1] <= config.MAX_CONTEXT_LENGTH

    def test_prices_nonnegative(self, pimpalgaon_ctx):
        prices = pimpalgaon_ctx["prices"]
        assert np.all(prices >= 0), "Prices must be non-negative after winsorization"

    def test_prices_not_zero(self, pimpalgaon_ctx):
        prices = pimpalgaon_ctx["prices"]
        assert np.all(prices > 0), "Winsorized prices should be > 0 for this market"

    def test_dates_chronological(self, pimpalgaon_ctx):
        dates = pimpalgaon_ctx["dates"]
        assert len(dates) > 0
        diffs = pd.Series(dates).diff().dropna()
        assert (diffs >= pd.Timedelta(0)).all(), "Dates must be in ascending order"

    def test_context_length_consistent(self, pimpalgaon_ctx):
        assert pimpalgaon_ctx["context_length"] == pimpalgaon_ctx["context_tensor"].shape[1]

    def test_gap_info_is_string_or_none(self, pimpalgaon_ctx):
        gi = pimpalgaon_ctx.get("gap_info")
        assert gi is None or isinstance(gi, str)

    def test_n_winsorized_nonneg(self, pimpalgaon_ctx):
        assert pimpalgaon_ctx.get("n_winsorized", 0) >= 0


# ===========================================================================
# 5. Forecast output shape
# ===========================================================================

class TestForecastShape:

    def test_forecast_length(self, pimpalgaon_ctx):
        from ml.forecaster import forecast_prices, load_model
        pipeline = load_model()
        fc = forecast_prices(pipeline, pimpalgaon_ctx["context_tensor"])
        assert len(fc) == config.FORECAST_HORIZON, (
            f"Expected {config.FORECAST_HORIZON} forecast values, got {len(fc)}")

    def test_forecast_nonneg(self, pimpalgaon_ctx):
        from ml.forecaster import forecast_prices, load_model
        pipeline = load_model()
        fc = forecast_prices(pipeline, pimpalgaon_ctx["context_tensor"])
        assert np.all(fc >= 0), "Forecast values must be non-negative"

    def test_forecast_scale_consistent(self, pimpalgaon_ctx):
        from ml.forecaster import forecast_prices, load_model
        pipeline = load_model()
        fc = forecast_prices(pipeline, pimpalgaon_ctx["context_tensor"])
        prices = pimpalgaon_ctx["prices"]
        recent_median = float(np.median(prices[-30:]))
        fc_median = float(np.median(fc))
        ratio = fc_median / recent_median if recent_median > 0 else 0
        assert 0.05 <= ratio <= 20, (
            f"Forecast scale ratio {ratio:.2f} is extreme relative to recent prices "
            f"(fc_median={fc_median:.0f}, recent_median={recent_median:.0f})")


# ===========================================================================
# 6. Evaluation behaviour
# ===========================================================================

class TestEvaluation:

    def test_returns_none_when_insufficient(self):
        """evaluate_model must return None for tiny price series."""
        tiny_prices = np.array([1000.0] * 10)
        from ml.forecaster import load_model
        pipeline = load_model()
        result = evaluate_model(pipeline, tiny_prices)
        assert result is None

    def test_returns_metrics_when_sufficient(self, pimpalgaon_ctx):
        from ml.forecaster import load_model
        pipeline = load_model()
        prices = pimpalgaon_ctx["prices"]
        if len(prices) < config.MIN_EVAL_RECORDS:
            pytest.skip("Pimpalgaon segment too small for evaluation test")
        result = evaluate_model(pipeline, prices)
        assert result is not None
        assert "mae" in result
        assert "rmse" in result
        assert "mape" in result
        assert result["mae"] >= 0
        assert result["rmse"] >= 0
        assert result["mape"] >= 0

    def test_evaluation_uses_consistent_data(self, pimpalgaon_ctx):
        """evaluate_model must receive the SAME series used for forecasting."""
        # The key invariant: ctx["prices"] is the preprocessed series
        # used for BOTH forecasting and evaluation. This test verifies
        # that the prices returned by prepare_context are the ones passed to evaluate.
        ctx_prices = pimpalgaon_ctx["prices"]
        ctx_tensor = pimpalgaon_ctx["context_tensor"]
        # The context tensor's values must be a tail-slice of ctx_prices
        tensor_vals = ctx_tensor.squeeze(0).numpy()
        assert np.allclose(tensor_vals, ctx_prices[-len(tensor_vals):], atol=1e-3), (
            "Context tensor values must match the tail of ctx['prices']")


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    # Run without pytest for quick manual execution
    print("Running tests manually (use pytest for proper output)...")
    import traceback
    passed, failed = 0, []

    # Instantiate fixtures manually
    print("  Loading combined dataset...")
    combined = load_combined_data()
    print(f"  Loaded {len(combined):,} records")

    pimp_mdf = get_market_data(combined, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon")
    pimp_ctx = prepare_context(pimp_mdf["data"])

    fixtures = {
        "combined_df": combined,
        "pimpalgaon_mdf": pimp_mdf,
        "pimpalgaon_ctx": pimp_ctx,
    }

    test_classes = [
        TestGapDetection, TestWinsorization, TestAPMCNormalization,
        TestPimpalgaonRegression, TestForecastShape, TestEvaluation,
    ]

    for cls in test_classes:
        inst = cls()
        methods = [m for m in dir(cls) if m.startswith("test_")]
        for mname in methods:
            method = getattr(inst, mname)
            import inspect
            sig = inspect.signature(method)
            kwargs = {}
            for pname in list(sig.parameters.keys()):
                if pname in fixtures:
                    kwargs[pname] = fixtures[pname]
            try:
                method(**kwargs)
                print(f"  PASS  {cls.__name__}.{mname}")
                passed += 1
            except pytest.skip.Exception as e:
                print(f"  SKIP  {cls.__name__}.{mname}: {e}")
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{mname}: {e}")
                failed.append(f"{cls.__name__}.{mname}")

    print(f"\n  Results: {passed} passed, {len(failed)} failed")
    if failed:
        print(f"  FAILED: {failed}")
