"""End-to-end event-driven construction of IL, LVR, and Predictable Loss."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .formulas import (
    SofrCurve,
    concavity_gap,
    human_liquidity,
    inventory_from_price,
    lvr_step,
    tick_to_price,
)
from .io import (
    NANOSECONDS_PER_SECOND,
    PartitionedOracle,
    SwapPath,
    encode_event_order,
    load_sofr_artifact,
    load_swap_path,
    sha256_file,
)


SECONDS_PER_DAY = 86_400
QVAR_FREQUENCIES = {"1s": 1, "5s": 5, "1m": 60}
FORMULA_VERSION = "il-lvr-pl-v1"
EXPECTED_POSITION_COUNT = 10_795
EXPECTED_STRICT_COUNT = 10_718
EXPECTED_REPRESENTATIVE_IDS = [
    "be54851eff87afe564b42729c5128af613662647d4597c6d903d841ca595a7cb",
    "05345cb10258b7f2eb935b0f328c253c175de7db6a9bc4f417972d186ec043e3",
    "02ab86f1afe5b84ba68eb5dd039d106c24d3985b7e003d5558f0bd1493696625",
    "9fa31bad04448caea02948722f424804d20e3ddc0cf514594fb9f389b71ea3ec",
]


@dataclass(frozen=True)
class RiskArtifacts:
    output_root: Path
    position_metrics: Path
    portfolio_daily: Path
    representative_positions: Path
    representative_paths: Path
    manifest: Path


@dataclass(frozen=True)
class PositionSteps:
    start: int
    end: int
    entry_pool_price: float
    pool_prices: np.ndarray
    timestamps_ns: np.ndarray
    lvr_steps: np.ndarray
    pl_core_steps: np.ndarray
    lvr_prefix: np.ndarray
    core_prefix: np.ndarray
    discounted_core_prefix: np.ndarray


def _numeric_pairs(
    frame: pd.DataFrame, *, enforce_frozen_sample: bool = True
) -> pd.DataFrame:
    required = {
        "operation_id",
        "tick_lower",
        "tick_upper",
        "liquidity_raw",
        "entry_block_number",
        "entry_timestamp",
        "entry_transaction_index",
        "entry_log_index",
        "entry_amount0_raw",
        "entry_amount1_raw",
        "exit_block_number",
        "exit_timestamp",
        "exit_transaction_index",
        "exit_log_index",
        "exit_amount0_raw",
        "exit_amount1_raw",
        "price_timestamp_entry",
        "price_timestamp_exit",
        "token0_price_usdt_entry",
        "token0_price_usdt_exit",
        "initial_wealth_usdt",
        "principal_exit_value_usdt",
        "hodl_exit_value_usdt",
        "holding_seconds",
        "is_strict_pair",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"pair-return input is missing columns: {sorted(missing)}")
    result = frame.copy().reset_index(drop=True)
    if enforce_frozen_sample and len(result) != EXPECTED_POSITION_COUNT:
        raise ValueError(
            f"expected {EXPECTED_POSITION_COUNT} primary pairs, found {len(result)}"
        )
    if result["operation_id"].duplicated().any():
        raise ValueError("operation IDs are not unique")
    if enforce_frozen_sample and int(result["is_strict_pair"].sum()) != EXPECTED_STRICT_COUNT:
        raise ValueError("strict-pair count does not match the frozen sample")
    for column in (
        "liquidity_raw",
        "entry_amount0_raw",
        "entry_amount1_raw",
        "exit_amount0_raw",
        "exit_amount1_raw",
        "token0_price_usdt_entry",
        "token0_price_usdt_exit",
        "initial_wealth_usdt",
        "principal_exit_value_usdt",
        "hodl_exit_value_usdt",
    ):
        result[f"_{column}"] = pd.to_numeric(result[column], errors="raise")
    result["entry_timestamp"] = pd.to_datetime(result["entry_timestamp"], utc=True)
    result["exit_timestamp"] = pd.to_datetime(result["exit_timestamp"], utc=True)
    result["price_timestamp_entry"] = pd.to_datetime(
        result["price_timestamp_entry"], utc=True
    )
    result["price_timestamp_exit"] = pd.to_datetime(
        result["price_timestamp_exit"], utc=True
    )
    if not (
        result["price_timestamp_entry"]
        == result["entry_timestamp"] - pd.Timedelta(seconds=1)
    ).all() or not (
        result["price_timestamp_exit"]
        == result["exit_timestamp"] - pd.Timedelta(seconds=1)
    ).all():
        raise ValueError("entry/exit prices are not strict-prior one-second marks")
    if not (result["entry_timestamp"] < result["exit_timestamp"]).all():
        raise ValueError("all primary positions must have positive holding time")
    return result


def _position_steps(
    row: pd.Series, swaps: SwapPath, swap_discount_factors: np.ndarray
) -> PositionSteps:
    entry_key = encode_event_order(
        row["entry_block_number"],
        row["entry_transaction_index"],
        row["entry_log_index"],
    )
    exit_key = encode_event_order(
        row["exit_block_number"],
        row["exit_transaction_index"],
        row["exit_log_index"],
    )
    start, end = swaps.bounds(entry_key, exit_key)
    entry_pool_price = swaps.state_before(entry_key)
    pool_prices = swaps.pool_prices[start:end]
    timestamps_ns = swaps.timestamps_ns[start:end]
    if len(pool_prices):
        previous = np.empty_like(pool_prices)
        previous[0] = entry_pool_price
        previous[1:] = pool_prices[:-1]
        lower = float(tick_to_price(row["tick_lower"]))
        upper = float(tick_to_price(row["tick_upper"]))
        liquidity = float(human_liquidity(row["_liquidity_raw"]))
        lvr_steps = np.asarray(
            lvr_step(
                previous,
                pool_prices,
                swaps.external_prices[start:end],
                lower,
                upper,
                liquidity,
            )
        )
        core_steps = np.asarray(
            concavity_gap(previous, pool_prices, lower, upper, liquidity)
        )
        lvr_prefix = np.cumsum(lvr_steps)
        core_prefix = np.cumsum(core_steps)
        discounted_prefix = np.cumsum(
            core_steps * swap_discount_factors[start:end]
        )
    else:
        lvr_steps = core_steps = np.empty(0, dtype=np.float64)
        lvr_prefix = core_prefix = discounted_prefix = np.empty(0, dtype=np.float64)
    return PositionSteps(
        start=start,
        end=end,
        entry_pool_price=entry_pool_price,
        pool_prices=pool_prices,
        timestamps_ns=timestamps_ns,
        lvr_steps=lvr_steps,
        pl_core_steps=core_steps,
        lvr_prefix=lvr_prefix,
        core_prefix=core_prefix,
        discounted_core_prefix=discounted_prefix,
    )


def _prefix_value(prefix: np.ndarray, counts: np.ndarray | int) -> np.ndarray:
    values = np.asarray(counts, dtype=np.int64)
    result = np.zeros_like(values, dtype=np.float64)
    positive = values > 0
    if positive.any():
        result[positive] = prefix[values[positive] - 1]
    return result


def _build_position_days(pairs: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    rows: list[dict[str, Any]] = []
    offsets = np.zeros(len(pairs) + 1, dtype=np.int64)
    for index, row in pairs.iterrows():
        entry = pd.Timestamp(row["entry_timestamp"])
        exit_time = pd.Timestamp(row["exit_timestamp"])
        first_day = entry.floor("D")
        last_day = (exit_time - pd.Timedelta(nanoseconds=1)).floor("D")
        for day in pd.date_range(first_day, last_day, freq="D"):
            day_end = day + pd.Timedelta(days=1)
            snapshot = min(exit_time, day_end)
            rows.append(
                {
                    "position_index": index,
                    "date": day,
                    "snapshot_timestamp": snapshot,
                    "is_terminal": snapshot == exit_time,
                }
            )
        offsets[index + 1] = len(rows)
    return pd.DataFrame(rows), offsets


def calculate_lifetime_and_daily(
    pairs: pd.DataFrame,
    swaps: SwapPath,
    oracle: PartitionedOracle,
    sofr: SofrCurve,
    *,
    enforce_frozen_sample: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate primary lifetime metrics and capital-weighted position days."""

    positions = _numeric_pairs(pairs, enforce_frozen_sample=enforce_frozen_sample)
    day_rows, day_offsets = _build_position_days(positions)
    day_rows["external_price_usdt"] = oracle.lookup_strict_prior(
        pd.DatetimeIndex(day_rows["snapshot_timestamp"])
    )
    day_count = len(day_rows)
    day_lp_value = np.empty(day_count, dtype=np.float64)
    day_hodl_value = np.empty(day_count, dtype=np.float64)
    day_lvr = np.empty(day_count, dtype=np.float64)
    day_core = np.empty(day_count, dtype=np.float64)
    day_pl = np.empty(day_count, dtype=np.float64)
    swap_discount_factors = np.exp(-sofr.accumulated_log_ns(swaps.timestamps_ns))

    lifetime_columns = {
        name: np.empty(len(positions), dtype=np.float64)
        for name in (
            "pool_price_entry_usdt",
            "pool_price_exit_usdt",
            "theoretical_entry_weth",
            "theoretical_entry_usdt",
            "theoretical_exit_weth",
            "theoretical_exit_usdt",
            "entry_inventory_reconciliation_usdt",
            "exit_inventory_reconciliation_usdt",
            "il_signed_vs_hodl",
            "il_loss_usdt",
            "il_loss_on_initial",
            "lvr_rebalancing_usdt",
            "lvr_rebalancing_on_initial",
            "pl_core_convexity_usdt",
            "pl_opportunity_cost_usdt",
            "pl_loss_usdt",
            "pl_signed_usdt",
            "pl_loss_on_initial",
        )
    }
    deposit_weth = positions["_entry_amount0_raw"].to_numpy(np.float64) / 1e18
    deposit_usdt = positions["_entry_amount1_raw"].to_numpy(np.float64) / 1e6
    principal_weth = positions["_exit_amount0_raw"].to_numpy(np.float64) / 1e18
    principal_usdt = positions["_exit_amount1_raw"].to_numpy(np.float64) / 1e6
    initial = positions["_initial_wealth_usdt"].to_numpy(np.float64)
    terminal_principal = positions["_principal_exit_value_usdt"].to_numpy(np.float64)
    terminal_hodl = positions["_hodl_exit_value_usdt"].to_numpy(np.float64)
    if np.any(initial <= 0) or np.any(terminal_hodl <= 0):
        raise ValueError("initial and HODL values must be positive")

    for index, row in positions.iterrows():
        steps = _position_steps(row, swaps, swap_discount_factors)
        lower = float(tick_to_price(row["tick_lower"]))
        upper = float(tick_to_price(row["tick_upper"]))
        liquidity = float(human_liquidity(row["_liquidity_raw"]))
        exit_key = encode_event_order(
            row["exit_block_number"],
            row["exit_transaction_index"],
            row["exit_log_index"],
        )
        exit_pool_price = swaps.state_before(exit_key)
        theoretical_entry = inventory_from_price(
            steps.entry_pool_price, lower, upper, liquidity
        )
        theoretical_exit = inventory_from_price(exit_pool_price, lower, upper, liquidity)
        lifetime_columns["pool_price_entry_usdt"][index] = steps.entry_pool_price
        lifetime_columns["pool_price_exit_usdt"][index] = exit_pool_price
        lifetime_columns["theoretical_entry_weth"][index] = theoretical_entry[0]
        lifetime_columns["theoretical_entry_usdt"][index] = theoretical_entry[1]
        lifetime_columns["theoretical_exit_weth"][index] = theoretical_exit[0]
        lifetime_columns["theoretical_exit_usdt"][index] = theoretical_exit[1]
        entry_price = float(row["_token0_price_usdt_entry"])
        exit_price = float(row["_token0_price_usdt_exit"])
        lifetime_columns["entry_inventory_reconciliation_usdt"][index] = (
            (theoretical_entry[0] - deposit_weth[index]) * entry_price
            + theoretical_entry[1]
            - deposit_usdt[index]
        )
        lifetime_columns["exit_inventory_reconciliation_usdt"][index] = (
            (theoretical_exit[0] - principal_weth[index]) * exit_price
            + theoretical_exit[1]
            - principal_usdt[index]
        )
        il_loss = terminal_hodl[index] - terminal_principal[index]
        lifetime_columns["il_signed_vs_hodl"][index] = -il_loss / terminal_hodl[index]
        lifetime_columns["il_loss_usdt"][index] = il_loss
        lifetime_columns["il_loss_on_initial"][index] = il_loss / initial[index]
        lvr_total = float(steps.lvr_prefix[-1]) if len(steps.lvr_prefix) else 0.0
        core_total = float(steps.core_prefix[-1]) if len(steps.core_prefix) else 0.0
        if len(steps.discounted_core_prefix):
            exit_accumulated = float(sofr.accumulated_log(row["exit_timestamp"]))
            pl_total = float(
                np.exp(exit_accumulated) * steps.discounted_core_prefix[-1]
            )
        else:
            pl_total = 0.0
        opportunity = pl_total - core_total
        if opportunity < 0 and abs(opportunity) <= 1e-10 * max(core_total, 1.0):
            opportunity = 0.0
            pl_total = core_total
        lifetime_columns["lvr_rebalancing_usdt"][index] = lvr_total
        lifetime_columns["lvr_rebalancing_on_initial"][index] = lvr_total / initial[index]
        lifetime_columns["pl_core_convexity_usdt"][index] = core_total
        lifetime_columns["pl_opportunity_cost_usdt"][index] = opportunity
        lifetime_columns["pl_loss_usdt"][index] = pl_total
        lifetime_columns["pl_signed_usdt"][index] = -pl_total
        lifetime_columns["pl_loss_on_initial"][index] = pl_total / initial[index]

        day_start = int(day_offsets[index])
        day_end = int(day_offsets[index + 1])
        day_slice = slice(day_start, day_end)
        day_part = day_rows.iloc[day_start:day_end]
        snapshots = pd.DatetimeIndex(day_part["snapshot_timestamp"])
        snapshot_ns = snapshots.as_unit("ns").asi8
        counts = np.searchsorted(steps.timestamps_ns, snapshot_ns, side="left")
        terminal_mask = day_part["is_terminal"].to_numpy(bool)
        counts[terminal_mask] = len(steps.timestamps_ns)
        pool_price = np.full(len(counts), steps.entry_pool_price)
        positive = counts > 0
        pool_price[positive] = steps.pool_prices[counts[positive] - 1]
        weth, usdt = inventory_from_price(pool_price, lower, upper, liquidity)
        external = day_part["external_price_usdt"].to_numpy(np.float64)
        lp_value = np.asarray(weth) * external + np.asarray(usdt)
        lp_value[terminal_mask] = (
            principal_weth[index] * external[terminal_mask]
            + principal_usdt[index]
        )
        hodl_value = deposit_weth[index] * external + deposit_usdt[index]
        lvr_values = _prefix_value(steps.lvr_prefix, counts)
        core_values = _prefix_value(steps.core_prefix, counts)
        discounted = _prefix_value(steps.discounted_core_prefix, counts)
        pl_values = np.exp(np.asarray(sofr.accumulated_log(snapshots))) * discounted
        day_lp_value[day_slice] = lp_value
        day_hodl_value[day_slice] = hodl_value
        day_lvr[day_slice] = lvr_values
        day_core[day_slice] = core_values
        day_pl[day_slice] = pl_values
        if index == 0 or (index + 1) % 1_000 == 0 or index + 1 == len(positions):
            print(f"calculated lifetime/daily metrics {index + 1:05d}/{len(positions)}")

    for name, values in lifetime_columns.items():
        positions[name] = values
    positions["pl_signed_on_initial"] = (
        positions["pl_signed_usdt"] / positions["_initial_wealth_usdt"]
    )
    positions["pl_core_convexity_on_initial"] = (
        positions["pl_core_convexity_usdt"] / positions["_initial_wealth_usdt"]
    )
    positions["pl_opportunity_cost_on_initial"] = (
        positions["pl_opportunity_cost_usdt"] / positions["_initial_wealth_usdt"]
    )
    day_rows["initial_capital_usdt"] = initial[
        day_rows["position_index"].to_numpy(np.int64)
    ]
    day_rows["il_loss_usdt"] = day_hodl_value - day_lp_value
    day_rows["lvr_rebalancing_usdt"] = day_lvr
    day_rows["pl_core_convexity_usdt"] = day_core
    day_rows["pl_loss_usdt"] = day_pl
    day_rows["pl_opportunity_cost_usdt"] = day_pl - day_core
    aggregate = (
        day_rows.groupby("date", sort=True)
        .agg(
            position_day_count=("position_index", "size"),
            initial_capital_usdt=("initial_capital_usdt", "sum"),
            il_loss_usdt=("il_loss_usdt", "sum"),
            lvr_rebalancing_usdt=("lvr_rebalancing_usdt", "sum"),
            pl_core_convexity_usdt=("pl_core_convexity_usdt", "sum"),
            pl_opportunity_cost_usdt=("pl_opportunity_cost_usdt", "sum"),
            pl_loss_usdt=("pl_loss_usdt", "sum"),
        )
        .reset_index()
    )
    for source, target in (
        ("il_loss_usdt", "capital_weighted_il_loss_pct"),
        ("lvr_rebalancing_usdt", "capital_weighted_lvr_loss_pct"),
        ("pl_core_convexity_usdt", "capital_weighted_pl_core_loss_pct"),
        ("pl_opportunity_cost_usdt", "capital_weighted_pl_opportunity_cost_pct"),
        ("pl_loss_usdt", "capital_weighted_pl_loss_pct"),
    ):
        aggregate[target] = 100.0 * aggregate[source] / aggregate["initial_capital_usdt"]
    close_events = pd.DatetimeIndex(aggregate["date"]) + pd.Timedelta(days=1)
    final_close_event = oracle.coverage_last + pd.Timedelta(seconds=1)
    close_events = pd.DatetimeIndex(
        np.minimum(close_events.as_unit("ns").asi8, final_close_event.value),
        tz="UTC",
    )
    aggregate["ethusdt_close"] = oracle.lookup_strict_prior(close_events)
    aggregate["sofr_percent"] = sofr.rates_for_dates(aggregate["date"])
    internal_columns = [column for column in positions if column.startswith("_")]
    return positions.drop(columns=internal_columns), aggregate


def calculate_qv_sensitivities(
    pairs: pd.DataFrame,
    oracle: PartitionedOracle,
    *,
    enforce_frozen_sample: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate CEX-path LVR QV approximations on 1s/5s/1m grids."""

    positions = _numeric_pairs(pairs, enforce_frozen_sample=enforce_frozen_sample)
    lower = np.asarray(tick_to_price(positions["tick_lower"].to_numpy(np.int64)))
    upper = np.asarray(tick_to_price(positions["tick_upper"].to_numpy(np.int64)))
    liquidity = np.asarray(human_liquidity(positions["_liquidity_raw"].to_numpy()))
    entry_mark_ns = (
        pd.DatetimeIndex(positions["price_timestamp_entry"]).as_unit("ns").asi8
    )
    exit_mark_ns = (
        pd.DatetimeIndex(positions["price_timestamp_exit"]).as_unit("ns").asi8
    )
    totals = {label: np.zeros(len(positions), dtype=np.float64) for label in QVAR_FREQUENCIES}
    previous_sample: dict[str, float | None] = {label: None for label in QVAR_FREQUENCIES}
    daily_close_rows: list[dict[str, Any]] = []

    month_total = len(oracle.artifacts)
    for month_number, (_, month_ns, month_price) in enumerate(
        oracle.iter_months(), start=1
    ):
        day_ns = (month_ns // (SECONDS_PER_DAY * NANOSECONDS_PER_SECOND)) * (
            SECONDS_PER_DAY * NANOSECONDS_PER_SECOND
        )
        boundaries = np.flatnonzero(np.diff(day_ns)) + 1
        starts = np.concatenate(([0], boundaries))
        ends = np.concatenate((boundaries, [len(month_ns)]))
        for start, end in zip(starts, ends):
            times = month_ns[start:end]
            prices = month_price[start:end]
            daily_close_rows.append(
                {
                    "date": pd.Timestamp(int(day_ns[start]), tz="UTC"),
                    "ethusdt_close": float(prices[-1]),
                }
            )
            for label, seconds in QVAR_FREQUENCIES.items():
                epoch_seconds = times // NANOSECONDS_PER_SECOND
                selected = epoch_seconds % seconds == 0
                current_times = times[selected]
                current_prices = prices[selected]
                if not len(current_times):
                    continue
                previous_prices = np.empty_like(current_prices)
                carry = previous_sample[label]
                previous_prices[0] = current_prices[0] if carry is None else carry
                previous_prices[1:] = current_prices[:-1]
                previous_sample[label] = float(current_prices[-1])
                base = np.square(current_prices - previous_prices) / (
                    4.0 * np.power(previous_prices, 1.5)
                )
                candidates = np.flatnonzero(
                    (entry_mark_ns < current_times[-1])
                    & (exit_mark_ns >= current_times[0])
                )
                if not len(candidates):
                    continue
                full = candidates[
                    (entry_mark_ns[candidates] < current_times[0])
                    & (exit_mark_ns[candidates] >= current_times[-1])
                ]
                partial = np.setdiff1d(candidates, full, assume_unique=True)
                if len(full):
                    order = np.argsort(previous_prices, kind="stable")
                    sorted_prices = previous_prices[order]
                    prefix = np.concatenate(([0.0], np.cumsum(base[order])))
                    lo = np.searchsorted(sorted_prices, lower[full], side="left")
                    hi = np.searchsorted(sorted_prices, upper[full], side="left")
                    totals[label][full] += liquidity[full] * (prefix[hi] - prefix[lo])
                for index in partial:
                    lo = int(
                        np.searchsorted(current_times, entry_mark_ns[index], side="right")
                    )
                    hi = int(
                        np.searchsorted(current_times, exit_mark_ns[index], side="right")
                    )
                    if hi <= lo:
                        continue
                    in_range = (previous_prices[lo:hi] >= lower[index]) & (
                        previous_prices[lo:hi] < upper[index]
                    )
                    totals[label][index] += liquidity[index] * base[lo:hi][in_range].sum()
        if month_number == 1 or month_number % 12 == 0 or month_number == month_total:
            print(f"calculated CEX QV sensitivity {month_number:02d}/{month_total} partitions")

    result = positions[["operation_id"]].copy()
    initial = positions["_initial_wealth_usdt"].to_numpy(np.float64)
    for label in QVAR_FREQUENCIES:
        result[f"lvr_qv_{label}_usdt"] = totals[label]
        result[f"lvr_qv_{label}_on_initial"] = totals[label] / initial
    market_daily = (
        pd.DataFrame(daily_close_rows)
        .sort_values("date", kind="stable")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )
    return result, market_daily


def add_expected_pl_robustness(
    positions: pd.DataFrame, market_daily: pd.DataFrame
) -> pd.DataFrame:
    result = positions.copy()
    daily = market_daily.set_index("date")["ethusdt_close"].sort_index()
    prior_sigma = np.log(daily).diff().rolling(30).std().shift(1)
    entry_dates = pd.DatetimeIndex(result["entry_timestamp"]).floor("D")
    sigma = prior_sigma.reindex(entry_dates).to_numpy(np.float64)
    entry_pool = result["pool_price_entry_usdt"].to_numpy(np.float64)
    lower = np.asarray(tick_to_price(result["tick_lower"].to_numpy(np.int64)))
    upper = np.asarray(tick_to_price(result["tick_upper"].to_numpy(np.int64)))
    applicable = (entry_pool >= lower) & (entry_pool <= upper) & np.isfinite(sigma)
    delta_lower = 2.0 * (1.0 - np.sqrt(lower / entry_pool))
    delta_upper = 2.0 * (1.0 - np.sqrt(entry_pool / upper))
    delta = delta_lower + delta_upper
    expected = np.full(len(result), np.nan)
    holding_days = result["holding_seconds"].to_numpy(np.float64) / SECONDS_PER_DAY
    expected[applicable] = (
        np.exp(-np.square(sigma[applicable]) * holding_days[applicable] / 8.0) - 1.0
    ) / delta[applicable]
    result["pre_entry_volatility_30d_daily"] = sigma
    result["expected_pl_r0_30d_applicable"] = applicable
    result["expected_pl_r0_30d_signed_on_initial"] = expected
    result["expected_pl_r0_30d_signed_usdt"] = expected * pd.to_numeric(
        result["initial_wealth_usdt"]
    ).to_numpy(np.float64)
    return result


def select_representative_positions(pairs: pd.DataFrame) -> pd.DataFrame:
    """Select ex-post bull/bear by short/long deterministic cell medoids."""

    data = pairs.copy()
    for column in (
        "initial_wealth_usdt",
        "token0_price_usdt_entry",
        "token0_price_usdt_exit",
        "holding_seconds",
    ):
        data[column] = pd.to_numeric(data[column])
    data["eth_log_return"] = np.log(
        data["token0_price_usdt_exit"] / data["token0_price_usdt_entry"]
    )
    data["log_initial_wealth"] = np.log(data["initial_wealth_usdt"])
    data["range_log_width"] = (
        data["tick_upper"] - data["tick_lower"]
    ) * np.log(1.0001)
    data["log_holding_seconds"] = np.log(data["holding_seconds"])
    life_low, life_high = data["holding_seconds"].quantile([0.25, 0.75])
    return_low, return_high = data["eth_log_return"].quantile([0.25, 0.75])
    features = (
        "log_initial_wealth",
        "range_log_width",
        "log_holding_seconds",
        "eth_log_return",
    )
    selected: list[pd.Series] = []
    for regime, regime_mask in (
        ("bull", data["eth_log_return"] >= return_high),
        ("bear", data["eth_log_return"] <= return_low),
    ):
        for lifetime, lifetime_mask in (
            ("short", data["holding_seconds"] <= life_low),
            ("long", data["holding_seconds"] >= life_high),
        ):
            candidates = data.loc[regime_mask & lifetime_mask].copy()
            score = np.zeros(len(candidates), dtype=np.float64)
            for feature in features:
                median = candidates[feature].median()
                iqr = candidates[feature].quantile(0.75) - candidates[feature].quantile(
                    0.25
                )
                if iqr > 0:
                    score += np.square((candidates[feature].to_numpy() - median) / iqr)
            candidates["medoid_score"] = score
            chosen = candidates.sort_values(
                ["medoid_score", "operation_id"], kind="stable"
            ).iloc[0].copy()
            chosen["market_regime"] = regime
            chosen["lifetime_bucket"] = lifetime
            chosen["candidate_count"] = len(candidates)
            chosen["lifetime_q25_seconds"] = life_low
            chosen["lifetime_q75_seconds"] = life_high
            chosen["eth_log_return_q25"] = return_low
            chosen["eth_log_return_q75"] = return_high
            selected.append(chosen)
    columns = [
        "operation_id",
        "market_regime",
        "lifetime_bucket",
        "candidate_count",
        "medoid_score",
        "entry_timestamp",
        "exit_timestamp",
        "holding_seconds",
        "initial_wealth_usdt",
        "tick_lower",
        "tick_upper",
        "token0_price_usdt_entry",
        "token0_price_usdt_exit",
        "eth_log_return",
        "is_strict_pair",
        "lifetime_q25_seconds",
        "lifetime_q75_seconds",
        "eth_log_return_q25",
        "eth_log_return_q75",
    ]
    return pd.DataFrame(selected).loc[:, columns].reset_index(drop=True)


def build_representative_paths(
    pairs: pd.DataFrame,
    representatives: pd.DataFrame,
    swaps: SwapPath,
    oracle: PartitionedOracle,
    sofr: SofrCurve,
    *,
    enforce_frozen_sample: bool = True,
) -> pd.DataFrame:
    numeric = _numeric_pairs(
        pairs, enforce_frozen_sample=enforce_frozen_sample
    ).set_index("operation_id", drop=False)
    swap_discount_factors = np.exp(-sofr.accumulated_log_ns(swaps.timestamps_ns))
    paths: list[pd.DataFrame] = []
    for representative in representatives.itertuples(index=False):
        row = numeric.loc[representative.operation_id]
        steps = _position_steps(row, swaps, swap_discount_factors)
        entry = pd.Timestamp(row["entry_timestamp"])
        exit_time = pd.Timestamp(row["exit_timestamp"])
        frequency = "1s" if row["holding_seconds"] <= SECONDS_PER_DAY else "1min"
        grid = pd.date_range(entry.ceil(frequency), exit_time.floor(frequency), freq=frequency)
        grid_frame = pd.DataFrame(
            {"timestamp": grid, "row_kind": "grid", "step_count": 0}
        )
        grid_frame["step_count"] = np.searchsorted(
            steps.timestamps_ns, grid.as_unit("ns").asi8, side="right"
        )
        swap_frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(steps.timestamps_ns, utc=True),
                "row_kind": "swap",
                "step_count": np.arange(1, len(steps.timestamps_ns) + 1),
                "block_number": swaps.block_numbers[steps.start : steps.end],
                "transaction_index": swaps.transaction_indices[steps.start : steps.end],
                "log_index": swaps.log_indices[steps.start : steps.end],
            }
        )
        endpoint_frame = pd.DataFrame(
            {
                "timestamp": [entry, exit_time],
                "row_kind": ["entry", "exit"],
                "step_count": [0, len(steps.timestamps_ns)],
            }
        )
        path = pd.concat([endpoint_frame, grid_frame, swap_frame], ignore_index=True)
        kind_order = path["row_kind"].map(
            {"entry": 0, "swap": 1, "grid": 2, "exit": 3}
        )
        path = (
            path.assign(_kind_order=kind_order)
            .sort_values(
                [
                    "timestamp",
                    "_kind_order",
                    "block_number",
                    "transaction_index",
                    "log_index",
                ],
                kind="stable",
                na_position="last",
            )
            .drop(columns="_kind_order")
            .reset_index(drop=True)
        )
        external = oracle.lookup_strict_prior(pd.DatetimeIndex(path["timestamp"]))
        counts = path["step_count"].to_numpy(np.int64)
        pool_price = np.full(len(path), steps.entry_pool_price)
        positive = counts > 0
        pool_price[positive] = steps.pool_prices[counts[positive] - 1]
        lower = float(tick_to_price(row["tick_lower"]))
        upper = float(tick_to_price(row["tick_upper"]))
        liquidity = float(human_liquidity(row["_liquidity_raw"]))
        weth, usdt = inventory_from_price(pool_price, lower, upper, liquidity)
        weth = np.asarray(weth)
        usdt = np.asarray(usdt)
        lp_value = weth * external + usdt
        deposit_weth = float(row["_entry_amount0_raw"]) / 1e18
        deposit_usdt = float(row["_entry_amount1_raw"]) / 1e6
        principal_weth = float(row["_exit_amount0_raw"]) / 1e18
        principal_usdt = float(row["_exit_amount1_raw"]) / 1e6
        entry_mask = path["row_kind"].eq("entry").to_numpy()
        exit_mask = path["row_kind"].eq("exit").to_numpy()
        weth[entry_mask] = deposit_weth
        usdt[entry_mask] = deposit_usdt
        weth[exit_mask] = principal_weth
        usdt[exit_mask] = principal_usdt
        lp_value[entry_mask] = deposit_weth * external[entry_mask] + deposit_usdt
        lp_value[exit_mask] = principal_weth * external[exit_mask] + principal_usdt
        hodl = deposit_weth * external + deposit_usdt
        lvr = _prefix_value(steps.lvr_prefix, counts)
        core = _prefix_value(steps.core_prefix, counts)
        discounted = _prefix_value(steps.discounted_core_prefix, counts)
        pl = np.exp(
            np.asarray(sofr.accumulated_log(pd.DatetimeIndex(path["timestamp"])))
        ) * discounted
        initial = float(row["_initial_wealth_usdt"])
        path["operation_id"] = representative.operation_id
        path["market_regime"] = representative.market_regime
        path["lifetime_bucket"] = representative.lifetime_bucket
        path["external_ethusdt"] = external
        path["pool_price_usdt"] = pool_price
        path["range_lower_usdt"] = lower
        path["range_upper_usdt"] = upper
        path["position_weth"] = weth
        path["position_usdt"] = usdt
        path["lp_intrinsic_value_usdt"] = lp_value
        path["hodl_value_usdt"] = hodl
        path["il_signed_vs_hodl"] = (lp_value - hodl) / hodl
        path["il_loss_on_initial"] = (hodl - lp_value) / initial
        path["lvr_rebalancing_usdt"] = lvr
        path["lvr_rebalancing_on_initial"] = lvr / initial
        path["pl_core_convexity_usdt"] = core
        path["pl_opportunity_cost_usdt"] = pl - core
        path["pl_loss_usdt"] = pl
        path["pl_loss_on_initial"] = pl / initial
        paths.append(path)
    return pd.concat(paths, ignore_index=True)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    partial = path.with_suffix(f"{path.suffix}.partial")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, partial, compression="zstd", row_group_size=131_072)
    partial.replace(path)


def validate_risk_outputs(
    positions: pd.DataFrame,
    portfolio_daily: pd.DataFrame,
    representatives: pd.DataFrame,
    representative_paths: pd.DataFrame,
) -> None:
    """Fail before writing when frozen-sample identities or accounting fail."""

    if len(positions) != EXPECTED_POSITION_COUNT or positions["operation_id"].duplicated().any():
        raise RuntimeError("position output does not preserve the frozen primary sample")
    if int(positions["is_strict_pair"].sum()) != EXPECTED_STRICT_COUNT:
        raise RuntimeError("position output strict-sample count changed")
    finite_columns = [
        "il_loss_on_initial",
        "lvr_rebalancing_on_initial",
        "lvr_qv_1s_on_initial",
        "lvr_qv_5s_on_initial",
        "lvr_qv_1m_on_initial",
        "pl_core_convexity_on_initial",
        "pl_opportunity_cost_on_initial",
        "pl_loss_on_initial",
    ]
    if not np.isfinite(positions[finite_columns].to_numpy(np.float64)).all():
        raise RuntimeError("primary risk outputs contain non-finite values")
    if (positions["pl_core_convexity_usdt"] < 0).any() or any(
        (positions[column] < 0).any()
        for column in ("lvr_qv_1s_usdt", "lvr_qv_5s_usdt", "lvr_qv_1m_usdt")
    ):
        raise RuntimeError("non-negative theoretical components became negative")
    if not np.allclose(
        positions["pl_loss_usdt"],
        positions["pl_core_convexity_usdt"]
        + positions["pl_opportunity_cost_usdt"],
        rtol=1e-12,
        atol=1e-10,
    ) or not np.allclose(
        positions["pl_signed_usdt"], -positions["pl_loss_usdt"], rtol=0, atol=0
    ):
        raise RuntimeError("Predictable-Loss decomposition or sign identity failed")
    if representatives["operation_id"].tolist() != EXPECTED_REPRESENTATIVE_IDS:
        raise RuntimeError("deterministic representative-position selection changed")
    terminal = representative_paths.loc[
        representative_paths["row_kind"] == "exit",
        [
            "operation_id",
            "il_loss_on_initial",
            "lvr_rebalancing_on_initial",
            "pl_loss_on_initial",
        ],
    ].set_index("operation_id")
    expected = positions.set_index("operation_id").loc[
        EXPECTED_REPRESENTATIVE_IDS,
        [
            "il_loss_on_initial",
            "lvr_rebalancing_on_initial",
            "pl_loss_on_initial",
        ],
    ]
    if not np.allclose(
        terminal.loc[expected.index].to_numpy(np.float64),
        expected.to_numpy(np.float64),
        rtol=1e-12,
        atol=1e-12,
    ):
        raise RuntimeError("representative terminal paths do not match lifetime output")
    denominator = portfolio_daily["initial_capital_usdt"].to_numpy(np.float64)
    for source, target in (
        ("il_loss_usdt", "capital_weighted_il_loss_pct"),
        ("lvr_rebalancing_usdt", "capital_weighted_lvr_loss_pct"),
        ("pl_core_convexity_usdt", "capital_weighted_pl_core_loss_pct"),
        ("pl_opportunity_cost_usdt", "capital_weighted_pl_opportunity_cost_pct"),
        ("pl_loss_usdt", "capital_weighted_pl_loss_pct"),
    ):
        if not np.allclose(
            portfolio_daily[target],
            100.0 * portfolio_daily[source] / denominator,
            rtol=1e-12,
            atol=1e-12,
        ):
            raise RuntimeError(f"daily capital-weighted identity failed for {target}")


def _git_revision(repository_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def build_risk_metrics(
    data_root: Path,
    *,
    output_root: Path | None = None,
    repository_root: Path | None = None,
) -> RiskArtifacts:
    """Build all versioned risk outputs for the frozen WETH/USDT sample."""

    data_root = Path(data_root)
    output_root = Path(output_root or data_root / "derived" / "risk_metrics" / "v1")
    output_root.mkdir(parents=True, exist_ok=True)
    pair_path = data_root / "derived" / "returns" / "non_same_block_pair_returns.parquet"
    pool_event_root = data_root / "processed" / "pool_events"
    oracle_root = data_root / "external" / "oracle" / "binance_ethusdt_1s"
    sofr_root = data_root / "external" / "rates" / "sofr_daily"
    pairs = pd.read_parquet(pair_path)
    oracle = PartitionedOracle(oracle_root)
    sofr_frame, sofr_manifest = load_sofr_artifact(sofr_root)
    sofr = SofrCurve.from_frame(sofr_frame)
    print("loading exact pool Swap path and strict-prior Binance marks")
    swaps = load_swap_path(pool_event_root, oracle)
    print("calculating realized IL/LVR/PL lifetime and daily paths")
    positions, portfolio_daily = calculate_lifetime_and_daily(
        pairs, swaps, oracle, sofr
    )
    print("calculating 1s/5s/1m CEX quadratic-variation sensitivities")
    qv, market_daily = calculate_qv_sensitivities(pairs, oracle)
    positions = positions.merge(qv, on="operation_id", how="left", validate="one_to_one")
    positions = add_expected_pl_robustness(positions, market_daily)
    representatives = select_representative_positions(positions)
    representative_paths = build_representative_paths(
        positions, representatives, swaps, oracle, sofr
    )
    validate_risk_outputs(
        positions, portfolio_daily, representatives, representative_paths
    )
    print("writing versioned risk-metric artifacts")

    paths = RiskArtifacts(
        output_root=output_root,
        position_metrics=output_root / "position_lifetime_metrics.parquet",
        portfolio_daily=output_root / "capital_weighted_position_daily.parquet",
        representative_positions=output_root / "representative_positions.parquet",
        representative_paths=output_root / "representative_position_paths.parquet",
        manifest=output_root / "run_manifest.json",
    )
    _atomic_parquet(positions, paths.position_metrics)
    _atomic_parquet(portfolio_daily, paths.portfolio_daily)
    _atomic_parquet(representatives, paths.representative_positions)
    _atomic_parquet(representative_paths, paths.representative_paths)
    repository_root = Path(repository_root or Path(__file__).resolve().parents[3])
    dataset_manifest = data_root / "manifest.json"
    if not dataset_manifest.exists():
        dataset_manifest = repository_root / "data" / "manifest.json"
    artifacts = []
    for path in (
        paths.position_metrics,
        paths.portfolio_daily,
        paths.representative_positions,
        paths.representative_paths,
    ):
        parquet = pq.ParquetFile(path)
        artifacts.append(
            {
                "path": path.name,
                "rows": parquet.metadata.num_rows,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "formula_version": FORMULA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_revision": _git_revision(repository_root),
        "sample": {
            "source": str(pair_path.relative_to(data_root)),
            "positions": len(positions),
            "strict_positions": int(positions["is_strict_pair"].sum()),
            "same_block_excluded": True,
            "fee_identity_overlap_excluded": True,
        },
        "inputs": {
            "dataset_manifest_sha256": sha256_file(dataset_manifest),
            "pair_returns_sha256": sha256_file(pair_path),
            "oracle_manifest_sha256": oracle.manifest_sha256,
            "sofr_manifest_sha256": sofr_manifest["manifest_sha256"],
        },
        "conventions": {
            "external_price": "Binance ETHUSDT close exactly one second before event",
            "pool_price": "exact sqrt_price_x96 ordered by block/transaction/log",
            "risk_free": "SOFR effective-date calendar forward-fill, ACT/360",
            "fees": "excluded from IL, LVR, and PL",
            "gas": "excluded from IL, LVR, and PL",
            "daily_sample": "positions whose half-open lifetime overlaps UTC date; snapshot=min(exit, day-end)",
        },
        "representative_operation_ids": representatives["operation_id"].tolist(),
        "artifacts": artifacts,
    }
    partial_manifest = paths.manifest.with_suffix(".json.partial")
    partial_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    partial_manifest.replace(paths.manifest)
    return paths
