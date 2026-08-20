"""Build or verify the partitioned Binance ETHUSDT 1-second oracle dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.oracle import build_oracle_dataset, verify_oracle_dataset
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="directory containing the Binance manifest.json and parquet/ files",
    )
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "default: <data-root>/external/oracle/binance_ethusdt_1s; "
            "must remain outside the repository"
        ),
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify an existing output without rebuilding it",
    )
    parser.add_argument(
        "--skip-hashes",
        action="store_true",
        help="with --verify-only, skip full partition SHA-256 checks",
    )
    args = parser.parse_args()

    data_root = initialize_data_root(resolve_data_root(args.data_root))
    output = args.output or (
        data_root / "external" / "oracle" / "binance_ethusdt_1s"
    )
    if args.verify_only:
        result = verify_oracle_dataset(output, verify_hashes=not args.skip_hashes)
    else:
        result = build_oracle_dataset(args.source_root, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
