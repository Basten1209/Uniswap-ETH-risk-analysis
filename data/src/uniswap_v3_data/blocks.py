"""Daily block and gas-regime inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd


def _decimals(frame: pd.DataFrame, column: str) -> list[Decimal]:
    if column not in frame.columns:
        return []
    return [
        Decimal(str(value))
        for value in frame[column].tolist()
        if value is not None and not pd.isna(value)
    ]


def _mean(values: list[Decimal]) -> str | None:
    return str(sum(values) / len(values)) if values else None


def _median(values: list[Decimal]) -> str | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return str(ordered[middle])
    return str((ordered[middle - 1] + ordered[middle]) / 2)


def summarize_blocks_daily(blocks: pd.DataFrame) -> pd.DataFrame:
    required = {"block_number", "block_timestamp"}
    missing = required.difference(blocks.columns)
    if missing:
        raise ValueError(f"raw blocks are missing columns: {sorted(missing)}")
    if blocks.empty:
        return pd.DataFrame()
    blocks = blocks.copy()
    blocks["block_timestamp"] = pd.to_datetime(blocks["block_timestamp"], utc=True)
    blocks["date"] = blocks["block_timestamp"].dt.date
    rows: list[dict[str, Any]] = []
    for day, group in blocks.groupby("date", sort=True):
        base_fee = _decimals(group, "base_fee_per_gas")
        gas_used = _decimals(group, "gas_used")
        gas_limit = _decimals(group, "gas_limit")
        utilization: list[Decimal] = []
        if "gas_used" in group.columns and "gas_limit" in group.columns:
            for used, limit in zip(
                group["gas_used"].tolist(), group["gas_limit"].tolist(), strict=True
            ):
                if used is None or limit is None or pd.isna(used) or pd.isna(limit):
                    continue
                used_decimal = Decimal(str(used))
                limit_decimal = Decimal(str(limit))
                if limit_decimal > 0:
                    utilization.append(used_decimal / limit_decimal)
        rows.append(
            {
                "date": day,
                "block_count": len(group),
                "first_block": int(group["block_number"].min()),
                "last_block": int(group["block_number"].max()),
                "mean_base_fee_per_gas_wei": _mean(base_fee),
                "median_base_fee_per_gas_wei": _median(base_fee),
                "mean_gas_used": _mean(gas_used),
                "mean_gas_limit": _mean(gas_limit),
                "mean_block_gas_utilization": _mean(utilization),
            }
        )
    return pd.DataFrame(rows)
