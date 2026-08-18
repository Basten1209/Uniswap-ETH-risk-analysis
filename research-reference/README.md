# Research Reference Catalog

This directory will catalog literature and documentation used for **An
Empirical Analysis of Uniswap V3 LP Risk Measures: Evidence from the WETH/USDT
Pool**. It currently contains six extracted detailed studies covering realized
LP returns, impermanent loss (IL), loss-versus-rebalancing (LVR), predictable
loss (PL), and related liquidity- and fee-design questions. References must not
be invented to fill remaining gaps.

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

## Detailed studies

This catalog is an index to the linked detailed studies rather than a duplicate
of their methods, evidence, findings, and limitations. All six reviews have
status `extracted`.

| Reference | Topics | Links |
| --- | --- | --- |
| Lioba Heimbach, Eric Schertenleib, and Roger Wattenhofer. “Risks and Returns of Uniswap V3 Liquidity Providers.” *Proceedings of the 4th ACM Conference on Advances in Financial Technologies (AFT '22)*, 89–101, 2022. | `uniswap-v3-amm`, `lp-returns`, `impermanent-loss`, `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1145/3558535.3559772) · [review — Seungjun Oh](https://app.notion.com/p/38e92b914dfc80d4b84cc42b7f58da7a) |
| Álvaro Cartea, Fayçal Drissi, and Marcello Monga. “Predictable Losses of Liquidity Provision in Constant Function Markets and Concentrated Liquidity Markets.” *Applied Mathematical Finance* 30(2), 69–93, 2023. | `uniswap-v3-amm`, `lp-returns`, `impermanent-loss`, `predictable-loss`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1080/1350486X.2023.2277957) · [review — Seungjun Oh](https://app.notion.com/p/39792b914dfc8089b520e709c5dd6ae3) |
| Álvaro Cartea, Fayçal Drissi, and Marcello Monga. “Decentralized Finance and Automated Market Making: Predictable Loss and Optimal Liquidity Provision.” *SIAM Journal on Financial Mathematics* 15(3), 931–959, 2024. | `uniswap-v3-amm`, `lp-returns`, `predictable-loss`, `market-regimes`, `lp-fee-design` | [paper](https://doi.org/10.1137/23M1602103) · [review — Jaeho Kim](https://infobox1335.tistory.com/78) |
| Zhou Fan, Francisco J. Marmolejo-Cossío, Ben Altschuler, He Sun, Xintong Wang, and David C. Parkes. “Differential Liquidity Provision in Uniswap v3 and Implications for Contract Design.” *Proceedings of the Third ACM International Conference on AI in Finance (ICAIF '22)*, 9–17, 2022. | `uniswap-v3-amm`, `lp-returns`, `market-regimes`, `lp-fee-design` | [paper](https://doi.org/10.1145/3533271.3561775) · [review — Jaeho Kim](https://infobox1335.tistory.com/77) |
| Jason Milionis, Ciamac C. Moallemi, and Tim Roughgarden. “Automated Market Making and Arbitrage Profits in the Presence of Fees.” *Financial Cryptography and Data Security: 28th International Conference, FC 2024, Revised Selected Papers, Part I*, 159–171, Springer, 2025. | `loss-versus-rebalancing`, `market-regimes`, `lp-fee-design` | [paper](https://doi.org/10.1007/978-3-031-78676-1_9) · [review — Jaeho Kim](https://infobox1335.tistory.com/61) |
| Jason Milionis, Ciamac C. Moallemi, Tim Roughgarden, and Anthony Lee Zhang. “Automated Market Making and Loss-Versus-Rebalancing.” arXiv:2208.06046v5, 2024. | `uniswap-v3-amm`, `lp-returns`, `loss-versus-rebalancing`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://arxiv.org/abs/2208.06046) · [review — Jaeho Kim](https://infobox1335.tistory.com/60) |

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

Keep the catalog itself concise. Methods, datasets, findings, relevance, and
limitations belong in the linked detailed study.

| Field | Required content |
| --- | --- |
| Reference | Authors, title, venue or publisher, year, and version |
| Topics | One or more tags from the review categories |
| Links | Stable paper link and detailed study labeled `review — Reviewer Name` |

## Review process

1. **Discover:** record the source and stable identifier without making a claim
   about its quality.
2. **Screen:** verify that it supports the selected WETH/USDT case, one of the
   three risk measures, regime analysis, or a transferable empirical method.
3. **Extract:** record method, dataset, contribution, relevance, and limitations
   in the linked detailed study.
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
reconciled before publication. Catalog entries summarize their cited sources and
do not turn prior findings into claims about the selected WETH/USDT pool.
