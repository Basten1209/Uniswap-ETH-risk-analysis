"""Dataset manifest validation, integrity checks, and safe transfer helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow.parquet as pq


MANIFEST_NAME = "manifest.json"
SUPPORTED_SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: object) -> Path:
    text = str(value)
    posix = PurePosixPath(text)
    if posix.is_absolute() or not posix.parts or ".." in posix.parts:
        raise ValueError(f"manifest artifact path must stay inside the data root: {text}")
    return Path(*posix.parts)


def validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported manifest schema_version: {payload.get('schema_version')}"
        )
    if not str(payload.get("dataset_id", "")).strip():
        raise ValueError("manifest dataset_id is empty")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts must be a non-empty list")
    seen: set[Path] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("manifest artifact must be an object")
        relative = _safe_relative_path(artifact.get("path"))
        if relative in seen:
            raise ValueError(f"duplicate manifest artifact path: {relative}")
        seen.add(relative)
        digest = str(artifact.get("sha256", ""))
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"invalid SHA-256 for {relative}")
        if int(artifact.get("row_count", -1)) < 0:
            raise ValueError(f"invalid row_count for {relative}")
        if int(artifact.get("size_bytes", -1)) < 0:
            raise ValueError(f"invalid size_bytes for {relative}")
    return payload


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return validate_manifest(payload)


def write_manifest(path: str | Path, payload: dict[str, Any]) -> None:
    validate_manifest(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def verify_artifact(root: Path, artifact: dict[str, Any]) -> None:
    relative = _safe_relative_path(artifact["path"])
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"missing dataset artifact: {path}")
    expected_size = int(artifact["size_bytes"])
    if path.stat().st_size != expected_size:
        raise RuntimeError(
            f"size mismatch for {path}: {path.stat().st_size} != {expected_size}"
        )
    expected_rows = int(artifact["row_count"])
    observed_rows = pq.ParquetFile(path).metadata.num_rows
    if observed_rows != expected_rows:
        raise RuntimeError(
            f"row mismatch for {path}: {observed_rows} != {expected_rows}"
        )
    observed_hash = sha256(path)
    if observed_hash != artifact["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {path}: {observed_hash} != {artifact['sha256']}"
        )


def verify_dataset(root: Path, manifest: dict[str, Any]) -> dict[str, int]:
    partials = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(".partial")
    ]
    if partials:
        raise RuntimeError(f"partial dataset files remain: {partials[0]}")
    files = rows = size_bytes = 0
    for artifact in manifest["artifacts"]:
        verify_artifact(root, artifact)
        files += 1
        rows += int(artifact["row_count"])
        size_bytes += int(artifact["size_bytes"])
    result = {"files": files, "rows": rows, "size_bytes": size_bytes}
    declared = manifest.get("totals", {})
    for key, observed in result.items():
        if key in declared and int(declared[key]) != observed:
            raise RuntimeError(
                f"manifest total mismatch for {key}: {declared[key]} != {observed}"
            )
    return result


def copy_dataset(
    source_root: Path,
    destination_root: Path,
    manifest: dict[str, Any],
) -> dict[str, int]:
    """Copy manifest-listed files safely, allowing resumable matching files."""

    source_root = source_root.resolve()
    destination_root = destination_root.resolve()
    if source_root == destination_root:
        raise ValueError("source and destination data roots are identical")
    destination_manifest = destination_root / MANIFEST_NAME
    if destination_manifest.exists():
        existing = load_manifest(destination_manifest)
        if existing["dataset_id"] != manifest["dataset_id"]:
            raise RuntimeError(
                "destination contains another dataset: "
                f"{existing['dataset_id']} != {manifest['dataset_id']}"
            )
    copied = skipped = 0
    staging_root = destination_root / ".staging" / "transfer"
    for artifact in manifest["artifacts"]:
        relative = _safe_relative_path(artifact["path"])
        source = source_root / relative
        verify_artifact(source_root, artifact)
        destination = destination_root / relative
        if destination.exists():
            verify_artifact(destination_root, artifact)
            skipped += 1
            continue
        staged = staging_root / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        if staged.exists():
            staged.unlink()
        shutil.copy2(source, staged)
        temporary_artifact = {**artifact, "path": str(relative.as_posix())}
        verify_artifact(staging_root, temporary_artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        copied += 1
    write_manifest(destination_manifest, manifest)
    return {"copied": copied, "skipped": skipped}
