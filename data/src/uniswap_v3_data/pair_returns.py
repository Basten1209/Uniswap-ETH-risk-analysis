"""Realized-fee attribution and close-marked returns for operation pairs."""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal, getcontext
from typing import Any

import pandas as pd

from .returns import _attach_asof_prices, prepare_prices


EVENT_ORDER = ("block_number", "transaction_index", "log_index")
PAIR_ORDER = (
    "entry_block_number",
    "entry_transaction_index",
    "entry_log_index",
)


def _int(value: Any) -> int:
    if value is None or value is pd.NA or pd.isna(value):
        return 0
    return int(str(value))


def _identity(row: pd.Series | dict[str, Any]) -> tuple[str, ...]:
    if bool(row["nfpm_token_id_consistent"]):
        return ("nfpm_token", str(row["nfpm_token_id"]))
    return (
        "pool_position",
        str(row["manager_address"]).lower(),
        str(int(row["tick_lower"])),
        str(int(row["tick_upper"])),
    )


def _pair_start(row: Any) -> tuple[int, int, int]:
    return (
        int(row.entry_block_number),
        int(row.entry_transaction_index),
        int(row.entry_log_index),
    )


def _pair_end(row: Any) -> tuple[int, int, int]:
    return (
        int(row.exit_block_number),
        int(row.exit_transaction_index),
        int(row.exit_log_index),
    )


def overlapping_fee_attribution_ids(pairs: pd.DataFrame) -> set[str]:
    """Return pair IDs whose fee-identity intervals overlap.

    NFPM-linked pairs use token ID as the identity. Other managers use the
    on-chain Pool position key (manager, lower tick, upper tick). A Collect
    cannot be assigned to one operation pair when two intervals for the same
    identity are simultaneously open, so those rows are excluded rather than
    allocated by assumption.
    """

    if pairs.empty:
        return set()
    grouped: dict[tuple[str, ...], list[Any]] = defaultdict(list)
    ordered = pairs.sort_values(list(PAIR_ORDER), kind="stable")
    for row in ordered.itertuples(index=False):
        grouped[_identity(row._asdict())].append(row)

    overlapping: set[str] = set()
    for rows in grouped.values():
        active: list[tuple[tuple[int, int, int], str]] = []
        for row in rows:
            start = _pair_start(row)
            active = [item for item in active if item[0] > start]
            if active:
                overlapping.add(str(row.operation_id))
                overlapping.update(operation_id for _, operation_id in active)
            active.append((_pair_end(row), str(row.operation_id)))
    return overlapping


def _collect_records(
    pool_events: pd.DataFrame, nfpm_events: pd.DataFrame
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    records: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)

    nfpm_collects = nfpm_events.loc[nfpm_events["event_type"] == "Collect"]
    for row in nfpm_collects.itertuples(index=False):
        records[("nfpm_token", str(row.token_id))].append(
            {
                "block_number": int(row.block_number),
                "transaction_index": int(row.transaction_index),
                "log_index": int(row.log_index),
                "transaction_hash": str(row.transaction_hash).lower(),
                "amount0_raw": _int(row.amount0_raw),
                "amount1_raw": _int(row.amount1_raw),
            }
        )

    pool_collects = pool_events.loc[pool_events["event_type"] == "Collect"]
    for row in pool_collects.itertuples(index=False):
        key = (
            "pool_position",
            str(row.owner).lower(),
            str(int(row.tick_lower)),
            str(int(row.tick_upper)),
        )
        records[key].append(
            {
                "block_number": int(row.block_number),
                "transaction_index": int(row.transaction_index),
                "log_index": int(row.log_index),
                "transaction_hash": str(row.transaction_hash).lower(),
                "amount0_raw": _int(row.amount0_raw),
                "amount1_raw": _int(row.amount1_raw),
            }
        )

    for values in records.values():
        values.sort(
            key=lambda item: (
                item["block_number"],
                item["transaction_index"],
                item["log_index"],
            )
        )
    return records


def attribute_realized_fees(
    pairs: pd.DataFrame,
    pool_events: pd.DataFrame,
    nfpm_events: pd.DataFrame,
    clean_token_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Attach observed realized fees through each pair's exit transaction.

    Collects in transactions strictly between entry and exit are fee cash
    flows. Collects after the matched Burn in the exit transaction contain
    principal plus fee; the matched Burn principal is subtracted. A missing
    post-Burn Collect means zero fee was realized at exit, not that accrued fee
    was zero. Rows with overlapping fee identities are retained for audit but
    excluded from fee/return analysis.
    """

    if pairs.empty:
        return pairs.copy()
    required = {
        "operation_id",
        "manager_address",
        "tick_lower",
        "tick_upper",
        "nfpm_token_id",
        "nfpm_token_id_consistent",
        "entry_block_number",
        "entry_transaction_index",
        "entry_log_index",
        "exit_block_number",
        "exit_transaction_index",
        "exit_log_index",
        "exit_transaction_hash",
        "exit_amount0_raw",
        "exit_amount1_raw",
    }
    missing = required.difference(pairs.columns)
    if missing:
        raise ValueError(f"operation pairs are missing columns: {sorted(missing)}")

    result = pairs.copy().reset_index(drop=True)
    excluded = overlapping_fee_attribution_ids(result)
    collects = _collect_records(pool_events, nfpm_events)
    clean_token_ids = clean_token_ids or set()
    fee_rows: list[dict[str, Any]] = []

    for row in result.to_dict(orient="records"):
        operation_id = str(row["operation_id"])
        identity = _identity(row)
        identity_source = identity[0]
        token_id = str(row["nfpm_token_id"]) if identity_source == "nfpm_token" else None
        if operation_id in excluded:
            fee_rows.append(
                {
                    "fee_analysis_included": False,
                    "fee_exclusion_reason": "overlapping_fee_attribution",
                    "fee_attribution_source": identity_source,
                    "interim_collect_count": 0,
                    "exit_collect_count": 0,
                    "exit_collect_observed": False,
                    "exit_collect_covers_principal": False,
                    "realized_fee0_raw": None,
                    "realized_fee1_raw": None,
                    "fee_complete_exact": False,
                }
            )
            continue

        entry_order = (
            int(row["entry_block_number"]),
            int(row["entry_transaction_index"]),
            int(row["entry_log_index"]),
        )
        exit_tx_order = (
            int(row["exit_block_number"]),
            int(row["exit_transaction_index"]),
        )
        exit_hash = str(row["exit_transaction_hash"]).lower()
        exit_log_index = int(row["exit_log_index"])
        interim = []
        exit_collects = []
        for collect in collects.get(identity, []):
            collect_order = (
                collect["block_number"],
                collect["transaction_index"],
                collect["log_index"],
            )
            if collect_order <= entry_order:
                continue
            collect_tx_order = collect_order[:2]
            if collect_tx_order < exit_tx_order:
                interim.append(collect)
            elif (
                collect["transaction_hash"] == exit_hash
                and collect["log_index"] > exit_log_index
            ):
                exit_collects.append(collect)

        interim0 = sum(item["amount0_raw"] for item in interim)
        interim1 = sum(item["amount1_raw"] for item in interim)
        exit_collect0 = sum(item["amount0_raw"] for item in exit_collects)
        exit_collect1 = sum(item["amount1_raw"] for item in exit_collects)
        principal0 = _int(row["exit_amount0_raw"])
        principal1 = _int(row["exit_amount1_raw"])
        observed = bool(exit_collects)
        covers_principal = bool(
            observed and exit_collect0 >= principal0 and exit_collect1 >= principal1
        )
        exit_fee0 = exit_collect0 - principal0 if covers_principal else 0
        exit_fee1 = exit_collect1 - principal1 if covers_principal else 0
        fee_rows.append(
            {
                "fee_analysis_included": True,
                "fee_exclusion_reason": None,
                "fee_attribution_source": identity_source,
                "interim_collect_count": len(interim),
                "exit_collect_count": len(exit_collects),
                "exit_collect_observed": observed,
                "exit_collect_covers_principal": covers_principal,
                "realized_fee0_raw": str(interim0 + exit_fee0),
                "realized_fee1_raw": str(interim1 + exit_fee1),
                "fee_complete_exact": bool(token_id in clean_token_ids),
            }
        )

    return pd.concat([result, pd.DataFrame(fee_rows)], axis=1)


def calculate_pair_returns(
    fee_pairs: pd.DataFrame,
    prices: pd.DataFrame,
    decimals0: int,
    decimals1: int,
    max_price_age_seconds: int,
) -> pd.DataFrame:
    """Value pair cash flows and calculate realized-fee close-marked returns."""

    if fee_pairs.empty:
        return fee_pairs.copy()
    prices = prepare_prices(prices)
    result = fee_pairs.rename(
        columns={
            "entry_block_timestamp": "entry_timestamp",
            "exit_block_timestamp": "exit_timestamp",
        }
    ).copy()
    result = _attach_asof_prices(
        result, prices, "entry_timestamp", "entry", max_price_age_seconds
    )
    result = _attach_asof_prices(
        result, prices, "exit_timestamp", "exit", max_price_age_seconds
    )
    price_columns = [
        "token0_price_usdt_entry",
        "token1_price_usdt_entry",
        "token0_price_usdt_exit",
        "token1_price_usdt_exit",
    ]
    included = result["fee_analysis_included"]
    if result.loc[included, price_columns].isna().any(axis=None):
        raise ValueError("an included operation pair lacks a strict-prior oracle price")

    getcontext().prec = 60
    calculations: list[dict[str, Any]] = []
    scale0 = Decimal(10) ** decimals0
    scale1 = Decimal(10) ** decimals1
    for row in result.to_dict(orient="records"):
        if not bool(row["fee_analysis_included"]):
            calculations.append(
                {
                    "initial_wealth_usdt": None,
                    "principal_exit_value_usdt": None,
                    "realized_fee_value_usdt": None,
                    "lp_exit_value_realized_fee_usdt": None,
                    "hodl_exit_value_usdt": None,
                    "lp_total_return_realized_fee": None,
                    "lp_excess_return_vs_hodl_realized_fee": None,
                    "fee_return_on_initial_wealth": None,
                    "holding_days": float(row["holding_seconds"]) / 86_400,
                    "realized_daily_log_return": None,
                    "realized_daily_return_geometric": None,
                    "realized_daily_return_simple": None,
                }
            )
            continue

        deposit0 = Decimal(str(row["entry_amount0_raw"])) / scale0
        deposit1 = Decimal(str(row["entry_amount1_raw"])) / scale1
        principal0 = Decimal(str(row["exit_amount0_raw"])) / scale0
        principal1 = Decimal(str(row["exit_amount1_raw"])) / scale1
        fee0 = Decimal(str(row["realized_fee0_raw"])) / scale0
        fee1 = Decimal(str(row["realized_fee1_raw"])) / scale1
        p0_entry = Decimal(str(row["token0_price_usdt_entry"]))
        p1_entry = Decimal(str(row["token1_price_usdt_entry"]))
        p0_exit = Decimal(str(row["token0_price_usdt_exit"]))
        p1_exit = Decimal(str(row["token1_price_usdt_exit"]))
        initial = deposit0 * p0_entry + deposit1 * p1_entry
        principal_exit = principal0 * p0_exit + principal1 * p1_exit
        fee_exit = fee0 * p0_exit + fee1 * p1_exit
        lp_exit = principal_exit + fee_exit
        hodl_exit = deposit0 * p0_exit + deposit1 * p1_exit
        if initial <= 0 or hodl_exit <= 0:
            raise ValueError(f"operation_id={row['operation_id']} has a non-positive value")
        total_return = (lp_exit - initial) / initial
        excess_return = (lp_exit - hodl_exit) / hodl_exit
        holding_days = float(row["holding_seconds"]) / 86_400
        if holding_days <= 0:
            raise ValueError("pair-return input contains non-positive holding time")
        total_return_float = float(total_return)
        daily_log_return = (
            math.log1p(total_return_float) / holding_days
            if total_return_float > -1
            else math.nan
        )
        try:
            geometric = math.expm1(daily_log_return)
        except OverflowError:
            geometric = math.inf
        calculations.append(
            {
                "initial_wealth_usdt": str(initial),
                "principal_exit_value_usdt": str(principal_exit),
                "realized_fee_value_usdt": str(fee_exit),
                "lp_exit_value_realized_fee_usdt": str(lp_exit),
                "hodl_exit_value_usdt": str(hodl_exit),
                "lp_total_return_realized_fee": str(total_return),
                "lp_excess_return_vs_hodl_realized_fee": str(excess_return),
                "fee_return_on_initial_wealth": str(fee_exit / initial),
                "holding_days": holding_days,
                "realized_daily_log_return": daily_log_return,
                "realized_daily_return_geometric": geometric,
                "realized_daily_return_simple": total_return_float / holding_days,
            }
        )
    return pd.concat([result.reset_index(drop=True), pd.DataFrame(calculations)], axis=1)
