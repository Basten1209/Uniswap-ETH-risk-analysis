# Research Reference Catalog

This directory will catalog research used to define and interpret LP risk in
Uniswap V3 on Ethereum Mainnet. It currently contains no papers, datasets, or
completed citations. The project must not invent references to fill that gap.

Return to the [repository overview](../README.md) or review the
[research workflow](../flow.md).

## Review categories

Each source should use one or more of the following topic tags:

| Tag | Coverage |
| --- | --- |
| `uniswap-v3-design` | Concentrated liquidity, ticks, fees, positions, and protocol mechanics |
| `lp-performance` | LP returns, fee income, inventory exposure, and empirical performance |
| `impermanent-loss` | Divergence loss and passive-hold comparisons |
| `lvr-adverse-selection` | Loss-versus-rebalancing, arbitrage, informed flow, and stale pricing |
| `range-management` | Range choice, time in range, rebalancing, and active strategies |
| `mev-market-quality` | MEV, execution ordering, price impact, and market quality |
| `liquidity-concentration` | Liquidity distribution, capital efficiency, and pool competition |
| `blockchain-data-methods` | Event reconstruction, measurement error, sampling, and reproducibility |

Tags describe the project's review structure. They do not imply that a source
has already been found or supports a particular claim.

## Inclusion criteria

A source may enter the reviewed catalog when it:

- has an identifiable author or institution, title, date, and stable location;
- directly informs a research question, metric, data method, or interpretation;
- states enough of its method and evidence to assess relevance and limitations;
- can be cited or linked without violating access or redistribution terms; and
- is labeled by source type, such as peer-reviewed paper, working paper, protocol
  documentation, audit, dataset, or technical note.

Protocol documentation and code may establish mechanics. They should not be
treated as independent evidence of economic outcomes without a separate analysis.

## Catalog entry template

Use one row per source in the catalog and add a longer note when the method or
limitations need more space.

| Field | Required content |
| --- | --- |
| ID | Stable local identifier, such as `author-year-short-title` |
| Full citation | Authors, title, venue or publisher, year, and version |
| Source type | Paper, documentation, dataset, audit, or technical note |
| Topic tags | One or more tags from the review categories |
| Research question | Which repository question or metric the source informs |
| Method | Theoretical, empirical, simulation, case study, or other design |
| Dataset | Network, protocol, period, sample, and access notes when applicable |
| Main contribution | A concise paraphrase of the source's supported result or method |
| Relevance | How the source changes this project's design or interpretation |
| Limitations | Assumptions, threats to validity, and transfer limits |
| Persistent link | DOI, arXiv identifier, official documentation URL, or equivalent |
| Review status | Discovered, screened, extracted, verified, or excluded |

Do not copy an abstract as the main contribution. Use a short paraphrase and
retain page, section, theorem, table, or figure pointers when they help another
researcher verify the note.

## Review process

1. **Discover:** record the source and stable identifier without making a claim
   about its quality.
2. **Screen:** verify that it fits the Ethereum Mainnet Uniswap V3 LP-risk scope
   or supplies a transferable method.
3. **Extract:** record method, dataset, contribution, relevance, and limitations.
4. **Connect:** map the source to a research question, metric, or design choice.
5. **Verify:** check the citation and extracted note against the source version
   that will be cited.
6. **Version:** record material revisions to working papers or documentation.

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
citation toolchain are TBD. Catalog metadata and manuscript citations must be
reconciled before publication.
