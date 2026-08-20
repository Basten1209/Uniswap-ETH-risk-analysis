from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.pair_returns import (  # noqa: E402
    attribute_realized_fees,
    calculate_pair_returns,
    overlapping_fee_attribution_ids,
)


def pair(
    operation_id: str,
    entry_block: int,
    exit_block: int,
    *,
    token_id: str | None = "1",
    manager: str = "0xmanager",
    tick_lower: int = -100,
    tick_upper: int = 100,
) -> dict[str, object]:
    start = pd.Timestamp("2022-01-01T00:00:00Z")
    return {
        "operation_id": operation_id,
        "manager_address": manager,
        "tick_lower": tick_lower,
        "tick_upper": tick_upper,
        "liquidity_raw": "1000",
        "nfpm_token_id": token_id,
        "nfpm_token_id_consistent": token_id is not None,
        "entry_block_number": entry_block,
        "entry_block_timestamp": start + pd.Timedelta(seconds=entry_block),
        "entry_transaction_hash": f"0xentry{operation_id}",
        "entry_transaction_index": 1,
        "entry_log_index": 10,
        "entry_amount0_raw": "1000000000000000000",
        "entry_amount1_raw": "1000000",
        "exit_block_number": exit_block,
        "exit_block_timestamp": start + pd.Timedelta(seconds=exit_block),
        "exit_transaction_hash": f"0xexit{operation_id}",
        "exit_transaction_index": 2,
        "exit_log_index": 20,
        "exit_amount0_raw": "1000000000000000000",
        "exit_amount1_raw": "1000000",
        "holding_seconds": float(exit_block - entry_block),
    }


class PairReturnTest(unittest.TestCase):
    def test_overlapping_fee_identities_are_excluded(self) -> None:
        pairs = pd.DataFrame(
            [
                pair("a", 1, 5, token_id="7"),
                pair("b", 3, 6, token_id="7"),
                pair("c", 7, 8, token_id=None),
                pair("d", 9, 10, token_id=None),
            ]
        )
        self.assertEqual(overlapping_fee_attribution_ids(pairs), {"a", "b"})

    def test_realized_fee_uses_interim_and_post_burn_collects(self) -> None:
        pairs = pd.DataFrame([pair("a", 1, 4), pair("b", 5, 8, token_id=None)])
        nfpm = pd.DataFrame(
            [
                {
                    "event_type": "Collect",
                    "token_id": "1",
                    "block_number": 2,
                    "transaction_index": 1,
                    "log_index": 1,
                    "transaction_hash": "0xinterim",
                    "amount0_raw": "10",
                    "amount1_raw": "20",
                },
                {
                    "event_type": "Collect",
                    "token_id": "1",
                    "block_number": 4,
                    "transaction_index": 2,
                    "log_index": 21,
                    "transaction_hash": "0xexita",
                    "amount0_raw": "1000000000000000030",
                    "amount1_raw": "1000040",
                },
            ]
        )
        pool = pd.DataFrame(
            columns=[
                "event_type",
                "owner",
                "tick_lower",
                "tick_upper",
                "block_number",
                "transaction_index",
                "log_index",
                "transaction_hash",
                "amount0_raw",
                "amount1_raw",
            ]
        )
        fees = attribute_realized_fees(pairs, pool, nfpm, {"1"})
        first = fees.iloc[0]
        self.assertEqual(first["realized_fee0_raw"], "40")
        self.assertEqual(first["realized_fee1_raw"], "60")
        self.assertTrue(first["fee_complete_exact"])
        second = fees.iloc[1]
        self.assertEqual(second["realized_fee0_raw"], "0")
        self.assertFalse(second["exit_collect_observed"])

        event_times = pd.concat(
            [fees["entry_block_timestamp"], fees["exit_block_timestamp"]]
        )
        prices = pd.DataFrame(
            {
                "timestamp": [timestamp - pd.Timedelta(seconds=1) for timestamp in event_times],
                "token0_price_usdt": [2000, 2000, 2100, 2100],
                "token1_price_usdt": [1, 1, 1, 1],
            }
        )
        returns = calculate_pair_returns(fees, prices, 18, 6, 3600)
        self.assertTrue(returns["fee_analysis_included"].all())
        self.assertTrue(returns["lp_total_return_realized_fee"].notna().all())
        self.assertTrue(returns["realized_daily_log_return"].notna().all())


if __name__ == "__main__":
    unittest.main()
