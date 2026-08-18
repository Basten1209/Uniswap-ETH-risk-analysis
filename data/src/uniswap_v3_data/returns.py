"""Closed-position return construction using external valuation prices."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, getcontext
from typing import Any

import pandas as pd

PRICE_COLUMNS = ("timestamp", "token0_price_usdt", "token1_price_usdt")


def prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    missing = set(PRICE_COLUMNS).difference(prices.columns)
    if missing:
        raise ValueError(f"price data is missing columns: {sorted(missing)}")
    result = prices.loc[:, PRICE_COLUMNS].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    if result["timestamp"].isna().any():
        raise ValueError("price data contains invalid timestamps")
    result = result.sort_values("timestamp", kind="stable").drop_duplicates(
        "timestamp", keep="last"
    )
    for column in ("token0_price_usdt", "token1_price_usdt"):
        try:
            values = result[column].map(lambda value: Decimal(str(value)))
        except InvalidOperation as exc:
            raise ValueError(f"{column} contains a non-decimal value") from exc
        if any(value <= 0 for value in values):
            raise ValueError(f"{column} must be strictly positive")
        result[column] = result[column].astype(str)
    return result.reset_index(drop=True)


def _attach_asof_prices(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    timestamp_column: str,
    suffix: str,
    max_age_seconds: int,
) -> pd.DataFrame:
    left = positions.copy().reset_index(names="_original_index")
    left[timestamp_column] = pd.to_datetime(left[timestamp_column], utc=True)
    left = left.sort_values(timestamp_column, kind="stable")
    right = prices.rename(
        columns={
            "timestamp": f"price_timestamp_{suffix}",
            "token0_price_usdt": f"token0_price_usdt_{suffix}",
            "token1_price_usdt": f"token1_price_usdt_{suffix}",
        }
    )
    result = pd.merge_asof(
        left,
        right,
        left_on=timestamp_column,
        right_on=f"price_timestamp_{suffix}",
        direction="backward",
        tolerance=pd.Timedelta(seconds=max_age_seconds),
    )
    return (
        result.sort_values("_original_index", kind="stable")
        .drop(columns="_original_index")
        .reset_index(drop=True)
    )


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _human(raw: Any, decimals: int) -> Decimal:
    return _decimal(raw) / (Decimal(10) ** decimals)


def calculate_closed_returns(
    clean_positions: pd.DataFrame,
    prices: pd.DataFrame,
    decimals0: int,
    decimals1: int,
    max_price_age_seconds: int,
) -> pd.DataFrame:
    """Calculate fee-inclusive terminal return and paper-style HODL excess return.

    All lifetime token fees are inferred as total Collect minus total
    DecreaseLiquidity principal. Both principal and fee token quantities are
    marked at the exit price. This assumes collected fee tokens are retained
    until exit and deliberately excludes gas.
    """
    if clean_positions.empty:
        return clean_positions.copy()
    required = {
        "entry_timestamp",
        "exit_timestamp",
        "deposit_amount0_raw",
        "deposit_amount1_raw",
        "withdraw_principal0_raw",
        "withdraw_principal1_raw",
        "fee_amount0_raw",
        "fee_amount1_raw",
        "is_clean_closed",
    }
    missing = required.difference(clean_positions.columns)
    if missing:
        raise ValueError(f"clean position data is missing columns: {sorted(missing)}")
    if not clean_positions["is_clean_closed"].all():
        raise ValueError("return input contains positions not marked is_clean_closed")
    if max_price_age_seconds <= 0:
        raise ValueError("max_price_age_seconds must be positive")

    prices = prepare_prices(prices)
    result = _attach_asof_prices(
        clean_positions, prices, "entry_timestamp", "entry", max_price_age_seconds
    )
    result = _attach_asof_prices(
        result, prices, "exit_timestamp", "exit", max_price_age_seconds
    )
    price_fields = [
        "token0_price_usdt_entry",
        "token1_price_usdt_entry",
        "token0_price_usdt_exit",
        "token1_price_usdt_exit",
    ]
    missing_price = result[price_fields].isna().any(axis=1)
    if missing_price.any():
        token_ids = result.loc[missing_price, "token_id"].astype(str).head(10).tolist()
        raise ValueError(
            "no prior oracle observation within max price age for token IDs "
            f"{token_ids}; increase coverage or --max-price-age-seconds"
        )

    getcontext().prec = 60
    calculated: list[dict[str, str]] = []
    for row in result.to_dict(orient="records"):
        deposit0 = _human(row["deposit_amount0_raw"], decimals0)
        deposit1 = _human(row["deposit_amount1_raw"], decimals1)
        principal0 = _human(row["withdraw_principal0_raw"], decimals0)
        principal1 = _human(row["withdraw_principal1_raw"], decimals1)
        fee0 = _human(row["fee_amount0_raw"], decimals0)
        fee1 = _human(row["fee_amount1_raw"], decimals1)
        p0_entry = _decimal(row["token0_price_usdt_entry"])
        p1_entry = _decimal(row["token1_price_usdt_entry"])
        p0_exit = _decimal(row["token0_price_usdt_exit"])
        p1_exit = _decimal(row["token1_price_usdt_exit"])

        initial_wealth = deposit0 * p0_entry + deposit1 * p1_entry
        principal_exit = principal0 * p0_exit + principal1 * p1_exit
        fee_exit = fee0 * p0_exit + fee1 * p1_exit
        lp_exit = principal_exit + fee_exit
        hodl_exit = deposit0 * p0_exit + deposit1 * p1_exit
        if initial_wealth <= 0 or hodl_exit <= 0:
            raise ValueError(
                f"token_id={row['token_id']} has a non-positive denominator"
            )

        calculated.append(
            {
                "deposit_token0": str(deposit0),
                "deposit_token1": str(deposit1),
                "withdraw_principal_token0": str(principal0),
                "withdraw_principal_token1": str(principal1),
                "fee_token0": str(fee0),
                "fee_token1": str(fee1),
                "initial_wealth_usdt": str(initial_wealth),
                "principal_exit_value_usdt": str(principal_exit),
                "fee_exit_value_usdt": str(fee_exit),
                "lp_exit_value_usdt": str(lp_exit),
                "hodl_exit_value_usdt": str(hodl_exit),
                "lp_total_return_close_marked": str(
                    (lp_exit - initial_wealth) / initial_wealth
                ),
                "lp_excess_return_vs_hodl_close": str(
                    (lp_exit - hodl_exit) / hodl_exit
                ),
                "fee_return_on_initial_wealth": str(fee_exit / initial_wealth),
                "il_return_vs_hodl_fee_exclusive": str(
                    (principal_exit - hodl_exit) / hodl_exit
                ),
            }
        )
    return pd.concat([result.reset_index(drop=True), pd.DataFrame(calculated)], axis=1)
