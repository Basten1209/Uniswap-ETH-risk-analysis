"""Value clean-closed positions and calculate fee-inclusive terminal returns."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import load_config
from uniswap_v3_data.returns import calculate_closed_returns


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".gz"}:
        return pd.read_csv(path, dtype=str)
    raise ValueError(f"unsupported input format: {path}; use CSV or parquet")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATA_DIR / "config" / "selected_pool.json",
    )
    parser.add_argument("--project", help="override config project for validation")
    parser.add_argument("--data-root", type=Path, default=DATA_DIR)
    parser.add_argument("--metadata-root", type=Path, default=DATA_DIR / "metadata")
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument(
        "--positions",
        type=Path,
        help="default: data/derived/positions/clean_closed_positions.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="default: data/derived/returns/clean_closed_returns.parquet",
    )
    parser.add_argument("--max-price-age-seconds", type=int, default=3600)
    args = parser.parse_args()

    config = load_config(args.config, args.project)
    positions_path = args.positions or (
        args.data_root / "derived" / "positions" / "clean_closed_positions.parquet"
    )
    output_path = args.output or (
        args.data_root / "derived" / "returns" / "clean_closed_returns.parquet"
    )
    positions = read_table(positions_path)
    prices = read_table(args.prices)
    result = calculate_closed_returns(
        positions,
        prices,
        config.token0.decimals,
        config.token1.decimals,
        args.max_price_age_seconds,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".parquet.partial")
    result.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(output_path)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(args.config.resolve()),
        "positions_path": str(positions_path.resolve()),
        "positions_sha256": sha256(positions_path),
        "prices_path": str(args.prices.resolve()),
        "prices_sha256": sha256(args.prices),
        "output_path": str(output_path.resolve()),
        "output_sha256": sha256(output_path),
        "row_count": len(result),
        "max_price_age_seconds": args.max_price_age_seconds,
        "valuation_convention": (
            "entry deposits valued at last oracle price at/before entry; principal and "
            "lifetime fees valued at last oracle price at/before final liquidity decrease; "
            "collected fee tokens assumed held until exit; gas excluded"
        ),
        "fee_identity": "sum(NFPM Collect) - sum(NFPM DecreaseLiquidity principal)",
    }
    metadata_path = args.metadata_root / "processing" / "closed_returns.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"saved {len(result):,} closed-position returns to {output_path}")
    print(f"metadata: {metadata_path}")


if __name__ == "__main__":
    main()
