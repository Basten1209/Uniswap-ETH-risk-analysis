# Contributing

Thank you for contributing to **An Empirical Analysis of Uniswap V3 LP Risk
Measures: Evidence from the WETH/USDT Pool**. This open research project compares
impermanent loss (IL), loss-versus-rebalancing (LVR), and predictable loss (PL)
as explanations of realized returns for actual LP positions in the fixed
Ethereum Mainnet WETH/USDT 0.05% pool. Every contribution should make that
research easier to verify, reproduce, or understand.

All changes must reach `main` through a pull request (PR). Do not push directly
to `main`, even if you have write access.

## Before you start

Read the [project overview](README.md) and [research flow](flow.md). For work in a
specific area, also read its local guide:

- [data methodology](data/README.md);
- [research reference catalog](research-reference/README.md);
- [analysis roadmap](analysis/README.md); and
- [paper plan](paper/README.md).

Opening an Issue before a PR is optional. It is useful when you want early
feedback on a material change to RQ1 or RQ2, the selected pool or position
sample, a return or risk-measure definition, a regime method, a data source, or
work that affects more than one research stage. Small corrections and focused
documentation updates may go directly to a PR.

Keep each PR focused on one coherent change. Separate unrelated research,
analysis, and documentation work so that each contribution can be reviewed and
reverted independently.

## What you can contribute

| Contribution | Include in the PR |
| --- | --- |
| Research design or methodology | RQ1 or RQ2, realized-return outcome, affected risk measure or regime, proposed assumptions, limitations, and workflow stage |
| Data methodology or pipeline | Fixed WETH/USDT pool and contracts, full-history snapshot coverage, actual-position rules, source and retrieval method, provenance, validation checks, and data rights |
| Research reference | Full citation, stable link, relevant return, IL, LVR, PL, regime or data-method tag, method, dataset, limitations, and review status |
| Analysis code | Realized-return, IL, LVR, PL or regime definition, inputs, configuration, reproducible command, tests or reconciliation checks, and expected outputs |
| Paper content | Supporting analysis output, citations, scope of the claim, limitations, and table or figure provenance |
| Documentation | Intended reader, corrected or added guidance, checked internal links, and rendered Markdown review |

Distinguish observed evidence, calculated results, assumptions, and
interpretation. Do not present unverified outputs as findings, use causal
language without a supporting design, or omit a failed check that changes how a
result should be interpreted.

## Choose a contribution workflow

External contributors should work from a fork. Contributors with write access
may create a branch in this repository. Both workflows end with a PR targeting
`main` in `Basten1209/Uniswap-ETH-risk-analysis`.

### External contributors: work from a fork

1. Fork `Basten1209/Uniswap-ETH-risk-analysis` on GitHub.

2. Clone your fork and register this repository as `upstream`. Replace
   `YOUR_GITHUB_USERNAME` with your GitHub username.

   ```bash
   git clone https://github.com/YOUR_GITHUB_USERNAME/Uniswap-ETH-risk-analysis.git
   cd Uniswap-ETH-risk-analysis
   git remote add upstream https://github.com/Basten1209/Uniswap-ETH-risk-analysis.git
   git fetch upstream
   ```

3. Create a branch from the current upstream `main`.

   ```bash
   git switch -c docs/short-description upstream/main
   ```

4. Make and validate the change, then stage only the intended files.

   ```bash
   git add path/to/changed-file
   git commit -m "docs: describe the change"
   ```

5. Rebase onto the latest upstream `main`, then push the branch to your fork.

   ```bash
   git fetch upstream
   git rebase upstream/main
   git push -u origin docs/short-description
   ```

6. Open a PR on GitHub with:

   - base repository: `Basten1209/Uniswap-ETH-risk-analysis`;
   - base branch: `main`; and
   - compare branch: the branch in your fork.

### Contributors with write access: work from a repository branch

1. Clone the repository and create a branch from the latest `main`.

   ```bash
   git clone https://github.com/Basten1209/Uniswap-ETH-risk-analysis.git
   cd Uniswap-ETH-risk-analysis
   git fetch origin
   git switch -c analysis/short-description origin/main
   ```

2. Make and validate the change, then stage only the intended files.

   ```bash
   git add path/to/changed-file
   git commit -m "analysis: describe the change"
   ```

3. Rebase onto the latest `main` and push the branch.

   ```bash
   git fetch origin
   git rebase origin/main
   git push -u origin analysis/short-description
   ```

4. Open a PR from the new branch into `main`. Do not merge the branch locally
   into `main` and push the result.

## Branch and commit names

Names should make the purpose of a change easy to scan, but formatting is a
recommendation rather than a merge requirement.

Use `type/short-description` for branches. Suggested types are:

- `research/` for questions, hypotheses, and methodology;
- `data/` for collection, provenance, processing, and validation;
- `analysis/` for metrics, tests, models, and analytical outputs;
- `paper/` for TeX, tables, figures, and manuscript text;
- `docs/` for documentation; and
- `fix/` for focused corrections.

Prefer concise commit subjects in the form `type: summary`, such as
`data: document LP position sample inputs`. A PR may contain multiple commits
when they describe useful review steps, but each commit should remain internally
coherent.

## Data and external-material policy

Do not commit raw datasets or third-party PDFs without prior maintainer approval.
Before requesting approval, document:

- the source and stable access location;
- the author, publisher, or data provider;
- the license or applicable redistribution terms;
- the expected file size and storage requirements;
- a checksum or other integrity identifier; and
- why a repository copy is necessary for the research.

Prefer the single `data/manifest.json`, persistent links, and reproducible
retrieval instructions over copied files. Store actual data outside every Git
checkout at `~/Data/uniswapdata` (or the explicitly configured external root),
as described in [the data guide](data/README.md). Clearly labeled synthetic
fixtures may be included when they are small and required for tests.

Never commit credentials, private RPC URLs, personal data, confidential
material, or content whose redistribution rights are unclear. Keep local secrets
outside the repository and inspect the complete diff before pushing.

The project license is still TBD. This guide does not create a license or a
copyright assignment. Submit only material that you have the right to share;
maintainers may postpone acceptance when ownership or licensing is unclear.

## Validate your change

First, update your view of `main`. Use `upstream` for a fork or `origin` for a
branch in the main repository:

```bash
BASE_REMOTE=upstream  # Use origin when you have write access.
git fetch "$BASE_REMOTE"
git diff --check "$BASE_REMOTE/main"...HEAD
git diff --name-status "$BASE_REMOTE/main"...HEAD
git status --short
```

`git diff --check` must finish without output. Review the file list and confirm
that the working tree does not contain accidental changes.

Also complete the checks that match your contribution:

- **Research design:** confirm that the fixed-pool snapshot, EDA-supported
  analytical interval, actual LP positions, realized-return outcome, IL/LVR/PL
  measures, regime variables, assumptions, exclusions, and exploratory versus
  confirmatory status are explicit.
- **Data:** run the available coverage, uniqueness, decoding, unit, provenance,
  and reconciliation checks; report their commands and results.
- **Analysis:** run all relevant tests and the reproducibility entry point;
  report the data and configuration versions used.
- **References and paper:** verify citations, source versions, claims, rights,
  and table or figure provenance.
- **Documentation:** inspect the rendered Markdown, test every changed relative
  link, and confirm that command examples match the current repository.

For data-pipeline changes, install `data/requirements.txt` and run
`python -m pytest -q data/tests`. Do not invent a test result. If another
automated check is unavailable, state `Not run`, explain why, and describe the
manual validation performed.

## Open the pull request

Draft PRs are welcome for early feedback. Before requesting review or merging,
include the following information in the PR description:

````markdown
## Purpose

[What this changes and why]

## Research context

- Research question (RQ1 or RQ2) or workflow stage:
- Affected outcome, risk measure, or regime:
- Assumptions and limitations:
- Related Issue, if any:

## Data and provenance

- Sources and versions:
- Block or time range:
- Licensing or redistribution notes:

## Validation

- [ ] Diff contains only intended files
- [ ] Relevant tests or research checks pass
- [ ] Documentation links and citations were checked
- [ ] No secrets or restricted external material are included

Commands and results:

```text
[Paste the commands and concise results, or explain why a check was not run]
```
````

Remove sections that genuinely do not apply, but do not omit material
assumptions, provenance, failed checks, or licensing concerns. Keep the PR title
specific and use the PR discussion to record decisions that change the research
design.

## Review and merge

A PR is ready to merge when:

- it targets `main` and contains one coherent contribution;
- required provenance, assumptions, limitations, and validation results are in
  the PR description;
- the branch is rebased onto the current `main` and has no conflicts;
- all relevant checks pass or unavailable checks are explained; and
- requested changes are addressed and no review discussion remains unresolved.

The repository uses **rebase merge** as the default merge method. A contributor
with write access may rebase-merge a ready PR without a separate approval.
External contributors need a contributor with write access to perform the
merge. A maintainer or reviewer may still request changes and block the merge
while a material research, reproducibility, rights, or security concern remains.

If you rebase a branch after publishing it, update only that contribution branch
with `git push --force-with-lease`. Coordinate before rewriting a branch shared
with another contributor.

Thank you for helping make this research auditable and useful.
