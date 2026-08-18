"""Lossless parsing for target-pool and NFPM decoded events."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

POOL_INITIALIZE = "Initialize(uint160,int24)"
POOL_MINT = "Mint(address,address,int24,int24,uint128,uint256,uint256)"
POOL_BURN = "Burn(address,int24,int24,uint128,uint256,uint256)"
POOL_SWAP = "Swap(address,address,int256,int256,uint160,uint128,int24)"
POOL_COLLECT = "Collect(address,address,int24,int24,uint128,uint128)"
POOL_SIGNATURES = (POOL_INITIALIZE, POOL_MINT, POOL_BURN, POOL_SWAP, POOL_COLLECT)

NFPM_INCREASE = "IncreaseLiquidity(uint256,uint128,uint256,uint256)"
NFPM_DECREASE = "DecreaseLiquidity(uint256,uint128,uint256,uint256)"
NFPM_COLLECT = "Collect(uint256,address,uint256,uint256)"
NFPM_TRANSFER = "Transfer(address,address,uint256)"
NFPM_SIGNATURES = (NFPM_INCREASE, NFPM_DECREASE, NFPM_COLLECT, NFPM_TRANSFER)

EXPECTED_ARG_COUNTS = {
    POOL_INITIALIZE: 2,
    POOL_MINT: 7,
    POOL_BURN: 6,
    POOL_SWAP: 7,
    POOL_COLLECT: 6,
    NFPM_INCREASE: 4,
    NFPM_DECREASE: 4,
    NFPM_COLLECT: 4,
    NFPM_TRANSFER: 3,
}

BASE_COLUMNS = (
    "block_number",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "log_index",
    "address",
    "event_signature",
    "args_json",
)


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError(f"invalid decoded argument: {value!r}")
    return str(value)


def _integer_text(value: Any) -> str:
    return str(int(_text(value), 10))


def _integer(value: Any) -> int:
    return int(_text(value), 10)


def _address(value: Any) -> str:
    result = _text(value).lower()
    if len(result) != 42 or not result.startswith("0x"):
        raise ValueError(f"invalid decoded address: {result}")
    return result


def _base(row: dict[str, Any], event_type: str) -> dict[str, Any]:
    return {
        "block_number": int(row["block_number"]),
        "block_timestamp": pd.to_datetime(row["block_timestamp"], utc=True),
        "transaction_hash": str(row["transaction_hash"]).lower(),
        "transaction_index": int(row["transaction_index"]),
        "log_index": int(row["log_index"]),
        "address": str(row["address"]).lower(),
        "event_signature": str(row["event_signature"]),
        "event_type": event_type,
        "args_json": str(row["args_json"]),
    }


def _args(row: dict[str, Any]) -> list[Any]:
    signature = str(row["event_signature"])
    values = json.loads(str(row["args_json"]))
    expected = EXPECTED_ARG_COUNTS.get(signature)
    if expected is None:
        raise ValueError(f"unsupported event signature: {signature}")
    if not isinstance(values, list) or len(values) != expected:
        raise ValueError(f"{signature}: expected {expected} args, received {values!r}")
    return values


def parse_raw_events(
    raw: pd.DataFrame, pool_address: str, nfpm_address: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split and decode a raw monthly extract without coercing uint256 to float."""
    missing = set(BASE_COLUMNS).difference(raw.columns)
    if missing:
        raise ValueError(f"raw events are missing columns: {sorted(missing)}")

    pool_rows: list[dict[str, Any]] = []
    nfpm_rows: list[dict[str, Any]] = []
    pool_address = pool_address.lower()
    nfpm_address = nfpm_address.lower()

    for row in raw.to_dict(orient="records"):
        address = str(row["address"]).lower()
        signature = str(row["event_signature"])
        values = _args(row)

        if address == pool_address:
            if signature == POOL_INITIALIZE:
                out = _base(row, "Initialize")
                out.update(
                    sqrt_price_x96=_integer_text(values[0]), tick=_integer(values[1])
                )
            elif signature == POOL_MINT:
                out = _base(row, "Mint")
                out.update(
                    sender=_address(values[0]),
                    owner=_address(values[1]),
                    tick_lower=_integer(values[2]),
                    tick_upper=_integer(values[3]),
                    liquidity_delta_raw=_integer_text(values[4]),
                    amount0_raw=_integer_text(values[5]),
                    amount1_raw=_integer_text(values[6]),
                )
            elif signature == POOL_BURN:
                out = _base(row, "Burn")
                out.update(
                    owner=_address(values[0]),
                    tick_lower=_integer(values[1]),
                    tick_upper=_integer(values[2]),
                    liquidity_delta_raw=str(-_integer(values[3])),
                    amount0_raw=_integer_text(values[4]),
                    amount1_raw=_integer_text(values[5]),
                )
            elif signature == POOL_SWAP:
                out = _base(row, "Swap")
                out.update(
                    sender=_address(values[0]),
                    recipient=_address(values[1]),
                    amount0_raw=_integer_text(values[2]),
                    amount1_raw=_integer_text(values[3]),
                    sqrt_price_x96=_integer_text(values[4]),
                    active_liquidity_raw=_integer_text(values[5]),
                    tick=_integer(values[6]),
                )
            elif signature == POOL_COLLECT:
                out = _base(row, "Collect")
                out.update(
                    owner=_address(values[0]),
                    recipient=_address(values[1]),
                    tick_lower=_integer(values[2]),
                    tick_upper=_integer(values[3]),
                    amount0_raw=_integer_text(values[4]),
                    amount1_raw=_integer_text(values[5]),
                )
            else:
                raise ValueError(f"unexpected pool signature: {signature}")
            pool_rows.append(out)
            continue

        if address == nfpm_address:
            if signature == NFPM_INCREASE:
                out = _base(row, "IncreaseLiquidity")
                out.update(
                    token_id=_integer_text(values[0]),
                    liquidity_delta_raw=_integer_text(values[1]),
                    amount0_raw=_integer_text(values[2]),
                    amount1_raw=_integer_text(values[3]),
                )
            elif signature == NFPM_DECREASE:
                out = _base(row, "DecreaseLiquidity")
                out.update(
                    token_id=_integer_text(values[0]),
                    liquidity_delta_raw=str(-_integer(values[1])),
                    amount0_raw=_integer_text(values[2]),
                    amount1_raw=_integer_text(values[3]),
                )
            elif signature == NFPM_COLLECT:
                out = _base(row, "Collect")
                out.update(
                    token_id=_integer_text(values[0]),
                    recipient=_address(values[1]),
                    amount0_raw=_integer_text(values[2]),
                    amount1_raw=_integer_text(values[3]),
                )
            elif signature == NFPM_TRANSFER:
                out = _base(row, "Transfer")
                out.update(
                    from_address=_address(values[0]),
                    to_address=_address(values[1]),
                    token_id=_integer_text(values[2]),
                )
            else:
                raise ValueError(f"unexpected NFPM signature: {signature}")
            nfpm_rows.append(out)
            continue

        raise ValueError(f"unexpected emitting contract: {address}")

    def frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        result = pd.DataFrame(rows)
        if not result.empty:
            result = result.sort_values(
                ["block_number", "transaction_index", "log_index"], kind="stable"
            ).reset_index(drop=True)
        return result

    return frame(pool_rows), frame(nfpm_rows)
