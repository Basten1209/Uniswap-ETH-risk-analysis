"""Collect transaction senders for target-pool Mint and Burn operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import collection_run_id, load_config
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root

TRANSACTION_COLUMNS = (
    "block_number",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "from_address",
    "to_address",
)
MINIMUM_QUERY_BYTES = 10 * 2**20


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.partial")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def build_transactions_query(
    transactions_table: str,
    start: date,
    end: date,
    start_block: int,
    end_block_exclusive: int,
) -> str:
    return f"""SELECT
  block_number,
  block_timestamp,
  transaction_hash,
  transaction_index,
  from_address,
  to_address
FROM `{transactions_table}`
WHERE block_timestamp >= TIMESTAMP('{start.isoformat()}')
  AND block_timestamp < TIMESTAMP('{end.isoformat()}')
  AND block_number >= {start_block}
  AND block_number < {end_block_exclusive}
  AND transaction_hash IN UNNEST(@transaction_hashes)
ORDER BY block_number, transaction_index"""


def interval_from_path(path: Path) -> tuple[date, date]:
    value = path.stem.removeprefix("pool_events_")
    start_text, end_text = value.split("_", 1)
    return date.fromisoformat(start_text), date.fromisoformat(end_text)


def load_transaction_keys(path: Path) -> pd.DataFrame:
    columns = [
        "event_type",
        "block_number",
        "block_timestamp",
        "transaction_hash",
        "transaction_index",
    ]
    frame = pd.read_parquet(path, columns=columns)
    frame = frame.loc[frame["event_type"].isin(("Mint", "Burn"))].drop(
        columns="event_type"
    )
    frame["transaction_hash"] = frame["transaction_hash"].astype(str).str.lower()
    conflicts = (
        frame.groupby("transaction_hash", sort=False)[
            ["block_number", "block_timestamp", "transaction_index"]
        ]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
    )
    if conflicts.any():
        raise RuntimeError(
            f"{path} has transaction hashes with inconsistent block metadata"
        )
    return (
        frame.drop_duplicates("transaction_hash")
        .sort_values(["block_number", "transaction_index"], kind="stable")
        .reset_index(drop=True)
    )


def keys_digest(keys: pd.DataFrame) -> str:
    payload = "\n".join(keys["transaction_hash"].astype(str).sort_values()) + "\n"
    return sha256_bytes(payload.encode("ascii"))


def query_parameters(keys: pd.DataFrame) -> list[bigquery.ArrayQueryParameter]:
    return [
        bigquery.ArrayQueryParameter(
            "transaction_hashes", "STRING", keys["transaction_hash"].tolist()
        )
    ]


def validate_result(result: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    missing_columns = set(TRANSACTION_COLUMNS).difference(result.columns)
    if missing_columns:
        raise RuntimeError(
            f"transaction result is missing columns: {sorted(missing_columns)}"
        )
    result = result.loc[:, TRANSACTION_COLUMNS].copy()
    result["transaction_hash"] = result["transaction_hash"].astype(str).str.lower()
    result["from_address"] = result["from_address"].astype(str).str.lower()
    result["to_address"] = result["to_address"].where(
        result["to_address"].notna(), None
    )
    result.loc[result["to_address"].notna(), "to_address"] = (
        result.loc[result["to_address"].notna(), "to_address"].astype(str).str.lower()
    )
    if result["transaction_hash"].duplicated().any():
        raise RuntimeError("transaction result contains duplicate transaction hashes")
    expected = set(keys["transaction_hash"])
    observed = set(result["transaction_hash"])
    if expected != observed:
        raise RuntimeError(
            "transaction result key mismatch: "
            f"missing={len(expected - observed)}, unexpected={len(observed - expected)}"
        )
    joined = result.merge(
        keys,
        on="transaction_hash",
        how="inner",
        suffixes=("", "_expected"),
        validate="one_to_one",
    )
    for column in ("block_number", "block_timestamp", "transaction_index"):
        left = joined[column]
        right = joined[f"{column}_expected"]
        if column == "block_timestamp":
            left = pd.to_datetime(left, utc=True)
            right = pd.to_datetime(right, utc=True)
        if not left.equals(right):
            raise RuntimeError(f"transaction result has a {column} mismatch")
    if result["from_address"].isna().any() or (result["from_address"] == "none").any():
        raise RuntimeError("transaction result contains a missing from_address")
    return result.sort_values(
        ["block_number", "transaction_index"], kind="stable"
    ).reset_index(drop=True)


def job_id_for(start: date, digest: str) -> str:
    return f"wethusdt_transactions_{start.strftime('%Y_%m')}_{digest[:16]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--metadata-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--budget-bytes", type=int, required=True)
    parser.add_argument("--max-jobs", type=int)
    args = parser.parse_args()
    if args.budget_bytes <= 0:
        raise ValueError("--budget-bytes must be positive")
    if args.max_jobs is not None and args.max_jobs <= 0:
        raise ValueError("--max-jobs must be positive")

    data_root = initialize_data_root(resolve_data_root(args.data_root))
    metadata_base = args.metadata_root or data_root / ".runs"
    config = load_config(args.config, args.project)
    client = bigquery.Client(project=config.project, location=config.location)
    run_id = collection_run_id(config)
    processed_paths = sorted(
        (data_root / "processed" / "pool_events").glob("pool_events_*.parquet")
    )
    if not processed_paths:
        raise FileNotFoundError(
            "no processed pool events; run data/scripts/dataset.py build first"
        )
    output_root = data_root / "raw" / "bigquery" / run_id / "transactions"
    metadata_root = metadata_base / "bigquery" / run_id / "transactions"
    plans: list[dict[str, Any]] = []
    total_requested = 0
    completed_job_count = 0
    completed_bytes_processed = 0
    completed_bytes_billed = 0

    for path in processed_paths:
        start, end = interval_from_path(path)
        keys = load_transaction_keys(path)
        total_requested += len(keys)
        target = output_root / f"transactions_{start}_{end}.parquet"
        digest = keys_digest(keys)
        if target.exists():
            frame = validate_result(pd.read_parquet(target), keys)
            run_path = (
                metadata_root
                / "query_runs"
                / f"transactions_{start}_{end}.json"
            )
            if not run_path.exists():
                raise RuntimeError(f"existing raw file has no query metadata: {target}")
            run = json.loads(run_path.read_text(encoding="utf-8"))
            if (
                run.get("status") != "complete"
                or run.get("keys_sha256") != digest
                or int(run.get("row_count", -1)) != len(frame)
                or run.get("output_sha256") != sha256(target)
            ):
                raise RuntimeError(
                    f"existing raw file does not match query metadata: {target}"
                )
            completed_job_count += 1
            completed_bytes_processed += int(run["total_bytes_processed"])
            completed_bytes_billed += int(run["total_bytes_billed"])
            print(f"skip verified immutable raw file: {target}", flush=True)
            continue
        sql = build_transactions_query(
            config.transactions_table,
            start,
            end,
            config.start_block,
            config.end_block_exclusive,
        )
        parameters = query_parameters(keys)
        dry_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            query_parameters=parameters,
        )
        dry_job = client.query(sql, job_config=dry_config, location=config.location)
        estimated = int(dry_job.total_bytes_processed or 0)
        maximum = max(
            estimated,
            math.ceil(estimated * 1.10),
            MINIMUM_QUERY_BYTES,
        )
        plans.append(
            {
                "start": start,
                "end": end,
                "keys": keys,
                "keys_sha256": digest,
                "sql": sql,
                "sql_sha256": sha256_bytes((sql + "\n").encode()),
                "parameters": parameters,
                "estimated_bytes": estimated,
                "maximum_bytes_billed": maximum,
                "job_id": job_id_for(start, digest),
                "target": target,
            }
        )
        print(
            f"transactions {start}..{end}: keys={len(keys):,}, "
            f"dry-run={estimated / 2**30:.3f} GiB",
            flush=True,
        )

    if args.max_jobs is not None:
        plans = plans[: args.max_jobs]
    remaining_estimated = sum(int(plan["estimated_bytes"]) for plan in plans)
    remaining_maximum = sum(
        int(plan["maximum_bytes_billed"]) for plan in plans
    )
    projected_processed = completed_bytes_processed + remaining_estimated
    projected_maximum_billed = completed_bytes_billed + remaining_maximum
    plan_payload = {
        "mode": "execute" if args.execute else "dry-run",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": config.project,
        "location": config.location,
        "source_table": config.transactions_table,
        "requested_transaction_count_all_months": total_requested,
        "completed_job_count": completed_job_count,
        "completed_bytes_processed": completed_bytes_processed,
        "completed_bytes_billed": completed_bytes_billed,
        "planned_job_count": len(plans),
        "remaining_estimated_bytes_processed": remaining_estimated,
        "remaining_maximum_bytes_billed": remaining_maximum,
        "projected_bytes_processed": projected_processed,
        "projected_maximum_bytes_billed": projected_maximum_billed,
        "projected_gib_processed": projected_processed / 2**30,
        "projected_maximum_gib_billed": projected_maximum_billed / 2**30,
        "budget_bytes": args.budget_bytes,
        "jobs": [
            {
                key: plan[key]
                for key in (
                    "start",
                    "end",
                    "keys_sha256",
                    "sql_sha256",
                    "estimated_bytes",
                    "maximum_bytes_billed",
                    "job_id",
                )
            }
            | {
                "key_count": len(plan["keys"]),
                "target": plan["target"].relative_to(data_root).as_posix(),
            }
            for plan in plans
        ],
    }
    plan_path = metadata_root / (
        f"plan_{config.start_date}_{config.end_date}_"
        f"{'execute' if args.execute else 'dry-run'}.json"
    )
    write_json(plan_path, plan_payload)
    print(
        f"projected total={projected_processed / 2**30:.3f} GiB, "
        f"maximum={projected_maximum_billed / 2**30:.3f} GiB; "
        f"manifest={plan_path}",
        flush=True,
    )
    if projected_maximum_billed > args.budget_bytes:
        raise RuntimeError(
            f"projected maximum billed bytes {projected_maximum_billed} "
            f"exceeds --budget-bytes {args.budget_bytes}"
        )
    if not args.execute:
        return

    for plan in plans:
        job_config = bigquery.QueryJobConfig(
            use_query_cache=True,
            maximum_bytes_billed=plan["maximum_bytes_billed"],
            query_parameters=plan["parameters"],
        )
        try:
            job = client.get_job(plan["job_id"], location=config.location)
            print(f"recover existing BigQuery job: {plan['job_id']}", flush=True)
        except NotFound:
            job = client.query(
                plan["sql"],
                job_config=job_config,
                job_id=plan["job_id"],
                job_retry=None,
                location=config.location,
            )
        result = job.result()
        frame = result.to_arrow(create_bqstorage_client=False).to_pandas()
        frame = validate_result(frame, plan["keys"])
        write_parquet(frame, plan["target"])
        run_payload = {
            "status": "complete",
            "start_date": plan["start"],
            "end_date": plan["end"],
            "project": config.project,
            "location": config.location,
            "source_table": config.transactions_table,
            "job_id": job.job_id,
            "key_count": len(plan["keys"]),
            "keys_sha256": plan["keys_sha256"],
            "sql_sha256": plan["sql_sha256"],
            "row_count": len(frame),
            "estimated_bytes": plan["estimated_bytes"],
            "total_bytes_processed": int(job.total_bytes_processed or 0),
            "total_bytes_billed": int(job.total_bytes_billed or 0),
            "maximum_bytes_billed": plan["maximum_bytes_billed"],
            "cache_hit": bool(job.cache_hit),
            "output_path": plan["target"].relative_to(data_root).as_posix(),
            "output_size_bytes": plan["target"].stat().st_size,
            "output_sha256": sha256(plan["target"]),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(
            metadata_root
            / "query_runs"
            / f"transactions_{plan['start']}_{plan['end']}.json",
            run_payload,
        )
        print(
            f"saved {len(frame):,} rows to {plan['target']} "
            f"({plan['target'].stat().st_size / 2**20:.2f} MiB)",
            flush=True,
        )


if __name__ == "__main__":
    main()
