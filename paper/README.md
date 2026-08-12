# Paper Plan

This directory will turn the Ethereum Mainnet Uniswap V3 LP risk research into a
TeX manuscript and a generated PDF. It currently contains documentation only;
there is no TeX source, bibliography, figure, table, or `paper.pdf` yet.

Only results that pass the [research workflow](../flow.md) and retain the
provenance defined by the [analysis roadmap](../analysis/) should enter the
manuscript.

## Planned manuscript structure

1. **Abstract:** research question, data scope, method, principal results, and
   limitations after the results exist.
2. **Introduction:** motivation, contribution, and bounded Ethereum Mainnet
   Uniswap V3 LP-risk scope.
3. **Protocol and risk framework:** concentrated liquidity, position ranges,
   fees, inventory exposure, impermanent loss, LVR, adverse selection, and costs.
4. **Data and sample:** sources, study period, pool and position rules,
   transformations, validation, and sample coverage.
5. **Methods:** metric definitions, benchmarks, hypotheses, empirical
   specifications, and identification limits.
6. **Results:** descriptive evidence and frozen primary analyses.
7. **Robustness:** alternative benchmarks, windows, filters, estimators, and cost
   assumptions.
8. **Limitations and discussion:** measurement error, external validity, protocol
   scope, data constraints, and unresolved risks.
9. **Conclusion:** supported findings and open questions without claims beyond the
   evidence.
10. **Appendix:** supplemental definitions, diagnostics, checks, and results.

## Proposed TeX layout

The future paper implementation may follow this layout. Only this README is
created in the current draft.

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
| `main.tex` | Document class, shared commands, metadata, and section assembly |
| `sections/` | Reviewable TeX files for the manuscript sections |
| `figures/` | Analysis-generated figures or declared source assets |
| `tables/` | Analysis-generated TeX tables |
| `references.bib` | Verified references reconciled with the research catalog |
| `paper.pdf` | Reproducible manuscript output generated from the TeX sources |

The TeX engine, document class, package set, build command, and artifact policy
are TBD. Temporary compiler files should not be treated as research outputs.

## Table and figure provenance

Every generated table and figure must be traceable to:

- its analysis entry point and output identifier;
- the exact input dataset version and integrity value;
- the study or model configuration;
- the repository revision;
- the generation time in UTC; and
- any filters, transformations, rounding, or manual annotations.

Numerical values must flow from reviewed analysis outputs into TeX without manual
retyping. Cosmetic edits must not change the underlying values or conceal failed
checks. Captions and notes should define units, samples, benchmarks, and
uncertainty where relevant.

## Citation and claim rules

- Add a citation only after it has a verified catalog entry in
  [`research-reference/`](../research-reference/).
- Cite the specific version of evolving working papers, protocol documentation,
  and datasets.
- Distinguish protocol mechanics, prior findings, this project's results, and the
  authors' interpretation.
- Do not fabricate references, results, sample sizes, or statistical evidence to
  complete a draft section.
- Keep null results, failed robustness checks, and material limitations visible.
- Avoid causal language unless the research design supports it.

## Future build and publication checks

When TeX is added, the paper workflow should verify that:

1. the manuscript builds from a clean checkout with a documented toolchain;
2. all citations resolve and all figures and tables exist;
3. generated values match the approved analysis outputs;
4. the PDF contains no placeholder claims presented as findings;
5. the repository records the data, code, configuration, and revision used for
   the release; and
6. licenses and redistribution rights are documented for external assets and
   source material.

The completed PDF will remain a research artifact, not financial advice.
