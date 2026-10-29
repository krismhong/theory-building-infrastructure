# Agent execution entry point

Reuse the Python runner for preparation, parsing, merging, rechecks, and receipts. The human's scope, confidentiality permissions, and budget govern execution. Reason through an available agent interface; no API account is assumed.

## Prepare and execute within authorization

- Run from this folder with Python 3.10+. The core uses only its standard library.
- Choose a Markdown draft and fresh output outside this repository for actual work. Inspect sibling `model.md`, `project.md`, and `rulings.md`, which the CLI can discover; exclude unintended context.
- No genre is required. Optionally select `--genre genres/theory-paper.md` or `genres/empirical-paper.md`. `--project`, `--personal`, and `--sources` are authorized context, never new core criteria. No outlet configuration is needed.
- Before dispatch state scope, job count, estimated agent usage, and unavailable usage metrics. For this project's own work, semantic evaluation requires separate authorization; no API spending is authorized here.
- Preserve the ruleset marker in each report. See `levels/RULESET.md`; changed criteria invalidate comparisons with older runs.

### Whole draft

```text
python -B -m runner script <draft.md> --out <run>
python -B -m runner bundle <draft.md> --out <run> --level all
```

Use the same context options throughout. Each printed line is `bundle -> report`. Give a fresh isolated checker only that bundle and its report destination. Prevent inherited project notes, previous findings, answer keys, and other reports from entering its context. If isolation is unavailable, disclose that before claiming independence; sequential checking with shared memory does not satisfy it.

Confirm each job completed; preserve raw bytes, executor/model metadata and usage when available, marking unknown fields unknown. Interrupted or token-limited responses are incomplete. Only author-confirmed interpretations may be shared with other initial levels.

For every prepared job return `executor-<label>.json` with task identity, confirmed completion, exact report/bundle SHA-256, backend, executor ID, model identity and known usage (otherwise `null`). Merge and route reject missing/empty/malformed reports, missing receipts and changed prepared inputs. See [completion and recovery](RUN-COMPLETENESS.md) for the receipt schema, failure states and legacy-run boundary.

```text
python -B -m runner merge <run> --draft <draft.md>
```

Merge groups locations, not semantic equivalence. After all independent reports, give a separate horizontal verifier the draft and findings to examine same-parent fit, duplication, disagreement, and missing context. Preserve raw flags and unresolved judgments. Whole-draft merge has no automatic horizontal dispatcher or verifier receipt validator; an external coordinator must record completion. Optional `route`/conferring is a different protocol; only each flag's checker revises or withdraws it.

### Bounded section with receipts

`python -B tools/section_trial.py --help` gives exact commands. `--input <section.md> --out <run>` prepares independent Level-3/full-Level-4 tasks. Input and output must be in dedicated local Temp storage outside Git/sync. The helper executes nothing. Dispatch through an authorized agent interface and return the receipt schema specified in each task. Preflight, then accept in the prescribed order. `--reuse` reuses unchanged preparation, never authorizes execution. A gated comparison is optional; do not dispatch it merely because it is prepared.

After both independent reports are accepted, `--verification --out <run>` prepares the separate verifier. Confirm completion and use `--verification-response <response.json>` for coverage/reference validation. This checks structure, not correct judgments.

## Decisions and rechecks

Present `decisions.md`, keeping `logic_defect`, `indeterminate`, `policy_note`, and `reference_check` visible. Legacy unclassified reports remain legacy evidence. Missing context needs a question, not an invented failure; clean logic does not establish truth/evidence sufficiency.

Keep topic-sentence-first within paragraph-level logic-related structure guidance. Rule 3.1 distinguishes placement from absent/inconsistent claims; Level 4 checks support, explanation, qualification, and conflict. Placement alone is a calibrated structure finding (`policy_note`), not an automatic invalid-logic count or a proofreading pass.

The author chooses revisions. Reuse `bundle --from <previous>` and `merge --from <previous>`; inspect the plan, prepare `--level all`, then additional `--level 4` and `--level 5` pass-down tasks. Preserve previous runs and author rulings. A ruleset change requires a fresh check, not incremental carryover.

## Optional API adapters

Only explicitly selected live adapters in `check`/`recheck` call an API, with authorization and endpoint-specific setup. Stub responses are offline plumbing, not semantic checking.

- `--provider openai-compatible --model <name> --base-url <endpoint>`: standard-library HTTP; a key only if the endpoint requires it. `--api-key-env <name>` selects its variable. Local endpoints may need none.
- `--provider anthropic --model <name>`: install `anthropic` separately only for this optional choice and configure its credential. No model, reasoning mode, or fallback is assumed. Optional `--effort` needs model support.
- For a bounded authorized trial set `--max-tokens` and `--retries 0`. Live compatibility and semantic performance are unverified.

## Offline verification

`python -B -m unittest discover -s tests` runs synthetic/mocked tests. `python -B tools/offline_smoke.py` guards network access and exercises the workflow. Neither dispatches agents or models.
