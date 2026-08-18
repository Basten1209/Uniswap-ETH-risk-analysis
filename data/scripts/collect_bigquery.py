"""Dry-run or collect all on-chain inputs for the Uniswap v3 study."""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import bigquery

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import ResearchConfig, collection_run_id, load_config
from uniswap_v3_data.events import (
    NFPM_COLLECT,
    NFPM_DECREASE,
    NFPM_INCREASE,
    NFPM_TRANSFER,
    POOL_MINT,
    POOL_SIGNATURES,
)

BLOCK_OPTIONAL_COLUMNS = (
    "base_fee_per_gas",
    "gas_limit",
    "gas_used",
)


def _sql_strings(values: tuple[str, ...]) -> str:
    return ",\n      ".join("'" + value.replace("'", "''") + "'" for value in values)


def build_position_seed_query(config: ResearchConfig, start: date, end: date) -> str:
    """Find NFPM token IDs created or increased through the selected pool."""
    return f"""WITH pool_mints AS (
  SELECT
    block_number,
    block_timestamp,
    transaction_hash,
    transaction_index,
    log_index,
    CAST(STRING(args[2]) AS INT64) AS tick_lower,
    CAST(STRING(args[3]) AS INT64) AS tick_upper,
    STRING(args[4]) AS liquidity_raw,
    STRING(args[5]) AS amount0_raw,
    STRING(args[6]) AS amount1_raw
  FROM `{config.events_table}`
  WHERE block_timestamp >= TIMESTAMP('{start.isoformat()}')
    AND block_timestamp < TIMESTAMP('{end.isoformat()}')
    AND block_number >= {config.start_block}
    AND block_number < {config.end_block_exclusive}
    AND address = '{config.pool_address}'
    AND event_signature = '{POOL_MINT}'
    AND LOWER(STRING(args[1])) = '{config.nfpm_address}'
), nfpm_increases AS (
  SELECT
    block_number,
    block_timestamp,
    transaction_hash,
    transaction_index,
    log_index,
    STRING(args[0]) AS token_id,
    STRING(args[1]) AS liquidity_raw,
    STRING(args[2]) AS amount0_raw,
    STRING(args[3]) AS amount1_raw
  FROM `{config.events_table}`
  WHERE block_timestamp >= TIMESTAMP('{start.isoformat()}')
    AND block_timestamp < TIMESTAMP('{end.isoformat()}')
    AND block_number >= {config.start_block}
    AND block_number < {config.end_block_exclusive}
    AND address = '{config.nfpm_address}'
    AND event_signature = '{NFPM_INCREASE}'
)
SELECT
  n.token_id,
  n.block_number,
  n.block_timestamp,
  n.transaction_hash,
  n.transaction_index,
  p.log_index AS pool_mint_log_index,
  n.log_index AS nfpm_increase_log_index,
  p.tick_lower,
  p.tick_upper,
  n.liquidity_raw,
  n.amount0_raw,
  n.amount1_raw
FROM nfpm_increases AS n
JOIN pool_mints AS p
  ON n.transaction_hash = p.transaction_hash
  AND p.log_index < n.log_index
  AND p.liquidity_raw = n.liquidity_raw
  AND p.amount0_raw = n.amount0_raw
  AND p.amount1_raw = n.amount1_raw
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY n.transaction_hash, n.log_index
  ORDER BY p.log_index DESC
) = 1
ORDER BY block_number, transaction_index, nfpm_increase_log_index"""


def build_events_query(config: ResearchConfig, start: date, end: date) -> str:
    pool_signatures = _sql_strings(POOL_SIGNATURES)
    nfpm_position_signatures = _sql_strings(
        (NFPM_INCREASE, NFPM_DECREASE, NFPM_COLLECT)
    )
    return f"""SELECT
  block_number,
  block_timestamp,
  transaction_hash,
  transaction_index,
  log_index,
  address,
  event_signature,
  TO_JSON_STRING(args) AS args_json
FROM `{config.events_table}`
WHERE block_timestamp >= TIMESTAMP('{start.isoformat()}')
  AND block_timestamp < TIMESTAMP('{end.isoformat()}')
  AND block_number >= {config.start_block}
  AND block_number < {config.end_block_exclusive}
  AND (
    (
      address = '{config.pool_address}'
      AND event_signature IN (
      {pool_signatures}
      )
    )
    OR
    (
      address = '{config.nfpm_address}'
      AND (
        (
          event_signature IN (
          {nfpm_position_signatures}
          )
          AND STRING(args[0]) IN UNNEST(@target_token_ids)
        )
        OR
        (
          event_signature = '{NFPM_TRANSFER}'
          AND STRING(args[2]) IN UNNEST(@target_token_ids)
        )
      )
    )
  )
ORDER BY block_number, transaction_index, log_index"""


def block_columns(client: bigquery.Client, config: ResearchConfig) -> list[str]:
    table = client.get_table(config.blocks_table)
    available = {field.name for field in table.schema}
    required = {"block_number", "block_timestamp"}
    missing = required.difference(available)
    if missing:
        raise RuntimeError(
            f"{config.blocks_table} is missing required fields: {sorted(missing)}"
        )
    return ["block_number", "block_timestamp"] + [
        field for field in BLOCK_OPTIONAL_COLUMNS if field in available
    ]


def build_blocks_query(
    config: ResearchConfig, start: date, end: date, columns: list[str]
) -> str:
    aggregates = [
        "COUNT(*) AS block_count",
        "MIN(block_number) AS first_block",
        "MAX(block_number) AS last_block",
    ]
    if "base_fee_per_gas" in columns:
        aggregates.extend(
            [
                (
                    "CAST(AVG(CAST(base_fee_per_gas AS BIGNUMERIC)) AS STRING) "
                    "AS mean_base_fee_per_gas_wei"
                ),
                (
                    "CAST(APPROX_QUANTILES("
                    "CAST(base_fee_per_gas AS BIGNUMERIC), 2)"
                    "[OFFSET(1)] AS STRING) AS median_base_fee_per_gas_wei"
                ),
            ]
        )
    if "gas_used" in columns:
        aggregates.append(
            "CAST(AVG(CAST(gas_used AS BIGNUMERIC)) AS STRING) AS mean_gas_used"
        )
    if "gas_limit" in columns:
        aggregates.append(
            "CAST(AVG(CAST(gas_limit AS BIGNUMERIC)) AS STRING) AS mean_gas_limit"
        )
    if "gas_used" in columns and "gas_limit" in columns:
        aggregates.append(
            "CAST(AVG(SAFE_DIVIDE(CAST(gas_used AS BIGNUMERIC), "
            "CAST(gas_limit AS BIGNUMERIC))) AS STRING) "
            "AS mean_block_gas_utilization"
        )
    selected = ",\n  ".join(aggregates)
    return f"""SELECT
  DATE(block_timestamp) AS date,
  {selected}
FROM `{config.blocks_table}`
WHERE block_timestamp >= TIMESTAMP('{start.isoformat()}')
  AND block_timestamp < TIMESTAMP('{end.isoformat()}')
  AND block_number >= {config.start_block}
  AND block_number < {config.end_block_exclusive}
GROUP BY date
ORDER BY date"""


def monthly_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        next_month = month_end.fromordinal(month_end.toordinal() + 1)
        boundary = min(next_month, end)
        ranges.append((cursor, boundary))
        cursor = boundary
    return ranges


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def query_parameters(kind: str, target_token_ids: list[str]) -> list[Any]:
    if kind != "events":
        return []
    return [
        bigquery.ArrayQueryParameter(
            "target_token_ids", "STRING", target_token_ids or ["0"]
        )
    ]


def execute_plan(
    client: bigquery.Client,
    config: ResearchConfig,
    metadata_root: Path,
    plan: dict[str, Any],
    target_token_ids: list[str],
) -> None:
    maximum = max(
        int(plan["estimated_bytes"]),
        math.ceil(int(plan["estimated_bytes"]) * 1.10),
    )
    job_config = bigquery.QueryJobConfig(
        use_query_cache=True,
        query_parameters=query_parameters(plan["kind"], target_token_ids),
    )
    if maximum > 0:
        job_config.maximum_bytes_billed = maximum
    job = client.query(
        plan["sql"],
        job_config=job_config,
        location=config.location,
    )
    result = job.result()
    frame = result.to_arrow(create_bqstorage_client=False).to_pandas()
    target: Path = plan["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.partial")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(target)
    run_payload = {
        "status": "complete",
        "kind": plan["kind"],
        "start_date": plan["start"],
        "end_date": plan["end"],
        "project": config.project,
        "location": config.location,
        "source_table": (
            config.blocks_table
            if plan["kind"] == "block_daily"
            else config.events_table
        ),
        "job_id": job.job_id,
        "row_count": len(frame),
        "target_token_id_count": (
            len(target_token_ids) if plan["kind"] == "events" else None
        ),
        "estimated_bytes": plan["estimated_bytes"],
        "total_bytes_processed": int(job.total_bytes_processed or 0),
        "total_bytes_billed": int(job.total_bytes_billed or 0),
        "maximum_bytes_billed": maximum or None,
        "cache_hit": bool(job.cache_hit),
        "sql_path": plan["sql_path"],
        "output_path": target,
        "output_size_bytes": target.stat().st_size,
        "output_sha256": sha256(target),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    run_path = (
        metadata_root
        / "query_runs"
        / f"{plan['kind']}_{plan['start']}_{plan['end']}.json"
    )
    write_json(run_path, run_payload)
    print(
        f"saved {len(frame):,} rows to {target} "
        f"({target.stat().st_size / 2**20:.2f} MiB)",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument(
        "--project", help="override the billing/quota project in config"
    )
    parser.add_argument(
        "--data-root", "--out-root", dest="out_root", type=Path, default=DATA_DIR
    )
    parser.add_argument("--metadata-root", type=Path, default=DATA_DIR / "metadata")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--budget-bytes",
        type=int,
        help="required for --execute; total maximum dry-run bytes across missing jobs",
    )
    args = parser.parse_args()

    config = load_config(args.config, args.project)
    client = bigquery.Client(project=config.project, location=config.location)
    columns = block_columns(client, config)
    run_id = collection_run_id(config)
    raw_root = args.out_root / "raw" / "bigquery" / run_id
    metadata_root = args.metadata_root / "bigquery" / run_id
    plans: list[dict[str, Any]] = []

    for start, end in monthly_ranges(config.start_date, config.end_date):
        interval = f"{start.isoformat()}_{end.isoformat()}"
        queries = {
            "position_seeds": build_position_seed_query(config, start, end),
            "events": build_events_query(config, start, end),
            "block_daily": build_blocks_query(config, start, end, columns),
        }
        for kind, sql in queries.items():
            target = raw_root / kind / f"{kind}_{interval}.parquet"
            if target.exists():
                print(f"skip existing immutable raw file: {target}", flush=True)
                continue
            sql_path = metadata_root / "sql" / f"{kind}_{interval}.sql"
            sql_path.parent.mkdir(parents=True, exist_ok=True)
            sql_path.write_text(sql + "\n", encoding="utf-8")
            dry_job = client.query(
                sql,
                job_config=bigquery.QueryJobConfig(
                    dry_run=True,
                    use_query_cache=False,
                    query_parameters=query_parameters(kind, ["0"]),
                ),
                location=config.location,
            )
            estimated = int(dry_job.total_bytes_processed or 0)
            plans.append(
                {
                    "kind": kind,
                    "start": start,
                    "end": end,
                    "sql": sql,
                    "sql_path": sql_path,
                    "target": target,
                    "estimated_bytes": estimated,
                }
            )
            print(
                f"{kind:14s} {start}..{end}: {estimated / 2**30:.3f} GiB dry-run",
                flush=True,
            )

    total = sum(plan["estimated_bytes"] for plan in plans)
    plan_payload = {
        "mode": "execute" if args.execute else "dry-run",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(args.config.resolve()),
        "config": asdict(config),
        "block_columns": columns,
        "planned_job_count": len(plans),
        "estimated_bytes_processed": total,
        "estimated_gib_processed": total / 2**30,
        "budget_bytes": args.budget_bytes,
        "jobs": [
            {key: value for key, value in plan.items() if key not in {"sql"}}
            for plan in plans
        ],
    }
    plan_path = (
        metadata_root
        / "query_plans"
        / (
            f"plan_{config.start_date}_{config.end_date}_"
            f"{'execute' if args.execute else 'dry-run'}.json"
        )
    )
    write_json(plan_path, plan_payload)
    print(
        f"planned total: {total} bytes ({total / 2**30:.3f} GiB); manifest={plan_path}",
        flush=True,
    )

    if args.budget_bytes is not None and total > args.budget_bytes:
        raise RuntimeError(
            f"planned scan {total} exceeds --budget-bytes {args.budget_bytes}"
        )
    if not args.execute:
        return
    if args.budget_bytes is None or args.budget_bytes <= 0:
        raise ValueError("--execute requires a positive --budget-bytes")

    seed_plans = [plan for plan in plans if plan["kind"] == "position_seeds"]
    for plan in seed_plans:
        execute_plan(client, config, metadata_root, plan, [])

    seed_paths = sorted((raw_root / "position_seeds").glob("*.parquet"))
    if not seed_paths:
        raise RuntimeError("position seed collection produced no parquet files")
    seed_frames = [pd.read_parquet(path, columns=["token_id"]) for path in seed_paths]
    target_token_ids = sorted(
        {
            str(value)
            for frame in seed_frames
            for value in frame["token_id"].dropna().tolist()
        },
        key=int,
    )
    if not target_token_ids:
        raise RuntimeError(
            "no NFPM token IDs matched the fixed pool; verify decoded-event coverage"
        )
    parameter_size = sum(len(value) + 3 for value in target_token_ids)
    if parameter_size > 8_000_000:
        raise RuntimeError(
            "target token-ID parameter is too large for direct collection; "
            "materialize position_seeds in BigQuery and join server-side"
        )
    print(
        f"identified {len(target_token_ids):,} fixed-pool NFPM token IDs",
        flush=True,
    )

    for plan in plans:
        if plan["kind"] == "position_seeds":
            continue
        execute_plan(client, config, metadata_root, plan, target_token_ids)


if __name__ == "__main__":
    main()
