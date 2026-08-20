from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.oracle import (  # noqa: E402
    ORACLE_SCHEMA,
    build_oracle_dataset,
    load_partitioned_oracle_prices,
    verify_oracle_dataset,
)


class OraclePipelineTest(unittest.TestCase):
    def _source(
        self,
        root: Path,
        files: list[tuple[str, str, list[str], list[float], list[float]]],
        *,
        quote_as_integer: bool = False,
    ) -> Path:
        source = root / "source"
        parquet_root = source / "parquet"
        parquet_root.mkdir(parents=True)
        manifest_files: dict[str, object] = {}
        all_timestamps: list[pd.Timestamp] = []
        total_rows = 0
        for period, frequency, timestamps, prices, volumes in files:
            frame = pd.DataFrame(
                {
                    "open_time": pd.to_datetime(timestamps, utc=True),
                    "close": pd.Series(prices, dtype="float64"),
                    "quote_volume": pd.Series(
                        volumes, dtype="int64" if quote_as_integer else "float64"
                    ),
                }
            )
            filename = f"ETHUSDT-1s-{period}.parquet"
            path = parquet_root / filename
            frame.to_parquet(path, index=False, compression="zstd")
            archive = f"ETHUSDT-1s-{period}.zip"
            manifest_files[archive] = {
                "spec": {"frequency": frequency, "period": period},
                "parquet_bytes": path.stat().st_size,
                "quality": {
                    "rows": len(frame),
                    "first_open_time_utc": frame["open_time"].iloc[0].isoformat(),
                    "last_open_time_utc": frame["open_time"].iloc[-1].isoformat(),
                },
            }
            all_timestamps.extend(frame["open_time"].tolist())
            total_rows += len(frame)
        manifest = {
            "dataset": "Binance spot ETHUSDT 1-second klines",
            "symbol": "ETHUSDT",
            "interval": "1s",
            "stored_start_utc": all_timestamps[0].isoformat(),
            "verification": {
                "file_count": len(files),
                "total_rows": total_rows,
                "last_open_time_utc": all_timestamps[-1].isoformat(),
            },
            "files": manifest_files,
        }
        (source / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return source

    def test_mapping_forward_fill_month_boundary_and_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-31T23:59:58Z", "2021-01-31T23:59:59Z"],
                        [10.0, 11.0],
                        [100.0, 110.0],
                    ),
                    (
                        "2021-02-01",
                        "daily",
                        ["2021-02-01T00:00:02Z", "2021-02-01T00:00:04Z"],
                        [12.0, 14.0],
                        [120.0, 140.0],
                    ),
                ],
            )
            output = root / "oracle"
            result = build_oracle_dataset(source, output)
            self.assertFalse(result["reused"])
            self.assertEqual(result["partitions"], 2)
            self.assertEqual(result["rows"], 7)
            self.assertEqual(result["imputed_rows"], 3)

            january = pq.read_table(output / "weth_usdt_1s_2021-01.parquet")
            february = pq.read_table(output / "weth_usdt_1s_2021-02.parquet")
            self.assertTrue(january.schema.equals(ORACLE_SCHEMA, check_metadata=False))
            self.assertTrue(february.schema.equals(ORACLE_SCHEMA, check_metadata=False))
            observed = february.to_pandas()
            self.assertEqual(observed["price"].tolist(), [11.0, 11.0, 12.0, 12.0, 14.0])
            self.assertEqual(observed["volume"].tolist(), [0.0, 0.0, 120.0, 0.0, 140.0])

            verified = verify_oracle_dataset(output, verify_hashes=True)
            self.assertTrue(verified["complete"])
            prices, provenance = load_partitioned_oracle_prices(
                output,
                ["2021-02-01T00:00:00Z", "2021-02-01T00:00:03Z"],
                1,
            )
            self.assertEqual(prices["token0_price_usdt"].tolist(), [11.0, 12.0])
            self.assertEqual(prices["token1_price_usdt"].tolist(), ["1", "1"])
            self.assertEqual(
                provenance["oracle_partitions"],
                [
                    "weth_usdt_1s_2021-01.parquet",
                    "weth_usdt_1s_2021-02.parquet",
                ],
            )

    def test_existing_identical_dataset_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:00Z"],
                        [10.0],
                        [100.0],
                    )
                ],
            )
            output = root / "oracle"
            build_oracle_dataset(source, output)
            result = build_oracle_dataset(source, output)
            self.assertTrue(result["reused"])

    def test_manifest_size_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:00Z"],
                        [10.0],
                        [100.0],
                    )
                ],
            )
            manifest_path = source / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            item = next(iter(manifest["files"].values()))
            item["parquet_bytes"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source size mismatch"):
                build_oracle_dataset(source, root / "oracle")

    def test_overlapping_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:00Z", "2021-01-01T00:00:01Z"],
                        [10.0, 11.0],
                        [100.0, 110.0],
                    ),
                    (
                        "2021-01-01",
                        "daily",
                        ["2021-01-01T00:00:01Z", "2021-01-01T00:00:02Z"],
                        [11.0, 12.0],
                        [110.0, 120.0],
                    ),
                ],
            )
            with self.assertRaisesRegex(ValueError, "overlap"):
                build_oracle_dataset(source, root / "oracle")

    def test_backward_timestamps_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:01Z", "2021-01-01T00:00:00Z"],
                        [11.0, 10.0],
                        [110.0, 100.0],
                    )
                ],
            )
            with self.assertRaisesRegex(ValueError, "move backward"):
                build_oracle_dataset(source, root / "oracle")

    def test_wrong_source_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:00Z"],
                        [10.0],
                        [100.0],
                    )
                ],
                quote_as_integer=True,
            )
            with self.assertRaisesRegex(ValueError, "quote_volume must be float64"):
                build_oracle_dataset(source, root / "oracle")

    def test_fractional_event_timestamp_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-01T00:00:00Z"],
                        [10.0],
                        [100.0],
                    )
                ],
            )
            output = root / "oracle"
            build_oracle_dataset(source, output)
            with self.assertRaisesRegex(ValueError, "whole UTC seconds"):
                load_partitioned_oracle_prices(
                    output, ["2021-01-01T00:00:00.500Z"], 1
                )

    def test_closed_return_cli_accepts_partitioned_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(
                root,
                [
                    (
                        "2021-01",
                        "monthly",
                        ["2021-01-31T23:59:59Z"],
                        [11.0],
                        [110.0],
                    ),
                    (
                        "2021-02-01",
                        "daily",
                        ["2021-02-01T00:00:02Z"],
                        [12.0],
                        [120.0],
                    ),
                ],
            )
            oracle = root / "oracle"
            build_oracle_dataset(source, oracle)
            positions = root / "positions.parquet"
            pd.DataFrame(
                {
                    "token_id": ["1"],
                    "entry_timestamp": ["2021-02-01T00:00:00Z"],
                    "exit_timestamp": ["2021-02-01T00:00:03Z"],
                    "deposit_amount0_raw": [str(10**18)],
                    "deposit_amount1_raw": [str(100 * 10**6)],
                    "withdraw_principal0_raw": [str(10**18)],
                    "withdraw_principal1_raw": [str(100 * 10**6)],
                    "fee_amount0_raw": ["0"],
                    "fee_amount1_raw": ["0"],
                    "is_clean_closed": [True],
                }
            ).to_parquet(positions, index=False)
            returns = root / "returns.parquet"
            metadata_root = root / "metadata"
            subprocess.run(
                [
                    sys.executable,
                    str(DATA_DIR / "scripts" / "calculate_closed_returns.py"),
                    "--data-root",
                    str(root / "data-root"),
                    "--prices",
                    str(oracle),
                    "--positions",
                    str(positions),
                    "--output",
                    str(returns),
                    "--metadata-root",
                    str(metadata_root),
                    "--max-price-age-seconds",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = pd.read_parquet(returns)
            self.assertEqual(result["token0_price_usdt_entry"].iloc[0], "11.0")
            self.assertEqual(result["token0_price_usdt_exit"].iloc[0], "12.0")
            metadata = json.loads(
                (metadata_root / "processing" / "closed_returns.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("oracle_manifest_sha256", metadata)
            self.assertNotIn("prices_sha256", metadata)
            self.assertEqual(len(metadata["oracle_partitions"]), 2)


if __name__ == "__main__":
    unittest.main()
