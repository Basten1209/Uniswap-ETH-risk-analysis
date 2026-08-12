# Data Methodology

This directory documents how the project will collect, preserve, transform, and
validate data for the WETH/USDT case study. It currently contains documentation
only; no datasets or download pipeline have been added.

See the [research flow](../flow.md) for the gates that data must pass before it
can support analysis.

## Data scope

The dataset will cover one Uniswap V3 WETH/USDT pool on Ethereum Mainnet for
four years. WETH is the on-chain representation of ETH. The unit of analysis is
the actual on-chain LP position, and the analytical outcome is realized LP
return.

The following scope is fixed:

| Dimension | Fixed requirement |
| --- | --- |
| Network | Ethereum Mainnet |
| Protocol | Uniswap V3 |
| Pair and pool count | WETH/USDT, one pool |
| Study length | Four years |
| Observation unit | Actual LP position |
| Required analytical outputs | Realized return, IL, LVR, PL, and market-regime variables |

The following implementation choices remain TBD and must be versioned before
bulk collection:

- exact pool contract address and fee tier;
- start and end blocks or timestamps for the four-year window;
- LP-position inclusion, exclusion, and ownership rules;
- outcome and measure horizons;
- sampling frequency and finality policy;
- reference-price and benchmark inputs required by IL, LVR, and PL; and
- primary data-access provider and fallback provider.

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

Large datasets may ultimately live outside Git. The storage mechanism, retention
policy, and download interface remain TBD.

## Provenance record

Every collected or generated dataset should carry at least:

| Field | Meaning |
| --- | --- |
| Dataset identifier and version | Stable name for the exact extract or transformation |
| Network and chain ID | Evidence that records come from Ethereum Mainnet |
| Pool and contracts | Selected pool, token contracts, fee tier, and ABI revisions |
| Block or time range | Inclusive four-year boundaries and any known gaps |
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
2. **Coverage:** the complete four-year interval is accounted for, including
   explicit records of gaps, retries, and provider limits.
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

No data source, storage format, schema, or provider is selected by this
documentation.
