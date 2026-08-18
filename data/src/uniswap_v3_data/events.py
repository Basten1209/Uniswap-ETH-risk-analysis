"""Lossless parsing for target-pool and NFPM decoded events."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from eth_hash.auto import keccak

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


def event_topic(signature: str) -> str:
    """Return the Ethereum Keccak-256 topic for an event signature."""
    return "0x" + keccak(signature.encode("ascii")).hex()


SIGNATURE_TO_TOPIC = {
    signature: event_topic(signature)
    for signature in (*POOL_SIGNATURES, *NFPM_SIGNATURES)
}
TOPIC_TO_SIGNATURE = {topic: signature for signature, topic in SIGNATURE_TO_TOPIC.items()}

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
RAW_BASE_COLUMNS = (
    "block_number",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "log_index",
    "address",
    "topics_json",
    "data",
)


def _hex_text(value: Any) -> str:
    result = str(value or "0x").lower()
    if not result.startswith("0x"):
        raise ValueError(f"expected 0x-prefixed hex, received {result!r}")
    try:
        int(result[2:] or "0", 16)
    except ValueError as exc:
        raise ValueError(f"invalid event hex: {result!r}") from exc
    return result


def _words(data: Any) -> list[str]:
    payload = _hex_text(data)[2:]
    if len(payload) % 64:
        raise ValueError(f"event data is not ABI word-aligned: {len(payload)} hex chars")
    return [payload[index : index + 64] for index in range(0, len(payload), 64)]


def _uint(word: str) -> int:
    if len(word) != 64:
        raise ValueError(f"ABI word must contain 64 hex chars: {word!r}")
    return int(word, 16)


def _signed(word: str) -> int:
    value = _uint(word)
    return value - 2**256 if value >= 2**255 else value


def _abi_address(word: str) -> str:
    _uint(word)
    return "0x" + word[-40:].lower()


def _topic_word(topics: list[str], index: int) -> str:
    try:
        return _hex_text(topics[index])[2:].zfill(64)
    except IndexError as exc:
        raise ValueError(f"missing indexed topic {index}: {topics!r}") from exc


def _decode_raw_args(signature: str, topics: list[str], data: Any) -> list[Any]:
    words = _words(data)
    if signature == POOL_INITIALIZE:
        return [_uint(words[0]), _signed(words[1])]
    if signature == POOL_MINT:
        return [
            _abi_address(words[0]),
            _abi_address(_topic_word(topics, 1)),
            _signed(_topic_word(topics, 2)),
            _signed(_topic_word(topics, 3)),
            _uint(words[1]),
            _uint(words[2]),
            _uint(words[3]),
        ]
    if signature == POOL_BURN:
        return [
            _abi_address(_topic_word(topics, 1)),
            _signed(_topic_word(topics, 2)),
            _signed(_topic_word(topics, 3)),
            _uint(words[0]),
            _uint(words[1]),
            _uint(words[2]),
        ]
    if signature == POOL_SWAP:
        return [
            _abi_address(_topic_word(topics, 1)),
            _abi_address(_topic_word(topics, 2)),
            _signed(words[0]),
            _signed(words[1]),
            _uint(words[2]),
            _uint(words[3]),
            _signed(words[4]),
        ]
    if signature == POOL_COLLECT:
        return [
            _abi_address(_topic_word(topics, 1)),
            _abi_address(words[0]),
            _signed(_topic_word(topics, 2)),
            _signed(_topic_word(topics, 3)),
            _uint(words[1]),
            _uint(words[2]),
        ]
    if signature in (NFPM_INCREASE, NFPM_DECREASE):
        return [
            _uint(_topic_word(topics, 1)),
            _uint(words[0]),
            _uint(words[1]),
            _uint(words[2]),
        ]
    if signature == NFPM_COLLECT:
        return [
            _uint(_topic_word(topics, 1)),
            _abi_address(words[0]),
            _uint(words[1]),
            _uint(words[2]),
        ]
    if signature == NFPM_TRANSFER:
        return [
            _abi_address(_topic_word(topics, 1)),
            _abi_address(_topic_word(topics, 2)),
            _uint(_topic_word(topics, 3)),
        ]
    raise ValueError(f"unsupported raw event signature: {signature}")


def _decode_raw_frame(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in raw.to_dict(orient="records"):
        if bool(row.get("removed", False)):
            raise ValueError("raw input contains an orphaned log (removed=true)")
        topics = json.loads(str(row["topics_json"]))
        if not isinstance(topics, list) or not topics:
            raise ValueError(f"raw event has no topics: {topics!r}")
        topic0 = _hex_text(topics[0])
        signature = TOPIC_TO_SIGNATURE.get(topic0)
        if signature is None:
            raise ValueError(f"unsupported event topic: {topic0}")
        decoded = dict(row)
        decoded["event_signature"] = signature
        decoded["args_json"] = json.dumps(
            _decode_raw_args(signature, topics, row["data"]), separators=(",", ":")
        )
        rows.append(decoded)
    return pd.DataFrame(rows)


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
    if "args_json" not in raw.columns:
        missing_raw = set(RAW_BASE_COLUMNS).difference(raw.columns)
        if missing_raw:
            raise ValueError(
                f"raw logs are missing columns: {sorted(missing_raw)}"
            )
        raw = _decode_raw_frame(raw)
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
