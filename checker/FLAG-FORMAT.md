# Flag format

Every finding puts a decision or context question to the author. Record the bundle's exact `Ruleset: <version>` once near the report's start; a rule number has meaning only within that version.

## One finding

```text
[TAG] Rule N.N. Location: <heading, heading-local paragraph number, sentence number>
Quote: "<verbatim passage>"
What fails: <observed defect, missing context, preference, or reference discrepancy>
Decision: <specific choice or context question for the author>
Kind: <fork or slip>
Assessment: <logic_defect, indeterminate, policy_note, or reference_check>
```

The field `What fails` is retained for compatibility; for an indeterminate finding it states what cannot be assessed and why, without asserting failure.

- `logic_defect`: an observed inconsistency or unsupported inferential step within supplied context.
- `indeterminate`: needed context is missing; neither pass nor failure is established.
- `policy_note`: logic-related structure guidance (including default topic-first placement) or a requested optional preference. State which it is. Placement alone does not automatically establish a logical defect.
- `reference_check`: citation/reference integrity, separate from logical validity.

Tags express priority: CRITICAL for an observed failure breaking this level's argument; ISSUE for a defect needing a decision; SUGGEST for optional observations. Use ISSUE/SUGGEST for missing context; do not label it a proven CRITICAL failure. Style alone never earns a defect tag.

`fork` leaves consistent alternatives for the author; `slip` departs from a choice already made. These concern the kind of decision, not its evidentiary certainty.

For multiple passages, name every heading-local paragraph in Location and put all double-quoted verbatim passages on **one literal Quote:** line, separated by semicolons. Do not invent positions or silently correct quotes.

## Report

Start with `Ruleset: <bundle version>`, then `## Level N: <name>`. State Level 1's reading if assigned. List findings in draft order, finish with exactly one `### Pass down` section containing the prescribed location anchors or `None`, then an optional summary.

## Processing

Merging shared quotes/locations produces candidate decision groups, not proof that findings mean the same thing. Keep raw reports and each finding's assessment/version. Later horizontal verification preserves uncertainty and disagreement. Older missing assessment/version fields remain explicitly legacy/unclassified; never infer that they used the new criteria.
