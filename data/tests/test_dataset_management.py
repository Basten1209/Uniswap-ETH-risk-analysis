from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.manifest import (  # noqa: E402
    copy_dataset,
    load_manifest,
    sha256,
    verify_dataset,
    write_manifest,
)
from uniswap_v3_data.paths import (  # noqa: E402
    initialize_data_root,
    resolve_data_root,
)


class DataRootTest(unittest.TestCase):
    def test_resolution_precedence(self) -> None:
        self.assertEqual(
            resolve_data_root("/explicit", environ={"UNISWAP_DATA_ROOT": "/env"}),
            Path("/explicit"),
        )
        self.assertEqual(
            resolve_data_root(environ={"UNISWAP_DATA_ROOT": "/env"}, home="/home"),
            Path("/env"),
        )
        self.assertEqual(
            resolve_data_root(environ={}, home="/Users/researcher"),
            Path("/Users/researcher/Data/uniswapdata"),
        )

    def test_initialization_uses_archive_safe_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = initialize_data_root(Path(directory) / "uniswapdata")
            for relative in (
                "raw/bigquery",
                "processed",
                "derived",
                "external",
                ".staging",
                ".runs",
            ):
                self.assertTrue((root / relative).is_dir())

    def test_deleting_workspace_does_not_touch_external_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "conductor" / "workspace"
            workspace.mkdir(parents=True)
            external = base / "Data" / "uniswapdata"
            external.mkdir(parents=True)
            artifact = external / "keep.bin"
            artifact.write_bytes(b"archive-safe")
            inode = artifact.stat().st_ino
            checksum = sha256(artifact)
            shutil.rmtree(workspace.parent)
            self.assertEqual(artifact.stat().st_ino, inode)
            self.assertEqual(sha256(artifact), checksum)


class TransferTest(unittest.TestCase):
    def _fixture(self, root: Path) -> dict:
        artifacts = []
        for index in range(2):
            relative = Path("raw") / "bigquery" / "fixture" / f"part-{index}.parquet"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"value": [index, index + 1]}).to_parquet(path, index=False)
            artifacts.append(
                {
                    "path": relative.as_posix(),
                    "row_count": 2,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
        manifest = {
            "schema_version": 1,
            "dataset_id": "fixture",
            "artifacts": artifacts,
            "totals": {
                "files": 2,
                "rows": 4,
                "size_bytes": sum(item["size_bytes"] for item in artifacts),
            },
        }
        write_manifest(root / "manifest.json", manifest)
        return manifest

    def test_export_fetch_round_trip_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = initialize_data_root(base / "source")
            destination = initialize_data_root(base / "destination")
            manifest = self._fixture(source)
            second = source / manifest["artifacts"][1]["path"]
            held = second.read_bytes()
            second.unlink()
            with self.assertRaises(FileNotFoundError):
                copy_dataset(source, destination, manifest)
            first_destination = destination / manifest["artifacts"][0]["path"]
            first_inode = first_destination.stat().st_ino
            second.write_bytes(held)
            result = copy_dataset(source, destination, manifest)
            self.assertEqual(result, {"copied": 1, "skipped": 1})
            self.assertEqual(first_destination.stat().st_ino, first_inode)
            self.assertEqual(verify_dataset(destination, manifest)["rows"], 4)
            self.assertEqual(load_manifest(destination / "manifest.json"), manifest)

    def test_corruption_and_existing_file_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = initialize_data_root(base / "source")
            destination = initialize_data_root(base / "destination")
            manifest = self._fixture(source)
            target = destination / manifest["artifacts"][0]["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"do-not-overwrite")
            before = target.read_bytes()
            with self.assertRaises(RuntimeError):
                copy_dataset(source, destination, manifest)
            self.assertEqual(target.read_bytes(), before)

    def test_same_size_checksum_corruption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = initialize_data_root(Path(directory) / "root")
            manifest = self._fixture(root)
            target = root / manifest["artifacts"][0]["path"]
            corrupted = bytearray(target.read_bytes())
            corrupted[100] ^= 1
            target.write_bytes(corrupted)
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                verify_dataset(root, manifest)

    def test_missing_partial_and_unsafe_paths_fail_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = initialize_data_root(Path(directory) / "root")
            manifest = self._fixture(root)
            missing = root / manifest["artifacts"][0]["path"]
            missing.unlink()
            with self.assertRaises(FileNotFoundError):
                verify_dataset(root, manifest)
            unsafe = json.loads(json.dumps(manifest))
            unsafe["artifacts"][0]["path"] = "../escape.parquet"
            with self.assertRaises(ValueError):
                write_manifest(root / "unsafe.json", unsafe)

            partial = root / ".staging" / "interrupted.parquet.partial"
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(b"incomplete")
            with self.assertRaisesRegex(RuntimeError, "partial dataset files"):
                verify_dataset(root, manifest)


class RepositoryManifestTest(unittest.TestCase):
    def test_legacy_metadata_was_preserved_in_one_manifest(self) -> None:
        manifest = load_manifest(DATA_DIR / "manifest.json")
        self.assertEqual(manifest["dataset_id"], "11b815ef_b12376751_b25779958")
        self.assertEqual(len(manifest["artifacts"]), 192)
        self.assertEqual(manifest["totals"]["rows"], 14_443_396)
        self.assertEqual(manifest["totals"]["size_bytes"], 1_011_093_566)
        self.assertEqual(manifest["metadata_migration"]["source_file_count"], 273)
        self.assertEqual(len(manifest["collection_plans"]), 8)
        self.assertEqual(len(manifest["quality"]["source_shards"]), 3)
        self.assertEqual(
            len({item["query"]["job_id"] for item in manifest["artifacts"]}), 192
        )
        self.assertEqual(manifest["transaction_collection"]["file_count"], 64)
        self.assertEqual(manifest["transaction_collection"]["row_count"], 103_561)
        self.assertEqual(manifest["source"]["billing_projects"]["uniswapdata4"], 64)
        for artifact in manifest["artifacts"]:
            self.assertTrue(artifact["query"]["sql_sha256"])
            self.assertIn("total_bytes_billed", artifact["query"])
            self.assertFalse(Path(artifact["path"]).is_absolute())
        self.assertNotIn("/Users/", json.dumps(manifest))


if __name__ == "__main__":
    unittest.main()
