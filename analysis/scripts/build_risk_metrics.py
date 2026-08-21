#!/usr/bin/env python3
"""Build versioned IL, LVR, Predictable-Loss, and chart-source datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from lp_risk.pipeline import build_risk_metrics  # noqa: E402
from uniswap_v3_data.paths import resolve_data_root  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = arguments()
    data_root = resolve_data_root(args.data_root)
    artifacts = build_risk_metrics(
        data_root,
        output_root=args.output_root,
        repository_root=REPO_ROOT,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "output_root": str(artifacts.output_root),
                "position_metrics": str(artifacts.position_metrics),
                "portfolio_daily": str(artifacts.portfolio_daily),
                "representative_positions": str(artifacts.representative_positions),
                "representative_paths": str(artifacts.representative_paths),
                "manifest": str(artifacts.manifest),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
