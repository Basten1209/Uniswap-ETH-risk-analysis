"""Validated readers for the fixed-pool risk analysis."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .formulas import sqrt_price_x96_to_price


NANOSECONDS_PER_SECOND = 1_000_000_000
ORDER_TRANSACTION_BASE = 100_000
ORDER_BLOCK_BASE = ORDER_TRANSACTION_BASE**2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_event_order(
    block_number: Any, transaction_index: Any, log_index: Any
) -> np.ndarray | int:
    block = np.asarray(block_number, dtype=np.int64)
    transaction = np.asarray(transaction_index, dtype=np.int64)
    log = np.asarray(log_index, dtype=np.int64)
    if np.any(block < 0) or np.any(transaction < 0) or np.any(log < 0):
        raise ValueError("event order fields must be non-negative")
    if np.any(transaction >= ORDER_TRANSACTION_BASE) or np.any(
        log >= ORDER_TRANSACTION_BASE
    ):
        raise ValueError("event order field exceeds the lossless key encoding")
    result = block * ORDER_BLOCK_BASE + transaction * ORDER_TRANSACTION_BASE + log
    return int(result) if result.ndim == 0 else result


class PartitionedOracle:
    """Small-cache reader for the dense monthly Binance ETHUSDT oracle."""

    def __init__(self, root: Path, *, cache_months: int = 2) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"oracle manifest not found: {self.manifest_path}")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.artifacts = {item["month"]: item for item in self.manifest["artifacts"]}
        self.cache_months = cache_months
        self._cache: OrderedDict[str, tuple[np.ndarray, np.ndarray]] = OrderedDict()

    @property
    def coverage_last(self) -> pd.Timestamp:
        return pd.Timestamp(self.manifest["coverage"]["last_timestamp_utc"])

    @property
    def manifest_sha256(self) -> str:
        return sha256_file(self.manifest_path)

    def _artifact_path(self, month: str) -> Path:
        item = self.artifacts.get(month)
        if item is None:
            raise ValueError(f"oracle has no partition for {month}")
        relative = Path(str(item["path"]))
        if relative.is_absolute() or relative.name != str(item["path"]):
            raise ValueError(f"unsafe oracle artifact path: {relative}")
        path = self.root / relative
        if not path.is_file() or path.stat().st_size != int(item["size_bytes"]):
            raise RuntimeError(f"oracle partition is missing or changed: {path}")
        return path

    def load_month(self, month: str) -> tuple[np.ndarray, np.ndarray]:
        cached = self._cache.pop(month, None)
        if cached is not None:
            self._cache[month] = cached
            return cached
        path = self._artifact_path(month)
        frame = pd.read_parquet(path, columns=["timestamp", "price"])
        timestamps = (
            pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
            .as_unit("ns")
            .asi8
        )
        prices = frame["price"].to_numpy(dtype=np.float64)
        if len(timestamps) == 0 or not np.isfinite(prices).all() or np.any(prices <= 0):
            raise ValueError(f"invalid oracle partition: {path.name}")
        if len(timestamps) > 1 and not np.all(
            np.diff(timestamps) == NANOSECONDS_PER_SECOND
        ):
            raise ValueError(f"oracle partition is not a dense second grid: {path.name}")
        result = (timestamps, prices)
        self._cache[month] = result
        while len(self._cache) > self.cache_months:
            self._cache.popitem(last=False)
        return result

    def lookup_strict_prior(self, event_timestamps: Any) -> np.ndarray:
        events = pd.to_datetime(event_timestamps, utc=True)
        scalar = isinstance(events, pd.Timestamp)
        index = pd.DatetimeIndex([events]) if scalar else pd.DatetimeIndex(events)
        index_ns = index.as_unit("ns").asi8
        if index.hasnans or np.any(index_ns % NANOSECONDS_PER_SECOND):
            raise ValueError("oracle lookup events must be whole UTC seconds")
        required = index - pd.Timedelta(seconds=1)
        months = required.strftime("%Y-%m")
        result = np.empty(len(index), dtype=np.float64)
        for month in sorted(set(months)):
            positions = np.flatnonzero(months == month)
            stored_ns, prices = self.load_month(month)
            requested_ns = required.as_unit("ns").asi8[positions]
            offsets = (requested_ns - stored_ns[0]) // NANOSECONDS_PER_SECOND
            valid = (
                (offsets >= 0)
                & (offsets < len(stored_ns))
                & (stored_ns[np.clip(offsets, 0, len(stored_ns) - 1)] == requested_ns)
            )
            if not valid.all():
                raise ValueError(f"oracle lacks strict-prior rows for {month}")
            result[positions] = prices[offsets]
        return np.asarray([result[0]]) if scalar else result

    def iter_months(self) -> Iterator[tuple[str, np.ndarray, np.ndarray]]:
        for month in sorted(self.artifacts):
            timestamps, prices = self.load_month(month)
            yield month, timestamps, prices


@dataclass(frozen=True)
class SwapPath:
    keys: np.ndarray
    timestamps_ns: np.ndarray
    block_numbers: np.ndarray
    transaction_indices: np.ndarray
    log_indices: np.ndarray
    pool_prices: np.ndarray
    external_prices: np.ndarray
    initialize_key: int
    initialize_price: float

    def bounds(self, entry_key: int, exit_key: int) -> tuple[int, int]:
        start = int(np.searchsorted(self.keys, entry_key, side="right"))
        end = int(np.searchsorted(self.keys, exit_key, side="left"))
        return start, end

    def state_before(self, key: int) -> float:
        position = int(np.searchsorted(self.keys, key, side="left")) - 1
        if position >= 0:
            return float(self.pool_prices[position])
        if key <= self.initialize_key:
            raise ValueError("requested state does not follow pool initialization")
        return self.initialize_price


def load_swap_path(pool_event_root: Path, oracle: PartitionedOracle) -> SwapPath:
    """Load the exact ordered Swap path and strict-prior external marks."""

    paths = sorted(Path(pool_event_root).glob("pool_events_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no processed pool-event files under {pool_event_root}")
    chunks: list[dict[str, np.ndarray]] = []
    initialize_rows: list[pd.DataFrame] = []
    columns = [
        "event_type",
        "block_number",
        "block_timestamp",
        "transaction_index",
        "log_index",
        "sqrt_price_x96",
    ]
    for file_number, path in enumerate(paths, start=1):
        frame = pd.read_parquet(path, columns=columns)
        initialize = frame.loc[frame["event_type"] == "Initialize"]
        if not initialize.empty:
            initialize_rows.append(initialize)
        swaps = frame.loc[frame["event_type"] == "Swap"].copy()
        if swaps.empty:
            continue
        swaps = swaps.sort_values(
            ["block_number", "transaction_index", "log_index"], kind="stable"
        )
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(swaps["block_timestamp"], utc=True)
        )
        timestamps_ns = timestamps.as_unit("ns").asi8
        if np.any(timestamps_ns % NANOSECONDS_PER_SECOND):
            raise ValueError(f"Swap timestamps are not whole seconds in {path.name}")
        chunks.append(
            {
                "block": swaps["block_number"].to_numpy(dtype=np.int64),
                "timestamp": timestamps_ns,
                "transaction": swaps["transaction_index"].to_numpy(dtype=np.int64),
                "log": swaps["log_index"].to_numpy(dtype=np.int64),
                "pool_price": np.asarray(
                    sqrt_price_x96_to_price(swaps["sqrt_price_x96"].map(float))
                ),
                "external_price": oracle.lookup_strict_prior(timestamps),
            }
        )
        if file_number == 1 or file_number % 12 == 0 or file_number == len(paths):
            print(f"loaded ordered Swap path {file_number:02d}/{len(paths)} partitions")
    if len(initialize_rows) != 1:
        raise ValueError(f"expected one Initialize event, found {sum(map(len, initialize_rows))}")
    initialize = initialize_rows[0].iloc[0]
    initialize_key = encode_event_order(
        initialize["block_number"],
        initialize["transaction_index"],
        initialize["log_index"],
    )
    initialize_price = float(sqrt_price_x96_to_price(float(initialize["sqrt_price_x96"])))
    block = np.concatenate([chunk["block"] for chunk in chunks])
    transaction = np.concatenate([chunk["transaction"] for chunk in chunks])
    log = np.concatenate([chunk["log"] for chunk in chunks])
    keys = np.asarray(encode_event_order(block, transaction, log))
    if len(keys) == 0 or np.any(np.diff(keys) <= 0):
        raise ValueError("Swap event order is empty, duplicated, or decreasing")
    return SwapPath(
        keys=keys,
        timestamps_ns=np.concatenate([chunk["timestamp"] for chunk in chunks]),
        block_numbers=block,
        transaction_indices=transaction,
        log_indices=log,
        pool_prices=np.concatenate([chunk["pool_price"] for chunk in chunks]),
        external_prices=np.concatenate([chunk["external_price"] for chunk in chunks]),
        initialize_key=int(initialize_key),
        initialize_price=initialize_price,
    )


def load_sofr_artifact(root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"SOFR snapshot not found under {root}; run analysis/scripts/prepare_sofr.py"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative = Path(str(manifest["artifact"]["path"]))
    if relative.is_absolute() or relative.name != str(manifest["artifact"]["path"]):
        raise ValueError("unsafe SOFR artifact path")
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"SOFR parquet not found: {path}")
    if path.stat().st_size != int(manifest["artifact"]["size_bytes"]):
        raise RuntimeError("SOFR artifact size does not match its manifest")
    if sha256_file(path) != manifest["artifact"]["sha256"]:
        raise RuntimeError("SOFR artifact hash does not match its manifest")
    frame = pq.read_table(path).to_pandas()
    return frame, {**manifest, "manifest_sha256": sha256_file(manifest_path)}
