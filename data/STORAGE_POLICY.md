# Large-data storage policy

Uniswap event history is too large for normal Git storage. This project keeps
the reproducible recipe and provenance in Git while storing data artifacts in
Git-ignored workspace paths.

## What belongs in Git

- collection and transformation code;
- the fixed pool configuration and exact block snapshot;
- generated SQL;
- query job IDs, byte counts, row counts, hashes and QA reports;
- schemas and data dictionaries; and
- small synthetic test fixtures only.

## What must not enter Git

- raw BigQuery extracts;
- downloaded Oracle or interest-rate files;
- processed event parquet;
- derived position, metric or model datasets; and
- notebooks containing embedded copies of large data.

The repository `.gitignore` excludes `data/raw/`, `data/processed/`,
`data/derived/` and `data/external/`. Git LFS is not the default solution:
multi-gigabyte raw event history remains expensive to clone and difficult to
version even when stored through LFS.

## Recommended layout

The current machine has no external disk, so use the repository's ignored
`data/` subdirectories as the data root while leaving metadata trackable.

```text
repository/data/
├── raw/bigquery/POOL_BLOCK_SNAPSHOT/
├── processed/
├── derived/
├── external/
└── metadata/
├── pool_snapshot/
├── bigquery/
└── processing/
```

Pass the roots explicitly:

```bash
--data-root data \
--metadata-root data/metadata
```

Do not use a temporary directory or a cloud-synced desktop folder as the only
copy of raw data.

## Storage tiers

| Layer | Canonical location | Mutation rule | Backup rule |
| --- | --- | --- | --- |
| Raw | Git-ignored workspace path or GCS | Immutable; never overwrite | Keep at least one second copy before paper freeze |
| Processed | Git-ignored workspace path/GCS | Rebuild when code or config changes | Optional if reproducible |
| Derived | Git-ignored workspace path/GCS | Version by config/code hash | Preserve outputs used in paper |
| Metadata | Git | Review changes | Normal Git remote |

The raw run ID includes the exact half-open block snapshot, and monthly
filenames include their UTC partition interval. Collection scripts refuse to
overwrite an existing raw file and write SHA-256, row counts and BigQuery job
metadata for each completed query.

## Download strategies

### 1. Monthly BigQuery to local/external disk

This repository's default collector runs partition-bounded monthly queries and
writes parquet directly to `--data-root`. It is the simplest method when the
machine has enough free space and a stable connection. Interrupted collection
can resume because existing immutable months are skipped.

### 2. BigQuery to Google Cloud Storage

For full pool history, prefer materializing results in BigQuery and exporting
Parquet shards to GCS. The generated monthly SQL can be used as the SELECT in:

```sql
EXPORT DATA OPTIONS (
  uri='gs://YOUR_BUCKET/uniswap/raw/events_YYYY_MM_*.parquet',
  format='PARQUET',
  compression='SNAPPY',
  overwrite=false
) AS
SELECT ...;
```

GCS becomes the canonical raw layer. Download only the months required for
local processing:

```bash
gcloud storage rsync \
  gs://YOUR_BUCKET/uniswap/raw/POOL_BLOCK_SNAPSHOT/ \
  data/raw/bigquery/POOL_BLOCK_SNAPSHOT/
```

This avoids routing a large query result through one Python process and is the
recommended production path when local capacity is uncertain.

### 3. BigQuery destination tables plus `bq extract`

Another server-side option is to write each monthly query to a user-owned,
expiration-controlled BigQuery table and use `bq extract` to create GCS
Parquet. Destination tables should have an expiration policy because the raw
Parquet layer, not duplicate BigQuery tables, is the long-term archive.

## Capacity and retention rules

1. Run BigQuery dry runs before execution; do not extrapolate full pool history
   from a one-day sample alone.
2. Verify at least twice the expected local output space before direct local
   collection. This leaves room for raw plus processed outputs.
3. Keep raw and external source data immutable. Corrections create a new run ID.
4. Processed data may be deleted only after its raw inputs, config, code commit
   and rebuild command are recorded.
5. Before deleting a GCS or external-disk raw copy, verify another copy and its
   checksum manifest.
6. Paper tables and figures must record the selected-pool config, input hashes
   and processing QA manifest.
