# Research Reference Catalog

This directory will catalog literature and documentation used for **An
Empirical Analysis of Uniswap V3 LP Risk Measures: Evidence from the WETH/USDT
Pool**. It currently contains no cataloged papers, datasets, or completed
citations. References must not be invented to fill that gap.

Return to the [repository overview](../README.md) or review the [research
workflow](../flow.md).

## Review categories

Each source should use one or more of the following topic tags:

| Tag | Coverage |
| --- | --- |
| `uniswap-v3-amm` | AMM and concentrated-liquidity mechanics required to reconstruct the selected pool and actual LP positions |
| `lp-returns` | Realized LP return, position valuation, cash flows, and fee income |
| `impermanent-loss` | IL definitions, passive-hold benchmarks, estimation, and empirical evidence |
| `loss-versus-rebalancing` | LVR definitions, rebalancing benchmarks, estimators, and empirical evidence |
| `predictable-loss` | Predictable-loss definitions, self-financing benchmarks, estimators, and empirical evidence |
| `market-regimes` | Regime definitions and methods using price, volatility, gas fees, volume, trading activity, or other on-chain variables |
| `blockchain-data-methods` | Event and position reconstruction, reference prices, measurement error, sampling, and reproducibility |
| `lp-fee-design` | Implications of measured LP risk and return for LP compensation, fees, and revenue design |

Tags define the review structure; they do not imply that a source has already
been found or that it supports a particular claim. Literature on other topics
should enter the catalog only when it directly supports one of the two research
questions or a required data or empirical method.

## Inclusion criteria

A source may enter the reviewed catalog when it:

- has an identifiable author or institution, title, date, and stable location;
- directly informs realized LP return, IL, LVR, PL, a market regime, the
  WETH/USDT data method, or interpretation of the two research questions;
- states enough of its method and evidence to assess relevance and limitations;
- can be cited or linked without violating access or redistribution terms; and
- is labeled by source type, such as peer-reviewed paper, working paper,
  protocol documentation, dataset, or technical note.

Protocol documentation and code may establish mechanics. They must not be
treated as independent evidence of economic outcomes without separate analysis.

## Catalog entry template

Use one row per source in the catalog and add a longer note when the method or
limitations require more space.

| Field | Required content |
| --- | --- |
| ID | Stable local identifier, such as `author-year-short-title` |
| Full citation | Authors, title, venue or publisher, year, and version |
| Source type | Paper, documentation, dataset, audit, or technical note |
| Topic tags | One or more tags from the review categories |
| Research connection | RQ1, RQ2, realized return, IL, LVR, PL, a regime, or a required method |
| Method | Theoretical, empirical, simulation, case study, or another design |
| Dataset | Network, protocol, pool or pair, period, sample, and access notes when applicable |
| Main contribution | Concise paraphrase of the supported result or method |
| Relevance | How the source changes this project's design or interpretation |
| Limitations | Assumptions, threats to validity, and transfer limits |
| Persistent link | DOI, arXiv identifier, official documentation URL, or equivalent |
| Review status | Discovered, screened, extracted, verified, or excluded |

Do not copy an abstract as the main contribution. Paraphrase it and retain page,
section, theorem, table, or figure pointers when they help another researcher
verify the note.

## Review process

1. **Discover:** record the source and stable identifier without making a claim
   about its quality.
2. **Screen:** verify that it supports the selected WETH/USDT case, one of the
   three risk measures, regime analysis, or a transferable empirical method.
3. **Extract:** record method, dataset, contribution, relevance, and limitations.
4. **Connect:** map the source to RQ1, RQ2, an outcome or measure definition, a
   regime variable, or a design choice.
5. **Verify:** check the citation and extracted note against the exact version
   that will be cited.
6. **Version:** record material revisions to working papers, datasets, or
   documentation.

Excluded sources should keep a short reason when their exclusion could otherwise
create selection ambiguity.

## File and rights guidance

- Prefer persistent links and metadata over storing copyrighted PDFs.
- Store a local copy only when redistribution is permitted and document the
  applicable license or terms.
- Name permitted files with a stable convention such as
  `author-year-short-title.ext`.
- Keep reading notes distinguishable from source text and quote only what is
  necessary with a precise citation.
- Do not commit paywalled, confidential, personal, or provider-restricted
  material.

The future paper may maintain a BibTeX database, but its exact location and
citation toolchain remain TBD. Catalog metadata and manuscript citations must be
reconciled before publication. This documentation update does not populate the
catalog or make empirical claims.
