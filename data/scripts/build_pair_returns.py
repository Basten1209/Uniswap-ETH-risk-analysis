"""Build realized-fee returns for non-same-block operation pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import load_config
from uniswap_v3_data.oracle import load_partitioned_oracle_prices
from uniswap_v3_data.pair_returns import (
    attribute_realized_fees,
    calculate_pair_returns,
)
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root


POOL_EVENT_COLUMNS = (
    "block_number",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "log_index",
    "event_type",
    "owner",
    "tick_lower",
    "tick_upper",
    "amount0_raw",
    "amount1_raw",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.partial")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_pool_collects(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        table = pq.read_table(path, columns=list(POOL_EVENT_COLUMNS))
        frame = table.to_pandas()
        frame = frame.loc[frame["event_type"] == "Collect"]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=POOL_EVENT_COLUMNS)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["block_number", "transaction_index", "log_index"], kind="stable"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument("--project", help="override config project for validation")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--oracle-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-root", type=Path)
    parser.add_argument("--max-price-age-seconds", type=int, default=3600)
    args = parser.parse_args()

    data_root = initialize_data_root(resolve_data_root(args.data_root))
    config = load_config(args.config, args.project, require_project=False)
    oracle_root = args.oracle_root or (
        data_root / "external" / "oracle" / "binance_ethusdt_1s"
    )
    output = args.output or (
        data_root
        / "derived"
        / "returns"
        / "non_same_block_pair_returns.parquet"
    )
    metadata_root = args.metadata_root or data_root / ".runs"

    pairs_path = (
        data_root / "derived" / "operation_pairs" / "non_same_block_pairs.parquet"
    )
    target_events_path = (
        data_root / "processed" / "position_events" / "target_nfpm_events.parquet"
    )
    clean_path = (
        data_root / "derived" / "positions" / "clean_closed_positions.parquet"
    )
    pool_paths = sorted((data_root / "processed" / "pool_events").glob("*.parquet"))
    required_paths = [pairs_path, target_events_path, clean_path]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing or not pool_paths:
        raise FileNotFoundError(
            "required operation-pair inputs are missing: "
            + ", ".join(missing or [str(data_root / "processed" / "pool_events")])
        )

    pairs = pd.read_parquet(pairs_path)
    if pairs["is_same_block"].any() or not pairs["has_positive_holding_time"].all():
        raise RuntimeError("pair-return input must contain only positive-time pairs")
    target_events = pd.read_parquet(target_events_path)
    pool_collects = read_pool_collects(pool_paths)
    clean_token_ids = set(
        pd.read_parquet(clean_path, columns=["token_id"])["token_id"].astype(str)
    )
    fee_pairs = attribute_realized_fees(
        pairs, pool_collects, target_events, clean_token_ids
    )
    required_timestamps = pd.concat(
        [fee_pairs["entry_block_timestamp"], fee_pairs["exit_block_timestamp"]],
        ignore_index=True,
    )
    prices, oracle_metadata = load_partitioned_oracle_prices(
        oracle_root, required_timestamps, args.max_price_age_seconds
    )
    result = calculate_pair_returns(
        fee_pairs,
        prices,
        config.token0.decimals,
        config.token1.decimals,
        args.max_price_age_seconds,
    )

    excluded = result.loc[~result["fee_analysis_included"]]
    included = result.loc[result["fee_analysis_included"]]
    if len(excluded) != 11:
        raise RuntimeError(
            f"expected 11 overlapping fee-attribution rows, observed {len(excluded)}"
        )
    if included[
        ["realized_fee0_raw", "realized_fee1_raw", "lp_total_return_realized_fee"]
    ].isna().any(axis=None):
        raise RuntimeError("included fee-return output contains null calculations")

    included = included.reset_index(drop=True)
    write_parquet(included, output)
    qc = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_pair_count": len(pairs),
        "fee_return_analysis_count": len(included),
        "excluded_overlap_count": len(excluded),
        "excluded_operation_ids": sorted(excluded["operation_id"].astype(str)),
        "exclusion_reasons": {
            str(reason): int(count)
            for reason, count in excluded["fee_exclusion_reason"].value_counts().items()
        },
        "fee_attribution_sources": {
            str(source): int(count)
            for source, count in included["fee_attribution_source"].value_counts().items()
        },
        "exit_collect_observed_count": int(included["exit_collect_observed"].sum()),
        "exit_collect_missing_count": int((~included["exit_collect_observed"]).sum()),
        "exit_collect_covers_principal_count": int(
            included["exit_collect_covers_principal"].sum()
        ),
        "fee_complete_exact_count": int(included["fee_complete_exact"].sum()),
        "valuation_convention": (
            "entry deposits and exit principal use strict-prior Binance ETHUSDT; "
            "observed fee Collect cash flows through the exit transaction are marked "
            "at exit; gas excluded"
        ),
        "fee_convention": (
            "interim Collects are realized fees; post-Burn exit-transaction Collect "
            "minus matched Burn principal is exit realized fee; no exit Collect means "
            "zero fee realized at exit; overlapping fee identities are excluded"
        ),
        "input_sha256": sha256(pairs_path),
        "output": {
            "path": output.relative_to(data_root).as_posix()
            if output.is_relative_to(data_root)
            else str(output),
            "row_count": len(included),
            "sha256": sha256(output),
        },
        **oracle_metadata,
    }
    qc_path = metadata_root / "processing" / "build_pair_returns_qc.json"
    write_json(qc_path, qc)
    print(
        f"saved {len(included):,} fee/return analysis rows from "
        f"{len(result):,} non-same-block pairs to {output}"
    )
    print(f"metadata: {qc_path}")


if __name__ == "__main__":
    main()
