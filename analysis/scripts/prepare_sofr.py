#!/usr/bin/env python3
"""Freeze a dense effective-date SOFR snapshot for Predictable Loss."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pandas_datareader.data as web
import pyarrow as pa
import pyarrow.parquet as pq


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "src"))

from uniswap_v3_data.paths import resolve_data_root  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--start", default="2021-05-05")
    parser.add_argument("--end", default="2026-08-19", help="exclusive UTC date")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    data_root = resolve_data_root(args.data_root)
    output_root = data_root / "external" / "rates" / "sofr_daily"
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "sofr_daily.parquet"
    manifest_path = output_root / "manifest.json"
    if output_path.exists() or manifest_path.exists():
        if not output_path.is_file() or not manifest_path.is_file():
            raise RuntimeError("SOFR snapshot is incomplete; remove it explicitly before retrying")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = manifest.get("artifact", {})
        if (
            artifact.get("path") != output_path.name
            or output_path.stat().st_size != int(artifact.get("size_bytes", -1))
            or sha256_file(output_path) != artifact.get("sha256")
        ):
            raise RuntimeError("existing SOFR snapshot does not match its manifest")
        requested_start = pd.Timestamp(args.start, tz="UTC")
        requested_end = pd.Timestamp(args.end, tz="UTC") - pd.Timedelta(days=1)
        if (
            pd.Timestamp(manifest["coverage"]["start_utc"]) != requested_start
            or pd.Timestamp(manifest["coverage"]["end_utc_inclusive"])
            != requested_end
        ):
            raise RuntimeError("existing SOFR snapshot has different requested coverage")
        print(json.dumps({"status": "reused", "path": str(output_path)}, indent=2))
        return

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    if end <= start:
        raise ValueError("end must be after start")
    source = web.DataReader(
        "SOFR",
        "fred",
        (start - pd.Timedelta(days=14)).date(),
        (end - pd.Timedelta(days=1)).date(),
    )
    source.index = pd.to_datetime(source.index, utc=True)
    calendar = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    dense = source.rename(columns={"SOFR": "sofr_percent"}).reindex(calendar).ffill()
    if dense["sofr_percent"].isna().any():
        raise RuntimeError("FRED did not provide a pre-start SOFR observation")
    frame = dense.rename_axis("date").reset_index()
    frame["sofr_percent"] = frame["sofr_percent"].astype("float64")
    schema = pa.schema(
        [
            pa.field("date", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("sofr_percent", pa.float64(), nullable=False),
        ]
    )
    partial = output_path.with_suffix(".parquet.partial")
    pq.write_table(
        pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True),
        partial,
        compression="zstd",
    )
    partial.replace(output_path)
    manifest = {
        "schema_version": 1,
        "series": "SOFR",
        "provider": "Federal Reserve Bank of St. Louis FRED",
        "source_url": "https://fred.stlouisfed.org/series/SOFR",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage": {
            "start_utc": frame["date"].iloc[0].isoformat(),
            "end_utc_inclusive": frame["date"].iloc[-1].isoformat(),
            "calendar_days": len(frame),
            "missing_policy": "effective-date observations, calendar-day forward-fill",
        },
        "artifact": {
            "path": output_path.name,
            "rows": len(frame),
            "size_bytes": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
        },
    }
    partial_manifest = manifest_path.with_suffix(".json.partial")
    partial_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    partial_manifest.replace(manifest_path)
    print(json.dumps({"status": "created", "path": str(output_path), **manifest}, indent=2))


if __name__ == "__main__":
    main()
