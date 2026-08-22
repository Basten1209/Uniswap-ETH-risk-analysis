"""Definition-level formulas for IL, LVR, and Predictable Loss.

The fixed pool has token0=WETH (18 decimals), token1=USDT (6 decimals), so
human prices are USDT per WETH.  Fees and gas deliberately do not enter any
formula in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


Q96 = float(2**96)
TICK_BASE = 1.0001
TOKEN_DECIMAL_PRICE_SCALE = 1e12
RAW_LIQUIDITY_TO_HUMAN = 1e-12
SECONDS_PER_DAY = 86_400.0


def tick_to_price(tick: Any) -> np.ndarray | float:
    """Convert a raw Uniswap tick to human USDT/WETH price."""

    result = np.power(TICK_BASE, np.asarray(tick, dtype=np.float64))
    result *= TOKEN_DECIMAL_PRICE_SCALE
    return float(result) if result.ndim == 0 else result


def sqrt_price_x96_to_price(sqrt_price_x96: Any) -> np.ndarray | float:
    """Convert sqrtPriceX96 to human USDT/WETH price without tick rounding."""

    values = np.asarray(sqrt_price_x96, dtype=np.float64)
    result = np.square(values / Q96) * TOKEN_DECIMAL_PRICE_SCALE
    if not np.isfinite(result).all() or np.any(result <= 0):
        raise ValueError("sqrt_price_x96 produced a non-positive or non-finite price")
    return float(result) if result.ndim == 0 else result


def human_liquidity(liquidity_raw: Any) -> np.ndarray | float:
    """Convert raw V3 liquidity to the WETH/USDT human-unit convention."""

    result = np.asarray(liquidity_raw, dtype=np.float64) * RAW_LIQUIDITY_TO_HUMAN
    if not np.isfinite(result).all() or np.any(result <= 0):
        raise ValueError("liquidity must be positive and finite")
    return float(result) if result.ndim == 0 else result


def inventory_from_price(
    price: Any,
    lower_price: float,
    upper_price: float,
    liquidity: float,
) -> tuple[np.ndarray | float, np.ndarray | float]:
    """Return fee-exclusive WETH and USDT inventory at an internal price."""

    if not 0 < lower_price < upper_price:
        raise ValueError("price bounds must satisfy 0 < lower < upper")
    if not np.isfinite(liquidity) or liquidity <= 0:
        raise ValueError("liquidity must be positive and finite")
    values = np.asarray(price, dtype=np.float64)
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("prices must be positive and finite")
    bounded = np.clip(values, lower_price, upper_price)
    root = np.sqrt(bounded)
    amount0 = liquidity * (1.0 / root - 1.0 / np.sqrt(upper_price))
    amount1 = liquidity * (root - np.sqrt(lower_price))
    if values.ndim == 0:
        return float(amount0), float(amount1)
    return amount0, amount1


def value_at_internal_price(
    price: Any,
    lower_price: float,
    upper_price: float,
    liquidity: float,
) -> np.ndarray | float:
    """Return the concave, fee-exclusive LP value function V(P)."""

    amount0, amount1 = inventory_from_price(
        price, lower_price, upper_price, liquidity
    )
    result = np.asarray(amount0) * np.asarray(price, dtype=np.float64) + np.asarray(
        amount1
    )
    return float(result) if result.ndim == 0 else result


def lvr_step(
    previous_pool_price: Any,
    pool_price: Any,
    external_price: Any,
    lower_price: float,
    upper_price: float,
    liquidity: float,
) -> np.ndarray | float:
    """External-price self-financing rebalancing gap for pool inventory trades.

    The output uses the loss-positive LVR convention.  It is intentionally not
    clipped: observed pool/CEX basis and discrete event timing can produce a
    negative empirical step even though ideal-model LVR is non-negative.
    """

    before0, before1 = inventory_from_price(
        previous_pool_price, lower_price, upper_price, liquidity
    )
    after0, after1 = inventory_from_price(
        pool_price, lower_price, upper_price, liquidity
    )
    result = -(
        np.asarray(external_price, dtype=np.float64)
        * (np.asarray(after0) - np.asarray(before0))
        + (np.asarray(after1) - np.asarray(before1))
    )
    return float(result) if result.ndim == 0 else result


def convexity_cost(
    previous_pool_price: Any,
    pool_price: Any,
    lower_price: float,
    upper_price: float,
    liquidity: float,
    *,
    relative_tolerance: float = 1e-11,
) -> np.ndarray | float:
    """Exact discrete Predictable-Loss convexity cost.

    Computes V(P0) + x(P0) * (P1 - P0) - V(P1).  A stable closed form is used
    when both prices are inside the range, and exactly linear same-side moves
    return zero.  Only floating-point negatives within ``relative_tolerance``
    are set to zero; a material violation raises.
    """

    p0, p1 = np.broadcast_arrays(
        np.asarray(previous_pool_price, dtype=np.float64),
        np.asarray(pool_price, dtype=np.float64),
    )
    if (
        not np.isfinite(p0).all()
        or not np.isfinite(p1).all()
        or np.any(p0 <= 0)
        or np.any(p1 <= 0)
    ):
        raise ValueError("prices must be positive and finite")

    v0 = np.asarray(
        value_at_internal_price(p0, lower_price, upper_price, liquidity)
    )
    v1 = np.asarray(value_at_internal_price(p1, lower_price, upper_price, liquidity))
    x0, _ = inventory_from_price(p0, lower_price, upper_price, liquidity)
    result = v0 + np.asarray(x0) * (p1 - p0) - v1

    both_inside = (
        (p0 >= lower_price)
        & (p0 <= upper_price)
        & (p1 >= lower_price)
        & (p1 <= upper_price)
    )
    stable_inside = (
        liquidity
        * np.square(np.sqrt(p1) - np.sqrt(p0))
        / np.sqrt(p0)
    )
    result = np.where(both_inside, stable_inside, result)
    same_below = (p0 <= lower_price) & (p1 <= lower_price)
    same_above = (p0 >= upper_price) & (p1 >= upper_price)
    result = np.where(same_below | same_above, 0.0, result)

    scale = np.maximum.reduce((np.abs(v0), np.abs(v1), np.ones_like(v0)))
    materially_negative = result < -(relative_tolerance * scale)
    if np.any(materially_negative):
        minimum = float(np.min(result[materially_negative]))
        raise ArithmeticError(f"Predictable-Loss convexity cost is negative: {minimum}")
    result = np.where(result < 0, 0.0, result)
    return float(result) if result.ndim == 0 else result


@dataclass(frozen=True)
class SofrCurve:
    """ACT/360 gross-factor curve built from effective-date daily SOFR.

    Each published daily quote defines a one-day gross factor ``1 + r/360``.
    Fractional days use the corresponding fractional power.  This provides a
    deterministic cumulative log-factor that can be evaluated vectorially.
    """

    dates_ns: np.ndarray
    annual_rates: np.ndarray
    cumulative_log_at_midnight: np.ndarray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "SofrCurve":
        required = {"date", "sofr_percent"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"SOFR frame is missing columns: {sorted(missing)}")
        data = frame.loc[:, ["date", "sofr_percent"]].copy()
        data["date"] = pd.to_datetime(data["date"], utc=True).dt.floor("D")
        data["sofr_percent"] = pd.to_numeric(data["sofr_percent"])
        data = data.sort_values("date", kind="stable").drop_duplicates(
            "date", keep="last"
        )
        if data.empty or data.isna().any().any():
            raise ValueError("SOFR frame must be non-empty and complete")
        expected = pd.date_range(data["date"].iloc[0], data["date"].iloc[-1], freq="D")
        if not pd.DatetimeIndex(data["date"]).equals(expected):
            raise ValueError("SOFR frame must be a dense UTC calendar-day series")
        annual = data["sofr_percent"].to_numpy(dtype=np.float64) / 100.0
        if not np.isfinite(annual).all() or np.any(annual <= -360.0):
            raise ValueError("SOFR rates are invalid")
        daily_logs = np.log1p(annual / 360.0)
        cumulative = np.concatenate(([0.0], np.cumsum(daily_logs)))
        dates_ns = pd.DatetimeIndex(data["date"]).as_unit("ns").asi8
        return cls(dates_ns, annual, cumulative)

    @property
    def first_date(self) -> pd.Timestamp:
        return pd.Timestamp(int(self.dates_ns[0]), tz="UTC")

    @property
    def last_date(self) -> pd.Timestamp:
        return pd.Timestamp(int(self.dates_ns[-1]), tz="UTC")

    def accumulated_log(self, timestamps: Any) -> np.ndarray | float:
        values = pd.to_datetime(np.atleast_1d(timestamps), utc=True)
        ns = values.as_unit("ns").asi8
        result = self.accumulated_log_ns(ns)
        if np.asarray(timestamps).ndim == 0:
            return float(result[0])
        return result

    def accumulated_log_ns(self, timestamps_ns: Any) -> np.ndarray:
        """Vectorized cumulative log factor for UTC nanosecond integers."""

        ns = np.atleast_1d(np.asarray(timestamps_ns, dtype=np.int64))
        day_length_ns = int(SECONDS_PER_DAY * 1e9)
        day_ns = (ns // day_length_ns) * day_length_ns
        positions = np.searchsorted(self.dates_ns, day_ns)
        valid = (positions < len(self.dates_ns)) & (
            self.dates_ns[np.minimum(positions, len(self.dates_ns) - 1)] == day_ns
        )
        if not valid.all():
            bad = pd.Timestamp(int(ns[~valid][0]), tz="UTC")
            raise ValueError(f"SOFR curve does not cover {bad}")
        fractions = (ns - day_ns) / day_length_ns
        daily_logs = np.log1p(self.annual_rates[positions] / 360.0)
        result = self.cumulative_log_at_midnight[positions] + fractions * daily_logs
        return result

    def gross_factor(self, start: Any, end: Any) -> np.ndarray | float:
        start_log = np.asarray(self.accumulated_log(start), dtype=np.float64)
        end_log = np.asarray(self.accumulated_log(end), dtype=np.float64)
        if np.any(end_log < start_log - 1e-15):
            raise ValueError("gross-factor end precedes start")
        result = np.exp(end_log - start_log)
        return float(result) if result.ndim == 0 else result

    def rates_for_dates(self, dates: Any) -> np.ndarray:
        values = pd.DatetimeIndex(pd.to_datetime(dates, utc=True)).floor("D")
        values_ns = values.as_unit("ns").asi8
        positions = np.searchsorted(self.dates_ns, values_ns)
        if np.any(positions >= len(self.dates_ns)) or np.any(
            self.dates_ns[np.minimum(positions, len(self.dates_ns) - 1)] != values_ns
        ):
            raise ValueError("requested dates fall outside the SOFR curve")
        return self.annual_rates[positions] * 100.0
