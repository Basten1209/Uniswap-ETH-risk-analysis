"""Build paper-style one-to-one Mint/Burn liquidity operation pairs."""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from typing import Any

import pandas as pd


EVENT_ORDER = ("block_number", "transaction_index", "log_index")
PAIR_KEY = (
    "lp_wallet",
    "manager_address",
    "tick_lower",
    "tick_upper",
    "liquidity_raw",
)


def _int_text(value: Any) -> str:
    if value is None or value is pd.NA or pd.isna(value):
        return "0"
    return str(abs(int(str(value))))


def _optional_text(value: Any) -> str | None:
    if value is None or value is pd.NA or pd.isna(value):
        return None
    text = str(value)
    return None if text in ("", "<NA>", "nan", "None") else text


def _event_id(row: pd.Series | dict[str, Any]) -> str:
    return f"{row['transaction_hash']}:{int(row['log_index'])}"


def _operation_id(entry_event_id: str, exit_event_id: str) -> str:
    return hashlib.sha256(
        f"{entry_event_id}|{exit_event_id}".encode("ascii")
    ).hexdigest()


def link_pool_burns_to_nfpm_decreases(
    pool_events: pd.DataFrame,
    nfpm_events: pd.DataFrame,
    nfpm_address: str,
) -> pd.DataFrame:
    """Link core Pool Burn logs to canonical NFPM DecreaseLiquidity logs."""

    burns = pool_events.loc[
        (pool_events["event_type"] == "Burn")
        & (pool_events["owner"].astype(str).str.lower() == nfpm_address.lower())
    ].copy()
    decreases = nfpm_events.loc[
        nfpm_events["event_type"] == "DecreaseLiquidity"
    ].copy()
    if burns.empty or decreases.empty:
        return pd.DataFrame(
            columns=(
                "token_id",
                "transaction_hash",
                "pool_burn_log_index",
                "nfpm_decrease_log_index",
                "match_method",
            )
        )

    by_tx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for burn in burns.to_dict(orient="records"):
        by_tx[str(burn["transaction_hash"])].append(burn)
    for rows in by_tx.values():
        rows.sort(key=lambda row: int(row["log_index"]))

    used: set[tuple[str, int]] = set()
    links: list[dict[str, Any]] = []
    decreases = decreases.sort_values(list(EVENT_ORDER), kind="stable")
    for decrease in decreases.to_dict(orient="records"):
        tx_hash = str(decrease["transaction_hash"])
        candidates = []
        for burn in by_tx.get(tx_hash, []):
            key = (tx_hash, int(burn["log_index"]))
            if key in used or int(burn["log_index"]) >= int(decrease["log_index"]):
                continue
            if (
                _int_text(burn.get("liquidity_delta_raw"))
                == _int_text(decrease.get("liquidity_delta_raw"))
                and _int_text(burn.get("amount0_raw"))
                == _int_text(decrease.get("amount0_raw"))
                and _int_text(burn.get("amount1_raw"))
                == _int_text(decrease.get("amount1_raw"))
            ):
                candidates.append(burn)
        if not candidates:
            continue
        burn = max(candidates, key=lambda row: int(row["log_index"]))
        used.add((tx_hash, int(burn["log_index"])))
        links.append(
            {
                "token_id": str(decrease["token_id"]),
                "transaction_hash": tx_hash,
                "pool_burn_log_index": int(burn["log_index"]),
                "nfpm_decrease_log_index": int(decrease["log_index"]),
                "match_method": "same_tx_exact_amounts_nearest_preceding",
            }
        )
    return pd.DataFrame(links)


def prepare_liquidity_operations(
    pool_events: pd.DataFrame,
    transactions: pd.DataFrame,
    mint_links: pd.DataFrame | None = None,
    burn_links: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach transaction identity and optional NFPM token IDs to Mint/Burn logs."""

    pool = pool_events.loc[pool_events["event_type"].isin(("Mint", "Burn"))].copy()
    if pool.empty:
        return pool
    tx_columns = [
        "transaction_hash",
        "block_number",
        "block_timestamp",
        "transaction_index",
        "from_address",
        "to_address",
    ]
    missing = set(tx_columns).difference(transactions.columns)
    if missing:
        raise ValueError(f"transactions are missing columns: {sorted(missing)}")
    tx = transactions.loc[:, tx_columns].copy()
    if tx["transaction_hash"].duplicated().any():
        raise ValueError("transactions contain duplicate transaction hashes")
    pool["transaction_hash"] = pool["transaction_hash"].astype(str).str.lower()
    tx["transaction_hash"] = tx["transaction_hash"].astype(str).str.lower()
    result = pool.merge(
        tx,
        on="transaction_hash",
        how="left",
        suffixes=("", "_transaction"),
        validate="many_to_one",
    )
    if result["from_address"].isna().any():
        count = int(result["from_address"].isna().sum())
        raise RuntimeError(f"{count} pool liquidity operations lack transaction identity")
    for column in ("block_number", "block_timestamp", "transaction_index"):
        expected = result[f"{column}_transaction"]
        observed = result[column]
        if column == "block_timestamp":
            expected = pd.to_datetime(expected, utc=True)
            observed = pd.to_datetime(observed, utc=True)
        if not observed.equals(expected):
            raise RuntimeError(f"pool and transaction {column} values do not match")
        result = result.drop(columns=f"{column}_transaction")

    result = result.rename(
        columns={
            "event_type": "operation_type",
            "owner": "manager_address",
            "from_address": "lp_wallet",
            "to_address": "transaction_to_address",
            "liquidity_delta_raw": "signed_liquidity_delta_raw",
        }
    )
    result["liquidity_raw"] = result["signed_liquidity_delta_raw"].map(_int_text)
    result["tick_lower"] = result["tick_lower"].astype("int64")
    result["tick_upper"] = result["tick_upper"].astype("int64")
    for column in ("lp_wallet", "manager_address", "transaction_to_address", "address"):
        result[column] = result[column].map(
            lambda value: _optional_text(value).lower()
            if _optional_text(value) is not None
            else None
        )
    result["event_id"] = result.apply(_event_id, axis=1)
    if result["event_id"].duplicated().any():
        raise RuntimeError("pool liquidity operations contain duplicate event IDs")
    result["nfpm_entry_token_id"] = None
    result["nfpm_exit_token_id"] = None

    if mint_links is not None and not mint_links.empty:
        link_map = {
            (str(row.transaction_hash).lower(), int(row.pool_mint_log_index)): str(
                row.token_id
            )
            for row in mint_links.itertuples(index=False)
        }
        result["nfpm_entry_token_id"] = result.apply(
            lambda row: link_map.get(
                (str(row["transaction_hash"]).lower(), int(row["log_index"]))
            )
            if row["operation_type"] == "Mint"
            else None,
            axis=1,
        )
    if burn_links is not None and not burn_links.empty:
        link_map = {
            (str(row.transaction_hash).lower(), int(row.pool_burn_log_index)): str(
                row.token_id
            )
            for row in burn_links.itertuples(index=False)
        }
        result["nfpm_exit_token_id"] = result.apply(
            lambda row: link_map.get(
                (str(row["transaction_hash"]).lower(), int(row["log_index"]))
            )
            if row["operation_type"] == "Burn"
            else None,
            axis=1,
        )
    result["is_positive_liquidity"] = result["liquidity_raw"].map(int).gt(0)
    result["is_matched"] = False
    result["operation_id"] = None
    result["unmatched_reason"] = None
    return result.sort_values(list(EVENT_ORDER), kind="stable").reset_index(drop=True)


def _pair_row(
    entry: dict[str, Any],
    exit: dict[str, Any],
    candidate_count: int,
    has_intervening_liquidity_event: bool,
) -> dict[str, Any]:
    entry_event_id = str(entry["event_id"])
    exit_event_id = str(exit["event_id"])
    entry_time = pd.Timestamp(entry["block_timestamp"])
    exit_time = pd.Timestamp(exit["block_timestamp"])
    holding_seconds = (exit_time - entry_time).total_seconds()
    same_transaction = str(entry["transaction_hash"]) == str(exit["transaction_hash"])
    same_block = int(entry["block_number"]) == int(exit["block_number"])
    ambiguous = candidate_count > 1
    positive_holding = holding_seconds > 0
    entry_token = _optional_text(entry.get("nfpm_entry_token_id"))
    exit_token = _optional_text(exit.get("nfpm_exit_token_id"))
    token_consistent = bool(
        entry_token is not None and exit_token is not None and entry_token == exit_token
    )
    token_conflict = bool(
        entry_token is not None and exit_token is not None and entry_token != exit_token
    )
    operation_id = _operation_id(entry_event_id, exit_event_id)
    result: dict[str, Any] = {
        "operation_id": operation_id,
        "pool_address": entry["address"],
        "lp_wallet": entry["lp_wallet"],
        "manager_address": entry["manager_address"],
        "tick_lower": int(entry["tick_lower"]),
        "tick_upper": int(entry["tick_upper"]),
        "liquidity_raw": entry["liquidity_raw"],
        "entry_event_id": entry_event_id,
        "exit_event_id": exit_event_id,
        "entry_nfpm_token_id": entry_token,
        "exit_nfpm_token_id": exit_token,
        "nfpm_token_id": entry_token if token_consistent else None,
        "nfpm_token_id_consistent": token_consistent,
        "nfpm_token_id_conflict": token_conflict,
        "candidate_open_mint_count": candidate_count,
        "is_ambiguous": ambiguous,
        "has_intervening_same_range_liquidity_event": (
            has_intervening_liquidity_event
        ),
        "is_same_transaction": same_transaction,
        "is_same_block": same_block,
        "analysis_cohort": (
            "same_block_jit_mev_candidate"
            if same_block
            else "multi_block_lp_position"
        ),
        "has_positive_holding_time": positive_holding,
        "holding_seconds": holding_seconds,
        "is_strict_pair": bool(
            not ambiguous
            and not has_intervening_liquidity_event
            and not same_transaction
            and positive_holding
        ),
    }
    copied = (
        "block_number",
        "block_timestamp",
        "transaction_hash",
        "transaction_index",
        "log_index",
        "transaction_to_address",
        "amount0_raw",
        "amount1_raw",
    )
    for prefix, row in (("entry", entry), ("exit", exit)):
        for column in copied:
            result[f"{prefix}_{column}"] = row.get(column)
    return result


def build_operation_pairs(
    operations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return annotated operations, all, strict, ambiguous, and unmatched rows."""

    if operations.empty:
        empty = pd.DataFrame()
        return operations.copy(), empty, empty, empty, empty
    required = set(EVENT_ORDER + PAIR_KEY + ("operation_type", "event_id"))
    missing = required.difference(operations.columns)
    if missing:
        raise ValueError(f"operations are missing columns: {sorted(missing)}")
    result = operations.sort_values(list(EVENT_ORDER), kind="stable").reset_index(
        drop=True
    )
    open_mints: dict[tuple[Any, ...], deque[int]] = defaultdict(deque)
    base_event_counts: dict[tuple[Any, ...], int] = defaultdict(int)
    entry_base_sequence: dict[int, int] = {}
    pair_rows: list[dict[str, Any]] = []
    unmatched_reasons: dict[int, str] = {}

    for index, row in result.iterrows():
        if not bool(row["is_positive_liquidity"]):
            unmatched_reasons[index] = "zero_liquidity"
            continue
        key = tuple(row[column] for column in PAIR_KEY)
        base_key = key[:-1]
        base_sequence = base_event_counts[base_key]
        if row["operation_type"] == "Mint":
            open_mints[key].append(index)
            entry_base_sequence[index] = base_sequence
            base_event_counts[base_key] += 1
            continue
        if row["operation_type"] != "Burn":
            raise ValueError(f"unexpected operation type: {row['operation_type']}")
        candidates = open_mints[key]
        if not candidates:
            unmatched_reasons[index] = "no_preceding_exact_mint"
            base_event_counts[base_key] += 1
            continue
        candidate_count = len(candidates)
        entry_index = candidates.popleft()
        pair = _pair_row(
            result.loc[entry_index].to_dict(),
            row.to_dict(),
            candidate_count,
            has_intervening_liquidity_event=(
                base_sequence - entry_base_sequence[entry_index] - 1 > 0
            ),
        )
        pair_rows.append(pair)
        result.loc[[entry_index, index], "is_matched"] = True
        result.loc[[entry_index, index], "operation_id"] = pair["operation_id"]
        base_event_counts[base_key] += 1

    for indexes in open_mints.values():
        for index in indexes:
            unmatched_reasons[index] = "no_subsequent_exact_burn"
    for index, reason in unmatched_reasons.items():
        result.at[index, "unmatched_reason"] = reason

    all_pairs = pd.DataFrame(pair_rows)
    if not all_pairs.empty:
        all_pairs = all_pairs.sort_values(
            ["entry_block_number", "entry_transaction_index", "entry_log_index"],
            kind="stable",
        ).reset_index(drop=True)
    strict = (
        all_pairs.loc[all_pairs["is_strict_pair"]].reset_index(drop=True)
        if not all_pairs.empty
        else all_pairs.copy()
    )
    ambiguous = (
        all_pairs.loc[all_pairs["is_ambiguous"]].reset_index(drop=True)
        if not all_pairs.empty
        else all_pairs.copy()
    )
    unmatched = result.loc[~result["is_matched"]].reset_index(drop=True)
    return result, all_pairs, strict, ambiguous, unmatched
