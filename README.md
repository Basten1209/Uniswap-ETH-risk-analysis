# Uniswap V3 Ethereum LP Risk Research

This repository is an open research workspace for studying the risks borne by
liquidity providers (LPs) in Uniswap V3 pools on Ethereum Mainnet. The project
will connect source data, reproducible analysis, research references, and a
paper in one auditable workflow.

The repository is currently in its documentation and research-design stage. It
does not yet contain datasets, analysis code, TeX sources, or research results.

## Research scope

| Dimension | Current scope |
| --- | --- |
| Network | Ethereum Mainnet |
| Protocol | Uniswap V3 |
| Primary perspective | Liquidity provider |
| Units of analysis | Pools and LP positions, subject to the final study design |
| Study period | TBD |
| Pool selection rule | TBD |
| Data providers | TBD; canonical on-chain records remain the source of truth |

The first research phase focuses on economic and execution risks that affect
LP outcomes. Smart-contract exploits, token governance, and legal or regulatory
risk may be discussed as limitations, but they are not primary empirical
outcomes in the initial study.

## Research questions

1. How do Uniswap V3 LP positions perform against a passive holding benchmark
   after fees and transaction costs?
2. How do price movement and chosen tick ranges affect time in range and capital
   utilization?
3. Under which market conditions does fee income compensate for impermanent
   loss, loss-versus-rebalancing (LVR), and adverse selection?
4. How do rebalancing frequency and Ethereum gas costs change realized LP
   returns?
5. How are LP outcomes associated with volatility, trading volume, fee tier,
   and liquidity concentration?

Specific hypotheses, thresholds, and statistical models are TBD and must be
fixed before confirmatory analysis begins.

## Risk framework

| Risk | Mechanism | Candidate measures |
| --- | --- | --- |
| Impermanent loss | Pool inventory changes as the relative token price moves | LP value versus a passive holding benchmark |
| Range risk | Concentrated liquidity stops earning fees after price leaves its range | Time in range, inactive capital duration, boundary crossings |
| Fee-income uncertainty | Trading volume and fee capture may not offset inventory losses | Gross and net fee income, fee yield, fee-to-loss ratio |
| LVR and adverse selection | Arbitrage and informed flow trade against stale pool prices | LVR estimates, post-trade price movement, benchmark-relative loss |
| Rebalancing and gas cost | Position management consumes capital and incurs execution costs | Rebalance count, gas paid, turnover, return before and after costs |

All measures in this table are candidates. Their final definitions, units,
benchmarks, and sampling frequencies belong in the research design and data
dictionary before implementation.

## Repository structure

| Path | Purpose |
| --- | --- |
| [`flow.md`](flow.md) | End-to-end research workflow and stage gates |
| [`data/`](data/) | Data sourcing, provenance, processing layers, and validation methodology |
| [`research-reference/`](research-reference/) | Literature catalog, review categories, and citation rules |
| [`analysis/`](analysis/) | Planned metrics, analytical stages, and reproducibility rules |
| [`paper/`](paper/) | Planned TeX manuscript, generated figures and tables, and final PDF |

## Research principles

- **On-chain first:** treat Ethereum records and identified Uniswap V3 contract
  events as the canonical evidence. Any indexer must be reconciled against them.
- **Predeclare choices:** record the study window, pool filters, benchmarks,
  exclusions, and model specifications before confirmatory analysis.
- **Preserve provenance:** trace every derived value to a source, block range,
  query or transformation version, configuration, and checksum where practical.
- **Separate data layers:** keep immutable source extracts distinct from cleaned
  and derived datasets.
- **Prevent look-ahead:** construct every metric using information available at
  the evaluated block or timestamp unless a documented analysis explicitly
  requires otherwise.
- **Make results reproducible:** record environment, configuration, random seeds,
  and exact commands once the analysis implementation is added.

## Project status

- [x] Define the initial repository and documentation structure.
- [ ] Freeze the study period and pool-selection criteria.
- [ ] Select and document data access methods.
- [ ] Build and validate the data pipeline.
- [ ] Implement and test the LP risk metrics.
- [ ] Add and review research references.
- [ ] Run the empirical analysis and robustness checks.
- [ ] Add the TeX manuscript and generate `paper/paper.pdf`.

## Contributing and citation

Contributions should state which research question they address, identify all
data and methodological assumptions, and avoid presenting unverified outputs as
findings. Reference material must follow the catalog and rights guidance in
[`research-reference/README.md`](research-reference/README.md).

A project license, contribution process, and formal citation format have not yet
been selected. Until they are added, do not assume that repository contents may
be redistributed under a particular open-source or open-data license.

## Disclaimer

This repository is for open research and education. It does not provide
financial, investment, legal, or tax advice. DeFi positions can lose some or all
of their value, and future empirical results will not guarantee future outcomes.
