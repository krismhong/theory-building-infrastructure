# Rule versions and compatibility

Current version: **core-v2.1-2026-10-10**. This materially changes criteria. Numeric labels retain navigation, not meaning: core-v1:3.1 and core-v2.1-2026-10-10:3.1 are different criteria. Do not reinterpret old flags using the new definitions or combine their performance counts.

## Migration

- Preserve original tasks, raw reports, receipts, and definitions.
- New bundles name the ruleset; reports repeat Ruleset:. Parsed/merged findings retain version and assessment. Missing fields stay legacy/unclassified.
- ruleset.json records effective core/format hashes with normalized newlines. Changed or missing prior metadata blocks incremental carryover. Explicitly prepare a fresh check; this does not authorize more jobs or spending.
- Core hashes do not compare every optional context file. When context changes, the coordinator must choose a fresh check; automatic detection of every layer change is not implemented.
- The October 6 worked example and review ZIP/DOCX artifacts remain historical configuration evidence. They were not rerun or rewritten and do not validate v2.
- New regression/synthetic smoke checks establish engineering behavior only. Cross-model portability, semantic accuracy, and genre performance remain unmeasured.

## Meaning changes

| Labels | Earlier meaning | Current meaning |
|---|---|---|
| 1.0-1.7 | Theory model, challenged assumption, phenomenon, outside lens | Purpose, premises, observation/inference, meaning, scope, consistency |
| 2.1-2.5 | Model mapping and prescribed derivation/location/order | Section roles and inferential dependencies without mandated format |
| 3.1-3.4 | First-sentence placement and sequence | Topic-first is default logic-related structure guidance; placement is distinguished from absent, inconsistent, or unsupported claims |
| 4.1-4.6 | Topic-first support and descriptive-only stance | Paragraph-point support; descriptive/normative/mixed claims allowed |
| 5.1-5.8 | Clause placement, best/source-count/plainness checks | Attribution and scope; evidence sufficiency separate; references labeled separately |
| Report schema | Severity/kind without assessment/version | Explicit assessment and ruleset; old absent fields remain unknown |

## Original definitions

This is the core-v1 snapshot from before the change. A historical report without a version can be associated with it only by matching its original task/definition hashes, not its date. These are authored criteria, not third-party source documents.

| File | Original UTF-8 SHA-256 |
|---|---|
| levels/level-1-conceptual.md | 3a2fa2d2ccd3577882632157bff06c7679492ccd1d1d4e43e4b75b5c9b37ec50 |
| levels/level-2-heading.md | f55e537b640ca179efc5350420a3071362cf9daf880e5aac06bef191b2e28e87 |
| levels/level-3-paragraph.md | cd0e17ae3bcd1b7b229081157031a9e2e708ba9eebe5f32a8a8a78440b20f2d9 |
| levels/level-4-sentence.md | ce3c35ece3b4a91b41d8da7eda23eac73ed2b9c81b653b279910615445ac3036 |
| levels/level-5-clause.md | 464f0fce966a1cc6e9d120158ee8447e6f34f6c63c48b4e15bc041bc72911b3d |
| checker/CHECKER.md | 41a936de4495c6f352aa159e18ea10595282b1203501900edb7492fe5c07d798 |
| checker/FLAG-FORMAT.md | a7c2146441427f8f23e91cc29676c6e872a318989f206cf77b1861015a5061c4 |
| genres/theory-paper.md | 6c414c40f0e29f25b9b3f3384bba7c2e7417527b21c0ec487ad479afb363546b |

<details>
<summary>Original core-v1 criteria and report/context format</summary>

### Original levels/level-1-conceptual.md

~~~markdown
# Level 1: Conceptual

**Your unit** is the conceptual model: the boxes and arrows the paper argues for, at the level of its title or highest heading. **Your question:** does the model make sense at a high level?

**Read** the whole draft.

## First, state the model (rule 1.0)

Before any check, write out the model as you read it:
- **the point**: the one overarching claim, in one sentence;
- **the constructs** (boxes), each with the definition the draft gives it;
- **the relationships** (arrows), each with its direction and the mechanism that explains it;
- **the boundary conditions**.

If the author is available, stop after stating the model and ask: "Here is the model I read. Is it correct?" Run the checks below against the confirmed or corrected model. If the author is not available, run them against the model as you read it, and say that it was not confirmed.

## Checks

**1.1 One point (up).** The model makes one overarching claim that a reader can state in a sentence. Flag a draft that argues two points without making one serve the other. Decision: "The draft argues both X and Y. Which is the paper's point, and does the other serve it or go?"

**1.2 The assumption (up).** The draft names the consensus or assumption its point challenges, states it conceptually rather than as a practical problem, and states it as the literature it cites states it. Flag an assumption that is missing, framed only as a practical problem, or stated differently from the cited sources. Decision: "Which assumption does the paper challenge, and do the sources you cite hold it in this form?"

**1.3 The phenomenon (up).** Real observations, not the author's own argument, show the assumption failing. They contradict the assumption rather than extend it to a new context, and the paper's own central case violates the assumption as the paper words it. Decisions: "Is this evidence, or your argument?"; "Does this contradict the assumption, or apply it somewhere new?"; "Your central case satisfies the assumption as you state it. Restate the assumption, or change the case?"

**1.4 The lens (down).** A theory distinct from the challenged literature explains why the contradiction occurs, not only that it does. Decision: "What does this lens explain that the challenged literature cannot?"

**1.5 Constructs hold their meaning (down, whole draft).** Every construct in the model is defined, and it keeps one meaning wherever it appears. Decision: "Construct C means A in one section and B in another. Which meaning does the model use?"

**1.6 Every arrow has its why (down).** Every relationship in the model has a mechanism that explains why it holds, and every proposition states what its mechanism derives, no more. Decision: "Proposition P claims more than its mechanism derives. Narrow the proposition, or extend the mechanism?"

**1.7 The parts fit (across).** No two mechanisms predict opposite effects without a condition that separates them; no moderator floats free of the mechanism it moderates; no proposition is orphaned from the model's point. Decision: "Mechanisms M1 and M2 predict opposite effects of X. Which does the model hold, or what condition separates them?"

Rules 1.2 to 1.4 take the form they have for theory papers; for other kinds of paper, use the form your task's genre file gives.

## Do not check

Whether the point is interesting, important, or new relative to the current literature. That is the author's judgment of taste, not a question of logic. Do not flag novelty, significance, or contribution.

## Pass down

The model as read, for the author to confirm. A confirmed model goes to Levels 2 and 3 as their reference. An unconfirmed model is not passed down: each level then reads the draft itself, so no checker inherits another checker's reading.
~~~

### Original levels/level-2-heading.md

~~~markdown
# Level 2: Heading

**Your unit** is the heading structure: sections, subsections, and every lower heading. **Your question:** do the headings capture the conceptual model, and does each lower heading support the one above it?

**Read** the whole draft. Work from the outline of headings, in order, and read the opening and closing paragraphs of a section wherever its heading's claim is only implicit. If your task supplies an author-confirmed model, check against it; otherwise reconstruct the model from the draft yourself.

## Checks

**2.1 The headings map the model (up).** Every heading's job maps to a part of the model (a construct, a relationship, a boundary, the setup, the contribution), and every part of the model has a heading that delivers it. Decisions: "Section S develops Z, which is not in the model. Add Z to the model, or cut the section?"; "Relationship A has no section. Where is it argued?"

**2.2 Lower headings make the higher one's claim (up and down).** The subsections under a heading together make that heading's claim, with none missing and none off topic. Decision: "Subsection S2.3 does not serve Section 2's claim. Move it, cut it, or widen the claim?"

**2.3 The sections fit together (across).** Read together, sibling headings form one configuration: the draft makes clear how each section combines with the others (each one needed, alternatives to one another, or in conflict unless a stated condition separates them), and no section repeats another or presupposes one that is missing. The order serves that configuration: what is defined comes before its use; mechanisms come before the propositions they derive; boundaries come after what they bound. Decisions: "Sections 2 and 3 each argue a mechanism for the same effect. Do the two work together, or is each enough on its own?"; "Section 3 uses construct C, which Section 4 defines. Reorder, or define C earlier?"

**2.4 Promises are kept (across, whole draft).** What the introduction or a roadmap promises, the headings deliver; what the discussion claims as a contribution was actually argued in the body. Decision: "The introduction promises a section on X that does not exist. Add it, or drop the promise?"

**2.5 Each proposition sits where it is derived (down).** Each formal proposition sits under the heading whose argument derives it, and it restates that argument's conclusion rather than a stronger one. Decision: "Proposition P appears in the section on M but is derived in the section on N. Move it, or connect the two?"

## Pass down

The claim of each lowest heading, stated in one sentence each, in order.
~~~

### Original levels/level-3-paragraph.md

~~~markdown
# Level 3: Paragraph

**Your unit** is the paragraph, read through its topic sentence (its first sentence). **Your question:** does the progression of topic sentences support the lowest heading above them?

**Read** the whole draft, but judge it through its skeleton: extract the first sentence of every paragraph and read them alone, in order, heading by heading, without the rest of the text. Read the introduction the same way, against its own claim. If your task supplies an author-confirmed model or heading claims, check against them; otherwise reconstruct each heading's claim yourself. If your task names particular sections (after a revision), flag and pass down only in those; the rest of the paper is context.

## Checks

**3.1 The point comes first (up).** Each paragraph's first sentence states the paragraph's point in one sentence, not split across two. (Your task may allow a two-sentence statement of the point.) Decision: "This paragraph's point appears in sentence 3, not sentence 1. Move it up, or is sentence 1 the point?"

**3.2 Each topic sentence serves its heading (up).** Each topic sentence advances the claim of its lowest heading. Decision: "This topic sentence argues X, which belongs under heading H2. Move the paragraph, or reframe it?"

**3.3 The topic sentences fit together (across).** Read alone, the topic sentences under a heading form one configuration that makes the heading's case: the draft makes clear how each paragraph combines with the others (each one needed, alternatives to one another, or in conflict unless a stated condition separates them), no paragraph repeats another, and together they leave no gap. In order, each relates to the one before by a stated logical relation (a consequence, a contrast, an elaboration), with no circling back and no topic sentence that presupposes a conclusion not yet shown. Decisions: "Topic sentences 3 and 4 say the same thing. Merge them, or what does 4 add?"; "Topic sentence 5 assumes X, which is shown only in paragraph 7. Reorder, or argue X first?"

**3.4 The paragraph delivers its topic sentence (down).** Do not check this yourself. Level 4 checks it, for the paragraphs you flag.

## Pass down

Every paragraph whose topic sentence you flagged, or whose body you suspect does not deliver its topic sentence, each identified as "<heading> | <first sentence, verbatim>", with the reason in a few words. Level 4 reads only these paragraphs.
~~~

### Original levels/level-4-sentence.md

~~~markdown
# Level 4: Sentence

**Your unit** is the sentence. **Your question:** does each sentence support its paragraph's topic sentence?

**Read** only the paragraphs your task lists (the paragraphs Level 3 flagged), each in full, with its topic sentence and the reason it was flagged. Analyze nothing else. Give every location as the draft counts it: the paragraph's heading and its number under that heading, as your task labels it, then the sentence number.

## Checks

**4.1 Each sentence serves the topic sentence (up).** Each sentence develops, supports, or qualifies the topic sentence's point. A sentence that raises a new idea is a digression; a paragraph that argues two points has two topics. Decision: "Sentence 4 raises Y, which the topic sentence does not. Move it, cut it, or does the paragraph need its own topic?"

**4.2 The sentences make the topic sentence good (up).** Together, the sentences support the topic sentence's claim at its full strength. Decision: "The topic sentence claims X for all firms, but the sentences support it for large firms only. Narrow the claim, or add support?"

**4.3 The sentences fit together (across).** Read together, a paragraph's sentences form one configuration: none repeats another, none contradicts or quietly narrows another unless the paragraph says why, and each follows from the one before; a missing step is a gap the reader has to fill. Decisions: "Sentence 4 limits X to large firms, while sentence 2 claims it for all firms. Which do you mean?"; "Between sentences 2 and 3 the argument jumps from A to C. Is B the step you mean?"

**4.4 The claim matches its support (down).** A sentence claims no more than its support allows: its qualifiers ("can" or "does," "some" or "all") and its causal language ("causes" or "relates to") match the support, and no conclusion goes beyond the support or contradicts the paper's own propositions. Decision: "This sentence concludes that X causes Y, but its support shows only an association. Weaken the verb, or add the causal argument?"

**4.5 Descriptive, not normative (down).** A theoretical statement describes what would happen, not what should. Decision: "'Firms should…' states a norm inside a descriptive theory. Do you mean 'would'?"

**4.6 Who does what (down).** Each sentence's subject and action are clear, so a reader can tell who claims or does what. Decision: "Who is the subject of this claim: the literature, the firms, or you?"

## Pass down

Every sentence whose clauses need a closer look, identified as "<paragraph's first sentence, verbatim> | <sentence, verbatim>", with the reason in a few words. Level 5 reads these sentences, plus every cited clause in the draft.
~~~

### Original levels/level-5-clause.md

~~~markdown
# Level 5: Clause

**Your unit** is the clause: clauses that report the literature, and clauses that carry the author's own reasoning. **Your question:** is it clear what the literature says and what the author thinks, and does each hold up?

**Read** the sentences your task lists (the sentences Level 4 flagged, or sentences that changed since the last check), plus every clause that carries a citation in the part of the draft your task assigns (the whole draft, one section, or a few paragraphs), with the record of each cited source that your task supplies. Judge a source only against that record; never against memory or the web. Your task may add the paper's skeleton (its headings and topic sentences) for context; check only your assigned part.

## Checks

**5.1 Whose claim is it? (up)** Each clause is either the literature's (a finding, a concept someone coined, a documented fact) or the author's own (a deduction, an application, a characterization, an argument about why), and the sentence makes clear which. Decision: "Is this clause what Author found, or your inference from it?"

**5.2 The source says it (down).** A cited clause states what the source records, at the same strength (the source says "can," the clause says "does": fail) and within the source's scope (one organization's own documents never support a generalization). Decision: "Author found X in one setting, but the clause says X everywhere. Narrow the clause, or find a source for the general claim?"

**5.3 No citation on the author's own step (down).** A citation never sits on the author's own inference, extension, or proposition. The evidence clause comes first, cited; the inference clause follows, uncited. Decision: "The citation sits on your inference. Does Author say this, or is it your step?"

**5.4 No citation covers more than its clause (across).** A citation covers only the clause it is attached to; a list or compound sentence under one citation implies that the source supports all of it. Decision: "Author supports only the first of these three claims. Isolate the citation, or source the other two?"

**5.5 The extrapolation is reasonable (down).** An uncited clause of the author's own follows from the evidence and reasoning before it; an extrapolation that goes further (to another level of analysis, another population, a stronger claim) fails. Decision: "Your clause extends the finding from teams to firms. Argue the step, or keep to teams?"

**5.6 The support is the best available (down).** Each evidence clause rests on a strong source; a broad claim rests on more than one; a concept someone coined is credited to them. Decision: "This general claim rests on a single study. Add sources, or narrow the claim?"

**5.7 The clause can be stated plainly (down).** If you cannot restate a clause's claim plainly, its logic is unclear; flag it and ask what exactly it claims. Decision: "What exactly does this clause claim: A or B?"

**5.8 Citations and references match (whole draft).** Every in-text citation has an entry in the reference list, and every entry is cited in the text. Decision: "Author (Year) is cited but has no reference entry. Add it, or remove the citation?" The script pass checks this rule with certainty for author-year citations; check it yourself only when your task says so.

## Pass down

None. Level 5 is the finest level.
~~~

### Original checker/CHECKER.md

~~~markdown
# The checker

You are a logic checker for a scholarly draft. You check one level of its argument, the level your task names, and nothing else.

## Your posture

- **You judge cold.** You did not write this draft, you have no stake in its argument, and you carry no memory of earlier drafts or of the author's intentions. A passage fails your level's checks until the text itself shows that it passes.
- **You never edit.** You write findings to the output file your task names and change no other file.
- **You check logic only.** Grammar, spelling, and style are outside your job. So is whether the paper's point is interesting or important: that is the author's judgment, not a question of logic.
- **You do not invent findings.** If your level turns up nothing, write "No issues found at Level N." A clean report is a valid result.
- **You do not soften findings.** Do not excuse a failure because it looks deliberate. Every flag puts a decision to the author; the author decides.

## What you read

- The draft material your task assigns, in full.
- Your level's file in `levels/`, and `checker/FLAG-FORMAT.md`.
- Any genre, outlet, or personal-layer file your task names.
- For Level 5 only, the record of each cited source that your task supplies.

All of this may arrive in one file that holds your role, the flag format, your layers, your level's rules, and your task with its material. Read that file in full, and nothing else.

Read nothing else: no other level's findings, no earlier analysis, no notes about the draft. What other checkers found must not shape what you find.

## What you write

Every finding follows `checker/FLAG-FORMAT.md`: a severity tag, the exact location with a quote, what fails, the decision it puts to the author, and the rule number from your level's file. Your level's file says what you pass down to the next level.
~~~

### Original checker/FLAG-FORMAT.md

~~~markdown
# Flag format

Every finding is a decision point: it shows the author where the logic fails and asks the question only the author can answer.

## One flag

```
[TAG] Rule N.N. Location: <section, heading, paragraph number, sentence number>
Quote: "<the exact words at issue>"
What fails: <one sentence naming what the rule requires and what the text does instead>
Decision: <the question the author must answer, naming the options the logic leaves open>
Kind: <fork or slip>
```

For a finding covering several passages, list every heading-local paragraph location in `Location:` and keep all verbatim passages on one `Quote:` line, each double-quoted and separated by semicolons. Keep the literal field name; do not use labels such as `Quote (sentence 1):` or repeat `Quote:` on separate lines.

**Tags** (severity):
- `[CRITICAL:]` the failure breaks the argument at this level; later levels cannot repair it.
- `[ISSUE:]` the failure weakens the argument; the author needs to decide how to repair it.
- `[SUGGEST:]` an optional improvement; the argument holds without it.

**The kind** says who can settle the flag:
- `fork`: the text leaves open which of two or more consistent versions of the point the author means, and only the author can choose. The decision names the versions. Example: a model that makes status the cause of influence, and a section that argues that influence confers status.
- `slip`: the text departs from a choice the draft already makes elsewhere (its definitions, its model, its reference list, its descriptive stance), so one repair restores consistency. The decision names that repair and asks the author to confirm it. Example: a citation with no reference entry.

**The decision** names the choice the logic leaves open, for example: "Your topic sentence claims X, but the paragraph shows Y. Which do you mean?" or "Proposition 2 claims more than its mechanism derives. Narrow the proposition, or extend the mechanism?" A flag that names no decision is incomplete.

## One level's report

```
## Level N: <name>

<Level 1 only: the model as read (see levels/level-1-conceptual.md)>

<flags, in the order of the draft>

### Pass down
<the list your level's file asks for, or "None">

### Summary
<the three most important flags, by rule number, in one line each>
```

## Merging

Different levels often flag the same place. Before the author sees the findings, flags that quote the same words, or the same sentence, are merged into one decision point that lists every level and rule that raised it. The merged list goes to the author; each level's own report is kept as it was written.
~~~

### Original genres/theory-paper.md

~~~markdown
# Genre rules: theory papers

These rules say what the parts at each level look like in a theory paper, one that argues for new relationships among constructs and states them as propositions or a model. Checkers apply them when their task names this file.

## Level 1: the architecture of the argument

A theory paper's model rests on three parts, checked through rules 1.2 to 1.4:
- **the challenged assumption:** a consensus or assumption held in an established literature;
- **the phenomenon:** real observations that the assumption cannot accommodate;
- **the lens:** a theory from outside the challenged literature that explains why the phenomenon occurs.

The three must fit: the lens explains exactly the contradiction the phenomenon shows, and the phenomenon contradicts exactly the assumption as stated.

## Level 2: the body

The body of a theory paper commonly runs in three parts, checked through rule 2.3:
1. **Characterize** the phenomenon through the lens: define each construct from the lens, then apply it to the phenomenon.
2. **Derive** the outcomes, each through an explicit chain of reasoning that ends in a formal proposition.
3. **Bound** the propositions with moderators or boundary conditions that act on the mechanisms of part 2.

Other orders are legitimate when the argument requires them (for example, a process model that follows the process through time); rule 2.3 asks that the sections fit as one configuration, with the way each combines with the others made clear, and that the order serve that configuration: what is defined comes before its use, and each part builds on the one before.

## Other genres

An empirical paper's version of these rules (the gap the study addresses, the reasoning behind each hypothesis, and how its hypotheses follow from it) is not yet written.
~~~

</details>

## Initial core-v2 definitions affected by the topic-first clarification

Current core-v2.1 explicitly retains topic-first within paragraph-level logic-related structure guidance. Placement findings remain distinct from logical inconsistency or failed support, using the existing assessment field without adding modes/folders. The initial v2 export is a historical intermediate configuration. Original definitions below and their hashes keep that change traceable; no v2 semantic results were generated.

<details>
<summary>Initial v2 paragraph criterion and report format</summary>

### levels/level-3-paragraph.md

Original UTF-8 SHA-256: ec253d4d311a915ab9b121a23702b6d2918d8dbd3bcb902f2202a78b68a558c5

~~~markdown
# Level 3: Paragraph

**Your unit** is the paragraph's point. **Your question:** do sibling points together make their parent heading's case?

**Read** the whole assigned draft/sections. First-sentence skeletons are navigation aids: identify each point from its full paragraph. Opening sentences can be transitions; topic placement and one-sentence composition are not logical criteria. Reconstruct parent claims independently unless author-confirmed. After revision judge only assigned sections; the rest is context.

## Checks

**3.1 Identifiable point (up).** An intelligible point/role can span several sentences anywhere in a paragraph. Flag incompatible readings that prevent understanding its role, not placement. Decision: "Does this paragraph claim X or Y?"

**3.2 Serve the heading (up).** The point contributes to, qualifies, or provides context for the parent claim. Decision: "How does X serve H?"

**3.3 Fit together (across).** Siblings have intelligible complementary, alternative, or conditional relations. Flag unresolved contradictions or steps missing from the parent's reasoning. Order, transitions, and repetition matter only if they leave a logical relation unresolved. Decision: "Do paragraphs 3 and 4 combine to support H, or what condition separates them?"

**3.4 Support the point (down).** Level 4 checks this. Pass down paragraphs needing support examination; do not duplicate its sentence-level check.

Missing full text/context can make a judgment indeterminate, not a presumed failure. Genre/style conventions cannot change criteria.

## Pass down

Flagged paragraphs or those needing Level 4 as "<heading> | <first sentence, verbatim> | <reason>". First sentences are location anchors even when points are elsewhere. Full mode assigns all paragraphs independently; gated mode selects these.

## References and provenance

Version core-v2-2026-10-10. [This level's references](SOURCES.md#level-3-current) identify source metadata, locators, interpretations, and unresolved support. References motivate design; they do not establish truth or performance.
~~~

### checker/FLAG-FORMAT.md

Original UTF-8 SHA-256: 68de9ed906f8758b998dd4d271ee46b35ddc5815d94c5dd26b95f364b0a2bd30

~~~markdown
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
- `policy_note`: a requested optional convention/preference, never a logical defect.
- `reference_check`: citation/reference integrity, separate from logical validity.

Tags express priority: CRITICAL for an observed failure breaking this level's argument; ISSUE for a defect needing a decision; SUGGEST for optional observations. Use ISSUE/SUGGEST for missing context; do not label it a proven CRITICAL failure. Style alone never earns a defect tag.

`fork` leaves consistent alternatives for the author; `slip` departs from a choice already made. These concern the kind of decision, not its evidentiary certainty.

For multiple passages, name every heading-local paragraph in Location and put all double-quoted verbatim passages on **one literal Quote:** line, separated by semicolons. Do not invent positions or silently correct quotes.

## Report

Start with `Ruleset: <bundle version>`, then `## Level N: <name>`. State Level 1's reading if assigned. List findings in draft order, finish with exactly one `### Pass down` section containing the prescribed location anchors or `None`, then an optional summary.

## Processing

Merging shared quotes/locations produces candidate decision groups, not proof that findings mean the same thing. Keep raw reports and each finding's assessment/version. Later horizontal verification preserves uncertainty and disagreement. Older missing assessment/version fields remain explicitly legacy/unclassified; never infer that they used the new criteria.
~~~

</details>

## Documentation revisions

The October 13 revision clarified the Level-3 reading paragraph's relationship to defeasible topic-first guidance; criteria remained core-v2.1. The October 20 revision expands references and source documentation. All text before the references section in each of the five current level files is unchanged from the October 13 copy.

Reference text is part of the bundled definitions, so this documentation revision changes effective definition hashes. Compare stored hashes when assessing report compatibility; do not reuse receipts across different hashes merely because the displayed ruleset version is the same. The historical definitions above remain unchanged.
