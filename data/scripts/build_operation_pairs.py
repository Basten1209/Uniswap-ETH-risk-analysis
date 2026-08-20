"""Build transaction-identified Pool Mint/Burn operation pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import collection_run_id, load_config
from uniswap_v3_data.operation_pairs import (
    PAIR_KEY,
    build_operation_pairs,
    link_pool_burns_to_nfpm_decreases,
    prepare_liquidity_operations,
)
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root

POOL_COLUMNS = (
    "block_number",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "log_index",
    "address",
    "event_type",
    "sender",
    "owner",
    "tick_lower",
    "tick_upper",
    "liquidity_delta_raw",
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


def read_pool_liquidity_events(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        frame = pd.read_parquet(path, columns=list(POOL_COLUMNS))
        frame = frame.loc[frame["event_type"].isin(("Mint", "Burn"))]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=POOL_COLUMNS)
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(
            ["block_number", "transaction_index", "log_index"], kind="stable"
        )
        .reset_index(drop=True)
    )


def read_transactions(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return pd.DataFrame()
    result = pd.concat(
        [pd.read_parquet(path) for path in paths], ignore_index=True
    ).sort_values(["block_number", "transaction_index"], kind="stable")
    if result["transaction_hash"].duplicated().any():
        raise RuntimeError("raw transaction files contain duplicate hashes")
    return result.reset_index(drop=True)


def count_depth_mismatch_candidates(unmatched: pd.DataFrame) -> int:
    """Count unmatched rows having an opposite operation at another depth."""

    if unmatched.empty:
        return 0
    base_key = list(PAIR_KEY[:-1])
    groups = {
        key: group
        for key, group in unmatched.groupby(base_key, sort=False, dropna=False)
    }
    count = 0
    for group in groups.values():
        mint_depths = set(
            group.loc[group["operation_type"] == "Mint", "liquidity_raw"]
        )
        burn_depths = set(
            group.loc[group["operation_type"] == "Burn", "liquidity_raw"]
        )
        if not mint_depths or not burn_depths:
            continue
        count += int(
            group.apply(
                lambda row: bool(
                    (row["operation_type"] == "Mint" and burn_depths - {row["liquidity_raw"]})
                    or (
                        row["operation_type"] == "Burn"
                        and mint_depths - {row["liquidity_raw"]}
                    )
                ),
                axis=1,
            ).sum()
        )
    return count


def strict_exclusion_waterfall(pairs: pd.DataFrame) -> dict[str, int]:
    """Assign every exact pair to the first strict exclusion it triggers."""

    if pairs.empty:
        return {
            "multiple_open_exact_mints": 0,
            "intervening_same_range_liquidity": 0,
            "same_transaction": 0,
            "non_positive_holding_time": 0,
            "strict": 0,
        }
    remaining = pd.Series(True, index=pairs.index)
    waterfall: dict[str, int] = {}
    rules = (
        ("multiple_open_exact_mints", pairs["is_ambiguous"]),
        (
            "intervening_same_range_liquidity",
            pairs["has_intervening_same_range_liquidity_event"],
        ),
        ("same_transaction", pairs["is_same_transaction"]),
        ("non_positive_holding_time", ~pairs["has_positive_holding_time"]),
    )
    for reason, mask in rules:
        excluded = remaining & mask
        waterfall[reason] = int(excluded.sum())
        remaining &= ~mask
    waterfall["strict"] = int(remaining.sum())
    return waterfall


def validate_pairs(operations: pd.DataFrame, pairs: pd.DataFrame) -> None:
    if operations["event_id"].duplicated().any():
        raise RuntimeError("duplicate liquidity event IDs")
    if pairs.empty:
        return
    if pairs["operation_id"].duplicated().any():
        raise RuntimeError("duplicate operation pair IDs")
    if pairs["entry_event_id"].duplicated().any():
        raise RuntimeError("a Mint event is reused by multiple pairs")
    if pairs["exit_event_id"].duplicated().any():
        raise RuntimeError("a Burn event is reused by multiple pairs")
    if set(pairs["entry_event_id"]) & set(pairs["exit_event_id"]):
        raise RuntimeError("one event is used as both Mint and Burn")
    for column in ("lp_wallet", "manager_address", "tick_lower", "tick_upper", "liquidity_raw"):
        entry_column = (
            column
            if column in ("lp_wallet", "manager_address", "tick_lower", "tick_upper", "liquidity_raw")
            else f"entry_{column}"
        )
        if pairs[entry_column].isna().any():
            raise RuntimeError(f"pair output has missing {column}")
    entry_order = list(
        zip(
            pairs["entry_block_number"],
            pairs["entry_transaction_index"],
            pairs["entry_log_index"],
        )
    )
    exit_order = list(
        zip(
            pairs["exit_block_number"],
            pairs["exit_transaction_index"],
            pairs["exit_log_index"],
        )
    )
    if any(entry >= exit for entry, exit in zip(entry_order, exit_order)):
        raise RuntimeError("pair output has invalid entry/exit event order")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument("--project")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--metadata-root", type=Path)
    args = parser.parse_args()

    data_root = initialize_data_root(resolve_data_root(args.data_root))
    metadata_root = args.metadata_root or data_root / ".runs"
    config = load_config(args.config, args.project, require_project=False)
    run_id = collection_run_id(config)
    pool_paths = sorted(
        (data_root / "processed" / "pool_events").glob("pool_events_*.parquet")
    )
    transaction_paths = sorted(
        (
            data_root / "raw" / "bigquery" / run_id / "transactions"
        ).glob("transactions_*.parquet")
    )
    if not pool_paths:
        raise FileNotFoundError("processed pool event files are missing")
    if not transaction_paths:
        raise FileNotFoundError("raw transaction sender files are missing")

    pool = read_pool_liquidity_events(pool_paths)
    transactions = read_transactions(transaction_paths)
    expected_hashes = set(pool["transaction_hash"].astype(str).str.lower())
    observed_hashes = set(transactions["transaction_hash"].astype(str).str.lower())
    if expected_hashes != observed_hashes:
        raise RuntimeError(
            "transaction coverage mismatch: "
            f"missing={len(expected_hashes - observed_hashes)}, "
            f"unexpected={len(observed_hashes - expected_hashes)}"
        )

    mint_links_path = (
        data_root / "processed" / "position_links" / "pool_mint_nfpm_links.parquet"
    )
    target_events_path = (
        data_root / "processed" / "position_events" / "target_nfpm_events.parquet"
    )
    mint_links = (
        pd.read_parquet(mint_links_path)
        if mint_links_path.exists()
        else pd.DataFrame()
    )
    target_events = (
        pd.read_parquet(target_events_path)
        if target_events_path.exists()
        else pd.DataFrame()
    )
    burn_links = link_pool_burns_to_nfpm_decreases(
        pool, target_events, config.nfpm_address
    )
    operations = prepare_liquidity_operations(
        pool, transactions, mint_links=mint_links, burn_links=burn_links
    )
    operations, all_pairs, strict, ambiguous, unmatched = build_operation_pairs(
        operations
    )
    validate_pairs(operations, all_pairs)
    same_block = all_pairs.loc[all_pairs["is_same_block"]].reset_index(drop=True)
    non_same_block = all_pairs.loc[~all_pairs["is_same_block"]].reset_index(
        drop=True
    )
    if len(same_block) + len(non_same_block) != len(all_pairs):
        raise RuntimeError("same-block cohorts do not partition all exact pairs")
    if not same_block.empty and not same_block["is_same_block"].all():
        raise RuntimeError("same-block output contains a multi-block pair")
    if not non_same_block.empty and non_same_block["is_same_block"].any():
        raise RuntimeError("non-same-block output contains a same-block pair")
    if not strict.empty:
        if not strict["is_strict_pair"].all():
            raise RuntimeError("strict pair output contains a non-strict row")
        if strict["is_ambiguous"].any():
            raise RuntimeError("strict pair output contains an ambiguous row")
        if strict["is_same_transaction"].any():
            raise RuntimeError("strict pair output contains a same-transaction row")
        if not strict["has_positive_holding_time"].all():
            raise RuntimeError("strict pair output contains non-positive holding time")

    outputs = {
        "transaction_senders": data_root
        / "processed"
        / "transaction_senders.parquet",
        "liquidity_operations": data_root
        / "processed"
        / "pool_liquidity_operations.parquet",
        "all_pairs": data_root
        / "derived"
        / "operation_pairs"
        / "all_pairs.parquet",
        "strict_pairs": data_root
        / "derived"
        / "operation_pairs"
        / "strict_pairs.parquet",
        "same_block_pairs": data_root
        / "derived"
        / "operation_pairs"
        / "same_block_pairs.parquet",
        "non_same_block_pairs": data_root
        / "derived"
        / "operation_pairs"
        / "non_same_block_pairs.parquet",
        "ambiguous_pairs": data_root
        / "derived"
        / "operation_pairs"
        / "ambiguous_pairs.parquet",
        "unmatched_operations": data_root
        / "derived"
        / "operation_pairs"
        / "unmatched_operations.parquet",
    }
    frames = {
        "transaction_senders": transactions,
        "liquidity_operations": operations,
        "all_pairs": all_pairs,
        "strict_pairs": strict,
        "same_block_pairs": same_block,
        "non_same_block_pairs": non_same_block,
        "ambiguous_pairs": ambiguous,
        "unmatched_operations": unmatched,
    }
    for name, path in outputs.items():
        write_parquet(frames[name], path)

    clean_path = (
        data_root / "derived" / "positions" / "clean_closed_positions.parquet"
    )
    clean_token_ids = (
        set(pd.read_parquet(clean_path, columns=["token_id"])["token_id"].astype(str))
        if clean_path.exists()
        else set()
    )
    strict_tokens = set(
        strict["nfpm_token_id"].dropna().astype(str)
        if "nfpm_token_id" in strict
        else []
    )
    unmatched_reasons = {
        str(reason): int(count)
        for reason, count in unmatched["unmatched_reason"]
        .fillna("unknown")
        .value_counts()
        .items()
    }
    strict_waterfall = strict_exclusion_waterfall(all_pairs)
    if sum(strict_waterfall.values()) != len(all_pairs):
        raise RuntimeError("strict pair waterfall does not cover every exact pair")
    if strict_waterfall["strict"] != len(strict):
        raise RuntimeError("strict pair waterfall does not reproduce strict output")
    zero_liquidity = unmatched.loc[
        unmatched["unmatched_reason"] == "zero_liquidity"
    ]
    qc = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": args.config.name,
        "config_sha256": sha256(args.config),
        "pool_liquidity_event_count": len(pool),
        "pool_mint_count": int((pool["event_type"] == "Mint").sum()),
        "pool_burn_count": int((pool["event_type"] == "Burn").sum()),
        "requested_unique_transaction_count": len(expected_hashes),
        "transaction_sender_count": len(transactions),
        "transaction_sender_coverage": len(observed_hashes) / len(expected_hashes),
        "canonical_nfpm_operation_count": int(
            (operations["manager_address"] == config.nfpm_address).sum()
        ),
        "nfpm_mint_link_count": len(mint_links),
        "nfpm_burn_link_count": len(burn_links),
        "all_pair_count": len(all_pairs),
        "strict_pair_count": len(strict),
        "same_block_pair_count": len(same_block),
        "non_same_block_pair_count": len(non_same_block),
        "same_block_share_of_all_pairs": (
            len(same_block) / len(all_pairs) if len(all_pairs) else 0.0
        ),
        "ambiguous_pair_count": len(ambiguous),
        "intervening_liquidity_pair_count": int(
            all_pairs["has_intervening_same_range_liquidity_event"].sum()
        )
        if not all_pairs.empty
        else 0,
        "same_transaction_pair_count": int(all_pairs["is_same_transaction"].sum())
        if not all_pairs.empty
        else 0,
        "non_positive_holding_time_pair_count": int(
            (~all_pairs["has_positive_holding_time"]).sum()
        )
        if not all_pairs.empty
        else 0,
        "strict_exclusion_waterfall": strict_waterfall,
        "unmatched_operation_count": len(unmatched),
        "unmatched_reasons": unmatched_reasons,
        "zero_liquidity_burn_count": int(
            (zero_liquidity["operation_type"] == "Burn").sum()
        ),
        "zero_liquidity_mint_count": int(
            (zero_liquidity["operation_type"] == "Mint").sum()
        ),
        "snapshot_open_exact_mint_count": int(
            (unmatched["unmatched_reason"] == "no_subsequent_exact_burn").sum()
        ),
        "burn_without_preceding_exact_mint_count": int(
            (unmatched["unmatched_reason"] == "no_preceding_exact_mint").sum()
        ),
        "unmatched_depth_mismatch_candidate_count": count_depth_mismatch_candidates(
            unmatched
        ),
        "operation_classification_check": {
            "matched_operation_count": 2 * len(all_pairs),
            "unmatched_operation_count": len(unmatched),
            "classified_operation_count": 2 * len(all_pairs) + len(unmatched),
            "source_operation_count": len(operations),
        },
        "pairs_with_consistent_nfpm_token_id": int(
            all_pairs["nfpm_token_id_consistent"].sum()
        )
        if not all_pairs.empty
        else 0,
        "strict_pair_overlap_with_clean_closed_token_ids": len(
            strict_tokens & clean_token_ids
        ),
        "manager_operation_counts": {
            str(manager): int(count)
            for manager, count in operations["manager_address"].value_counts().items()
        },
        "outputs": {
            name: {
                "path": path.relative_to(data_root).as_posix(),
                "row_count": len(frames[name]),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in outputs.items()
        },
    }
    qc_path = metadata_root / "processing" / "build_operation_pairs_qc.json"
    write_json(qc_path, qc)
    print(
        f"built {len(all_pairs):,} exact FIFO pairs; {len(strict):,} are strict. "
        f"QC: {qc_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
