from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.blocks import summarize_blocks_daily
from uniswap_v3_data.events import (
    NFPM_COLLECT,
    NFPM_DECREASE,
    NFPM_INCREASE,
    NFPM_TRANSFER,
    POOL_BURN,
    POOL_MINT,
    SIGNATURE_TO_TOPIC,
    ZERO_ADDRESS,
    parse_raw_events,
)
from uniswap_v3_data.positions import reconstruct_positions
from uniswap_v3_data.returns import calculate_closed_returns

POOL = "0x1111111111111111111111111111111111111111"
NFPM = "0x2222222222222222222222222222222222222222"
ALICE = "0x3333333333333333333333333333333333333333"
SENDER = "0x4444444444444444444444444444444444444444"


def event(
    block: int,
    timestamp: str,
    transaction_hash: str,
    log_index: int,
    address: str,
    signature: str,
    args: list[object],
) -> dict[str, object]:
    return {
        "block_number": block,
        "block_timestamp": timestamp,
        "transaction_hash": transaction_hash,
        "transaction_index": 0,
        "log_index": log_index,
        "address": address,
        "event_signature": signature,
        "args_json": json.dumps(args),
    }


def abi_word(value: int | str) -> str:
    if isinstance(value, str):
        return value.removeprefix("0x").zfill(64)
    return f"{value % (2**256):064x}"


def raw_event(
    block: int,
    transaction_hash: str,
    log_index: int,
    address: str,
    signature: str,
    indexed: list[int | str],
    unindexed: list[int | str],
) -> dict[str, object]:
    return {
        "block_number": block,
        "block_timestamp": "2021-06-01T00:00:00Z",
        "transaction_hash": transaction_hash,
        "transaction_index": 0,
        "log_index": log_index,
        "address": address,
        "topics_json": json.dumps(
            [SIGNATURE_TO_TOPIC[signature], *["0x" + abi_word(v) for v in indexed]]
        ),
        "data": "0x" + "".join(abi_word(v) for v in unindexed),
        "removed": False,
    }


class PositionPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        mint_tx = "0x" + "aa" * 32
        fee_tx = "0x" + "bb" * 32
        exit_tx = "0x" + "cc" * 32
        self.raw = pd.DataFrame(
            [
                event(
                    100,
                    "2021-06-01T00:00:00Z",
                    mint_tx,
                    10,
                    POOL,
                    POOL_MINT,
                    [SENDER, NFPM, -100, 100, 1000, 10**18, 2_000 * 10**6],
                ),
                event(
                    100,
                    "2021-06-01T00:00:00Z",
                    mint_tx,
                    11,
                    NFPM,
                    NFPM_TRANSFER,
                    [ZERO_ADDRESS, ALICE, 123],
                ),
                event(
                    100,
                    "2021-06-01T00:00:00Z",
                    mint_tx,
                    12,
                    NFPM,
                    NFPM_INCREASE,
                    [123, 1000, 10**18, 2_000 * 10**6],
                ),
                event(
                    150,
                    "2021-06-10T00:00:00Z",
                    fee_tx,
                    20,
                    NFPM,
                    NFPM_COLLECT,
                    [123, ALICE, 10**16, 20 * 10**6],
                ),
                event(
                    200,
                    "2021-07-01T00:00:00Z",
                    exit_tx,
                    30,
                    POOL,
                    POOL_BURN,
                    [NFPM, -100, 100, 1000, 9 * 10**17, 2_100 * 10**6],
                ),
                event(
                    200,
                    "2021-07-01T00:00:00Z",
                    exit_tx,
                    31,
                    NFPM,
                    NFPM_DECREASE,
                    [123, 1000, 9 * 10**17, 2_100 * 10**6],
                ),
                event(
                    200,
                    "2021-07-01T00:00:00Z",
                    exit_tx,
                    32,
                    NFPM,
                    NFPM_COLLECT,
                    [123, ALICE, 92 * 10**16, 2_110 * 10**6],
                ),
                event(
                    200,
                    "2021-07-01T00:00:00Z",
                    exit_tx,
                    33,
                    NFPM,
                    NFPM_TRANSFER,
                    [ALICE, ZERO_ADDRESS, 123],
                ),
            ]
        )

    def test_clean_position_and_lifetime_fee(self) -> None:
        pool, nfpm = parse_raw_events(self.raw, POOL, NFPM)
        positions, clean, links = reconstruct_positions(
            pool, nfpm, NFPM, date(2021, 1, 1), date(2022, 1, 1)
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(len(positions), 1)
        self.assertEqual(len(clean), 1)
        row = clean.iloc[0]
        self.assertTrue(row["is_clean_closed"])
        self.assertEqual(row["token_id"], "123")
        self.assertEqual(row["tick_lower"], -100)
        self.assertEqual(row["tick_upper"], 100)
        self.assertEqual(row["fee_amount0_raw"], str(3 * 10**16))
        self.assertEqual(row["fee_amount1_raw"], str(30 * 10**6))

    def test_raw_receipt_log_abi_decoding_and_link(self) -> None:
        mint_tx = "0x" + "dd" * 32
        raw = pd.DataFrame(
            [
                raw_event(
                    100,
                    mint_tx,
                    10,
                    POOL,
                    POOL_MINT,
                    [NFPM, -100, 100],
                    [SENDER, 1000, 10**18, 2_000 * 10**6],
                ),
                raw_event(
                    100,
                    mint_tx,
                    11,
                    NFPM,
                    NFPM_TRANSFER,
                    [ZERO_ADDRESS, ALICE, 123],
                    [],
                ),
                raw_event(
                    100,
                    mint_tx,
                    12,
                    NFPM,
                    NFPM_INCREASE,
                    [123],
                    [1000, 10**18, 2_000 * 10**6],
                ),
            ]
        )
        pool, nfpm = parse_raw_events(raw, POOL, NFPM)
        self.assertEqual(pool.iloc[0]["tick_lower"], -100)
        self.assertEqual(pool.iloc[0]["owner"], NFPM)
        self.assertEqual(nfpm.loc[nfpm["event_type"] == "Transfer"].iloc[0]["token_id"], "123")
        self.assertEqual(
            nfpm.loc[nfpm["event_type"] == "IncreaseLiquidity"].iloc[0][
                "amount0_raw"
            ],
            str(10**18),
        )

    def test_closed_return_conventions(self) -> None:
        pool, nfpm = parse_raw_events(self.raw, POOL, NFPM)
        _, clean, _ = reconstruct_positions(
            pool, nfpm, NFPM, date(2021, 1, 1), date(2022, 1, 1)
        )
        prices = pd.DataFrame(
            {
                "timestamp": ["2021-06-01T00:00:00Z", "2021-07-01T00:00:00Z"],
                "token0_price_usdt": ["2000", "2500"],
                "token1_price_usdt": ["1", "1"],
            }
        )
        result = calculate_closed_returns(clean, prices, 18, 6, 60)
        row = result.iloc[0]
        self.assertEqual(Decimal(row["initial_wealth_usdt"]), Decimal(4000))
        self.assertEqual(Decimal(row["principal_exit_value_usdt"]), Decimal(4350))
        self.assertEqual(Decimal(row["fee_exit_value_usdt"]), Decimal(105))
        self.assertEqual(Decimal(row["lp_exit_value_usdt"]), Decimal(4455))
        self.assertEqual(
            Decimal(row["lp_total_return_close_marked"]), Decimal("0.11375")
        )
        self.assertEqual(
            Decimal(row["lp_excess_return_vs_hodl_close"]), Decimal("-0.01")
        )

    def test_daily_block_gas_summary(self) -> None:
        blocks = pd.DataFrame(
            {
                "block_number": [1, 2],
                "block_timestamp": [
                    "2021-07-01T00:00:00Z",
                    "2021-07-01T00:00:12Z",
                ],
                "base_fee_per_gas": [100, 200],
                "gas_used": [50, 150],
                "gas_limit": [100, 300],
            }
        )
        row = summarize_blocks_daily(blocks).iloc[0]
        self.assertEqual(row["block_count"], 2)
        self.assertEqual(Decimal(row["mean_base_fee_per_gas_wei"]), Decimal(150))
        self.assertEqual(Decimal(row["mean_block_gas_utilization"]), Decimal("0.5"))


if __name__ == "__main__":
    unittest.main()
