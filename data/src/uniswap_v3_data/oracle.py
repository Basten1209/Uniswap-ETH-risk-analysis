"""Prepare and query the partitioned Binance ETHUSDT valuation oracle."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


SOURCE_COLUMNS = ("open_time", "close", "quote_volume")
ORACLE_COLUMNS = ("timestamp", "price", "volume")
ORACLE_SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("volume", pa.float64(), nullable=False),
    ]
)
SOURCE_NAME = re.compile(r"^ETHUSDT-1s-(\d{4}-\d{2}(?:-\d{2})?)\.parquet$")
OUTPUT_NAME = re.compile(r"^weth_usdt_1s_(\d{4}-\d{2})\.parquet$")


@dataclass(frozen=True)
class SourcePartition:
    path: Path
    filename: str
    frequency: str
    period: str
    expected_rows: int
    expected_bytes: int
    first_timestamp: pd.Timestamp
    last_timestamp: pd.Timestamp


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _utc_timestamp(value: Any, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a valid timestamp: {value!r}") from exc
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return result.tz_convert("UTC")


def _iso_utc(value: pd.Timestamp) -> str:
    return value.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _first_and_last_timestamp(parquet: pq.ParquetFile) -> tuple[pd.Timestamp, pd.Timestamp]:
    if parquet.metadata.num_rows == 0:
        raise ValueError("source parquet must not be empty")
    first_group = parquet.read_row_group(0, columns=["open_time"])
    last_group = parquet.read_row_group(
        parquet.metadata.num_row_groups - 1, columns=["open_time"]
    )
    first = pd.Timestamp(first_group.column(0)[0].as_py()).tz_convert("UTC")
    last = pd.Timestamp(last_group.column(0)[len(last_group) - 1].as_py()).tz_convert(
        "UTC"
    )
    return first, last


def _validate_source_schema(schema: pa.Schema, filename: str) -> None:
    missing = set(SOURCE_COLUMNS).difference(schema.names)
    if missing:
        raise ValueError(f"{filename} is missing source columns: {sorted(missing)}")
    open_time = schema.field("open_time").type
    if not pa.types.is_timestamp(open_time) or open_time.tz != "UTC":
        raise ValueError(f"{filename} open_time must be a UTC timestamp")
    for column in ("close", "quote_volume"):
        if not pa.types.is_float64(schema.field(column).type):
            raise ValueError(f"{filename} {column} must be float64")


def load_source_partitions(
    source_root: Path,
) -> tuple[dict[str, Any], str, list[SourcePartition], pd.Timestamp, pd.Timestamp]:
    """Validate source manifest/file metadata and return chronological partitions."""
    source_root = Path(source_root)
    manifest_path = source_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"source manifest not found: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("symbol") != "ETHUSDT" or manifest.get("interval") != "1s":
        raise ValueError("source manifest must describe ETHUSDT 1-second data")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("source manifest files must be a non-empty object")

    partitions: list[SourcePartition] = []
    for archive_name, item in entries.items():
        if Path(archive_name).name != archive_name or not archive_name.endswith(".zip"):
            raise ValueError(f"unsafe or unsupported source filename: {archive_name}")
        filename = f"{archive_name[:-4]}.parquet"
        match = SOURCE_NAME.fullmatch(filename)
        if not match:
            raise ValueError(f"unexpected source parquet filename: {filename}")
        spec = item.get("spec", {})
        frequency = str(spec.get("frequency", ""))
        period = str(spec.get("period", ""))
        if frequency not in {"monthly", "daily"} or period != match.group(1):
            raise ValueError(f"source period metadata does not match {filename}")
        path = source_root / "parquet" / filename
        if not path.is_file():
            raise FileNotFoundError(f"source parquet not found: {path}")
        expected_bytes = int(item["parquet_bytes"])
        if path.stat().st_size != expected_bytes:
            raise RuntimeError(
                f"source size mismatch for {filename}: expected {expected_bytes}, "
                f"found {path.stat().st_size}"
            )
        quality = item.get("quality", {})
        expected_rows = int(quality["rows"])
        parquet = pq.ParquetFile(path)
        _validate_source_schema(parquet.schema_arrow, filename)
        if parquet.metadata.num_rows != expected_rows:
            raise RuntimeError(
                f"source row mismatch for {filename}: expected {expected_rows}, "
                f"found {parquet.metadata.num_rows}"
            )
        first, last = _first_and_last_timestamp(parquet)
        declared_first = _utc_timestamp(
            quality["first_open_time_utc"], f"{filename}.first_open_time_utc"
        )
        declared_last = _utc_timestamp(
            quality["last_open_time_utc"], f"{filename}.last_open_time_utc"
        )
        if first != declared_first or last != declared_last:
            raise RuntimeError(
                f"source timestamp metadata mismatch for {filename}: "
                f"declared [{declared_first}, {declared_last}], found [{first}, {last}]"
            )
        partitions.append(
            SourcePartition(
                path=path,
                filename=filename,
                frequency=frequency,
                period=period,
                expected_rows=expected_rows,
                expected_bytes=expected_bytes,
                first_timestamp=first,
                last_timestamp=last,
            )
        )

    partitions.sort(key=lambda item: (item.first_timestamp, item.filename))
    for previous, current in zip(partitions, partitions[1:]):
        if current.first_timestamp <= previous.last_timestamp:
            raise ValueError(
                f"source parquet ranges overlap or are out of order: "
                f"{previous.filename}, {current.filename}"
            )
    first = partitions[0].first_timestamp
    last = partitions[-1].last_timestamp
    stored_start = _utc_timestamp(manifest["stored_start_utc"], "stored_start_utc")
    declared_last = _utc_timestamp(
        manifest["verification"]["last_open_time_utc"],
        "verification.last_open_time_utc",
    )
    if first != stored_start or last != declared_last:
        raise RuntimeError(
            "source coverage does not match manifest: "
            f"declared [{stored_start}, {declared_last}], found [{first}, {last}]"
        )
    expected_file_count = int(manifest["verification"]["file_count"])
    expected_total_rows = int(manifest["verification"]["total_rows"])
    if len(partitions) != expected_file_count:
        raise RuntimeError(
            f"source file count mismatch: expected {expected_file_count}, "
            f"found {len(partitions)}"
        )
    if sum(item.expected_rows for item in partitions) != expected_total_rows:
        raise RuntimeError("source manifest file rows do not sum to verification total")
    return manifest, sha256_file(manifest_path), partitions, first, last


def _read_source_frame(partition: SourcePartition) -> pd.DataFrame:
    frame = pq.read_table(partition.path, columns=list(SOURCE_COLUMNS)).to_pandas()
    if len(frame) != partition.expected_rows:
        raise RuntimeError(f"source row count changed while reading {partition.filename}")
    frame = frame.rename(
        columns={
            "open_time": "timestamp",
            "close": "price",
            "quote_volume": "volume",
        }
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame[list(ORACLE_COLUMNS)].isna().any().any():
        raise ValueError(f"{partition.filename} contains null source values")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError(f"{partition.filename} timestamps move backward")
    if frame["timestamp"].duplicated().any():
        raise ValueError(f"{partition.filename} contains duplicate timestamps")
    if (frame["timestamp"].dt.microsecond != 0).any() or (
        frame["timestamp"].dt.nanosecond != 0
    ).any():
        raise ValueError(f"{partition.filename} timestamps are not whole seconds")
    price = frame["price"].to_numpy(dtype="float64", copy=False)
    volume = frame["volume"].to_numpy(dtype="float64", copy=False)
    if not np.isfinite(price).all() or (price <= 0).any():
        raise ValueError(f"{partition.filename} contains invalid prices")
    if not np.isfinite(volume).all() or (volume < 0).any():
        raise ValueError(f"{partition.filename} contains invalid quote volumes")
    frame["price"] = price
    frame["volume"] = volume
    return frame.loc[:, ORACLE_COLUMNS]


def _gap_ranges(index: pd.DatetimeIndex, missing: np.ndarray) -> list[dict[str, Any]]:
    positions = np.flatnonzero(missing)
    if not len(positions):
        return []
    groups = np.split(positions, np.flatnonzero(np.diff(positions) > 1) + 1)
    return [
        {
            "start_timestamp_utc": _iso_utc(index[group[0]]),
            "end_timestamp_utc": _iso_utc(index[group[-1]]),
            "seconds": int(len(group)),
        }
        for group in groups
    ]


def _write_partition(frame: pd.DataFrame, path: Path) -> tuple[int, str]:
    table = pa.Table.from_pandas(
        frame, schema=ORACLE_SCHEMA, preserve_index=False, safe=True
    )
    partial = path.with_suffix(f"{path.suffix}.partial")
    if partial.exists():
        raise RuntimeError(f"partial output already exists: {partial}")
    pq.write_table(
        table,
        partial,
        compression="zstd",
        row_group_size=131_072,
        write_statistics=True,
    )
    digest = sha256_file(partial)
    size = partial.stat().st_size
    if path.exists():
        if path.stat().st_size != size or sha256_file(path) != digest:
            partial.unlink()
            raise RuntimeError(f"refusing to overwrite different oracle output: {path}")
        partial.unlink()
    else:
        partial.replace(path)
    return size, digest


def build_oracle_dataset(source_root: Path, output_root: Path) -> dict[str, Any]:
    """Build a dense, monthly, three-column ETHUSDT oracle dataset."""
    (
        source_manifest,
        source_manifest_sha256,
        source_partitions,
        coverage_start,
        coverage_end,
    ) = load_source_partitions(Path(source_root))
    output_root = Path(output_root)
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        existing = verify_oracle_dataset(output_root, verify_hashes=True)
        manifest = _read_json(manifest_path)
        if manifest["source"]["manifest_sha256"] != source_manifest_sha256:
            raise RuntimeError("existing oracle was built from a different source manifest")
        if manifest["transform"] != _transform_contract():
            raise RuntimeError("existing oracle uses a different transform contract")
        return {**existing, "reused": True}

    output_root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[SourcePartition]] = {}
    for partition in source_partitions:
        month = partition.first_timestamp.strftime("%Y-%m")
        if partition.last_timestamp.strftime("%Y-%m") != month:
            raise ValueError(f"source file crosses a UTC month: {partition.filename}")
        grouped.setdefault(month, []).append(partition)

    previous_price: float | None = None
    artifacts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    total_source_rows = total_output_rows = total_imputed_rows = 0
    months = sorted(grouped)
    for month in months:
        sources = grouped[month]
        frames = [_read_source_frame(item) for item in sources]
        observed = pd.concat(frames, ignore_index=True)
        if not observed["timestamp"].is_monotonic_increasing:
            raise ValueError(f"source timestamps move backward within {month}")
        if observed["timestamp"].duplicated().any():
            raise ValueError(f"source timestamps overlap within {month}")

        month_start = pd.Timestamp(f"{month}-01", tz="UTC")
        next_month = month_start + pd.offsets.MonthBegin(1)
        partition_start = max(month_start, coverage_start)
        partition_end = min(next_month - pd.Timedelta(seconds=1), coverage_end)
        if observed["timestamp"].iloc[0] < partition_start or observed[
            "timestamp"
        ].iloc[-1] > partition_end:
            raise ValueError(f"source rows fall outside output partition {month}")
        grid = pd.date_range(
            partition_start, partition_end, freq="s", tz="UTC", name="timestamp"
        )
        dense = observed.set_index("timestamp").reindex(grid)
        missing = dense["price"].isna().to_numpy()
        if not np.array_equal(missing, dense["volume"].isna().to_numpy()):
            raise ValueError(f"price/volume missingness differs in {month}")
        dense["price"] = dense["price"].ffill()
        if dense["price"].isna().any():
            if previous_price is None:
                raise ValueError("cannot forward-fill before the first observed price")
            dense["price"] = dense["price"].fillna(previous_price)
        dense["volume"] = dense["volume"].fillna(0.0)
        previous_price = float(dense["price"].iloc[-1])
        output = dense.reset_index().loc[:, ORACLE_COLUMNS]

        filename = f"weth_usdt_1s_{month}.parquet"
        path = output_root / filename
        size, digest = _write_partition(output, path)
        imputed_rows = int(missing.sum())
        month_gaps = _gap_ranges(grid, missing)
        for gap in month_gaps:
            gap["partition"] = filename
        gaps.extend(month_gaps)
        artifacts.append(
            {
                "month": month,
                "path": filename,
                "source_files": [item.filename for item in sources],
                "source_rows": int(len(observed)),
                "row_count": int(len(output)),
                "imputed_rows": imputed_rows,
                "first_timestamp_utc": _iso_utc(grid[0]),
                "last_timestamp_utc": _iso_utc(grid[-1]),
                "size_bytes": size,
                "sha256": digest,
            }
        )
        total_source_rows += len(observed)
        total_output_rows += len(output)
        total_imputed_rows += imputed_rows

    if total_source_rows != int(source_manifest["verification"]["total_rows"]):
        raise RuntimeError("transformed source row total does not match source manifest")
    if total_output_rows - total_source_rows != total_imputed_rows:
        raise RuntimeError("oracle output and imputed row totals do not reconcile")

    manifest = {
        "schema_version": 1,
        "dataset": "Binance spot ETHUSDT 1-second close oracle",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "dataset": source_manifest["dataset"],
            "symbol": source_manifest["symbol"],
            "interval": source_manifest["interval"],
            "manifest_sha256": source_manifest_sha256,
            "file_count": len(source_partitions),
            "row_count": total_source_rows,
        },
        "schema": [
            {"name": "timestamp", "type": "timestamp[us, UTC]"},
            {"name": "price", "type": "float64", "unit": "USDT per ETH"},
            {"name": "volume", "type": "float64", "unit": "USDT"},
        ],
        "transform": _transform_contract(),
        "coverage": {
            "first_timestamp_utc": _iso_utc(coverage_start),
            "last_timestamp_utc": _iso_utc(coverage_end),
            "source_rows": total_source_rows,
            "output_rows": total_output_rows,
            "imputed_rows": total_imputed_rows,
            "gap_runs": len(gaps),
        },
        "artifacts": artifacts,
        "gaps": gaps,
        "quality": {
            "monthly_partitions": len(artifacts),
            "timestamps_are_contiguous_seconds": True,
            "duplicate_timestamps": 0,
            "null_values": 0,
            "negative_volume_rows": 0,
        },
    }
    partial_manifest = manifest_path.with_suffix(".json.partial")
    if partial_manifest.exists():
        raise RuntimeError(f"partial output already exists: {partial_manifest}")
    partial_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    partial_manifest.replace(manifest_path)
    summary = verify_oracle_dataset(output_root, verify_hashes=False)
    return {**summary, "reused": False}


def _transform_contract() -> dict[str, Any]:
    return {
        "timestamp": "source open_time normalized to a whole UTC second",
        "price": "source close",
        "volume": "source quote_volume (USDT)",
        "missing_price": "forward-fill the latest strictly prior observed close",
        "missing_volume": "0",
        "partitioning": "UTC calendar month",
        "compression": "ZSTD",
        "row_group_size": 131_072,
    }


def _artifact_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or candidate.name != relative
        or not OUTPUT_NAME.fullmatch(relative)
    ):
        raise ValueError(f"unsafe oracle artifact path: {relative}")
    return root / candidate


def _validate_oracle_schema(schema: pa.Schema, filename: str) -> None:
    if not schema.equals(ORACLE_SCHEMA, check_metadata=False):
        raise ValueError(
            f"{filename} has an invalid oracle schema: expected {ORACLE_SCHEMA}, "
            f"found {schema}"
        )


def verify_oracle_dataset(
    output_root: Path, *, verify_hashes: bool = True
) -> dict[str, Any]:
    """Verify partition metadata, dense coverage, statistics, and optional hashes."""
    output_root = Path(output_root)
    manifest_path = output_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"oracle manifest not found: {manifest_path}")
    manifest = _read_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("oracle manifest artifacts must be a non-empty list")

    total_rows = total_size = total_imputed = 0
    previous_last: pd.Timestamp | None = None
    for artifact in artifacts:
        path = _artifact_path(output_root, str(artifact["path"]))
        if not path.is_file():
            raise FileNotFoundError(f"oracle partition not found: {path}")
        if path.stat().st_size != int(artifact["size_bytes"]):
            raise RuntimeError(f"oracle size mismatch: {path.name}")
        if verify_hashes and sha256_file(path) != artifact["sha256"]:
            raise RuntimeError(f"oracle SHA-256 mismatch: {path.name}")
        parquet = pq.ParquetFile(path)
        _validate_oracle_schema(parquet.schema_arrow, path.name)
        rows = int(artifact["row_count"])
        if parquet.metadata.num_rows != rows:
            raise RuntimeError(f"oracle row count mismatch: {path.name}")
        first = _utc_timestamp(artifact["first_timestamp_utc"], "first_timestamp_utc")
        last = _utc_timestamp(artifact["last_timestamp_utc"], "last_timestamp_utc")
        expected_rows = int((last - first).total_seconds()) + 1
        if rows != expected_rows:
            raise RuntimeError(f"oracle partition is not a dense second grid: {path.name}")
        if previous_last is not None and first != previous_last + pd.Timedelta(seconds=1):
            raise RuntimeError(f"oracle partitions are not contiguous at {path.name}")
        previous_last = last
        for row_group_index in range(parquet.metadata.num_row_groups):
            row_group = parquet.metadata.row_group(row_group_index)
            for column_index, column_name in ((1, "price"), (2, "volume")):
                statistics = row_group.column(column_index).statistics
                if statistics is None or not statistics.has_min_max:
                    raise RuntimeError(
                        f"oracle statistics missing for {path.name}.{column_name}"
                    )
                if statistics.null_count:
                    raise RuntimeError(f"oracle contains nulls: {path.name}.{column_name}")
                if column_name == "price" and statistics.min <= 0:
                    raise RuntimeError(f"oracle contains non-positive prices: {path.name}")
                if column_name == "volume" and statistics.min < 0:
                    raise RuntimeError(f"oracle contains negative volume: {path.name}")
        total_rows += rows
        total_size += path.stat().st_size
        total_imputed += int(artifact["imputed_rows"])

    coverage = manifest["coverage"]
    if total_rows != int(coverage["output_rows"]):
        raise RuntimeError("oracle artifact rows do not match coverage total")
    if total_imputed != int(coverage["imputed_rows"]):
        raise RuntimeError("oracle imputed rows do not match coverage total")
    if len(artifacts) != int(manifest["quality"]["monthly_partitions"]):
        raise RuntimeError("oracle partition count does not match quality metadata")
    if total_rows - int(coverage["source_rows"]) != total_imputed:
        raise RuntimeError("oracle source/output/imputed totals do not reconcile")
    return {
        "output_root": str(output_root),
        "partitions": len(artifacts),
        "rows": total_rows,
        "imputed_rows": total_imputed,
        "size_bytes": total_size,
        "hashes_verified": verify_hashes,
        "complete": True,
    }


def load_partitioned_oracle_prices(
    oracle_root: Path,
    event_timestamps: Iterable[Any],
    max_price_age_seconds: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load only needed UTC months and return strict-prior WETH/USDT prices."""
    if max_price_age_seconds < 1:
        raise ValueError("max_price_age_seconds must be at least 1")
    oracle_root = Path(oracle_root)
    manifest_path = oracle_root / "manifest.json"
    manifest = _read_json(manifest_path)
    artifacts = {item["month"]: item for item in manifest["artifacts"]}
    timestamps = pd.Series(list(event_timestamps), dtype="object")
    try:
        timestamps = pd.to_datetime(timestamps, utc=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("event timestamps contain an invalid value") from exc
    if timestamps.isna().any():
        raise ValueError("event timestamps contain nulls")
    if (timestamps.dt.floor("s") != timestamps).any():
        raise ValueError("event timestamps must be aligned to whole UTC seconds")
    provenance = {
        "oracle_manifest_sha256": sha256_file(manifest_path),
        "oracle_partitions": [],
        "oracle_transform": manifest["transform"],
    }
    if timestamps.empty:
        return pd.DataFrame(
            columns=("timestamp", "token0_price_usdt", "token1_price_usdt")
        ), provenance
    unique_events = pd.DatetimeIndex(timestamps.unique()).sort_values()
    required = unique_events - pd.Timedelta(seconds=1)
    requested = pd.DataFrame({"timestamp": required})
    requested["month"] = requested["timestamp"].dt.strftime("%Y-%m")

    matched: list[pd.DataFrame] = []
    used_partitions: list[str] = []
    for month, group in requested.groupby("month", sort=True):
        artifact = artifacts.get(month)
        if artifact is None:
            raise ValueError(f"oracle has no partition for required month {month}")
        path = _artifact_path(oracle_root, str(artifact["path"]))
        if not path.is_file() or path.stat().st_size != int(artifact["size_bytes"]):
            raise RuntimeError(f"oracle partition is missing or has changed: {path}")
        parquet = pq.ParquetFile(path)
        _validate_oracle_schema(parquet.schema_arrow, path.name)
        table = parquet.read(columns=["timestamp", "price"])
        prices = table.to_pandas().set_index("timestamp")["price"]
        required_index = pd.DatetimeIndex(group["timestamp"])
        values = prices.reindex(required_index)
        if values.isna().any():
            missing = required_index[values.isna()].astype(str).tolist()[:10]
            raise ValueError(
                f"oracle is missing strict-prior price rows in {path.name}: {missing}"
            )
        matched.append(
            pd.DataFrame(
                {
                    "timestamp": required_index,
                    "token0_price_usdt": values.to_numpy(dtype="float64"),
                    "token1_price_usdt": "1",
                }
            )
        )
        used_partitions.append(path.name)
    result = (
        pd.concat(matched, ignore_index=True)
        .sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    provenance["oracle_partitions"] = used_partitions
    return result, provenance
