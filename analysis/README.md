# Analysis Roadmap

This directory will contain the code that transforms validated Ethereum Mainnet
Uniswap V3 data into reproducible LP risk measurements and research outputs. It
currently contains documentation only; no notebooks, modules, tests, or results
have been implemented.

Read the [data methodology](../data/) before adding analysis and follow the stage
gates in the [research flow](../flow.md).

## Analytical objective

The analysis will estimate how concentrated-liquidity positions perform and why
their outcomes differ across market conditions and management choices. Gross LP
performance must remain distinguishable from performance after gas and
rebalancing costs.

The study period, pool sample, benchmarks, statistical hypotheses, model choices,
and numerical tolerances are TBD. Results must not be produced as confirmatory
evidence until those decisions are versioned.

## Candidate metric set

| Metric family | Question answered | Required distinctions |
| --- | --- | --- |
| LP value and return | What did the position earn or lose over the observation period? | Deposits, withdrawals, ending inventory, collected and uncollected fees, gross and net return |
| Fee income | How much compensation did trading activity provide? | Token denomination, valuation time, realized versus accrued fees, fee tier |
| Impermanent loss | How did LP inventory perform relative to passive holding? | Initial inventory, comparison benchmark, valuation price, horizon |
| Time in range | When was liquidity active and eligible to earn fees? | Tick boundaries, price path, observation frequency, boundary convention |
| LVR and adverse selection | What value was lost when informed or arbitrage flow traded against pool pricing? | Reference price, event ordering, time horizon, estimator assumptions |
| Rebalancing activity | How did active position management change exposure? | Range changes, deposits, withdrawals, collections, turnover, strategy rule |
| Gas and execution cost | What did position management cost on Ethereum? | Gas used, gas price, native-asset valuation, transaction attribution |
| Market context | Which conditions are associated with LP outcomes? | Volatility, volume, liquidity, concentration, fee tier, token pair, time effects |

These are candidate measures rather than final formulas. Every implemented metric
must document its unit, frequency, benchmark, assumptions, source dependencies,
missing-data behavior, and validation rule.

## Planned analysis stages

1. **Load the frozen study configuration.** Reject or clearly label runs that do
   not specify the data version, block range, pool universe, and benchmark.
2. **Verify input quality.** Consume only datasets that passed the documented
   chain, coverage, decoding, unit, and reconciliation checks.
3. **Reconstruct state and cash flows.** Build the pool and position histories
   needed for inventory, fees, range status, and cost attribution.
4. **Construct metrics.** Produce documented pool-, position-, and interval-level
   measures without overwriting their inputs.
5. **Run descriptive analysis.** Report distributions, coverage, missingness, and
   economically relevant group comparisons before model estimates.
6. **Run the frozen empirical specifications.** Keep exploratory variants labeled
   and separate from planned tests.
7. **Test sensitivity.** Re-run defensible alternatives for benchmarks, windows,
   sampling, pool filters, outliers, and cost assumptions.
8. **Export publication inputs.** Generate tables, figures, and metadata for the
   paper without manual transcription.

## Proposed code layout

The implementation may use the following structure after the language and
toolchain are selected. These paths are not created in this draft.

```text
analysis/
├── config/     # Versioned study and run configurations
├── src/        # Reusable ingestion, metric, model, and export modules
├── notebooks/  # Exploratory work and presentation, not core metric logic
├── tests/      # Unit, reconciliation, regression, and integration tests
└── outputs/    # Versioned tables, figures, diagnostics, and run manifests
```

Core transformations and metric definitions should live in reusable modules,
not only in notebooks. Notebook outputs must be reproducible from a clean kernel
and a recorded configuration.

## Validation expectations

- Reconcile deposits, withdrawals, fees, costs, inventory, and ending value using
  documented accounting identities.
- Test tick, price, token-order, decimal, and sign conventions with controlled
  fixtures before using observed data.
- Compare a reviewed sample of reconstructed positions or pool intervals against
  an independent calculation.
- Prevent future blocks, prices, or final outcomes from entering historical
  features unless the analysis explicitly calls for an ex-post measure.
- Define and enforce numerical tolerances instead of relying on visual agreement.
- Keep deterministic outputs stable for the same data, configuration, code
  revision, and random seed.
- Fail clearly when required data, provenance, or configuration is missing.

## Output contract

Each analysis run should eventually record:

- input dataset identifiers and integrity values;
- study and model configuration versions;
- repository revision and execution environment;
- start and completion time in UTC;
- validation and diagnostic results;
- generated table and figure paths; and
- warnings, exclusions, and failed checks.

No analytical result is claimed by this document. It defines the work needed to
produce reviewable evidence.
