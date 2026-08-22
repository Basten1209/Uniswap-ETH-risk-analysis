# Analysis Roadmap

This directory contains the exploratory analysis that turns validated Ethereum
Mainnet Uniswap V3 data into reviewable population, market, and risk summaries.
Core reconstruction and return calculations remain reusable code under
`data/src`; risk formulas and event-driven construction live under
`analysis/src`; notebooks consume those modules instead of redefining accounting
logic.

Read the [data methodology](../data/) before adding analysis and follow the stage
gates in the [research flow](../flow.md).

## Implemented EDA

[`notebooks/eda.ipynb`](notebooks/eda.ipynb) is a clean-kernel executable overview
of the fixed WETH/USDT pool. It reports the raw-event-to-position reconstruction
funnel and removes 11 overlapping fee identities before defining the 41,660-pair
analytical population. Counts and shares are shown for the full snapshot and for
the fully observed `[2021-07-01, 2026-07-01)` sample: 40,259 total pairs, 30,101
same-block pairs, and 10,158 multi-block pairs.

The notebook plots active pair count and raw liquidity including intraday
same-block activity; distributions and daily mean/median series for lifetime
and entry liquidity value with 30-day moving averages; observed realized fee,
fee-inclusive return, daily return, size versus lifetime, lifetime and size
versus daily return, and daily
realized volatility versus EOD active-position count. It also separates the
all-day and positive-activity-day relationships between same-block pair count,
10-minute realized volatility, and 30-day historical volatility. These three
series are also aligned in a shared-axis time-series figure with daily values and
30-day means where appropriate. Daily pool swap count is compared against both
volatility measures, and swap count and USDT-leg volume are included as
market-activity context.

The same notebook also plots Binance ETHUSDT daily close and 30-day annualized
historical volatility, daily realized volatility from 10-minute returns, and
FRED SOFR with calendar-day forward-fill. Its full-period fee/return dataset
excludes the 11 overlapping fee-attribution pairs instead of allocating their
fees pro rata; the boundary-complete EDA period leaves 10,158 observations. See
the [data dictionary](../data/DATA_DICTIONARY.md) for the accounting convention
and column definitions.

Run it from the repository root after rebuilding pair returns:

```bash
python data/scripts/dataset.py build-pair-returns
jupyter nbconvert --to notebook --execute --inplace analysis/notebooks/eda.ipynb
```

## Implemented IL/LVR/Predictable-Loss build

[`../data_processing.ipynb`](../data_processing.ipynb) is a clean-kernel
executable presentation of the versioned `il-lvr-pl-v1` build. The primary
sample is the 10,795-row return-comparable multi-block operation-pair dataset;
the 10,718 strict pairs remain a sensitivity subset. The build uses exact
`sqrt_price_x96` and blockchain event order, strict-prior Binance prices, and a
frozen SOFR snapshot. Fees and gas do not enter IL, LVR, or PL.

IL compares fee-exclusive principal with the actual deposited-asset HODL
benchmark. Primary LVR is the external-price self-financing rebalancing gap;
CEX quadratic-variation estimates at 1 second, 5 seconds, and 1 minute are
robustness outputs. Predictable Loss is decomposed using the paper's terminology
as **Convexity Cost + Opportunity Cost**. Convexity Cost is calculated from the
exact discrete gap on the internal pool-price path; Opportunity Cost accrues
SOFR only on an already accumulated replication gap. The old
full-WETH-inventory SOFR charge is not PL and is no longer produced.

Prepare the versioned SOFR input once, then build or execute the notebook without
network access:

```bash
python analysis/scripts/prepare_sofr.py
python analysis/scripts/build_risk_metrics.py
jupyter nbconvert --to notebook --execute data_processing.ipynb \
  --output data_processing.executed.ipynb
```

Outputs and their run manifest are written under
`$UNISWAP_DATA_ROOT/derived/risk_metrics/v1/`; figures are saved in its
`figures/` directory.

## Analytical objective

The analysis will test when, why, and how much three LP risk measures explain
realized returns for actual on-chain positions in the fixed WETH/USDT 0.05%
pool over an EDA-supported analytical interval drawn from full-history data.

| Research element | Fixed scope |
| --- | --- |
| Outcome | Realized LP return |
| Risk measures | Impermanent loss (IL), loss-versus-rebalancing (LVR), and predictable loss (PL) |
| Unit of analysis | Actual on-chain LP position |
| Primary comparison | Explanatory power across the three measures |
| Conditional comparison | Relative explanatory power across market regimes |

Return construction and risk formulas are versioned. Statistical models,
confirmatory horizons, and ex-ante regime definitions remain to be frozen before
confirmatory results are produced. The bull/bear labels in the four
representative-position charts are explicitly ex-post descriptive strata and
must not be reused as confirmatory historical features.

## EDA universe and risk-analysis cohort

For dataset `11b815ef_b12376751_b25779958`, describe the sample in the
following order. The full immutable raw snapshot has 14,443,396 rows:
14,337,903 event rows, 1,932 daily block rows, and 103,561 transaction-identity
rows. Of the decoded target-pool events, 51,428 are Mint and 56,767 are Burn,
giving 108,195 liquidity operations. Exact FIFO matching on LP wallet, manager,
tick range, and absolute liquidity produces 41,671 observations in
`all_pairs.parquet`.

EDA uses all 41,671 operation pairs. It must identify the 30,865 pairs whose
Mint and Burn occur in the same block as a separate
`same_block_jit_mev_candidate` cohort. For this study that cohort is the
operational proxy for JIT/MEV activity. The label is a reproducible event-timing
classification, not proof of an actor's intent or that every observation is an
attack.

The pool-level non-same-block cohort has 10,806 observations. The primary
return-comparable risk build removes the same 11 overlapping fee identities as
the realized-return outcome and therefore uses 10,795 observations. Within that
common sample, 10,718 satisfy the strict pair rule; use them as a
quality-controlled sensitivity sample rather than silently substituting them
for the primary cohort.

## Future cross-pool validation

After the primary WETH/USDT study is complete, a separate follow-up study will
apply its frozen empirical design to the Ethereum Mainnet Uniswap V3 WETH/USDC
0.05% pool (`0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`), which interfaces may display
as ETH/USDC. This comparison holds the network, protocol version, and fee tier
constant while changing the quote stablecoin and pool contract.

Before examining outcomes from the validation pool, freeze the primary study's
measure definitions, position rules, analytical window, return horizon, regime
construction, model specifications, and evaluation criteria. Apply those choices
unchanged unless a pool-specific incompatibility is documented in advance.

The validation pool must use separate raw, processed, and derived datasets and a
separate empirical-design version. Do not pool its observations with WETH/USDT
observations in the primary analysis. The follow-up will test whether the
predeclared signals replicate and assess pool or stablecoin dependence and
generalizability; it does not assume that the primary findings will reproduce.

## Measure construction

| Item | Analytical role | Required distinctions |
| --- | --- | --- |
| Realized LP return | Dependent outcome | Deposits, withdrawals, ending inventory, collected and uncollected fees, valuation convention, and horizon |
| Impermanent loss | Risk measure | Initial inventory, passive-hold benchmark, valuation price, and horizon |
| Loss-versus-rebalancing | Risk measure | Rebalancing benchmark, reference price, event ordering, and estimator assumptions |
| Predictable loss | Risk measure | Self-financing benchmark, market-risk replication, risk-free component, liquidity-taking activity, and concentrated-liquidity range |

PL means predictable loss, not profit and loss. Fee income is an accounting
input to realized return rather than a fourth risk measure. Tick ranges and
position activity are inputs needed to reconstruct Uniswap V3 positions and
compute the measures; they do not define additional research outcomes.

Each implemented outcome or measure must document its unit, frequency,
benchmark, assumptions, source dependencies, missing-data behavior, and
validation rule.

## Market-regime variables

Candidate variables for the regime-dependent analysis are:

| Candidate | Intended use |
| --- | --- |
| ETH price level | Identify price-level conditions |
| Volatility | Identify low- and high-volatility conditions |
| Gas fees | Describe network-cost conditions, not position transaction costs |
| Transaction volume | Describe pool demand and market intensity |
| Trading activity | Capture swap frequency or other predeclared activity measures |
| Other on-chain variables | Extend the regime set only when motivated, documented, and fixed before confirmatory analysis |

The final feature definitions, windows, thresholds, and regime-assignment method
must be predeclared. Historical regimes must not use future information.

## Planned analysis stages

1. **Load the frozen study configuration.** Require the fixed-pool data
   snapshot, EDA-supported analytical interval, position rules, data version,
   metric definitions, and empirical specification.
2. **Verify input quality.** Consume only datasets that passed the documented
   chain, coverage, decoding, unit, and reconciliation checks.
3. **Reconstruct positions and cash flows.** Build histories for actual LP
   positions, including liquidity changes, fees, inventory, and valuation
   inputs.
4. **Construct the outcome and measures.** Produce realized return, IL, LVR, and
   PL at the predeclared unit and horizon without overwriting inputs.
5. **Describe the sample.** Report coverage, missingness, distributions, the
   same-block JIT/MEV candidate cohort, and position-level exclusions before
   model estimates.
6. **Estimate full-sample explanatory power.** Apply the frozen specification to
   each measure and report comparable model outputs and diagnostics.
7. **Compare the measures.** Evaluate their relative explanatory power using the
   same sample, outcome, horizon, and evaluation criteria.
8. **Run regime-dependent analysis.** Re-estimate or interact the frozen
   specifications using the predeclared market regimes.
9. **Test sensitivity and export results.** Run defensible alternatives and
   generate traceable tables, figures, diagnostics, and metadata for the paper.

Exploratory specifications must remain labeled and separate from confirmatory
results.

## Code layout

```text
analysis/
├── scripts/    # Frozen external-rate preparation and risk build entry points
├── src/lp_risk/ # Reusable formulas, validated readers, and output pipeline
├── notebooks/  # Exploration and presentation, not core metric logic
└── tests/      # Formula, sign, range, ordering, and accounting tests
```

Core transformations and measure definitions should live in reusable modules,
not only in notebooks. Notebook outputs must be reproducible from a clean kernel
and a recorded configuration.

## Validation expectations

- Reconcile deposits, withdrawals, fee income, inventory, ending value, and
  realized return with documented accounting identities.
- Test tick, price, token-order, decimal, sign, and benchmark conventions using
  controlled fixtures.
- Independently verify a reviewed sample of reconstructed positions and each
  risk-measure calculation.
- Apply identical samples, horizons, and evaluation criteria when comparing IL,
  LVR, and PL.
- Prevent future blocks, prices, returns, or regime labels from entering
  historical features unless explicitly required by an ex-post measure.
- Define numerical tolerances and keep deterministic outputs stable for the same
  data, configuration, code revision, and random seed.
- Fail clearly when required data, provenance, or configuration is missing.

## Output contract

The risk-measure run manifest records:

- input dataset identifiers and integrity values;
- formula version and repository revision;
- exact primary and strict sample counts;
- dataset, return, Binance-oracle, and SOFR hashes;
- valuation, risk-free, fee/gas, and daily aggregation conventions; and
- generated Parquet paths, row counts, sizes, and SHA-256 values.

Model diagnostics and confirmatory empirical results remain future stages.
