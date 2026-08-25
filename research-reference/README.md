# Research Reference Catalog

This directory will catalog literature and documentation used for **An
Empirical Analysis of Uniswap V3 LP Risk Measures: Evidence from the WETH/USDT
Pool**. It currently contains six extracted detailed studies and seventeen
discovered sources awaiting review. Together, they cover realized LP returns,
impermanent loss (IL), loss-versus-rebalancing (LVR), predictable loss (PL),
and related liquidity- and fee-design questions. References must not be
invented to fill remaining gaps.

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

## Discovered studies

The following seventeen sources have status `discovered`. Their detailed
reviews and summaries have not yet been created.

| Reference | Topics | Links |
| --- | --- | --- |
| Andrea Barbon and Angelo Ranaldo. “On the Quality of Cryptocurrency Markets: Centralized vs. Decentralized Exchanges.” *Management Science*, Articles in Advance, 2026. | `uniswap-v3-amm`, `market-regimes`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1287/mnsc.2024.07703) |
| Maxim Bichuch and Zachary Feinstein. “Axioms for Automated Market Makers: A Mathematical Framework in FinTech and Decentralized Finance.” *Operations Research* 74(3), 1187–1202, 2026. | `uniswap-v3-amm`, `impermanent-loss`, `lp-fee-design` | [paper](https://doi.org/10.1287/opre.2022.0520) |
| Agostino Capponi and Ruizhe Jia. “Liquidity Provision on Blockchain-Based Decentralized Exchanges.” *The Review of Financial Studies* 38(10), 3040–3085, 2025. | `uniswap-v3-amm`, `lp-returns`, `market-regimes`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1093/rfs/hhaf046) |
| Tian Chen, Jun Deng, Jing Nie, Bin Zou, and Qi Fu. “Liquidity Provision and Its Information Content in Decentralized Markets.” *Journal of Financial Markets*, article 101073, 2026. | `uniswap-v3-amm`, `lp-returns`, `impermanent-loss`, `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1016/j.finmar.2026.101073) |
| Gang Chu, Michael Dowling, and Xiao Li. “Impermanent Loss in Cryptocurrency.” *Journal of International Money and Finance* 160, article 103476, 2026. | `lp-returns`, `impermanent-loss`, `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1016/j.jimonfin.2025.103476) |
| Michele Fabi and Julien Prat. “The Economics of Constant Function Market Makers.” *Journal of Corporate Finance* 91, article 102737, 2025. | `uniswap-v3-amm`, `lp-fee-design` | [paper](https://doi.org/10.1016/j.jcorpfin.2025.102737) |
| Hisham Farag, Di Luo, Larisa Yarovaya, and Damian Zięba. “Returns from Liquidity Provision in Cryptocurrency Markets.” *Journal of Banking & Finance* 175, article 107411, 2025. | `lp-returns`, `impermanent-loss`, `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1016/j.jbankfin.2025.107411) |
| Joel Hasbrouck, Thomas J. Rivera, and Fahad Saleh. “An Economic Model of a Decentralized Exchange with Concentrated Liquidity.” *Management Science* 72(5), 3666–3683, 2026. | `uniswap-v3-amm`, `lp-returns`, `lp-fee-design` | [paper](https://doi.org/10.1287/mnsc.2024.04510) |
| Woojin Jeong, Seongwan Park, Jaewook Lee, and Yunyoung Lee. “LiqBoost: Enhancing Liquidity Provision for Blockchain-Based Decentralized Exchanges.” *Expert Systems with Applications* 297, article 129230, 2026. | `uniswap-v3-amm`, `lp-returns`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1016/j.eswa.2025.129230) |
| Alfred Lehar and Christine Parlour. “Decentralized Exchange: The Uniswap Automated Market Maker.” *The Journal of Finance* 80(1), 321–374, 2025. | `uniswap-v3-amm`, `lp-returns`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1111/jofi.13405) |
| Tristan Lim. “Predictive Crypto-Asset Automated Market Maker Architecture for Decentralized Finance Using Deep Reinforcement Learning.” *Financial Innovation* 10(1), article 144, 2024. | `uniswap-v3-amm`, `impermanent-loss`, `lp-fee-design` | [paper](https://doi.org/10.1186/s40854-024-00660-0) |
| Vijay Mohan. “Automated Market Makers and Decentralized Exchanges: A DeFi Primer.” *Financial Innovation* 8(1), article 20, 2022. | `uniswap-v3-amm`, `impermanent-loss`, `lp-fee-design` | [paper](https://doi.org/10.1186/s40854-021-00314-5) |
| Andreas Park. “The Conceptual Flaws of Decentralized Automated Market Making.” *Management Science* 69(11), 6731–6751, 2023. | `uniswap-v3-amm`, `market-regimes`, `lp-fee-design` | [paper](https://doi.org/10.1287/mnsc.2021.02802) |
| Seongwan Park, Seungju Lee, Yunyoung Lee, Hyungjin Ko, Bumho Son, Jaewook Lee, and Huisu Jang. “Price Co-Movements in Decentralized Financial Markets.” *Applied Economics Letters* 30(21), 3075–3082, 2023. | `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1080/13504851.2022.2120952) |
| Seongwan Park, Woojin Jeong, Yunyoung Lee, Bumho Son, Huisu Jang, and Jaewook Lee. “Unraveling the MEV Enigma: ABI-Free Detection Model Using Graph Neural Networks.” *Future Generation Computer Systems* 153, 70–83, 2024. | `uniswap-v3-amm`, `blockchain-data-methods`, `lp-fee-design` | [paper](https://doi.org/10.1016/j.future.2023.11.014) |
| Angelo Ranaldo, Ganesh Viswanath-Natraj, and Junxuan Wang. “Blockchain Currency Markets.” *Journal of Financial and Quantitative Analysis*, accepted manuscript, 2026. | `uniswap-v3-amm`, `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1017/S0022109026102841) |
| Bumho Son, Seongwan Park, Jaewook Lee, and Huisu Jang. “Optimal Strategy in Blockchain Transaction Issuances with CIR Process.” *Computational Economics* 66(5), 4137–4159, 2025. | `market-regimes`, `blockchain-data-methods` | [paper](https://doi.org/10.1007/s10614-024-10839-3) |

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

A `discovered` entry carries only its stable paper link until a detailed study
has been created.

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
