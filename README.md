# Levels of logic

Levels of logic helps an author examine how an argument holds together, from the overall claims down to individual clauses. Separate AI checkers examine five depths: the overall argument, sections, paragraphs, sentences, and clauses. They return questions for the author to consider; they do not edit the draft. The same core can be used for theory papers, empirical papers, and other arguments.

In the direct-agent workflow, a person or the AI agent coordinates the separate checks and gathers the completed reports. A later verifier compares the findings for overlap, conflict, or missing context, so the author can consider them together before deciding what to revise. The Python program prepares material and processes reports, while the coordinator assigns the checkers and arranges the later comparison.

## Reviewing the prototype

**You can inspect the design and evidence without installing software or running an AI agent.** Start with the [reviewer guide](REVIEWER-GUIDE.md), or follow this reading path:

| What to inspect | What it helps you assess |
|---|---|
| [The five levels](levels/README.md) | What each checker asks and how the parts of an argument relate. |
| [The fictional sample draft](examples/sample-draft.md) | The kind of text the tool accepts. Its argument and sources are invented, as explained in [fixture provenance](examples/PROVENANCE.md). |
| [Sources and checks](levels/SOURCES.md) | How the literature informs design choices, including the limits of each connection. |
| [Evidence and its limits](evidence/README.md) | What the software checks demonstrate and what remains to be evaluated. |

The October 29 offline check passed **115 tests, with one Windows privilege-related skip**. These tests check software behavior using synthetic inputs and simulated responses. They do not establish whether the AI's judgments are accurate or improve theory writing. The [reviewer guide](REVIEWER-GUIDE.md) explains how to inspect or repeat these checks.

## Trying the software without an AI call

Install Python 3.10 or later, download or clone this repository, and open a terminal in its folder. The core uses Python's standard library; no extra Python package or credentials for a model service are needed for the following example:

```text
python -B -m runner check examples/sample-draft.md --out ../logic-check-demo/stub-01 --provider stub
```

This command creates a demonstration folder beside the repository, where you can open `decisions.md` to inspect the output format. Because the `stub` option supplies scripted responses, **the example does not assess the sample's argument**. Use a new output folder for each attempt. The reviewer guide also gives the command for the complete offline software check.

## Checking an argument with an agent

Give your agent this folder and your Markdown draft. Say: **"Follow AGENTS.md to check this draft. Prepare tasks first and show me the scope and estimated agent usage before launching checkers."** For a smaller first try, ask for one bounded section.

The [agent execution guide](AGENTS.md) explains how to give each checker its assigned material without exposing it to other checkers' findings. It also explains how to confirm completion and arrange a separate verifier to compare the reports. Completion records, called *receipts*, tie each finished report to its assigned task and input, so an incomplete run cannot be merged as a completed check. [Completion and recovery](RUN-COMPLETENESS.md) gives the technical details. The Python program does not itself launch plan agents or automatically dispatch the whole-draft verifier.

Keep confidential drafts, filled context, and reports in authorized local storage outside this repository. Sending them to an external service requires authorization. Optional [genre guidance](genres/README.md) supplies theory or empirical context; neither is required.

## Interpreting the findings

A clean report does not establish empirical truth, sufficient evidence, novelty, or publication readiness. Missing context can leave a finding unresolved. Paragraph guidance distinguishes where a point is placed from whether it is missing, inconsistent, or unsupported. Word-choice and automated pattern checks remain separate from argument judgments.

The [source bibliography](SOURCE-BIBLIOGRAPHY.md) records what was read and the limits of those readings. Sources motivate design; they do not establish checker accuracy or benefits to theorizing. No source books, PDFs, or transcripts are distributed.

Release date: **29 October 2026**. Check definitions: **core-v2.1-2026-10-10**; see [rule versions](levels/RULESET.md). The [file manifest](evidence/FILE-MANIFEST.json) identifies the release contents. Project-owned code and documentation use the [MIT license](LICENSE); [third-party rights](THIRD-PARTY-NOTICES.md) remain separate.
