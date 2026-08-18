"""Verify the fixed WETH/USDT 0.05% pool and freeze the latest data snapshot."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import bigquery

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import FixedPoolConfig, load_fixed_pool_config

POOL_CREATED_SIGNATURE = "PoolCreated(address,address,uint24,int24,address)"
EXPECTED_CREATION_BLOCK = 12_376_751
CREATION_DAY = "2021-05-05"
CREATION_DAY_END = "2021-05-06"


def build_snapshot_query(
    config: FixedPoolConfig, lookback_days: int, finality_blocks: int
) -> str:
    """Return the verified creation event and latest finalized decoded block."""
    return f"""WITH pool_created AS (
  SELECT
    block_number AS creation_block,
    block_timestamp AS creation_timestamp,
    LOWER(STRING(args[0])) AS factory_token0,
    LOWER(STRING(args[1])) AS factory_token1,
    CAST(STRING(args[2]) AS INT64) AS factory_fee_tier,
    CAST(STRING(args[3]) AS INT64) AS tick_spacing,
    LOWER(STRING(args[4])) AS factory_pool_address
  FROM `{config.events_table}`
  WHERE block_timestamp >= TIMESTAMP('{CREATION_DAY}')
    AND block_timestamp < TIMESTAMP('{CREATION_DAY_END}')
    AND block_number = {EXPECTED_CREATION_BLOCK}
    AND address = '{config.factory_address}'
    AND event_signature = '{POOL_CREATED_SIGNATURE}'
    AND LOWER(STRING(args[4])) = '{config.pool_address}'
), latest_decoded AS (
  SELECT MAX(block_number) AS latest_decoded_block
  FROM `{config.events_table}`
  WHERE block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
), cutoff AS (
  SELECT AS VALUE ARRAY_AGG(
    STRUCT(b.block_number, b.block_timestamp)
    ORDER BY b.block_number DESC
    LIMIT 1
  )[OFFSET(0)]
  FROM `{config.blocks_table}` AS b
  CROSS JOIN latest_decoded AS d
  WHERE b.block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
    AND b.block_number <= d.latest_decoded_block - {finality_blocks}
)
SELECT
  p.*,
  d.latest_decoded_block,
  c.block_number AS snapshot_end_block_inclusive,
  c.block_timestamp AS snapshot_end_timestamp
FROM pool_created AS p
CROSS JOIN latest_decoded AS d
CROSS JOIN cutoff AS c"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "fixed_pool.example.json",
    )
    parser.add_argument("--project", help="override billing/quota project")
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "config" / "selected_pool.json"
    )
    parser.add_argument("--metadata-root", type=Path, default=DATA_DIR / "metadata")
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--finality-blocks", type=int, default=64)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-bytes-billed", type=int)
    parser.add_argument("--replace-snapshot", action="store_true")
    args = parser.parse_args()

    if args.lookback_days < 2:
        raise ValueError("--lookback-days must be at least 2")
    if args.finality_blocks < 0:
        raise ValueError("--finality-blocks cannot be negative")
    config = load_fixed_pool_config(args.config, args.project)
    sql = build_snapshot_query(config, args.lookback_days, args.finality_blocks)
    metadata_root = args.metadata_root / "pool_snapshot"
    sql_path = metadata_root / "prepare_fixed_pool.sql"
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(sql + "\n", encoding="utf-8")

    client = bigquery.Client(project=config.project, location=config.location)
    dry_job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        location=config.location,
    )
    estimated = int(dry_job.total_bytes_processed or 0)
    plan = {
        "mode": "execute" if args.execute else "dry-run",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixed_pool": config.pool_address,
        "fixed_fee_tier": config.fee_tier,
        "lookback_days": args.lookback_days,
        "finality_blocks": args.finality_blocks,
        "estimated_bytes_processed": estimated,
        "estimated_gib_processed": estimated / 2**30,
        "sql_path": sql_path,
    }
    write_json(metadata_root / "plan.json", plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
    if not args.execute:
        return
    if args.maximum_bytes_billed is None or args.maximum_bytes_billed <= 0:
        raise ValueError("--execute requires positive --maximum-bytes-billed")
    if estimated > args.maximum_bytes_billed:
        raise RuntimeError(
            f"estimated scan {estimated} exceeds maximum {args.maximum_bytes_billed}"
        )
    if args.output.exists() and not args.replace_snapshot:
        raise FileExistsError(
            f"snapshot already exists: {args.output}; use --replace-snapshot explicitly"
        )

    maximum = min(
        max(estimated, math.ceil(estimated * 1.05)), args.maximum_bytes_billed
    )
    job_config = bigquery.QueryJobConfig(use_query_cache=True)
    if maximum > 0:
        job_config.maximum_bytes_billed = maximum
    job = client.query(sql, job_config=job_config, location=config.location)
    frame = job.result().to_arrow(create_bqstorage_client=False).to_pandas()
    if len(frame) != 1:
        raise RuntimeError(
            f"expected one canonical PoolCreated record, received {len(frame)}"
        )
    row = frame.iloc[0]
    observed_pair = {str(row["factory_token0"]), str(row["factory_token1"])}
    expected_pair = {config.token0.address, config.token1.address}
    if observed_pair != expected_pair:
        raise RuntimeError(f"factory token pair mismatch: {observed_pair}")
    if int(row["factory_fee_tier"]) != config.fee_tier:
        raise RuntimeError(f"factory fee tier mismatch: {row['factory_fee_tier']}")
    if str(row["factory_pool_address"]) != config.pool_address:
        raise RuntimeError("factory pool address mismatch")

    creation_timestamp = pd.to_datetime(row["creation_timestamp"], utc=True)
    snapshot_timestamp = pd.to_datetime(row["snapshot_end_timestamp"], utc=True)
    end_date = snapshot_timestamp.date() + timedelta(days=1)
    selected = {
        "project": config.project,
        "location": config.location,
        "network": config.network,
        "pool_address": config.pool_address,
        "nfpm_address": config.nfpm_address,
        "fee_tier": config.fee_tier,
        "token0": asdict(config.token0),
        "token1": asdict(config.token1),
        "start_date": creation_timestamp.date().isoformat(),
        "end_date": end_date.isoformat(),
        "start_block": int(row["creation_block"]),
        "end_block_exclusive": int(row["snapshot_end_block_inclusive"]) + 1,
        "bigquery": {
            "events_table": config.events_table,
            "logs_table": config.logs_table,
            "blocks_table": config.blocks_table,
        },
        "pool_snapshot": {
            "selection": "fixed WETH/USDT 0.05% pool",
            "factory_address": config.factory_address,
            "tick_spacing": int(row["tick_spacing"]),
            "creation_timestamp": creation_timestamp.isoformat(),
            "latest_decoded_block_observed": int(row["latest_decoded_block"]),
            "snapshot_end_timestamp": snapshot_timestamp.isoformat(),
            "finality_blocks": args.finality_blocks,
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "query_job_id": job.job_id,
        },
    }
    write_json(args.output, selected)
    write_json(
        metadata_root / "run.json",
        {
            **plan,
            "status": "complete",
            "job_id": job.job_id,
            "output_config": args.output,
            "start_block": selected["start_block"],
            "end_block_exclusive": selected["end_block_exclusive"],
            "total_bytes_processed": int(job.total_bytes_processed or 0),
            "total_bytes_billed": int(job.total_bytes_billed or 0),
        },
    )
    print(
        f"verified {config.pool_address}; snapshot blocks "
        f"[{selected['start_block']}, {selected['end_block_exclusive']}) -> "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
