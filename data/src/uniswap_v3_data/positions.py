"""Link NFPM token IDs to a pool and reconstruct closed position lifecycles."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import pandas as pd

from .events import ZERO_ADDRESS


def _as_int(value: Any) -> int:
    if value is None or value is pd.NA or pd.isna(value):
        return 0
    return int(str(value), 10)


def _sum_raw(frame: pd.DataFrame, column: str, absolute: bool = False) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    values = (_as_int(value) for value in frame[column].tolist())
    return sum(abs(value) if absolute else value for value in values)


def link_pool_mints_to_nfpm(
    pool_events: pd.DataFrame, nfpm_events: pd.DataFrame, nfpm_address: str
) -> pd.DataFrame:
    """Match target-pool Mint logs to NFPM IncreaseLiquidity logs.

    The core pool emits Mint before the manager emits IncreaseLiquidity. The
    liquidity and token amounts are identical, so transaction hash, log order,
    liquidity, amount0 and amount1 provide a deterministic event-level link.
    """
    pool_mints = pool_events.loc[pool_events["event_type"] == "Mint"].copy()
    if "owner" in pool_mints:
        pool_mints = pool_mints.loc[pool_mints["owner"] == nfpm_address.lower()]
    increases = nfpm_events.loc[nfpm_events["event_type"] == "IncreaseLiquidity"].copy()
    if pool_mints.empty or increases.empty:
        return pd.DataFrame()

    by_tx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mint in pool_mints.to_dict(orient="records"):
        by_tx[str(mint["transaction_hash"])].append(mint)
    for rows in by_tx.values():
        rows.sort(key=lambda row: int(row["log_index"]))

    used_pool_logs: set[tuple[str, int]] = set()
    links: list[dict[str, Any]] = []
    increases = increases.sort_values(
        ["block_number", "transaction_index", "log_index"], kind="stable"
    )
    for increase in increases.to_dict(orient="records"):
        tx_hash = str(increase["transaction_hash"])
        candidates = []
        for mint in by_tx.get(tx_hash, []):
            key = (tx_hash, int(mint["log_index"]))
            if key in used_pool_logs or int(mint["log_index"]) >= int(
                increase["log_index"]
            ):
                continue
            if (
                _as_int(mint.get("liquidity_delta_raw"))
                == _as_int(increase.get("liquidity_delta_raw"))
                and _as_int(mint.get("amount0_raw"))
                == _as_int(increase.get("amount0_raw"))
                and _as_int(mint.get("amount1_raw"))
                == _as_int(increase.get("amount1_raw"))
            ):
                candidates.append(mint)
        if not candidates:
            continue
        # The nearest exact Mint before Increase is the corresponding core call.
        mint = max(candidates, key=lambda row: int(row["log_index"]))
        used_pool_logs.add((tx_hash, int(mint["log_index"])))
        links.append(
            {
                "token_id": str(increase["token_id"]),
                "transaction_hash": tx_hash,
                "block_number": int(increase["block_number"]),
                "block_timestamp": increase["block_timestamp"],
                "pool_mint_log_index": int(mint["log_index"]),
                "nfpm_increase_log_index": int(increase["log_index"]),
                "tick_lower": int(mint["tick_lower"]),
                "tick_upper": int(mint["tick_upper"]),
                "liquidity_raw": str(increase["liquidity_delta_raw"]),
                "amount0_raw": str(increase["amount0_raw"]),
                "amount1_raw": str(increase["amount1_raw"]),
                "match_method": "same_tx_exact_amounts_nearest_preceding",
            }
        )
    result = pd.DataFrame(links)
    if not result.empty:
        result = result.sort_values(
            ["block_number", "pool_mint_log_index"], kind="stable"
        ).reset_index(drop=True)
    return result


def reconstruct_positions(
    pool_events: pd.DataFrame,
    nfpm_events: pd.DataFrame,
    nfpm_address: str,
    study_start: date,
    study_end: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return all target positions, the clean-burned subset and link evidence."""
    links = link_pool_mints_to_nfpm(pool_events, nfpm_events, nfpm_address)
    if links.empty:
        return pd.DataFrame(), pd.DataFrame(), links

    target_ids = set(links["token_id"].astype(str))
    target_events = nfpm_events.loc[
        nfpm_events["token_id"].astype(str).isin(target_ids)
    ].copy()
    positions, clean = reconstruct_positions_from_links(
        links, target_events, study_start, study_end
    )
    return positions, clean, links


def reconstruct_positions_from_links(
    links: pd.DataFrame,
    target_events: pd.DataFrame,
    study_start: date,
    study_end: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct lifecycles after a scalable monthly link/filter pass."""
    if links.empty:
        return pd.DataFrame(), pd.DataFrame()
    target_ids = set(links["token_id"].astype(str))
    target_events = target_events.loc[
        target_events["token_id"].astype(str).isin(target_ids)
    ].copy()
    target_events = target_events.sort_values(
        ["block_number", "transaction_index", "log_index"], kind="stable"
    ).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    for token_id in sorted(target_ids, key=int):
        events = target_events.loc[target_events["token_id"].astype(str) == token_id]
        token_links = links.loc[links["token_id"].astype(str) == token_id]
        increases = events.loc[events["event_type"] == "IncreaseLiquidity"]
        decreases = events.loc[events["event_type"] == "DecreaseLiquidity"]
        collects = events.loc[events["event_type"] == "Collect"]
        transfers = events.loc[events["event_type"] == "Transfer"]
        creations = transfers.loc[transfers.get("from_address") == ZERO_ADDRESS]
        burns = transfers.loc[transfers.get("to_address") == ZERO_ADDRESS]
        ownership_transfers = transfers.loc[
            (transfers.get("from_address") != ZERO_ADDRESS)
            & (transfers.get("to_address") != ZERO_ADDRESS)
        ]

        ranges = {
            (int(link.tick_lower), int(link.tick_upper))
            for link in token_links.itertuples(index=False)
        }
        tick_lower = min((value[0] for value in ranges), default=None)
        tick_upper = max((value[1] for value in ranges), default=None)

        entry_link = token_links.sort_values("pool_mint_log_index", kind="stable").iloc[
            0
        ]
        exit_event = (
            decreases.sort_values(["block_number", "log_index"], kind="stable").iloc[-1]
            if not decreases.empty
            else None
        )
        burn_event = (
            burns.sort_values(["block_number", "log_index"], kind="stable").iloc[-1]
            if not burns.empty
            else None
        )
        creation_event = (
            creations.sort_values(["block_number", "log_index"], kind="stable").iloc[0]
            if not creations.empty
            else None
        )

        increased_liquidity = _sum_raw(increases, "liquidity_delta_raw")
        decreased_liquidity = _sum_raw(decreases, "liquidity_delta_raw", absolute=True)
        deposit0 = _sum_raw(increases, "amount0_raw")
        deposit1 = _sum_raw(increases, "amount1_raw")
        principal0 = _sum_raw(decreases, "amount0_raw")
        principal1 = _sum_raw(decreases, "amount1_raw")
        collected0 = _sum_raw(collects, "amount0_raw")
        collected1 = _sum_raw(collects, "amount1_raw")
        fee0 = collected0 - principal0
        fee1 = collected1 - principal1

        entry_timestamp = pd.Timestamp(entry_link["block_timestamp"])
        exit_timestamp = (
            pd.Timestamp(exit_event["block_timestamp"])
            if exit_event is not None
            else pd.NaT
        )
        settlement_timestamp = (
            pd.Timestamp(burn_event["block_timestamp"])
            if burn_event is not None
            else pd.NaT
        )
        initial_owner = (
            str(creation_event["to_address"]) if creation_event is not None else None
        )

        entry_in_window = study_start <= entry_timestamp.date() < study_end
        exit_in_window = bool(
            exit_event is not None and study_start <= exit_timestamp.date() < study_end
        )
        settlement_in_window = bool(
            burn_event is not None
            and study_start <= settlement_timestamp.date() < study_end
        )
        valid_order = bool(
            exit_event is not None
            and burn_event is not None
            and entry_timestamp <= exit_timestamp <= settlement_timestamp
        )
        fee_nonnegative = fee0 >= 0 and fee1 >= 0
        fully_withdrawn = (
            increased_liquidity > 0 and increased_liquidity == decreased_liquidity
        )
        unique_range = len(ranges) == 1

        clean_closed = all(
            (
                len(token_links) == 1,
                len(increases) == 1,
                len(decreases) == 1,
                len(creations) == 1,
                len(burns) == 1,
                len(ownership_transfers) == 0,
                len(collects) >= 1,
                fully_withdrawn,
                unique_range,
                fee_nonnegative,
                entry_in_window,
                exit_in_window,
                settlement_in_window,
                valid_order,
            )
        )

        rows.append(
            {
                "token_id": token_id,
                "initial_owner": initial_owner,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "entry_block": int(entry_link["block_number"]),
                "entry_timestamp": entry_timestamp,
                "entry_transaction_hash": str(entry_link["transaction_hash"]),
                "exit_block": int(exit_event["block_number"])
                if exit_event is not None
                else None,
                "exit_timestamp": exit_timestamp,
                "exit_transaction_hash": (
                    str(exit_event["transaction_hash"])
                    if exit_event is not None
                    else None
                ),
                "settlement_block": (
                    int(burn_event["block_number"]) if burn_event is not None else None
                ),
                "settlement_timestamp": settlement_timestamp,
                "increase_count": len(increases),
                "decrease_count": len(decreases),
                "collect_count": len(collects),
                "creation_count": len(creations),
                "burn_count": len(burns),
                "ownership_transfer_count": len(ownership_transfers),
                "matched_pool_mint_count": len(token_links),
                "liquidity_increased_raw": str(increased_liquidity),
                "liquidity_decreased_raw": str(decreased_liquidity),
                "liquidity_remaining_raw": str(
                    increased_liquidity - decreased_liquidity
                ),
                "deposit_amount0_raw": str(deposit0),
                "deposit_amount1_raw": str(deposit1),
                "withdraw_principal0_raw": str(principal0),
                "withdraw_principal1_raw": str(principal1),
                "collected_amount0_raw": str(collected0),
                "collected_amount1_raw": str(collected1),
                "fee_amount0_raw": str(fee0),
                "fee_amount1_raw": str(fee1),
                "is_fully_withdrawn": fully_withdrawn,
                "is_nft_burned": len(burns) == 1,
                "is_fee_complete_proven": len(burns) == 1,
                "has_unique_range": unique_range,
                "has_nonnegative_fee": fee_nonnegative,
                "entry_in_study_window": entry_in_window,
                "exit_in_study_window": exit_in_window,
                "settlement_in_study_window": settlement_in_window,
                "has_valid_event_order": valid_order,
                "is_clean_closed": clean_closed,
            }
        )

    positions = (
        pd.DataFrame(rows)
        .sort_values(["entry_block", "token_id"], kind="stable")
        .reset_index(drop=True)
    )
    clean = positions.loc[positions["is_clean_closed"]].reset_index(drop=True)
    return positions, clean


def summarize_pool_daily(pool_events: pd.DataFrame) -> pd.DataFrame:
    """Create auditable daily activity/regime inputs from target-pool events."""
    if pool_events.empty:
        return pd.DataFrame()
    events = pool_events.copy()
    events["date"] = events["block_timestamp"].dt.date
    rows: list[dict[str, Any]] = []
    for day, group in events.groupby("date", sort=True):
        group = group.sort_values(["block_number", "log_index"], kind="stable")
        swaps = group.loc[group["event_type"] == "Swap"]
        mints = group.loc[group["event_type"] == "Mint"]
        burns = group.loc[group["event_type"] == "Burn"]
        collects = group.loc[group["event_type"] == "Collect"]
        row: dict[str, Any] = {
            "date": day,
            "swap_count": len(swaps),
            "mint_count": len(mints),
            "burn_count": len(burns),
            "pool_collect_count": len(collects),
            "swap_abs_amount0_raw": str(
                sum(abs(_as_int(value)) for value in swaps.get("amount0_raw", []))
            ),
            "swap_abs_amount1_raw": str(
                sum(abs(_as_int(value)) for value in swaps.get("amount1_raw", []))
            ),
            "mint_amount0_raw": str(_sum_raw(mints, "amount0_raw")),
            "mint_amount1_raw": str(_sum_raw(mints, "amount1_raw")),
            "burn_amount0_raw": str(_sum_raw(burns, "amount0_raw")),
            "burn_amount1_raw": str(_sum_raw(burns, "amount1_raw")),
            "pool_collect_amount0_raw": str(_sum_raw(collects, "amount0_raw")),
            "pool_collect_amount1_raw": str(_sum_raw(collects, "amount1_raw")),
        }
        if not swaps.empty:
            first = swaps.iloc[0]
            last = swaps.iloc[-1]
            row.update(
                first_swap_timestamp=first["block_timestamp"],
                last_swap_timestamp=last["block_timestamp"],
                open_sqrt_price_x96=str(first["sqrt_price_x96"]),
                close_sqrt_price_x96=str(last["sqrt_price_x96"]),
                close_tick=int(last["tick"]),
                close_active_liquidity_raw=str(last["active_liquidity_raw"]),
            )
        rows.append(row)
    return pd.DataFrame(rows)
