"""Decode raw events and build auditable clean-burned NFPM positions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.config import collection_run_id, load_config
from uniswap_v3_data.events import parse_raw_events
from uniswap_v3_data.positions import (
    link_pool_mints_to_nfpm,
    reconstruct_positions_from_links,
    summarize_pool_daily,
)


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.partial")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


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
    args = parser.parse_args()

    config = load_config(args.config, args.project)
    run_id = collection_run_id(config)
    raw_paths = sorted(
        (args.data_root / "raw" / "bigquery" / run_id / "events").glob("*.parquet")
    )
    raw_block_paths = sorted(
        (args.data_root / "raw" / "bigquery" / run_id / "block_daily").glob("*.parquet")
    )
    if not raw_paths:
        raise FileNotFoundError(
            "no raw event parquet files; run data/scripts/collect_bigquery.py --execute first"
        )

    processed_root = args.data_root / "processed"
    all_links: list[pd.DataFrame] = []
    all_daily: list[pd.DataFrame] = []
    processed_nfpm_paths: list[Path] = []
    raw_rows = pool_rows = nfpm_rows = 0
    duplicate_events = 0

    for raw_path in raw_paths:
        raw = pd.read_parquet(raw_path)
        raw_rows += len(raw)
        duplicate_events += int(raw.duplicated(["block_number", "log_index"]).sum())
        pool, nfpm = parse_raw_events(raw, config.pool_address, config.nfpm_address)
        pool_rows += len(pool)
        nfpm_rows += len(nfpm)
        stem = raw_path.stem.removeprefix("events_")
        pool_path = processed_root / "pool_events" / f"pool_events_{stem}.parquet"
        nfpm_path = processed_root / "nfpm_events" / f"nfpm_events_{stem}.parquet"
        write_parquet(pool, pool_path)
        write_parquet(nfpm, nfpm_path)
        processed_nfpm_paths.append(nfpm_path)

        links = link_pool_mints_to_nfpm(pool, nfpm, config.nfpm_address)
        if not links.empty:
            all_links.append(links)
        daily = summarize_pool_daily(pool)
        if not daily.empty:
            all_daily.append(daily)
        print(
            f"parsed {raw_path.name}: pool={len(pool):,}, nfpm={len(nfpm):,}, "
            f"target links={len(links):,}",
            flush=True,
        )

    if duplicate_events:
        raise RuntimeError(
            f"raw input contains {duplicate_events} duplicate block/log event keys"
        )
    if not all_links:
        raise RuntimeError(
            "no target-pool Mint could be linked to NFPM IncreaseLiquidity; "
            "verify pool/NFPM addresses and raw-log coverage"
        )

    links = (
        pd.concat(all_links, ignore_index=True)
        .sort_values(["block_number", "pool_mint_log_index"], kind="stable")
        .reset_index(drop=True)
    )
    target_ids = set(links["token_id"].astype(str))
    target_event_frames: list[pd.DataFrame] = []
    for path in processed_nfpm_paths:
        nfpm = pd.read_parquet(path)
        selected = nfpm.loc[nfpm["token_id"].astype(str).isin(target_ids)]
        if not selected.empty:
            target_event_frames.append(selected)
    target_events = (
        pd.concat(target_event_frames, ignore_index=True)
        .sort_values(["block_number", "transaction_index", "log_index"], kind="stable")
        .reset_index(drop=True)
    )

    positions, clean = reconstruct_positions_from_links(
        links, target_events, config.start_date, config.end_date
    )
    daily = pd.concat(all_daily, ignore_index=True).sort_values("date", kind="stable")
    if daily["date"].duplicated().any():
        # Only possible when overlapping raw intervals were supplied.
        raise RuntimeError(
            "daily pool output has duplicate dates; raw intervals overlap"
        )

    block_daily_frames: list[pd.DataFrame] = []
    block_rows = 0
    for path in raw_block_paths:
        blocks = pd.read_parquet(path)
        if "block_count" in blocks:
            block_rows += int(pd.to_numeric(blocks["block_count"]).sum())
        if not blocks.empty:
            blocks["date"] = pd.to_datetime(blocks["date"]).dt.date
            block_daily_frames.append(blocks)
    block_daily = (
        pd.concat(block_daily_frames, ignore_index=True).sort_values(
            "date", kind="stable"
        )
        if block_daily_frames
        else pd.DataFrame()
    )
    if not block_daily.empty and block_daily["date"].duplicated().any():
        raise RuntimeError(
            "daily block output has duplicate dates; raw intervals overlap"
        )

    outputs = {
        "links": processed_root / "position_links" / "pool_mint_nfpm_links.parquet",
        "target_events": processed_root
        / "position_events"
        / "target_nfpm_events.parquet",
        "pool_daily": processed_root / "pool_daily" / "pool_daily.parquet",
        "block_daily": processed_root / "block_daily" / "block_daily.parquet",
        "all_positions": args.data_root
        / "derived"
        / "positions"
        / "all_target_positions.parquet",
        "clean_positions": args.data_root
        / "derived"
        / "positions"
        / "clean_closed_positions.parquet",
    }
    write_parquet(links, outputs["links"])
    write_parquet(target_events, outputs["target_events"])
    write_parquet(daily, outputs["pool_daily"])
    if not block_daily.empty:
        write_parquet(block_daily, outputs["block_daily"])
    write_parquet(positions, outputs["all_positions"])
    write_parquet(clean, outputs["clean_positions"])

    exclusion_counts = {
        "not_clean_closed": int((~positions["is_clean_closed"]).sum()),
        "multiple_or_missing_increase": int((positions["increase_count"] != 1).sum()),
        "multiple_or_missing_decrease": int((positions["decrease_count"] != 1).sum()),
        "not_fully_withdrawn": int((~positions["is_fully_withdrawn"]).sum()),
        "not_burned": int((~positions["is_nft_burned"]).sum()),
        "ownership_transferred": int(
            (positions["ownership_transfer_count"] != 0).sum()
        ),
        "fee_not_nonnegative": int((~positions["has_nonnegative_fee"]).sum()),
        "outside_study_window": int(
            (
                ~(
                    positions["entry_in_study_window"]
                    & positions["exit_in_study_window"]
                    & positions["settlement_in_study_window"]
                )
            ).sum()
        ),
    }
    qc = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(args.config.resolve()),
        "raw_file_count": len(raw_paths),
        "raw_row_count": raw_rows,
        "pool_event_count": pool_rows,
        "nfpm_event_count_all_pools": nfpm_rows,
        "block_count": block_rows,
        "target_position_count": len(positions),
        "clean_closed_position_count": len(clean),
        "clean_share_of_target_positions": (
            float(len(clean) / len(positions)) if len(positions) else None
        ),
        "exclusion_counts_nonexclusive": exclusion_counts,
        "outputs": {
            name: {
                "path": str(path),
                "row_count": int(
                    {
                        "links": len(links),
                        "target_events": len(target_events),
                        "pool_daily": len(daily),
                        "block_daily": len(block_daily),
                        "all_positions": len(positions),
                        "clean_positions": len(clean),
                    }[name]
                ),
                "sha256": sha256(path),
            }
            for name, path in outputs.items()
            if path.exists()
        },
    }
    qc_path = args.metadata_root / "processing" / "build_clean_positions_qc.json"
    write_json(qc_path, qc)
    print(
        f"built {len(positions):,} target positions; {len(clean):,} are clean-closed. "
        f"QC: {qc_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
