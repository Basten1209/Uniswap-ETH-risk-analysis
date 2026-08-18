from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))
sys.path.insert(0, str(DATA_DIR / "scripts"))

import collect_bigquery
import prepare_fixed_pool
from uniswap_v3_data.config import (
    FixedPoolConfig,
    ResearchConfig,
    TokenConfig,
    collection_run_id,
    load_fixed_pool_config,
)

WETH = TokenConfig(
    symbol="WETH",
    address="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    decimals=18,
)
USDT = TokenConfig(
    symbol="USDT",
    address="0xdac17f958d2ee523a2206206994597c13d831ec7",
    decimals=6,
)
POOL = "0x11b815efb8f581194ae79006d24e0d814b7697f6"
NFPM = "0xc36442b4a4522e871399cd717abdd847ab11fe88"
FACTORY = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
EVENTS = "bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events"
BLOCKS = "bigquery-public-data.goog_blockchain_ethereum_mainnet_us.blocks"


class BigQuerySqlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixed = FixedPoolConfig(
            project="billing-project",
            location="US",
            network="ethereum-mainnet",
            factory_address=FACTORY,
            pool_address=POOL,
            nfpm_address=NFPM,
            fee_tier=500,
            token0=WETH,
            token1=USDT,
            events_table=EVENTS,
            blocks_table=BLOCKS,
        )
        self.research = ResearchConfig(
            project="billing-project",
            location="US",
            network="ethereum-mainnet",
            pool_address=POOL,
            nfpm_address=NFPM,
            fee_tier=500,
            token0=WETH,
            token1=USDT,
            start_date=date(2021, 5, 1),
            end_date=date(2026, 8, 18),
            start_block=12_000_000,
            end_block_exclusive=24_000_001,
            events_table=EVENTS,
            blocks_table=BLOCKS,
        )

    def test_fixed_config_loads_with_project_override(self) -> None:
        loaded = load_fixed_pool_config(
            DATA_DIR / "config" / "fixed_pool.example.json", "billing-project"
        )
        self.assertEqual(loaded.pool_address, POOL)
        self.assertEqual(loaded.fee_tier, 500)

    def test_snapshot_query_verifies_factory_and_finality(self) -> None:
        sql = prepare_fixed_pool.build_snapshot_query(
            self.fixed, lookback_days=14, finality_blocks=64
        )
        self.assertIn(FACTORY, sql)
        self.assertIn(POOL, sql)
        self.assertIn("PoolCreated(address,address,uint24,int24,address)", sql)
        self.assertIn("block_number = 12376751", sql)
        self.assertIn("2021-05-05", sql)
        self.assertIn("latest_decoded_block - 64", sql)
        self.assertIn(BLOCKS, sql)

    def test_seed_and_event_queries_are_target_only_and_block_bounded(self) -> None:
        seed_sql = collect_bigquery.build_position_seed_query(
            self.research, date(2022, 1, 1), date(2022, 2, 1)
        )
        event_sql = collect_bigquery.build_events_query(
            self.research, date(2022, 1, 1), date(2022, 2, 1)
        )
        self.assertIn(POOL, seed_sql)
        self.assertIn(NFPM, seed_sql)
        self.assertIn("p.log_index < n.log_index", seed_sql)
        self.assertIn("@target_token_ids", event_sql)
        self.assertIn("STRING(args[2]) IN UNNEST(@target_token_ids)", event_sql)
        self.assertIn("block_number >= 12000000", event_sql)
        self.assertIn("block_number < 24000001", event_sql)
        self.assertNotIn("removed", event_sql)

    def test_block_query_aggregates_before_download(self) -> None:
        sql = collect_bigquery.build_blocks_query(
            self.research,
            date(2022, 1, 1),
            date(2022, 2, 1),
            [
                "block_number",
                "block_timestamp",
                "base_fee_per_gas",
                "gas_used",
                "gas_limit",
            ],
        )
        self.assertIn("DATE(block_timestamp) AS date", sql)
        self.assertIn("COUNT(*) AS block_count", sql)
        self.assertIn("GROUP BY date", sql)
        self.assertNotIn("block_hash", sql)

    def test_run_id_uses_exact_block_snapshot(self) -> None:
        self.assertEqual(
            collection_run_id(self.research), "11b815ef_b12000000_b24000001"
        )


if __name__ == "__main__":
    unittest.main()
