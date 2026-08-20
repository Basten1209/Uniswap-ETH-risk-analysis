"""Unified entry point for the versioned Uniswap research dataset."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_DIR.parent
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.manifest import (  # noqa: E402
    MANIFEST_NAME,
    copy_dataset,
    load_manifest,
    verify_dataset,
    write_manifest,
)
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root  # noqa: E402


REPOSITORY_MANIFEST = DATA_DIR / MANIFEST_NAME
COLLECTION_CONFIG = DATA_DIR / "config" / "selected_pool.json"


def runtime_manifest_path(data_root: Path) -> Path:
    path = data_root / MANIFEST_NAME
    return path if path.exists() else REPOSITORY_MANIFEST


def install_manifest(data_root: Path) -> None:
    repository_manifest = load_manifest(REPOSITORY_MANIFEST)
    destination = data_root / MANIFEST_NAME
    if destination.exists():
        existing = load_manifest(destination)
        if existing["dataset_id"] != repository_manifest["dataset_id"]:
            raise RuntimeError(
                f"data root contains another dataset: {existing['dataset_id']}"
            )
        if existing == repository_manifest:
            return
    write_manifest(destination, repository_manifest)


def command_init(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    print(json.dumps({"data_root": str(root), "manifest": str(root / MANIFEST_NAME)}, indent=2))


def command_status(args: argparse.Namespace) -> None:
    root = resolve_data_root(args.data_root)
    manifest = load_manifest(runtime_manifest_path(root))
    present = missing = bytes_present = 0
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        if path.is_file():
            present += 1
            bytes_present += path.stat().st_size
        else:
            missing += 1
    partials = sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(".partial")
    )
    print(
        json.dumps(
            {
                "data_root": str(root),
                "dataset_id": manifest["dataset_id"],
                "expected_files": len(manifest["artifacts"]),
                "present_files": present,
                "missing_files": missing,
                "bytes_present": bytes_present,
                "partial_files": partials,
                "complete": missing == 0 and partials == 0,
            },
            indent=2,
        )
    )


def command_verify(args: argparse.Namespace) -> None:
    root = resolve_data_root(args.data_root)
    manifest = load_manifest(runtime_manifest_path(root))
    result = verify_dataset(root, manifest)
    print(json.dumps({"data_root": str(root), "status": "verified", **result}, indent=2))


def command_fetch(args: argparse.Namespace) -> None:
    source = resolve_data_root(args.source)
    destination = initialize_data_root(args.data_root)
    manifest = load_manifest(source / MANIFEST_NAME)
    result = copy_dataset(source, destination, manifest)
    print(json.dumps({"source": str(source), "destination": str(destination), **result}, indent=2))


def command_export(args: argparse.Namespace) -> None:
    source = resolve_data_root(args.data_root)
    destination = initialize_data_root(args.destination)
    manifest = load_manifest(runtime_manifest_path(source))
    result = copy_dataset(source, destination, manifest)
    print(json.dumps({"source": str(source), "destination": str(destination), **result}, indent=2))


def run_repository_script(name: str, arguments: list[str]) -> None:
    command = [sys.executable, str(DATA_DIR / "scripts" / name), *arguments]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def command_collect(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    arguments = [
        "--config",
        str(COLLECTION_CONFIG),
        "--project",
        args.project,
        "--data-root",
        str(root),
        "--metadata-root",
        str(root / ".runs"),
        "--budget-bytes",
        str(args.budget_bytes),
    ]
    if args.max_jobs is not None:
        arguments.extend(["--max-jobs", str(args.max_jobs)])
    if not args.dry_run:
        arguments.append("--execute")
    run_repository_script("collect_bigquery.py", arguments)


def command_build(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    run_repository_script(
        "build_clean_positions.py",
        [
            "--config",
            str(COLLECTION_CONFIG),
            "--data-root",
            str(root),
            "--metadata-root",
            str(root / ".runs"),
        ],
    )


def command_collect_transactions(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    arguments = [
        "--config",
        str(COLLECTION_CONFIG),
        "--project",
        args.project,
        "--data-root",
        str(root),
        "--metadata-root",
        str(root / ".runs"),
        "--budget-bytes",
        str(args.budget_bytes),
    ]
    if args.max_jobs is not None:
        arguments.extend(["--max-jobs", str(args.max_jobs)])
    if not args.dry_run:
        arguments.append("--execute")
    run_repository_script("collect_transaction_senders.py", arguments)
    if not args.dry_run and args.max_jobs is None:
        run_repository_script(
            "register_transaction_artifacts.py",
            [
                "--config",
                str(COLLECTION_CONFIG),
                "--project",
                args.project,
                "--data-root",
                str(root),
                "--manifest",
                str(REPOSITORY_MANIFEST),
            ],
        )
        install_manifest(root)


def command_build_operation_pairs(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    run_repository_script(
        "build_operation_pairs.py",
        [
            "--config",
            str(COLLECTION_CONFIG),
            "--data-root",
            str(root),
            "--metadata-root",
            str(root / ".runs"),
        ],
    )


def command_build_pair_returns(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    arguments = [
        "--config",
        str(COLLECTION_CONFIG),
        "--data-root",
        str(root),
        "--metadata-root",
        str(root / ".runs"),
        "--max-price-age-seconds",
        str(args.max_price_age_seconds),
    ]
    if args.oracle_root is not None:
        arguments.extend(["--oracle-root", str(args.oracle_root)])
    run_repository_script("build_pair_returns.py", arguments)


def command_recover(args: argparse.Namespace) -> None:
    root = initialize_data_root(args.data_root)
    install_manifest(root)
    run_repository_script(
        "recover_bigquery_results.py",
        [
            "--project",
            args.project,
            "--data-root",
            str(root),
            "--manifest",
            str(REPOSITORY_MANIFEST),
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        help="override UNISWAP_DATA_ROOT and the default ~/Data/uniswapdata",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the stable data layout")
    init_parser.set_defaults(handler=command_init)
    status_parser = subparsers.add_parser("status", help="show dataset availability")
    status_parser.set_defaults(handler=command_status)
    verify_parser = subparsers.add_parser("verify", help="verify every artifact")
    verify_parser.set_defaults(handler=command_verify)

    fetch_parser = subparsers.add_parser("fetch", help="receive a direct-transfer dataset")
    fetch_parser.add_argument("--source", type=Path, required=True)
    fetch_parser.set_defaults(handler=command_fetch)

    export_parser = subparsers.add_parser("export", help="create a direct-transfer dataset")
    export_parser.add_argument("--destination", type=Path, required=True)
    export_parser.set_defaults(handler=command_export)

    collect_parser = subparsers.add_parser("collect", help="reproduce raw data from BigQuery")
    collect_parser.add_argument("--project", required=True)
    collect_parser.add_argument("--budget-bytes", type=int, required=True)
    collect_parser.add_argument("--max-jobs", type=int)
    collect_parser.add_argument("--dry-run", action="store_true")
    collect_parser.set_defaults(handler=command_collect)

    transaction_parser = subparsers.add_parser(
        "collect-transactions",
        help="collect transaction identity for target-pool Mint/Burn logs",
    )
    transaction_parser.add_argument("--project", required=True)
    transaction_parser.add_argument("--budget-bytes", type=int, required=True)
    transaction_parser.add_argument("--max-jobs", type=int)
    transaction_parser.add_argument("--dry-run", action="store_true")
    transaction_parser.set_defaults(handler=command_collect_transactions)

    build_data_parser = subparsers.add_parser("build", help="rebuild processed and derived layers")
    build_data_parser.set_defaults(handler=command_build)
    pair_parser = subparsers.add_parser(
        "build-operation-pairs",
        help="build transaction-identified Pool Mint/Burn pairs",
    )
    pair_parser.set_defaults(handler=command_build_operation_pairs)
    return_parser = subparsers.add_parser(
        "build-pair-returns",
        help="build realized-fee returns for non-same-block operation pairs",
    )
    return_parser.add_argument("--oracle-root", type=Path)
    return_parser.add_argument("--max-price-age-seconds", type=int, default=3600)
    return_parser.set_defaults(handler=command_build_pair_returns)
    recover_parser = subparsers.add_parser(
        "recover", help="recover still-retained completed BigQuery job results"
    )
    recover_parser.add_argument("--project", required=True)
    recover_parser.set_defaults(handler=command_recover)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.data_root is None:
        args.data_root = resolve_data_root(environ=os.environ)
    args.handler(args)


if __name__ == "__main__":
    main()
