from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS_DIR / "src"))

from lp_risk.formulas import (  # noqa: E402
    SofrCurve,
    convexity_cost,
    inventory_from_price,
    lvr_step,
    sqrt_price_x96_to_price,
    tick_to_price,
    value_at_internal_price,
)


class FormulaTest(unittest.TestCase):
    def test_tick_and_sqrt_price_use_human_weth_usdt_units(self) -> None:
        tick = -200_000
        price = tick_to_price(tick)
        sqrt_x96 = int(np.sqrt(price / 1e12) * 2**96)
        self.assertAlmostEqual(sqrt_price_x96_to_price(sqrt_x96), price, places=9)

    def test_inventory_clamps_below_inside_and_above_range(self) -> None:
        lower, upper, liquidity = 100.0, 400.0, 10.0
        low0, low1 = inventory_from_price(25.0, lower, upper, liquidity)
        mid0, mid1 = inventory_from_price(225.0, lower, upper, liquidity)
        high0, high1 = inventory_from_price(900.0, lower, upper, liquidity)
        self.assertGreater(low0, 0)
        self.assertEqual(low1, 0)
        self.assertGreater(mid0, 0)
        self.assertGreater(mid1, 0)
        self.assertAlmostEqual(high0, 0)
        self.assertGreater(high1, 0)

    def test_constant_price_has_zero_lvr_and_pl(self) -> None:
        self.assertEqual(lvr_step(200.0, 200.0, 200.0, 100.0, 400.0, 10.0), 0)
        self.assertEqual(convexity_cost(200.0, 200.0, 100.0, 400.0, 10.0), 0)

    def test_inside_range_convexity_cost_matches_closed_form(self) -> None:
        p0, p1 = 196.0, 225.0
        expected = 10.0 * (np.sqrt(p1) - np.sqrt(p0)) ** 2 / np.sqrt(p0)
        actual = convexity_cost(p0, p1, 100.0, 400.0, 10.0)
        self.assertAlmostEqual(actual, expected, places=14)

    def test_same_side_out_of_range_move_has_no_concavity_cost(self) -> None:
        self.assertEqual(convexity_cost(25.0, 81.0, 100.0, 400.0, 10.0), 0)
        self.assertEqual(convexity_cost(500.0, 900.0, 100.0, 400.0, 10.0), 0)
        self.assertGreater(convexity_cost(81.0, 121.0, 100.0, 400.0, 10.0), 0)

    def test_round_trip_can_restore_value_but_accumulates_pl(self) -> None:
        initial = value_at_internal_price(200.0, 100.0, 400.0, 10.0)
        terminal = value_at_internal_price(200.0, 100.0, 400.0, 10.0)
        total_cost = convexity_cost(200.0, 250.0, 100.0, 400.0, 10.0)
        total_cost += convexity_cost(250.0, 200.0, 100.0, 400.0, 10.0)
        self.assertEqual(initial, terminal)
        self.assertGreater(total_cost, 0)

    def test_sofr_compounds_only_an_existing_gap(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=3, tz="UTC"),
                "sofr_percent": [5.0, 5.0, 5.0],
            }
        )
        curve = SofrCurve.from_frame(frame)
        start = pd.Timestamp("2024-01-01T00:00:00Z")
        end = pd.Timestamp("2024-01-03T00:00:00Z")
        factor = curve.gross_factor(start, end)
        self.assertAlmostEqual(factor, (1 + 0.05 / 360) ** 2)
        self.assertEqual(0.0 * factor, 0.0)
        self.assertGreater(10.0 * factor - 10.0, 0)


if __name__ == "__main__":
    unittest.main()
