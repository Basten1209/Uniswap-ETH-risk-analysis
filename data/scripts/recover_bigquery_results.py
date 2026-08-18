"""Recover immutable artifacts from completed BigQuery jobs without re-querying."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import bigquery


DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR / "src"))

from uniswap_v3_data.manifest import load_manifest, verify_artifact  # noqa: E402
from uniswap_v3_data.paths import initialize_data_root, resolve_data_root  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="project that owns the jobs")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    args = parser.parse_args()

    root = initialize_data_root(resolve_data_root(args.data_root))
    manifest = load_manifest(args.manifest)
    artifacts = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["query"]["project"] == args.project
    ]
    if not artifacts:
        raise RuntimeError(f"manifest has no jobs owned by project {args.project}")

    staging_root = root / ".staging" / "bigquery-job-results" / args.project
    clients: dict[str, bigquery.Client] = {}
    recovered = skipped = 0
    for index, artifact in enumerate(artifacts, start=1):
        target = root / artifact["path"]
        if target.exists():
            verify_artifact(root, artifact)
            skipped += 1
            print(f"[{index}/{len(artifacts)}] verified {target.name}", flush=True)
            continue

        staged = staging_root / artifact["path"]
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged_artifact = {
            **artifact,
            "path": staged.relative_to(staging_root).as_posix(),
        }
        if staged.exists():
            verify_artifact(staging_root, staged_artifact)
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            recovered += 1
            print(f"[{index}/{len(artifacts)}] promoted {target.name}", flush=True)
            continue

        partial = staged.with_suffix(staged.suffix + ".partial")
        if partial.exists():
            partial.unlink()
        query = artifact["query"]
        location = str(query["location"])
        client = clients.setdefault(
            location,
            bigquery.Client(project=args.project, location=location),
        )
        try:
            job = client.get_job(
                str(query["job_id"]),
                project=args.project,
                location=location,
            )
            if job.state != "DONE" or job.error_result:
                raise RuntimeError(
                    "BigQuery job is not a successful completed job: "
                    f"{job.job_id}"
                )
            frame = job.result().to_arrow(create_bqstorage_client=False).to_pandas()
        except (Forbidden, NotFound) as exc:
            raise RuntimeError(
                f"cannot read saved job result {args.project}:{query['job_id']}; "
                "authenticate the owning Google account, or confirm that the result "
                "has expired. No query was executed."
            ) from exc
        if len(frame) != int(artifact["row_count"]):
            raise RuntimeError(
                f"job row mismatch for {query['job_id']}: "
                f"{len(frame)} != {artifact['row_count']}"
            )
        frame.to_parquet(partial, index=False, compression="zstd")
        partial_artifact = {
            **artifact,
            "path": partial.relative_to(staging_root).as_posix(),
        }
        verify_artifact(staging_root, partial_artifact)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial.replace(target)
        recovered += 1
        print(f"[{index}/{len(artifacts)}] recovered {target.name}", flush=True)

    print(
        json.dumps(
            {
                "project": args.project,
                "expected_files": len(artifacts),
                "recovered": recovered,
                "verified_existing": skipped,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
