"""Register completed transaction-sender Parquets in the dataset manifest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import collection_run_id, load_config
from uniswap_v3_data.manifest import load_manifest, sha256, write_manifest
from uniswap_v3_data.paths import resolve_data_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=DATA_DIR / "manifest.json"
    )
    args = parser.parse_args()

    data_root = resolve_data_root(args.data_root)
    config = load_config(args.config, args.project)
    run_id = collection_run_id(config)
    transaction_root = data_root / "raw" / "bigquery" / run_id / "transactions"
    run_root = (
        data_root
        / ".runs"
        / "bigquery"
        / run_id
        / "transactions"
        / "query_runs"
    )
    transaction_paths = sorted(transaction_root.glob("transactions_*.parquet"))
    run_paths = sorted(run_root.glob("transactions_*.json"))
    expected_count = len(
        list((data_root / "processed" / "pool_events").glob("pool_events_*.parquet"))
    )
    if expected_count == 0 or len(transaction_paths) != expected_count:
        raise RuntimeError(
            f"expected {expected_count} transaction files, found {len(transaction_paths)}"
        )
    if len(run_paths) != expected_count:
        raise RuntimeError(
            f"expected {expected_count} transaction query runs, found {len(run_paths)}"
        )
    runs = {}
    for path in run_paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        output_path = str(run["output_path"])
        if output_path in runs:
            raise RuntimeError(f"duplicate query metadata for {output_path}")
        runs[output_path] = run
    artifacts = []
    for path in transaction_paths:
        relative = path.relative_to(data_root).as_posix()
        if relative not in runs:
            raise RuntimeError(f"no query run metadata for {relative}")
        run = runs[relative]
        rows = pq.ParquetFile(path).metadata.num_rows
        if rows != int(run["row_count"]):
            raise RuntimeError(f"row count mismatch for {path}")
        digest = sha256(path)
        if digest != run["output_sha256"]:
            raise RuntimeError(f"checksum mismatch for {path}")
        artifacts.append(
            {
                "kind": "transactions",
                "start_date": run["start_date"],
                "end_date": run["end_date"],
                "path": relative,
                "row_count": rows,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "source_shard": run_id,
                "source_table": run["source_table"],
                "query": {
                    "project": run["project"],
                    "location": run["location"],
                    "job_id": run["job_id"],
                    "estimated_bytes": run["estimated_bytes"],
                    "total_bytes_processed": run["total_bytes_processed"],
                    "total_bytes_billed": run["total_bytes_billed"],
                    "maximum_bytes_billed": run["maximum_bytes_billed"],
                    "cache_hit": run["cache_hit"],
                    "sql_sha256": run["sql_sha256"],
                    "keys_sha256": run["keys_sha256"],
                    "completed_at_utc": run["completed_at_utc"],
                },
            }
        )

    manifest = load_manifest(args.manifest)
    base_artifacts = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact.get("kind") != "transactions"
    ]
    manifest["artifacts"] = base_artifacts + artifacts
    manifest["description"] = (
        "Immutable WETH/USDT 0.05% pool logs, daily block aggregates, and "
        "Mint/Burn transaction identities."
    )
    manifest["snapshot"]["bigquery"]["transactions_table"] = (
        config.transactions_table
    )
    billing_projects: dict[str, int] = manifest["source"].setdefault(
        "billing_projects", {}
    )
    for project in {artifact["query"]["project"] for artifact in artifacts}:
        billing_projects[project] = sum(
            artifact["query"]["project"] == project for artifact in artifacts
        )
    manifest["source"]["transaction_query_entrypoint"] = (
        "scripts/collect_transaction_senders.py"
    )
    manifest["transaction_collection"] = {
        "registered_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_table": config.transactions_table,
        "file_count": len(artifacts),
        "row_count": sum(int(item["row_count"]) for item in artifacts),
        "unique_key_count": sum(
            int(runs[item["path"]]["key_count"]) for item in artifacts
        ),
        "total_bytes_processed": sum(
            int(item["query"]["total_bytes_processed"]) for item in artifacts
        ),
        "total_bytes_billed": sum(
            int(item["query"]["total_bytes_billed"]) for item in artifacts
        ),
    }
    totals = manifest["totals"]
    totals["files"] = len(manifest["artifacts"])
    totals["rows"] = sum(int(item["row_count"]) for item in manifest["artifacts"])
    totals["size_bytes"] = sum(
        int(item["size_bytes"]) for item in manifest["artifacts"]
    )
    totals["transaction_rows"] = sum(int(item["row_count"]) for item in artifacts)
    totals["total_bytes_processed"] = sum(
        int(item["query"]["total_bytes_processed"])
        for item in manifest["artifacts"]
    )
    totals["total_bytes_billed"] = sum(
        int(item["query"]["total_bytes_billed"])
        for item in manifest["artifacts"]
    )
    write_manifest(args.manifest, manifest)
    print(
        f"registered {len(artifacts)} transaction files and "
        f"{totals['transaction_rows']:,} rows in {args.manifest}"
    )


if __name__ == "__main__":
    main()
