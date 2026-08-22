# An Empirical Analysis of Uniswap V3 LP Risk Measures: Evidence from the WETH/USDT Pool

This repository is an open research workspace for an empirical comparison of
risk measures for Uniswap V3 liquidity providers (LPs). The study asks when,
why, and how much each measure helps explain realized LP returns.

The repository contains the versioned collection, position reconstruction,
realized-return, and IL/LVR/Predictable-Loss code plus checksum manifests. Large
data artifacts live outside Git in a configurable data root; confirmatory
econometric analysis and paper results are still in progress.

## Research questions

1. Do impermanent loss (IL), loss-versus-rebalancing (LVR), and predictable loss
   (PL) explain realized LP returns?
2. Does the relative explanatory power of these measures change across market
   regimes?

## Research objective

The project will compute IL, LVR, PL, and realized return for each observed LP
position, then evaluate:

- the full-sample explanatory power of each risk measure for realized LP
  returns; and
- the relative importance of the measures under different market conditions.

The goal is empirical comparison, not the introduction of another risk measure
or the evaluation of a particular liquidity-management strategy.

## Dataset

| Dimension | Research scope |
| --- | --- |
| Network | Ethereum Mainnet |
| Protocol | Uniswap V3 |
| Pool | Fixed WETH/USDT 0.05% pool (`0x11b8…97f6`) verified against the V3 Factory |
| Collection interval | Pool creation through the latest finalized BigQuery snapshot |
| Unit of analysis | Actual on-chain LP positions |
| Outcome | Realized LP return |

The collection pipeline freezes the exact creation and cutoff blocks. Use the
single [data access and transfer guide](data/README.md) to initialize, receive,
verify, reproduce, or rebuild the external dataset. Position
filters, the analytical window, return horizon, and sampling frequency are
chosen after full-history EDA and then frozen in the empirical design. See the
versioned manifest and BigQuery workflow in [`data/`](data/).

The WETH/USDT 0.05% pool is the sole primary pool for the current study. A
separate follow-up study will apply the frozen empirical design to the Ethereum
Mainnet Uniswap V3 WETH/USDC 0.05% pool
(`0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`) to evaluate replication and
external validity. That follow-up is not part of the current sample or an
in-study robustness check, and observations from the two pools will not be
pooled in the primary analysis.

## Risk measures and outcome

| Item | Role in the study |
| --- | --- |
| Impermanent loss (IL) | Measures LP performance relative to passively holding the position's initial assets |
| Loss-versus-rebalancing (LVR) | Measures loss relative to a rebalancing benchmark |
| Predictable loss (PL) | Measures the predictable, unhedgeable loss of liquidity provision relative to its defined self-financing benchmark |
| Realized LP return | The outcome whose relationship with IL, LVR, and PL will be estimated |

PL means **predictable loss**, not profit and loss. Its implemented operational
definition follows the relevant literature, including
[Cartea, Drissi, and Monga](https://doi.org/10.1080/1350486X.2023.2277957).
PL is decomposed using the paper's terminology as **Convexity Cost + Opportunity
Cost**.
The versioned risk build keeps native signs and common loss-positive,
initial-capital-normalized values. Fee income remains an input to realized LP
return, not a fourth risk measure.

## Regime analysis

The study will test whether the measures' explanatory power varies with market
conditions. Candidate regime variables are:

- ETH price level;
- volatility;
- gas fees;
- transaction volume;
- trading activity; and
- other documented on-chain variables.

Gas fees enter this research as a candidate market-regime variable. LP
transaction-cost or rebalancing-strategy analysis is not a separate research
objective.

## Expected contributions

- Identify which risk measure is most informative under different market
  conditions.
- Provide practical guidance on which measures LPs should monitor.
- Supply empirical evidence for DEX LP risk evaluation and LP-side fee or
  revenue design.

## Brief paper index

- Abstract
- 1. Introduction
- 2. AMMs and Liquidity Provision
- 3. LP Risk and Performance Measures
  - 3.1 Impermanent Loss
  - 3.2 Loss-Versus-Rebalancing
  - 3.3 Predictable Loss
- 4. Data and Empirical Design
- 5. Empirical Results
  - 5.1 Explanatory Power for LP Returns
  - 5.2 Comparison across Risk Measures
  - 5.3 Regime-Dependent Explanatory Power
- 6. Conclusion

## Repository structure

| Path | Purpose |
| --- | --- |
| [`flow.md`](flow.md) | End-to-end research workflow and stage gates |
| [`data/`](data/) | Data scope, provenance, processing, and validation methodology |
| [`analysis/`](analysis/) | Metric construction and empirical-analysis roadmap |
| [`data_processing.ipynb`](data_processing.ipynb) | Reproducible IL/LVR/PL tables and requested portfolio/representative-position charts |
| [`research-reference/`](research-reference/) | Literature catalog and citation rules |
| [`paper/`](paper/) | Manuscript structure and publication workflow |

## Research principles

- Use canonical on-chain records as the primary evidence and reconcile
  accelerated data sources against them.
- Predeclare the pool, study window, position rules, return construction, metric
  definitions, regime variables, and empirical specifications.
- Preserve provenance across immutable raw, processed, and derived data layers.
- Prevent look-ahead in historical outcomes, measures, and regime assignments.
- Make every reported table and figure reproducible from versioned inputs,
  configuration, and code.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution and review
requirements.

## Disclaimer

This repository is for research and education. It does not provide financial,
investment, legal, or tax advice. DeFi positions can lose some or all of their
value, and future empirical results will not guarantee future outcomes.
