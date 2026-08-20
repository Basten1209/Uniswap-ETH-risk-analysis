# Analysis Roadmap

This directory will contain the code that converts validated Ethereum Mainnet
Uniswap V3 data into position-level returns, risk measures, and empirical
results. It currently contains documentation only; no notebooks, modules, tests,
or results have been implemented.

Read the [data methodology](../data/) before adding analysis and follow the stage
gates in the [research flow](../flow.md).

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

The exact return construction, metric formulas, horizons, statistical models,
regime definitions, and numerical tolerances remain TBD. They must be versioned
before confirmatory results are produced.

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
5. **Describe the sample.** Report coverage, missingness, distributions, and
   position-level exclusions before model estimates.
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

## Proposed code layout

The implementation may use the following structure after the language and
toolchain are selected. These paths are not created in this documentation pass.

```text
analysis/
├── config/     # Versioned study, measure, regime, and model configurations
├── src/        # Reusable reconstruction, metric, model, and export modules
├── notebooks/  # Exploration and presentation, not core metric logic
├── tests/      # Unit, reconciliation, regression, and integration tests
└── outputs/    # Versioned tables, figures, diagnostics, and run manifests
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

Each analysis run should eventually record:

- input dataset identifiers and integrity values;
- study, measure, regime, and model configuration versions;
- repository revision and execution environment;
- start and completion time in UTC;
- sample exclusions, validation results, and model diagnostics;
- generated table and figure paths; and
- warnings, sensitivity results, and failed checks.

No empirical result is claimed by this document. It defines the work needed to
produce reviewable evidence.
