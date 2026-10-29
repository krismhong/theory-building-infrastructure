# Completed runs and failure recovery

The runner validates completion before merging or routing prepared reports. This checks structure, not whether a judgment is correct. The five levels and their criteria are unchanged.

## Agent handoff

Use the same draft, context options and fresh output folder throughout preparation. The runner saves the draft, ruleset, input fingerprint, bundles and expected jobs before processing results. Do not edit those artifacts or reuse a folder for a different draft or task.

For every entry in `jobs.json`, return its nonempty `level-<label>.md` and `executor-<label>.json`. Split labels such as `4-1`, `5-2` and `4-b` identify distinct tasks.

A report must have:

- Exactly one current `Ruleset:` marker and the assigned `## Level N` heading.
- Complete findings with valid rule, location, literal verbatim Quote, What fails, Decision, Kind and Assessment fields. Quotes must occur in the prepared draft.
- Exactly one nonempty `### Pass down` section. Use `None` when nothing is routed; do not combine it with routed items.
- For zero findings, the explicit statement `No issues found at Level N`. A Summary section remains optional.

Only after an executor actually finishes, the coordinator records a receipt:

```json
{
  "task": "3",
  "status": "completed",
  "completion_confirmed": true,
  "report_sha256": "<SHA-256 of the exact report bytes>",
  "bundle_sha256": "<SHA-256 from the prepared task>",
  "backend": "agent-interface",
  "executor_id": "<the actual executor identifier>",
  "model": "<served model, or explicitly requested/unknown identity>",
  "stop_reason": null,
  "usage": null
}
```

Use the exact job label, lowercase hashes and identifiable executor/backend/model fields. Label a requested model when the served identity is unavailable; do not invent it. Unknown usage is `null`. Optional metadata may be added. Known incomplete/refusal/filter/error stop reasons are rejected. A receipt is evidence from the trusted coordinator, not independent proof of execution or correctness.

For an authorized Python coordinator, `runner.report_contract.receipt_for(...)` produces the structural record after the report exists. Replace its default provider/job executor identifier with the actual external executor ID when applicable. Never use it to certify an unexecuted task.

Merge checks expected job coverage, task/report/bundle hashes, report schema and input/ruleset consistency. Unexpected reports and missing, empty or unconfirmed reports block completion. Route uses the same preflight. A merge covers exactly its listed prepared tasks; selected levels and scoped rechecks do not mean that every level checked the whole draft.

The local script pass (`level-S.md`) is separate from semantic executor jobs. Horizontal verification remains a separate authorized agent step; completed merge does not assert that verification occurred.

## Optional adapters and partial failures

Adapters accept nonempty text with a recognized terminal reason: `stop`, `end_turn` or `stop_sequence`. Refusal, filtering, token/context limits, tool-only responses, missing/unknown stop reasons and unusable content cannot become completed reports. Available parsed completion metadata and usage accompany these errors. Malformed HTTP/SDK failures may have no available usage; unknown does not mean zero.

Native check/recheck saves each successful report, receipt and metadata as futures finish. If a sibling fails, remaining dispatched results are still collected and saved. Expected jobs, draft and ruleset are preserved. Available partial/error text is kept as `incomplete-<label>.md`, outside the merge's report filename pattern.

`execution.json` records task statuses; `run.json` is explicitly `incomplete` on failure. No completed decisions are produced. Network/SDK exceptions retain their type rather than dumping potentially sensitive diagnostics into the summary. A process kill, storage failure or power loss can prevent the next write; this is not a transactional execution service.

No automatic retry or resume of a failed native round is performed. Preserve the folder and review the task statuses, receipts, partial text and available usage before authorizing another run in a fresh folder. Completed evidence remains available for inspection and deliberate reuse when inputs, bundles and authorization match.

## Merge failures and previous rounds

Failed preflight writes `merge-status.json` with `status: incomplete` and `decisions_current: false`. Existing decisions and status records are preserved as `.previous`, `.previous-1`, etc. Current status is invalidated so an old result is not presented as current.

For manual bundle/merge work, finish an incomplete handoff by supplying the missing valid reports/receipts and rerunning merge. Failed native executor rounds stay failed and require a fresh round. Do not clear their failure state to force a merge.

Incremental carry-forward requires a previously completed merge with matching decision/draft hashes and current completion evidence. Preparation binds those previous artifacts; later changes block carry-forward. A model change that explicitly triggers a full fresh check does not reuse old decisions. An unchanged, completed prior round may legitimately need zero new jobs.

Legacy parsers still read earlier reports and preserve unclassified/version fields. Old folders lacking the new input/job/receipt/completion records are not automatically certified or upgraded by merge/recheck. Keep them as historical evidence and start a fresh prepared run. Deliberate reuse of old raw reports needs documented executor completion, exact matching bundles and explicit new receipts; file existence alone does not establish completion.
