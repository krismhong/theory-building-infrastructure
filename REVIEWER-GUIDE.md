# Review and reproduce the prototype

Artifact release: **2026-10-29**. Check definitions: **core-v2.1-2026-10-10**.

Start with [README.md](README.md) for use, [AGENTS.md](AGENTS.md) for execution, and [RUN-COMPLETENESS.md](RUN-COMPLETENESS.md) for completed-report receipts and failure recovery. The [source-to-check map](levels/SOURCES.md) and [122-source bibliography](SOURCE-BIBLIOGRAPHY.md) distinguish design grounding from measured performance.

## Local verification

Download or clone this repository and run the following from its root with Python 3.10 or later. Python 3.12.14 on Windows was used for the recorded release check. No extra package, credential or API account is needed for these commands.

```text
python -B tools/offline_smoke.py
```

The smoke command runs the complete synthetic/mocked suite and exercises scripted whole-draft checking, mechanical observations, bundle preparation, and bounded report/verifier contracts with network access guarded. It uses a fresh directory in local Temp; ensure TEMP/TMP or the platform equivalent points outside Git repositories and synced folders.

The October 29 result is **115 passed, one skipped, no failures or errors, out of 116 tests**. The skip concerns Windows symlink creation privilege. See [the dated machine-readable evidence](evidence/submission-checks-2026-10-29.json). The exact payload and SHA-256 hashes appear in [FILE-MANIFEST.json](evidence/FILE-MANIFEST.json), excluding the manifest itself. `.gitattributes` preserves exact file bytes in Git checkouts.

For an inspectable scripted example, choose a fresh output folder outside the repository:

```text
python -B -m runner check examples/sample-draft.md --out ../logic-check-demo/stub-01 --provider stub
```

The result includes raw level reports, executor receipts, execution metadata and merged decisions. Stub responses are scripted; they do not assess the sample's argument. Existing output folders are protected against accidental reuse.

## Checking an argument

Use the agent workflow in AGENTS.md. Task preparation alone does not execute a check. A coordinator assigns isolated level checkers, confirms completion and collects hash-bound reports/receipts. A separate horizontal verifier considers relationships among findings. The author supplies missing context and decides revisions. Whole-draft verifier dispatch/receipt checking is not automated by the Python runner.

The engineering evidence does not establish diagnostic accuracy, usefulness to authors, held-out benchmark performance or equivalence across model providers. Optional live API adapters require separate setup and authorization; their live endpoint compatibility is unverified. Independent adjudication and author studies remain future evaluation.

Keep private inputs, filled context, model reports and local logs outside this repository. The included examples are invented, as [documented](examples/PROVENANCE.md). Project-owned material is released under [MIT](LICENSE); [third-party rights](THIRD-PARTY-NOTICES.md) remain separate.
