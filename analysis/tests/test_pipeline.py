from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS_DIR / "src"))

from lp_risk.formulas import SofrCurve, inventory_from_price  # noqa: E402
from lp_risk.io import SwapPath, encode_event_order  # noqa: E402
from lp_risk.pipeline import calculate_lifetime_and_daily  # noqa: E402


class ConstantOracle:
    coverage_last = pd.Timestamp("2024-01-02T23:59:59Z")

    def lookup_strict_prior(self, timestamps: object) -> np.ndarray:
        return np.full(len(pd.DatetimeIndex(timestamps)), 200.0)


def constant_pair() -> pd.DataFrame:
    entry = pd.Timestamp("2024-01-01T00:00:00Z")
    exit_time = pd.Timestamp("2024-01-01T00:00:03Z")
    weth, usdt = inventory_from_price(200.0, 100.0, 400.0, 10.0)
    amount0_raw = str(round(weth * 1e18))
    amount1_raw = str(round(usdt * 1e6))
    initial = weth * 200.0 + usdt
    return pd.DataFrame(
        [
            {
                "operation_id": "constant",
                "tick_lower": round(np.log(100.0 / 1e12) / np.log(1.0001)),
                "tick_upper": round(np.log(400.0 / 1e12) / np.log(1.0001)),
                "liquidity_raw": "10000000000000",
                "entry_block_number": 10,
                "entry_timestamp": entry,
                "entry_transaction_index": 1,
                "entry_log_index": 1,
                "entry_amount0_raw": amount0_raw,
                "entry_amount1_raw": amount1_raw,
                "exit_block_number": 12,
                "exit_timestamp": exit_time,
                "exit_transaction_index": 1,
                "exit_log_index": 1,
                "exit_amount0_raw": amount0_raw,
                "exit_amount1_raw": amount1_raw,
                "price_timestamp_entry": entry - pd.Timedelta(seconds=1),
                "price_timestamp_exit": exit_time - pd.Timedelta(seconds=1),
                "token0_price_usdt_entry": "200",
                "token0_price_usdt_exit": "200",
                "initial_wealth_usdt": str(initial),
                "principal_exit_value_usdt": str(initial),
                "hodl_exit_value_usdt": str(initial),
                "holding_seconds": 3.0,
                "is_strict_pair": True,
            }
        ]
    )


class PipelineTest(unittest.TestCase):
    def test_event_order_encoding_is_lexicographic(self) -> None:
        keys = encode_event_order(
            np.array([1, 1, 2]), np.array([2, 3, 0]), np.array([9, 0, 0])
        )
        self.assertTrue(np.all(np.diff(keys) > 0))

    def test_constant_path_has_zero_metrics_even_with_positive_sofr(self) -> None:
        swap_time = pd.Timestamp("2024-01-01T00:00:01Z").value
        swap_key = encode_event_order(11, 1, 1)
        swaps = SwapPath(
            keys=np.array([swap_key], dtype=np.int64),
            timestamps_ns=np.array([swap_time], dtype=np.int64),
            block_numbers=np.array([11]),
            transaction_indices=np.array([1]),
            log_indices=np.array([1]),
            pool_prices=np.array([200.0]),
            external_prices=np.array([200.0]),
            initialize_key=encode_event_order(1, 0, 0),
            initialize_price=200.0,
        )
        curve = SofrCurve.from_frame(
            pd.DataFrame(
                {
                    "date": pd.date_range("2023-12-31", periods=3, tz="UTC"),
                    "sofr_percent": [5.0, 5.0, 5.0],
                }
            )
        )
        positions, daily = calculate_lifetime_and_daily(
            constant_pair(),
            swaps,
            ConstantOracle(),
            curve,
            enforce_frozen_sample=False,
        )
        row = positions.iloc[0]
        self.assertAlmostEqual(row["il_loss_usdt"], 0.0)
        self.assertAlmostEqual(row["lvr_rebalancing_usdt"], 0.0)
        self.assertAlmostEqual(row["pl_core_convexity_usdt"], 0.0)
        self.assertAlmostEqual(row["pl_opportunity_cost_usdt"], 0.0)
        self.assertAlmostEqual(row["pl_loss_usdt"], 0.0)
        self.assertAlmostEqual(daily.iloc[0]["capital_weighted_pl_loss_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
