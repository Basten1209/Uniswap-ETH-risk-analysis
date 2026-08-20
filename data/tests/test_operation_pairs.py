from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.operation_pairs import (
    build_operation_pairs,
    link_pool_burns_to_nfpm_decreases,
    prepare_liquidity_operations,
)

POOL = "0x1111111111111111111111111111111111111111"
MANAGER = "0x2222222222222222222222222222222222222222"
WALLET = "0x3333333333333333333333333333333333333333"


def tx_hash(number: int) -> str:
    return "0x" + f"{number:064x}"


def pool_event(
    event_type: str,
    block: int,
    transaction_number: int,
    log_index: int,
    liquidity: int,
    *,
    tick_lower: int = -100,
    tick_upper: int = 100,
) -> dict[str, object]:
    return {
        "block_number": block,
        "block_timestamp": pd.Timestamp("2022-01-01T00:00:00Z")
        + pd.Timedelta(seconds=block),
        "transaction_hash": tx_hash(transaction_number),
        "transaction_index": transaction_number,
        "log_index": log_index,
        "address": POOL,
        "event_type": event_type,
        "sender": MANAGER if event_type == "Mint" else None,
        "owner": MANAGER,
        "tick_lower": tick_lower,
        "tick_upper": tick_upper,
        "liquidity_delta_raw": str(
            liquidity if event_type == "Mint" else -liquidity
        ),
        "amount0_raw": str(liquidity * 2),
        "amount1_raw": str(liquidity * 3),
    }


def transactions_for(pool: pd.DataFrame) -> pd.DataFrame:
    return (
        pool[
            [
                "block_number",
                "block_timestamp",
                "transaction_hash",
                "transaction_index",
            ]
        ]
        .drop_duplicates("transaction_hash")
        .assign(from_address=WALLET, to_address=MANAGER)
        .reset_index(drop=True)
    )


class OperationPairTest(unittest.TestCase):
    def test_fifo_pairing_strict_ambiguity_and_intervening_events(self) -> None:
        rows = [
            pool_event("Mint", 1, 1, 1, 100),
            pool_event("Burn", 2, 2, 1, 100),
            pool_event("Mint", 3, 3, 1, 200, tick_lower=-200),
            pool_event("Mint", 4, 4, 1, 200, tick_lower=-200),
            pool_event("Burn", 5, 5, 1, 200, tick_lower=-200),
            pool_event("Mint", 6, 6, 1, 300, tick_lower=-300),
            pool_event("Burn", 6, 6, 2, 300, tick_lower=-300),
            pool_event("Burn", 7, 7, 1, 0, tick_lower=-400),
            pool_event("Burn", 8, 8, 1, 999, tick_lower=-500),
            pool_event("Mint", 9, 9, 1, 400, tick_lower=-600),
            pool_event("Burn", 10, 10, 1, 100, tick_lower=-600),
            pool_event("Burn", 11, 11, 1, 400, tick_lower=-600),
        ]
        pool = pd.DataFrame(rows)
        operations = prepare_liquidity_operations(pool, transactions_for(pool))
        operations, all_pairs, strict, ambiguous, unmatched = build_operation_pairs(
            operations
        )

        self.assertEqual(len(operations), 12)
        self.assertEqual(len(all_pairs), 4)
        self.assertEqual(len(strict), 1)
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(int(all_pairs["is_same_block"].sum()), 1)
        self.assertEqual(
            set(all_pairs["analysis_cohort"]),
            {"same_block_jit_mev_candidate", "multi_block_lp_position"},
        )
        self.assertEqual(
            ambiguous.iloc[0]["candidate_open_mint_count"], 2
        )
        same_tx = all_pairs.loc[all_pairs["is_same_transaction"]]
        self.assertEqual(len(same_tx), 1)
        intervening = all_pairs.loc[
            all_pairs["has_intervening_same_range_liquidity_event"]
        ]
        self.assertEqual(len(intervening), 2)
        self.assertFalse(intervening["is_strict_pair"].any())
        self.assertIn("zero_liquidity", set(unmatched["unmatched_reason"]))
        self.assertIn("no_preceding_exact_mint", set(unmatched["unmatched_reason"]))
        self.assertIn("no_subsequent_exact_burn", set(unmatched["unmatched_reason"]))
        self.assertFalse(all_pairs["entry_event_id"].duplicated().any())
        self.assertFalse(all_pairs["exit_event_id"].duplicated().any())

    def test_nfpm_entry_and_exit_token_ids_are_preserved(self) -> None:
        mint = pool_event("Mint", 1, 1, 10, 100)
        burn = pool_event("Burn", 2, 2, 20, 100)
        pool = pd.DataFrame([mint, burn])
        mint_links = pd.DataFrame(
            [
                {
                    "transaction_hash": tx_hash(1),
                    "pool_mint_log_index": 10,
                    "token_id": "123",
                }
            ]
        )
        nfpm = pd.DataFrame(
            [
                {
                    "event_type": "DecreaseLiquidity",
                    "transaction_hash": tx_hash(2),
                    "block_number": 2,
                    "block_timestamp": burn["block_timestamp"],
                    "transaction_index": 2,
                    "log_index": 21,
                    "token_id": "123",
                    "liquidity_delta_raw": "-100",
                    "amount0_raw": "200",
                    "amount1_raw": "300",
                }
            ]
        )
        burn_links = link_pool_burns_to_nfpm_decreases(pool, nfpm, MANAGER)
        self.assertEqual(len(burn_links), 1)
        operations = prepare_liquidity_operations(
            pool,
            transactions_for(pool),
            mint_links=mint_links,
            burn_links=burn_links,
        )
        _, pairs, strict, _, _ = build_operation_pairs(operations)
        self.assertEqual(len(strict), 1)
        self.assertEqual(pairs.iloc[0]["entry_nfpm_token_id"], "123")
        self.assertEqual(pairs.iloc[0]["exit_nfpm_token_id"], "123")
        self.assertEqual(pairs.iloc[0]["nfpm_token_id"], "123")
        self.assertTrue(pairs.iloc[0]["nfpm_token_id_consistent"])


if __name__ == "__main__":
    unittest.main()
