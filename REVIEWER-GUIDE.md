# A guide for reviewers

Levels of logic examines an argument at five depths so an author can consider how its parts support the overall claim. Separate checkers return questions for the author, and a later verifier compares their findings. At the proposal stage, these materials let a reviewer examine the design, what the software currently does, and how its usefulness would be evaluated. **You can read them without installing Python or setting up an AI account.**

## 1. Understand the design

Read [the five-level overview](levels/README.md), then the [short fictional draft](examples/sample-draft.md). The overview explains which part of an argument each checker examines, while the draft shows the kind of text it accepts. The draft's claims, cases, and sources are invented, so it provides no evidence of diagnostic accuracy.

To inspect a design choice more closely, open [Sources and checks](levels/SOURCES.md). Choose a level and read the relevant row, including its application boundary. The [bibliography](SOURCE-BIBLIOGRAPHY.md) distinguishes selected text, excerpts, abstracts, summaries, and identity-only records. A source may motivate a question without establishing that an AI can answer it reliably.

When checking an argument through an AI agent, a person or the agent coordinates the separate checkers and gathers their reports. A later verifier compares the findings for overlap, conflict, or missing context, allowing the author to consider the findings together before deciding what to revise. The Python program prepares tasks and processes reports, but it does not automatically arrange this reasoning process.

## 2. Read the evidence with the claims in mind

| Evidence in this release | What it establishes | What it does not establish |
|---|---|---|
| [October 29 offline checks](evidence/submission-checks-2026-10-29.json) | Recorded software behavior on synthetic tests and simulated responses: 115 passed, one skipped, no failures or errors, out of 116 tests. | Accuracy of AI judgments, usefulness to authors, or benefits to theory building. |
| [October 21 reliability record](evidence/reliability-checks-2026-10-21.json) | Historical tests of report completion, response handling, and recovery from failures. It also reports a preserved-response replay. | Independent reproduction of that replay from this package: its underlying reports, receipts, and outputs are not provided. |
| [Source bibliography](SOURCE-BIBLIOGRAPHY.md) and [source map](levels/SOURCES.md) | The literature behind design choices, with reading limits and attribution. | A measured test of the checker's performance. |
| [File manifest](evidence/FILE-MANIFEST.json) | The exact package contents, identified by SHA-256 file fingerprints. | The validity of a scientific or diagnostic claim. |

The [evidence overview](evidence/README.md) explains the remaining dated records. The current engineering results do not establish held-out benchmark performance, equivalence across model providers, or live endpoint compatibility. Independent assessment of findings and studies with authors remain future evaluation.

## 3. Optionally inspect a demonstration

To see the output format, install Python 3.10 or later, download or clone the repository, and open a terminal in its root folder. Run:

```text
python -B -m runner check examples/sample-draft.md --out ../logic-check-demo/stub-01 --provider stub
```

Open `decisions.md` in the new `logic-check-demo/stub-01` folder beside the repository to inspect the output format. The same folder contains the original level reports and completion records. Because the `stub` option supplies scripted responses and makes no model call, this demonstration shows how the software handles reports without measuring AI judgment. Choose a fresh output folder each time, because the software protects existing folders from accidental reuse.

## 4. Optionally repeat the software check

From the same repository folder, run:

```text
python -B tools/offline_smoke.py
```

This runs the complete synthetic test suite and exercises the reporting workflow while blocking network access. It prints a result summary and uses a temporary local folder that is removed afterward. No extra Python package or account with a model service is needed. Python 3.12.14 on Windows was used for the recorded October 29 check; its one skip reflects unavailable Windows permission to create a symbolic link.

If temporary-storage checks fail, ensure the operating system's temporary folder (`TEMP`/`TMP` on Windows) is outside a Git repository or synced folder. This storage condition matters for the bounded-section workflow; it is not a request to change a manuscript's location or upload it.

## For a real argument check or implementation review

[AGENTS.md](AGENTS.md) gives the execution instructions. A coordinator must confirm that each checker finished and provide completion records tied to the correct report and input. A completed merge does not establish that the later whole-draft verifier ran. [RUN-COMPLETENESS.md](RUN-COMPLETENESS.md) explains these checks and failure recovery; it is optional implementation detail for the initial review.

Keep private drafts, filled context, model reports, and local logs outside this repository. Optional connections to model services require separate setup and authorization. The sample's [provenance notice](examples/PROVENANCE.md) explains its synthetic status.

Release date: **29 October 2026**. Check definitions: **core-v2.1-2026-10-10**. The release contains 64 files: 63 listed in the manifest, plus the manifest itself. `.gitattributes` preserves exact file bytes across Git platforms. Project-owned materials use [MIT](LICENSE); [third-party rights](THIRD-PARTY-NOTICES.md) remain separate.
