# Data Methodology

This directory documents how the project will collect, preserve, transform, and
validate data for Ethereum Mainnet Uniswap V3 LP risk analysis. It currently
contains documentation only; no datasets or download pipeline have been added.

See the [research flow](../flow.md) for the gates that data must pass before it
can support analysis.

## Data scope

The intended data universe is limited to Uniswap V3 on Ethereum Mainnet. The
primary analytical perspective is the liquidity provider, with pool-level and
position-level observations used where the final design requires them.

The following study choices remain TBD and must be versioned before bulk data
collection:

- study start and end block or timestamp;
- included pool and token addresses;
- included fee tiers;
- minimum liquidity, volume, or history requirements;
- LP-position inclusion and exclusion rules;
- sampling frequency and finality policy;
- data-access provider and fallback provider.

## Source domains

Canonical Ethereum records should anchor the dataset. A final source plan may
use an RPC provider, archive node, indexed database, or public dataset for access,
but accelerated sources must be reconciled against on-chain evidence.

| Domain | Candidate content | Research use |
| --- | --- | --- |
| Chain and blocks | Block number, timestamp, hash, parent hash, and gas fields | Ordering, timing, cost conversion, and reorganization checks |
| Uniswap V3 registry | Factory-created pool addresses, token pairs, and fee tiers | Define and verify the pool universe |
| Pool activity | Swap, mint, burn, collect, liquidity, tick, and price state | Reconstruct market activity, liquidity, and fee-generating periods |
| LP positions | Position ownership, liquidity changes, collections, and transfers where required | Reconstruct position cash flows and holding intervals |
| Tokens | Contract address, decimals, symbol, and supply metadata where relevant | Normalize units and identify assets |
| Benchmarks | Reference prices and gas valuation inputs selected in the study design | Value inventory, costs, and passive-hold comparisons |

This table defines data domains, not a selected vendor or committed schema.
Contract addresses, ABI versions, queries, and providers must be recorded when
collection is implemented.

## Planned data layers

The future pipeline will separate source evidence from research-ready outputs.
The folders below are a proposed convention and are not created in this draft.

```text
data/
├── raw/        # Immutable source extracts
├── processed/  # Decoded, normalized, and validated records
├── derived/    # Analysis-ready metrics and joined panels
└── metadata/   # Manifests, checksums, schemas, and QA reports
```

- **Raw:** preserve the provider response or canonical extract without manual
  correction. Corrections create a new version.
- **Processed:** decode events, normalize addresses and token units, resolve
  ordering, and apply documented quality rules.
- **Derived:** construct position, pool, benchmark, and cost measures required by
  the analysis.
- **Metadata:** make every layer traceable without relying on filenames alone.

Large datasets may ultimately live outside Git. The storage mechanism, retention
policy, and download interface are TBD.

## Provenance record

Every collected or generated dataset should eventually carry at least the
following metadata. This is a documentation template, not a runtime schema.

| Field | Meaning |
| --- | --- |
| Dataset identifier and version | Stable name for the exact extract or transformation |
| Network and chain ID | Evidence that records come from Ethereum Mainnet |
| Protocol and contracts | Uniswap V3 contract addresses and ABI revisions used |
| Block or time range | Inclusive boundaries and any known gaps |
| Source | Provider, endpoint class, dataset release, or node configuration |
| Retrieval time | UTC time at which the source was queried or copied |
| Query or transform version | Repository revision and entry point that produced the data |
| Configuration | Pool filters, batching, finality, and normalization settings |
| Integrity value | Checksum or equivalent content identifier where practical |
| Rights and terms | License, provider terms, and redistribution constraints |

## Validation methodology

Validation should produce a machine-readable result and a human-readable QA
summary. At minimum, the implemented pipeline must check:

1. **Network identity:** chain ID, block hashes, and contract addresses match the
   declared Ethereum Mainnet source.
2. **Coverage:** requested block intervals are accounted for, including explicit
   records of gaps, retries, and provider limits.
3. **Uniqueness and ordering:** event identity, transaction order, and log order
   are stable; duplicate ingestion is rejected or deterministically removed.
4. **Decoding:** events use the intended contract ABI and unknown or failed
   decodes are reported.
5. **Units and signs:** token decimals, token ordering, signed quantities, price
   conventions, and gas denominations are tested.
6. **Cross-source reconciliation:** selected event counts, pool state, balances,
   or aggregates are compared with an independent source or direct call.
7. **Reorganization handling:** the chosen finality policy is applied and changed
   block hashes trigger an explicit recollection or invalidation path.
8. **Economic reconciliation:** position cash flows, inventory, fees, and ending
   value satisfy the accounting checks defined with the analysis metrics.

Exact tolerances and sample sizes for reconciliation are TBD and must be fixed
before the data-quality gate is considered operational.

## Reproducibility and data governance

- Record time in UTC and identify time intervals with block boundaries whenever
  possible.
- Keep raw data immutable and make transformations deterministic.
- Store secrets such as provider credentials outside the repository.
- Do not commit provider responses or reference materials without checking their
  redistribution terms.
- Document missing values and exclusions rather than silently filling or dropping
  them.
- Link every derived dataset to the metric definition and analysis that consumes
  it.

No data source, storage format, schema, or provider is endorsed by this draft.
