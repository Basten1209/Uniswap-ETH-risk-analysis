# Paper Plan

This directory will turn **An Empirical Analysis of Uniswap V3 LP Risk
Measures: Evidence from the WETH/USDT Pool** into a TeX manuscript and generated
PDF. It currently contains documentation only; there is no TeX source,
bibliography, figure, table, or `paper.pdf`.

Only results that pass the [research workflow](../flow.md) and retain the
provenance defined by the [analysis roadmap](../analysis/) should enter the
manuscript.

## Official manuscript structure

The paper will use the following top-level structure:

- **Abstract**
- **1. Introduction**
- **2. AMMs and Liquidity Provision**
- **3. LP Risk and Performance Measures**
  - **3.1 Impermanent Loss**
  - **3.2 Loss-Versus-Rebalancing**
  - **3.3 Predictable Loss**
- **4. Data and Empirical Design**
- **5. Empirical Results**
  - **5.1 Explanatory Power for LP Returns**
  - **5.2 Comparison across Risk Measures**
  - **5.3 Regime-Dependent Explanatory Power**
- **6. Conclusion**

### Abstract

State the two research questions, fixed-pool sample and EDA-supported analytical
interval, actual-position unit, empirical approach, supported results, and
limitations. Results must not be drafted before the analysis exists.

### 1. Introduction

Motivate LP risk measurement, state the explanatory-power and regime-dependent
questions, and define the paper's contributions without claiming results beyond
the evidence.

### 2. AMMs and Liquidity Provision

Explain only the Uniswap V3 mechanics needed to understand actual WETH/USDT LP
positions, fee income, realized return, and the inputs to the three measures.

### 3. LP Risk and Performance Measures

Define realized LP return as the outcome and distinguish it from the three risk
measures:

- **3.1 Impermanent Loss**
- **3.2 Loss-Versus-Rebalancing**
- **3.3 Predictable Loss**

PL always means predictable loss. Each subsection must state the benchmark,
unit, horizon, assumptions, and relationship to realized return.

### 4. Data and Empirical Design

Document the fixed WETH/USDT 0.05% pool and creation-to-snapshot collection,
EDA-supported analytical interval, actual LP-position sample, sources,
transformations, validation, outcome and measure construction, market-regime
definitions, statistical specifications, and identification limits.

### 5. Empirical Results

Report the three required analyses in order:

- **5.1 Explanatory Power for LP Returns**
- **5.2 Comparison across Risk Measures**
- **5.3 Regime-Dependent Explanatory Power**

Diagnostics, sensitivity checks, and relevant limitations belong within
Sections 4 and 5. They must not create additional top-level manuscript sections.

### 6. Conclusion

Summarize which measures are informative under which conditions, the practical
implications for LP monitoring and fee or revenue design, and the limits of the
evidence.

## Proposed TeX layout

The future paper implementation may follow this layout. These paths are not
created in this documentation pass.

```text
paper/
├── main.tex
├── sections/
├── figures/
├── tables/
├── references.bib
└── paper.pdf
```

| Path | Intended role |
| --- | --- |
| `main.tex` | Document class, shared commands, metadata, and assembly of the fixed manuscript structure |
| `sections/` | Reviewable TeX files corresponding to the official sections and subsections |
| `figures/` | Analysis-generated figures or declared source assets |
| `tables/` | Analysis-generated TeX tables |
| `references.bib` | Verified references reconciled with the research catalog |
| `paper.pdf` | Reproducible manuscript output generated from the TeX sources |

The TeX engine, document class, package set, build command, and artifact policy
remain TBD. Temporary compiler files are not research outputs.

## Table and figure provenance

Every generated table and figure must be traceable to:

- its analysis entry point and output identifier;
- the exact input dataset version and integrity value;
- study, measure, regime, and model configurations;
- the repository revision;
- generation time in UTC; and
- filters, transformations, rounding, and manual annotations.

Numerical values must flow from reviewed analysis outputs into TeX without
manual retyping. Captions and notes should define units, samples, benchmarks,
regimes, and uncertainty where relevant.

## Citation and claim rules

- Add a citation only after it has a verified catalog entry in
  [`research-reference/`](../research-reference/).
- Cite the specific version of papers, protocol documentation, and datasets.
- Distinguish protocol mechanics, prior findings, this project's empirical
  results, and the authors' interpretation.
- Do not fabricate references, results, sample sizes, or statistical evidence.
- Keep null results, failed diagnostics, sensitivity changes, and material
  limitations visible.
- Avoid causal language unless the empirical design supports it.

## Future build and publication checks

When TeX is added, verify that:

1. the manuscript builds from a clean checkout with a documented toolchain;
2. the title and section hierarchy match this plan;
3. all citations resolve and all figures and tables exist;
4. generated values match approved analysis outputs;
5. no placeholder claim is presented as a finding;
6. the data, code, configuration, and revision used for the release are
   recorded; and
7. licenses and redistribution rights are documented for external assets and
   source material.

The completed PDF will remain a research artifact, not financial advice.
