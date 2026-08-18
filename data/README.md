# Data Methodology

This directory documents and implements collection, preservation,
transformation, and validation for the WETH/USDT case study. The executable
BigQuery-to-clean-position workflow is described in
[`PIPELINE.md`](PIPELINE.md), with output fields in
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md). Generated datasets remain local and
are not committed.

See the [research flow](../flow.md) for the gates that data must pass before it
can support analysis.

## Data scope

The dataset covers the fixed Uniswap V3 WETH/USDT 0.05% pool
`0x11b815efb8f581194ae79006d24e0d814b7697f6` on Ethereum Mainnet. WETH is the
on-chain representation of ETH. The unit of analysis is the actual on-chain LP
position, and the analytical outcome is realized LP return. The snapshot fixes
the full available pool history. Collection is split into non-overlapping block
shards to respect query quotas; this workspace contains the completed recent
shard and a handoff config defines the historical shard. The research sample
window is chosen only after exploratory data analysis.

The following scope is fixed:

| Dimension | Fixed requirement |
| --- | --- |
| Network | Ethereum Mainnet |
| Protocol | Uniswap V3 |
| Pair and pool count | WETH/USDT 0.05%, one fixed pool |
| Collection interval | Pool's `PoolCreated` block through the latest finalized BigQuery snapshot |
| Observation unit | Actual LP position |
| Required analytical outputs | Realized return, IL, LVR, PL, and market-regime variables |

The following collection choices must be supplied and versioned before bulk
collection:

- snapshot finality depth;
- Google Cloud billing project and BigQuery budget; and
- canonical large-data storage location.

The preparation query verifies the fixed address, token pair and fee tier
against the canonical Factory, then writes the creation block and exact latest
cutoff to `config/selected_pool.json`. Google Cloud Blockchain Analytics
BigQuery tables are the primary extraction source. Direct Ethereum RPC is
reserved for validation and fallback checks.

LP-position filters, analytical start/end dates, outcome horizons, sampling
frequency, and reference-price rules are analysis choices. They are frozen
after EDA in a separate analysis configuration rather than limiting raw-data
collection.

## Source domains

Canonical Ethereum records should anchor the dataset. An RPC provider, archive
node, indexed database, or public dataset may accelerate access, but derived
records must remain reconcilable with on-chain evidence.

| Domain | Required content | Research use |
| --- | --- | --- |
| Chain and blocks | Block number, timestamp, hash, parent hash, and gas fields | Ordering, timing, finality, and gas-fee regimes |
| Pool identity | Factory verification, pool address, token ordering, fee tier, and contract version | Confirm the selected WETH/USDT pool |
| Pool activity | Swap, mint, burn, collect, liquidity, tick, and price state | Reconstruct positions, market activity, fees, and measure inputs |
| LP positions | Position identifier, ownership evidence where required, liquidity changes, collections, and transfers | Reconstruct actual position cash flows and holding intervals |
| Token metadata | Contract address, decimals, and symbol | Normalize amounts and distinguish WETH from ETH terminology |
| Prices and benchmarks | External or on-chain reference prices and other declared benchmark inputs | Value inventory and construct IL, LVR, and PL |
| Regime inputs | ETH price, volatility inputs, gas fees, transaction volume, trading activity, and approved on-chain variables | Assign market regimes without using future information |

Gas data is collected as a market-regime input. This study does not treat LP
transaction-cost or rebalancing-strategy performance as a separate data product.
Range boundaries remain necessary position and measure inputs but do not define
an additional research outcome.

## Planned data layers

The future pipeline will keep source evidence separate from research-ready
outputs.

```text
data/
├── raw/        # Immutable source extracts
├── processed/  # Decoded, normalized, and validated records
├── derived/    # Position returns, risk measures, regimes, and joined panels
└── metadata/   # Manifests, checksums, schemas, and QA reports
```

- **Raw:** preserve provider responses or canonical extracts without manual
  correction; recollection creates a new version.
- **Processed:** decode events, normalize addresses and token units, resolve
  ordering, and apply documented quality rules.
- **Derived:** construct actual position histories, realized returns, IL, LVR,
  PL, and regime features without overwriting source layers.
- **Metadata:** make every layer traceable without relying on filenames alone.

Large datasets live in Git-ignored workspace paths under the configurable data
root (or Google Cloud Storage for server-side export). Only
code, configuration, manifests, schemas, checksums, and QA summaries belong in
the repository. See [`STORAGE_POLICY.md`](STORAGE_POLICY.md) for the complete
storage, retention, and recovery rules.

## Provenance record

Every collected or generated dataset should carry at least:

| Field | Meaning |
| --- | --- |
| Dataset identifier and version | Stable name for the exact extract or transformation |
| Network and chain ID | Evidence that records come from Ethereum Mainnet |
| Pool and contracts | Selected pool, token contracts, fee tier, and ABI revisions |
| Block or time range | Half-open `[start, end)` UTC interval, block boundaries, and any known gaps |
| Source | Provider, endpoint class, dataset release, or node configuration |
| Retrieval time | UTC time at which the source was queried or copied |
| Query or transform version | Repository revision and entry point that produced the data |
| Configuration | Position rules, sampling, finality, benchmarks, and regime definitions |
| Integrity value | Checksum or equivalent content identifier where practical |
| Rights and terms | License, provider terms, and redistribution constraints |

## Validation methodology

Validation should produce a machine-readable result and a human-readable QA
summary. At minimum, the implemented pipeline must check:

1. **Network and pool identity:** chain ID, block hashes, token ordering, fee
   tier, ABI, and contracts match the declared Ethereum Mainnet pool.
2. **Coverage:** the complete declared collection interval is accounted for,
   including explicit records of gaps, retries, and provider limits.
3. **Uniqueness and ordering:** event identity, transaction order, and log order
   are stable; duplicate ingestion is rejected or deterministically removed.
4. **Decoding:** events use the intended contract ABI, and unknown or failed
   decodes are reported.
5. **Units and signs:** token decimals, signed quantities, WETH/USDT price
   conventions, fee units, and gas denominations are tested.
6. **Cross-source reconciliation:** selected event counts, pool state, balances,
   or aggregates are compared with an independent source or direct call.
7. **Reorganization handling:** the finality policy is applied, and changed block
   hashes trigger explicit recollection or invalidation.
8. **Position and economic reconciliation:** position liquidity, cash flows,
   inventory, fees, ending value, and realized return satisfy the accounting
   checks defined with the analysis.
9. **Feature timing:** reference inputs and regime variables are aligned without
   look-ahead.

Exact tolerances and reconciliation sample sizes remain TBD and must be fixed
before the data-quality gate becomes operational.

## Reproducibility and data governance

- Record time in UTC and identify intervals with block boundaries whenever
  possible.
- Keep raw data immutable and transformations deterministic.
- Store credentials and private provider endpoints outside the repository.
- Do not commit provider responses or external material without checking
  redistribution terms.
- Document missing values and exclusions rather than silently filling or
  dropping them.
- Link every derived dataset to the outcome, risk measure, or regime analysis
  that consumes it.

Executable commands, selected formats, expected outputs, and the inputs needed
to run the collection are documented in [`PIPELINE.md`](PIPELINE.md).
