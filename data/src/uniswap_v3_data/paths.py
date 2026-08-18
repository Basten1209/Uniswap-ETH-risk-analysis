"""Shared, archive-safe data-root resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


DATA_ROOT_ENV = "UNISWAP_DATA_ROOT"
DATA_DIRECTORIES = (
    Path("raw") / "bigquery",
    Path("processed"),
    Path("derived"),
    Path("external"),
    Path(".staging"),
    Path(".runs"),
)


def resolve_data_root(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    """Resolve the shared data root without depending on a Git worktree."""

    if explicit is not None:
        return Path(explicit).expanduser()
    environment = os.environ if environ is None else environ
    configured = environment.get(DATA_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    home_path = Path.home() if home is None else Path(home).expanduser()
    return home_path / "Data" / "uniswapdata"


def initialize_data_root(root: str | Path) -> Path:
    """Create the stable layer layout and return the normalized root."""

    resolved = resolve_data_root(root)
    resolved.mkdir(parents=True, exist_ok=True)
    for relative in DATA_DIRECTORIES:
        (resolved / relative).mkdir(parents=True, exist_ok=True)
    return resolved
