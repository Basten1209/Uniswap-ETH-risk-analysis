"""Validated configuration for the WETH/USDT data pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

FIXED_POOL_ADDRESS = "0x11b815efb8f581194ae79006d24e0d814b7697f6"
CANONICAL_FACTORY_ADDRESS = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
CANONICAL_NFPM_ADDRESS = "0xc36442b4a4522e871399cd717abdd847ab11fe88"
WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
USDT_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"


@dataclass(frozen=True)
class TokenConfig:
    symbol: str
    address: str
    decimals: int


@dataclass(frozen=True)
class ResearchConfig:
    project: str
    location: str
    network: str
    pool_address: str
    nfpm_address: str
    fee_tier: int
    token0: TokenConfig
    token1: TokenConfig
    start_date: date
    end_date: date
    start_block: int
    end_block_exclusive: int
    events_table: str
    logs_table: str
    blocks_table: str


@dataclass(frozen=True)
class FixedPoolConfig:
    project: str
    location: str
    network: str
    factory_address: str
    pool_address: str
    nfpm_address: str
    fee_tier: int
    token0: TokenConfig
    token1: TokenConfig
    events_table: str
    logs_table: str
    blocks_table: str


def _address(value: Any, field: str) -> str:
    address = str(value).lower()
    if len(address) != 42 or not address.startswith("0x"):
        raise ValueError(f"{field} must be a 20-byte 0x-prefixed address")
    try:
        int(address, 0)
    except ValueError as exc:
        raise ValueError(f"{field} is not hexadecimal: {address}") from exc
    return address


def _token(payload: dict[str, Any], field: str) -> TokenConfig:
    decimals = int(payload["decimals"])
    if decimals < 0 or decimals > 255:
        raise ValueError(f"{field}.decimals is out of range")
    symbol = str(payload["symbol"]).strip()
    if not symbol:
        raise ValueError(f"{field}.symbol is empty")
    return TokenConfig(
        symbol=symbol,
        address=_address(payload["address"], f"{field}.address"),
        decimals=decimals,
    )


def load_config(
    path: str | Path, project_override: str | None = None
) -> ResearchConfig:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    bigquery = payload["bigquery"]
    start = date.fromisoformat(str(payload["start_date"]))
    end = date.fromisoformat(str(payload["end_date"]))
    if end <= start:
        raise ValueError("end_date must be after start_date; end_date is exclusive")
    start_block = int(payload["start_block"])
    end_block_exclusive = int(payload["end_block_exclusive"])
    if start_block < 0 or end_block_exclusive <= start_block:
        raise ValueError("invalid half-open block range")
    project = (project_override or str(payload["project"])).strip()
    if not project or project == "YOUR_GOOGLE_CLOUD_PROJECT_ID":
        raise ValueError(
            "set a real Google Cloud project ID in the config or --project"
        )
    location = str(payload.get("location", "US")).strip()
    if not location:
        raise ValueError("location is empty")
    events_table = str(bigquery["events_table"]).strip(" `")
    logs_table = str(bigquery["logs_table"]).strip(" `")
    blocks_table = str(bigquery["blocks_table"]).strip(" `")
    if (
        events_table.count(".") != 2
        or logs_table.count(".") != 2
        or blocks_table.count(".") != 2
    ):
        raise ValueError("BigQuery table names must use project.dataset.table")
    pool_address = _address(payload["pool_address"], "pool_address")
    nfpm_address = _address(payload["nfpm_address"], "nfpm_address")
    fee_tier = int(payload["fee_tier"])
    token0 = _token(payload["token0"], "token0")
    token1 = _token(payload["token1"], "token1")
    if pool_address != FIXED_POOL_ADDRESS or fee_tier != 500:
        raise ValueError("selected config is not the fixed WETH/USDT 0.05% pool")
    if nfpm_address != CANONICAL_NFPM_ADDRESS:
        raise ValueError("selected config does not use the canonical Ethereum V3 NFPM")
    if {token0.address, token1.address} != {WETH_ADDRESS, USDT_ADDRESS}:
        raise ValueError("selected config token pair is not WETH/USDT")
    return ResearchConfig(
        project=project,
        location=location,
        network=str(payload["network"]),
        pool_address=pool_address,
        nfpm_address=nfpm_address,
        fee_tier=fee_tier,
        token0=token0,
        token1=token1,
        start_date=start,
        end_date=end,
        start_block=start_block,
        end_block_exclusive=end_block_exclusive,
        events_table=events_table,
        logs_table=logs_table,
        blocks_table=blocks_table,
    )


def load_fixed_pool_config(
    path: str | Path, project_override: str | None = None
) -> FixedPoolConfig:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    bigquery = payload["bigquery"]
    project = (project_override or str(payload["project"])).strip()
    if not project or project == "YOUR_GOOGLE_CLOUD_PROJECT_ID":
        raise ValueError(
            "set a real Google Cloud project ID in the config or --project"
        )
    location = str(payload.get("location", "US")).strip()
    if not location:
        raise ValueError("location is empty")
    events_table = str(bigquery["events_table"]).strip(" `")
    logs_table = str(bigquery["logs_table"]).strip(" `")
    blocks_table = str(bigquery["blocks_table"]).strip(" `")
    if (
        events_table.count(".") != 2
        or logs_table.count(".") != 2
        or blocks_table.count(".") != 2
    ):
        raise ValueError("BigQuery table names must use project.dataset.table")
    factory_address = _address(payload["factory_address"], "factory_address")
    pool_address = _address(payload["pool_address"], "pool_address")
    nfpm_address = _address(payload["nfpm_address"], "nfpm_address")
    token0 = _token(payload["token0"], "token0")
    token1 = _token(payload["token1"], "token1")
    fee_tier = int(payload["fee_tier"])
    if fee_tier != 500:
        raise ValueError("the fixed WETH/USDT pool must use the 0.05% (500) fee tier")
    if pool_address != FIXED_POOL_ADDRESS:
        raise ValueError(f"pool_address must be the fixed pool {FIXED_POOL_ADDRESS}")
    if factory_address != CANONICAL_FACTORY_ADDRESS:
        raise ValueError("factory_address is not the canonical Ethereum V3 Factory")
    if nfpm_address != CANONICAL_NFPM_ADDRESS:
        raise ValueError("nfpm_address is not the canonical Ethereum V3 NFPM")
    if {token0.address, token1.address} != {WETH_ADDRESS, USDT_ADDRESS}:
        raise ValueError("token pair must be WETH/USDT")
    return FixedPoolConfig(
        project=project,
        location=location,
        network=str(payload["network"]),
        factory_address=factory_address,
        pool_address=pool_address,
        nfpm_address=nfpm_address,
        fee_tier=fee_tier,
        token0=token0,
        token1=token1,
        events_table=events_table,
        logs_table=logs_table,
        blocks_table=blocks_table,
    )


def collection_run_id(config: ResearchConfig) -> str:
    """Stable raw-data snapshot identifier, including exact block boundaries."""
    return (
        f"{config.pool_address[2:10]}_"
        f"b{config.start_block}_b{config.end_block_exclusive}"
    )
