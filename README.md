# Levels of logic

Check definitions: **core-v2.1-2026-10-10**. Source documentation updated 20 October 2026.

Check an argument at five depths: overall claims, headings, paragraphs, sentences, and clauses. Independent checkers return questions for the author to decide; they never edit the draft. The same core applies to theory and empirical papers, and other arguments.

**Use your AI agent directly. No API account, credentials, or package installation is required.** Python 3.10+ prepares tasks and processes reports; the agent does the reasoning.

## Start here

1. Give your agent this folder and your Markdown draft. Say: **"Follow AGENTS.md to check this draft. Prepare tasks first and show me the scope and estimated agent usage before launching checkers."**
2. The agent prepares independent checks, collects completed reports, then runs a separate horizontal verifier within your authorization. For a smaller first try, ask for one bounded section.
3. Read the questions, supply missing context, choose changes, and ask for a focused recheck after revising.

Keep confidential inputs, filled context, and reports in authorized local storage outside this repository and shareable artifacts. Sending them to an external service needs authorization.

## Try the local plumbing

Run from this folder with Python installed:

```text
python -B -m runner bundle examples/sample-draft.md --out ../logic-check-demo/run-01 --level all
python -B -m runner check examples/sample-draft.md --out ../logic-check-demo/stub-01 --provider stub
```

Your agent must coordinate isolated checkers and confirm that they finished. Reports require matching completion receipts; incomplete runs cannot be merged as clean checks. See [completion and failure recovery](RUN-COMPLETENESS.md). The Python runner does not launch plan agents or automatically dispatch the whole-draft horizontal verifier; it prepares tasks and processes reports.

The first command prepares five bundles without calling a model. The second uses scripted responses; **it does not check the argument**. Choose new output folders on later tries. The sample and its sources are invented.

[AGENTS.md](AGENTS.md) is the execution guide, including rechecks and optional adapters. [genres/](genres/README.md) offers optional theory and empirical context; choose either or neither. [levels/](levels/README.md) explains the core and [SOURCES.md](levels/SOURCES.md) indexes source provenance.

A clean report establishes neither empirical truth nor evidence sufficiency, novelty, or publication readiness. Missing context can leave a finding indeterminate. Word-choice and regex observations remain separate.

Topic-sentence-first is default logic-related structure guidance: it identifies the claim that subsequent sentences support. Checkers distinguish placement problems from missing, inconsistent, or unsupported claims.

## Sources and evidence

[Source bibliography](SOURCE-BIBLIOGRAPHY.md) identifies the methodological literature, reading scope, and historical or supporting status. [Sources and checks](levels/SOURCES.md) maps concepts and locators to the five levels. Sources motivate design; they do not establish checker accuracy or benefits to theorizing.

[Evidence](evidence/README.md) explains the dated offline checks and current file manifest. [Rule versions](levels/RULESET.md) explains compatibility. No source books, PDFs, or transcripts are distributed.

Project-owned code and documentation are licensed under [MIT](LICENSE). See [third-party rights](THIRD-PARTY-NOTICES.md).

For the release version, offline reproduction and evidence limits, see the [reviewer guide](REVIEWER-GUIDE.md).
