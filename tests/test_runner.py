"""Tests for the runner, using the fictional sample draft and a scripted stand-in model (no API calls)."""

import json
import tempfile
import unittest
from pathlib import Path

from runner.cascade import (ROOT, Options, build_system, merge_directory, run_cascade, run_recheck, write_bundles, write_routes,
                            write_script)
from runner.draft import normalize, parse_draft, split_sentences
from runner.flags import assign_flag_ids, merge_flags, parse_flags, parse_pass_down, render_decisions
from runner.mechanical import in_text_citations, reference_entries, script_pass
from runner.prompts import jobs_level_4, personal_for
from runner.providers import StubProvider
from runner.report_contract import receipt_for, write_json
from runner.revise import apply_proposals, apply_rulings, learn, plan_recheck, read_priorities, read_rulings

SAMPLE = ROOT / "examples" / "sample-draft.md"
SAMPLE_TEXT = SAMPLE.read_text(encoding="utf-8")

LEVEL_3 = """Ruleset: core-v2.1-2026-10-10

## Level 3: Paragraph

[ISSUE:] Rule 3.3. Location: Slack Time as the Condition for Reflection, paragraph 3, sentence 1
Quote: "Teams should protect slack time, because reflection always improves performance on later projects"
What fails: The topic sentence turns from explaining learning to prescribing practice, which the heading's claim does not cover.
Decision: Is this paragraph part of the argument about learning, or advice that belongs in the discussion?
Kind: fork
Assessment: logic_defect

### Pass down
- Slack Time as the Condition for Reflection | Teams should protect slack time, because reflection always improves performance on later projects (Evers, 2016). (turns to prescription)

### Summary
3.3
"""

LEVEL_4 = """Ruleset: core-v2.1-2026-10-10

## Level 4: Sentence

[CRITICAL:] Rule 4.5. Location: Slack Time as the Condition for Reflection, paragraph 3, sentence 1
Quote: "Teams should protect slack time"
What fails: A normative statement inside a descriptive theory.
Decision: Do you mean that teams would protect slack time under some condition, or is this advice?
Kind: slip
Assessment: logic_defect

### Pass down
- Teams should protect slack time, because reflection always improves performance on later projects (Evers, 2016). | the same sentence (unsupported "always"; citation not in the reference list)
"""

LEVEL_5 = """Ruleset: core-v2.1-2026-10-10

## Level 5: Clause

[ISSUE:] Rule 5.2. Location: Slack Time as the Condition for Reflection, paragraph 3, sentence 1
Quote: "reflection always improves performance on later projects (Evers, 2016)"
What fails: The clause claims more than one study can show.
Decision: Narrow "always", or add sources?
Kind: fork
Assessment: logic_defect

### Pass down
None
"""


LEVEL_1_P = """Ruleset: core-v2.1-2026-10-10

## Level 1: Conceptual

**The model as read.** Slack time allows a team to learn.

[CRITICAL:] Rule 1.6. Location: Slack Time as the Condition for Reflection, Proposition 1
Quote: "The more slack time a team has at the end of a project, the more the team learns from that project."
What fails: The proposition claims a gradient that the mechanism does not derive.
Decision: Condition or gradient?
Kind: fork
Assessment: logic_defect

### Pass down
None
"""

LEVEL_4_I = """Ruleset: core-v2.1-2026-10-10

## Level 4: Sentence

[ISSUE:] Rule 4.4. Location: Heading "Introduction", paragraph 3, sentence 1
Quote: "is what allows a team to learn from a project"
What fails: This sentence makes slack a condition, while Proposition 1 makes learning rise with slack.
Decision: Condition, gradient, or both?
Kind: fork
Assessment: logic_defect

### Pass down
None
"""


def revise(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new)


class TestDraft(unittest.TestCase):
    def test_sentences_keep_abbreviations_together(self):
        text = "Teams differ (Brandt et al., 2017). Some learn, e.g. by review. Others do not."
        self.assertEqual(len(split_sentences(text)), 3)

    def test_paragraphs_headings_and_sections(self):
        draft = parse_draft(SAMPLE_TEXT)
        self.assertIn("Introduction", {p.heading for p in draft.paragraphs})
        found = draft.find_paragraph("Slack Time as the Condition for Reflection | Teams should protect slack time, because reflection always improves")
        self.assertTrue(found.first_sentence.startswith("Teams should protect slack time"))
        self.assertEqual((found.heading, found.number, found.section), ("Slack Time as the Condition for Reflection", 3, "Slack Time as the Condition for Reflection"))
        self.assertEqual(list(draft.sections()), ["(front matter)", "Introduction", "Slack Time as the Condition for Reflection"])
        self.assertIn("Dorsey, L. (2019)", draft.references_text())
        self.assertIn("- We argue that slack time", draft.skeleton())


class TestScriptPass(unittest.TestCase):
    def test_sample_draft(self):
        result = script_pass(SAMPLE_TEXT)
        flags = parse_flags(result.report, "S")
        rules = sorted(f.rule for f in flags)
        self.assertTrue(result.checked_citations)
        self.assertEqual(rules, ["4.4", "5.8"])  # quantifier question; reference mismatch; "should" is not a defect
        missing = next(f for f in flags if f.rule == "5.8")
        self.assertIn("Evers, 2016", missing.quote)
        self.assertEqual(missing.kind, "slip")

    def test_citation_forms(self):
        text = ("# T\n\n## A\n\nDorsey's (2019) study and Brandt and Cole (2017) agree (see Avery, 2014a, 2016; van Dijk et al., 2001, p. 3). "
                "As Kintsch (1978) showed, readers summarize.\n\n## B\n\nMore text here (Nobody, 2020).\n\n## References\n\n"
                "Avery, J. (2014a). One. *J*, 1.\n\nAvery, J. (2016). Two. *J*, 2.\n\nBrandt, K., & Cole, M. (2017). Three. *J*, 3.\n\n"
                "Dorsey, L. (2019). Four. *J*, 4.\n\nvan Dijk, T. A., Smith, A., & Jones, B. (2001). Five. *J*, 5.\n\n"
                "Kintsch, W. (1979). Six. *J*, 6.\n\nUncited, U. (2010). Seven. *J*, 7.\n")
        draft = parse_draft(text)
        self.assertEqual(len(reference_entries(draft)), 7)
        self.assertEqual({(c.year) for c in in_text_citations(draft)}, {"2019", "2017", "2014a", "2016", "2001", "1978", "2020"})
        flags = [f for f in parse_flags(script_pass(text).report, "S") if f.rule == "5.8"]
        what = " ".join(f.what_fails for f in flags)
        self.assertIn("Nobody, 2020", what)
        self.assertIn("Kintsch (1978)", what)
        self.assertIn("Kintsch (1979); is this the same source", what)
        self.assertIn("Uncited (2010)", what)
        self.assertEqual(len(flags), 4)

    def test_personal_words_and_what_checkers_see(self):
        personal = "# Me\n\n## Words to flag\n\n- leverage -> use\n\n## Priorities\n\n- 4.4: low\n\n## Recurring logic problems\n\nX\n"
        text = SAMPLE_TEXT.replace("allows a team", "leverages a team")
        self.assertFalse(any(f.rule == "P.1" for f in parse_flags(script_pass(text, personal).report, "S")))
        personal_exact = personal.replace("leverage -> use", "leverages -> uses")
        self.assertTrue(any(f.rule == "P.1" for f in parse_flags(script_pass(text, personal_exact).report, "S")))
        seen = personal_for("4", personal)
        self.assertNotIn("Priorities", seen)
        self.assertNotIn("leverage", seen)
        self.assertIn("Recurring logic problems", seen)
        self.assertIn("leverage", personal_for("W", personal))


class TestProjectLayer(unittest.TestCase):
    def test_project_terms_go_to_the_script_and_the_rest_to_every_checker(self):
        project = ("# Project\n\n## The consensus this paper engages\n\nDeadlines improve learning.\n\n"
                   "## Terms\n\n- slack time: the interval before the deadline\n\n## Terms to avoid\n\n- buffer -> slack time\n")
        text = SAMPLE_TEXT.replace("Slack time is the interval", "Buffer time is the interval")
        flags = [f for f in parse_flags(script_pass(text, "", project).report, "S") if f.rule == "P.2"]
        self.assertEqual(len(flags), 1)
        self.assertIn("slack time", flags[0].decision)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.md"
            path.write_text(project)
            system = build_system("1", Options(project=path))
            self.assertIn("Deadlines improve learning", system)
            self.assertIn("slack time: the interval", system)
            self.assertNotIn("buffer -> slack time", system)  # the script checks the terms to avoid; checkers never see the list
            self.assertIn("buffer -> slack time", build_system("W", Options(project=path)))


class TestFlags(unittest.TestCase):
    def test_parse_flags_kind_and_pass_down(self):
        flags = parse_flags(LEVEL_3, "3")
        self.assertEqual((flags[0].severity, flags[0].rule, flags[0].kind), ("ISSUE", "3.3", "fork"))
        self.assertEqual(len(parse_pass_down(LEVEL_3)), 1)
        self.assertEqual(parse_pass_down(LEVEL_5), [])
        self.assertEqual(len(parse_pass_down(LEVEL_3 + "\n\n" + LEVEL_3)), 2)  # joined parts

    def test_pass_down_none_with_a_reason_and_prose_around_a_list(self):
        self.assertEqual(parse_pass_down("### Pass down\n\nNone. The author has not confirmed the model.\n\n### Summary\n- x"), [])
        report = ("### Pass down\nThese paragraphs need Level 4:\n\n- A | First sentence one.\n  Reason: a gap.\n"
                  "- B | First sentence two. (repeats)\n\nThat is all.\n")
        self.assertEqual(parse_pass_down(report), ["A | First sentence one. Reason: a gap.", "B | First sentence two. (repeats)"])

    def test_merge_by_sentence_and_multi_place_flags_stand_alone(self):
        report = ('[ISSUE:] Rule 4.5. Location: x\nQuote: "Teams should protect slack time"\nWhat fails: a\nDecision: b\n\n'
                  '[ISSUE:] Rule 5.8. Location: x\nQuote: "(Evers, 2016)"\nWhat fails: a\nDecision: b\n\n'
                  '[CRITICAL:] Rule 1.5. Location: x\nQuote: "examines its mistakes more carefully" (Introduction); '
                  '"Teams should protect slack time" (Section 2)\nWhat fails: a\nDecision: b\n')
        points = merge_flags(parse_flags(report, "5"), SAMPLE_TEXT)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].severity, "CRITICAL")
        self.assertTrue(all(p.id.startswith("D-") for p in points))

    def test_quote_segments(self):
        from runner.flags import quote_segments
        self.assertEqual(quote_segments('changed more" and "so their mistakes go unexamined'), ["changed more", "so their mistakes go unexamined"])
        self.assertEqual(quote_segments('learned least" (sentence 1); "held longer reviews" (sentence 2)'), ["learned least", "held longer reviews"])
        self.assertEqual(quote_segments("one plain quote"), ["one plain quote"])

    def test_normalize_ignores_emphasis_and_quotes(self):
        self.assertEqual(normalize("**Teams** “should” protect"), normalize("Teams should protect"))


class TestCascade(unittest.TestCase):
    def test_system_prompt_ends_with_the_level_file(self):
        system = build_system("3", Options())
        self.assertIn("# The checker", system)
        self.assertTrue(system.rstrip().endswith((ROOT / "levels/level-3-paragraph.md").read_text(encoding="utf-8").rstrip()))

    def test_checker_files_never_mention_the_benchmark(self):
        words = ("seeded", "planted", "benchmark", "evaluation", "answer key")
        paths = list((ROOT / "levels").glob("level-*.md")) + list((ROOT / "checker").glob("*.md")) + [ROOT / "runner/prompts.py"]
        for path in paths:
            text = path.read_text(encoding="utf-8").lower()
            for word in words:
                self.assertNotIn(word, text, f"{path.name} mentions '{word}'")

    def test_escalation_and_merge_with_stub(self):
        provider = StubProvider({"3": LEVEL_3, "4": LEVEL_4, "5": LEVEL_5})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run-01"
            log = run_cascade(SAMPLE, out, provider, Options(parallel=False), log=lambda _: None)
            levels_called = [level for level, _ in provider.calls]
            self.assertEqual(sorted(levels_called[:3]), ["1", "2", "3"])
            self.assertEqual(levels_called[3:], ["4", "5"])
            level4_task = provider.calls[3][1]
            self.assertIn("Teams should protect slack time", level4_task)
            self.assertNotIn("Research on project teams holds", level4_task)  # Level 4 sees only the paragraphs passed down
            self.assertIn('Heading "Slack Time as the Condition for Reflection", paragraph 3', level4_task)
            self.assertIn("Rule 5.8 (citations and references match) is checked by the script pass", provider.calls[4][1])
            self.assertTrue((out / "decisions.md").exists() and (out / "draft.md").exists())
            self.assertEqual(log["flags_new"], 3 + 2)  # three scripted checker findings; quantifier/reference observations
            # All the flags on the "should protect" sentence, from Levels 3, 4, 5 and the script, make one decision point.
            data = json.loads((out / "decisions.json").read_text())
            point = next(p for p in data["points"] if "Teams should protect" in p["quote"])
            self.assertEqual({f["level"] for f in point["flags"]}, {"3", "4", "5", "S"})
            (out / "decisions.md").unlink()
            merge_directory(out)
            self.assertTrue((out / "decisions.md").exists())

    def test_level_4_skipped_when_level_3_passes_nothing_down(self):
        provider = StubProvider()
        with tempfile.TemporaryDirectory() as tmp:
            run_cascade(SAMPLE, Path(tmp), provider, Options(parallel=False), log=lambda _: None)
            self.assertNotIn("4", [level for level, _ in provider.calls])
            self.assertIn("5", [level for level, _ in provider.calls])

    def test_split_by_section_and_full_coverage(self):
        draft = parse_draft(SAMPLE_TEXT)
        items = [(p, "note") for p in draft.paragraphs if p.section in ("Introduction", "Slack Time as the Condition for Reflection")]
        self.assertEqual(len(jobs_level_4(draft, items, "always", "x")), 2)
        self.assertEqual(len(jobs_level_4(draft, items, "never", "x")), 1)
        provider = StubProvider()
        with tempfile.TemporaryDirectory() as tmp:
            run_cascade(SAMPLE, Path(tmp), provider, Options(parallel=False, full=True, split="always"), log=lambda _: None)
            self.assertEqual([level for level, _ in provider.calls].count("4"), 2)
            self.assertEqual([level for level, _ in provider.calls].count("5"), 2)

    def test_first_rounds_run_every_level_at_once_by_default(self):
        provider = StubProvider({"3": LEVEL_3})
        with tempfile.TemporaryDirectory() as tmp:
            run_cascade(SAMPLE, Path(tmp), provider, Options(split="never"), log=lambda _: None)
            tasks = {level: task for level, task in provider.calls}
            self.assertEqual(sorted(tasks), ["1", "2", "3", "4", "5"])
            self.assertIn("Research on project teams holds", tasks["4"])  # every paragraph, not only those passed down
            self.assertIn("every sentence in your part", tasks["5"])
            self.assertEqual(len(write_bundles(SAMPLE, Path(tmp) / "b", "all", Options(split="never"))), 5)

    def test_bundles_hold_everything_a_checker_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            context = out / "optional-context.md"
            context.write_text("# Optional context\n\nThe turn to the complication is a preference, not a core criterion.")
            written = write_bundles(SAMPLE, out, "1,2,3", Options(genre=ROOT / "genres/theory-paper.md", outlet=context))
            self.assertEqual([b.name for b, _ in written], ["bundle-1.md", "bundle-2.md", "bundle-3.md"])
            text = written[2][0].read_text()
            self.assertIn("# The checker", text)
            self.assertIn("# Level 3: Paragraph", text)
            self.assertIn("The turn to the complication", text)  # the outlet file, for Level 3
            self.assertIn("We argue that slack time", text)  # the draft itself
            self.assertEqual(write_bundles(SAMPLE, out, "4", Options()), [])  # no Level 3 report yet: nothing passed down
            (out / "level-3.md").write_text(LEVEL_3)
            self.assertEqual([b.name for b, _ in write_bundles(SAMPLE, out, "4", Options())], ["bundle-4.md"])
            (out / "level-4.md").write_text(LEVEL_4)
            self.assertIn("Teams should protect slack time", write_bundles(SAMPLE, out, "5", Options())[0][0].read_text())


class TestRecheck(unittest.TestCase):
    def test_plan_follows_the_nest(self):
        # A body sentence changes: Level 4 on its paragraph (one up) and Level 5 on the sentence (at its own depth).
        body = revise(SAMPLE_TEXT, "which is why slack teams hold longer reviews", "which would explain why slack teams hold longer reviews")
        plan = plan_recheck(SAMPLE_TEXT, body)
        self.assertEqual((plan.full, plan.level1, plan.level2, plan.level3_sections), (False, False, False, []))
        self.assertEqual([p.number for p, _ in plan.level4], [2])
        self.assertTrue(any("would explain why" in s for s in plan.level5_sentences))
        # A topic sentence changes: Level 3 on its section (one up) and Level 4 on its paragraph (one down).
        topic = revise(SAMPLE_TEXT, "Reflection requires time that no task claims.", "Slack gives a team time that no task claims.")
        plan = plan_recheck(SAMPLE_TEXT, topic)
        self.assertEqual(plan.level3_sections, ["Slack Time as the Condition for Reflection"])
        self.assertFalse(plan.level1)
        # A proposition changes: the model (Level 1) and the headings (Level 2).
        prop = revise(SAMPLE_TEXT, "The more slack time a team has", "A team with some slack time")
        plan = plan_recheck(SAMPLE_TEXT, prop)
        self.assertTrue(plan.level1 and plan.level2)
        # The author corrects the model: everything is checked against it.
        self.assertTrue(plan_recheck(SAMPLE_TEXT, SAMPLE_TEXT, "old model", "new model").full)
        # No change: nothing to check.
        plan = plan_recheck(SAMPLE_TEXT, SAMPLE_TEXT)
        self.assertEqual((plan.changes, plan.level4), ([], []))

    def test_recheck_carries_forward_marks_moved_up_and_applies_rulings(self):
        first = StubProvider({"3": LEVEL_3, "4": LEVEL_4, "5": LEVEL_5})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run1 = root / "run-01"
            run_cascade(SAMPLE, run1, first, Options(parallel=False), log=lambda _: None)
            old = json.loads((run1 / "decisions.json").read_text())["points"]
            evers = next(p for p in old if "Teams should protect" in p["quote"])

            # The author rules: the "should protect" point is fixed; then revises one body sentence of paragraph 2.
            (root / "rulings.md").write_text(f"{evers['id']} | fixed | changed to would\n")
            revised = root / "draft-2.md"
            revised.write_text(revise(SAMPLE_TEXT, "which is why slack teams hold longer reviews", "which would explain why slack teams hold longer reviews"))
            level_4_new = LEVEL_4.replace('"Teams should protect slack time"', '"which would explain why slack teams hold longer reviews"').replace("Rule 4.5", "Rule 4.2")
            level_4_new = level_4_new.split("### Pass down")[0] + "### Pass down\nNone\n"  # it checked only the revised paragraph
            second = StubProvider({"4": level_4_new})
            log = run_recheck(run1, revised, root / "run-02", second, Options(), root / "rulings.md", log=lambda _: None)
            self.assertEqual(sorted(level for level, _ in second.calls), ["4", "5"])  # Levels 1-3 were not rerun; 4 and 5 ran at once
            data = json.loads((root / "run-02" / "decisions.json").read_text())
            moved = [p for p in data["points"] if any(f["moved_up"] for f in p["flags"])]
            self.assertEqual(len(moved), 1)  # the new Level 4 flag on the revised paragraph: the revision moved up a level
            self.assertIn("would explain why", moved[0]["quote"])
            should = next(p for p in data["points"] if "Teams should protect" in p["quote"])
            self.assertEqual(should["status"], "reappeared")  # ruled fixed, but the text still says "should"
            self.assertTrue(any(f["origin"] == "carried" for f in should["flags"]))
            text = (root / "run-02" / "decisions.md").read_text()
            self.assertIn("Your revision moved up a level", text)
            self.assertTrue((root / "run-02" / "plan.md").exists())
            self.assertGreater(log["flags_carried"], 0)

    def test_carry_forward_marks_changed_words_stale_and_drops_what_was_rechecked(self):
        from runner.revise import carry_forward
        report = ('[ISSUE:] Rule 1.5. Location: x\nQuote: "examines its mistakes more carefully" and "Reflection requires time that no task claims."\nWhat fails: a\nDecision: b\n\n'
                  '[ISSUE:] Rule 4.2. Location: x\nQuote: "Reflection requires time that no task claims."\nWhat fails: a\nDecision: b\n\n'
                  '[ISSUE:] Rule 1.2. Location: x\nQuote: "Research on project teams holds that deadlines focus attention"\nWhat fails: a\nDecision: b\n')
        flags = parse_flags(report, "1")
        flags[1].level = "4"
        old_points = merge_flags(flags, SAMPLE_TEXT)
        revised = revise(SAMPLE_TEXT, "Reflection requires time that no task claims.", "Slack gives a team time that no task claims.")
        paragraph = next(p for p in parse_draft(revised).paragraphs if p.first_sentence.startswith("Slack gives"))
        carried, gone = carry_forward(old_points, revised, {"4": {paragraph.index}}, SAMPLE_TEXT)
        by_rule = {f.rule: f for f in carried}
        self.assertEqual(sorted(by_rule), ["1.2", "1.5"])  # the Level 4 flag was rechecked, so it is dropped
        self.assertTrue(by_rule["1.5"].stale)  # one of its quoted places changed, and Level 1 did not rerun
        self.assertFalse(by_rule["1.2"].stale)
        self.assertEqual(len(gone), 1)

    def test_recheck_waves_in_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run1 = root / "run-01"
            run_cascade(SAMPLE, run1, StubProvider({"3": LEVEL_3, "4": LEVEL_4, "5": LEVEL_5}), Options(), log=lambda _: None)
            revised = root / "draft-2.md"
            revised.write_text(revise(SAMPLE_TEXT, "Reflection requires time that no task claims.", "Slack gives a team time that no task claims."))
            run2 = root / "run-02"
            wave1 = [b.name for b, _ in write_bundles(revised, run2, "all", Options(), run1)]
            self.assertEqual([n.split("-")[1][0] for n in wave1], ["3", "4", "5"])  # scoped Level 3, and Levels 4 and 5 on the changed paragraph, at once
            # Level 3 passes down a further paragraph ("Teams should protect..."), so wave two runs Level 4 on it alone.
            (run2 / "level-3-slack-time-as-the-condition-fo.md").write_text(LEVEL_3)
            wave2 = write_bundles(revised, run2, "4", Options(), run1)
            self.assertEqual([b.name for b, _ in wave2], ["bundle-4-b.md"])
            self.assertIn("Teams should protect slack time", wave2[0][0].read_text(encoding="utf-8"))
            self.assertNotIn("Slack gives a team time", wave2[0][0].read_text(encoding="utf-8").split("# Your task", 1)[1])

    def test_rulings_and_learning(self):
        points = merge_flags(parse_flags(LEVEL_3 + LEVEL_4, "4"), SAMPLE_TEXT)
        rulings = {points[0].id: ("taste", "keep it")}
        apply_rulings(points, rulings)
        self.assertEqual(points[0].status, "new")  # a CRITICAL flag from a fresh check reopens a decided point
        for f in points[0].flags:
            f.severity = "ISSUE"
        points[0].severity = "ISSUE"
        apply_rulings(points, rulings)
        self.assertEqual(points[0].status, "decided")
        self.assertIn("Decided before", render_decisions(points))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = root / "decisions.json"
            ids = [f"D-{i:08x}" for i in range(4)]
            decisions.write_text(json.dumps({"points": [{"id": i, "quote": "q", "flags": [{"rule": "4.4"}]} for i in ids]}))
            (root / "rulings.md").write_text("\n".join(f"{i} | taste" for i in ids[:3]) + f"\n{ids[3]} | fixed\n")
            proposals = learn(read_rulings(root / "rulings.md"), [decisions])
            self.assertEqual([p.rule for p in proposals], ["4.4"])
            personal = root / "me.md"
            personal.write_text("# Me\n")
            apply_proposals(personal, proposals)
            self.assertEqual(read_priorities(personal), {"4.4"})
            self.assertNotIn("Priorities", personal_for("4", personal.read_text()))


class TestOrganizer(unittest.TestCase):
    """The organizer as a traffic controller: it routes flags down the nest; the checkers judge their own flags."""

    def _ids(self, root: Path) -> dict[str, str]:
        """Point ids of the three passages the scripted reports quote, from a round without the organizer."""
        run_cascade(SAMPLE, root / "plain", StubProvider({"1": LEVEL_1_P, "3": LEVEL_3, "4": LEVEL_4_I}), Options(split="never"), log=lambda _: None)
        points = json.loads((root / "plain" / "decisions.json").read_text())["points"]
        find = lambda words: next(p["id"] for p in points if words in p["quote"])
        return {"prop": find("The more slack time"), "intro": find("allows a team to learn"), "should": find("Teams should protect")}

    def test_routing_follows_the_nest(self):
        from runner.organize import routes
        report_4 = LEVEL_4.replace('"Teams should protect slack time"', '"Teams should protect slack time"')
        level_4_intro = LEVEL_4_I.replace("[ISSUE:] Rule 4.4", "[ISSUE:] Rule 4.2")
        level_5 = LEVEL_5 + '\n[ISSUE:] Rule 5.1. Location: x\nQuote: "Teams without slack move to the next task before they reflect"\nWhat fails: a\nDecision: b\n'
        flags = (parse_flags(LEVEL_1_P, "1", "1") + parse_flags(LEVEL_3, "3", "3") + parse_flags(report_4 + level_4_intro, "4", "4")
                 + parse_flags(level_5, "5", "5"))
        points = merge_flags(flags, SAMPLE_TEXT)
        assign_flag_ids(points)
        routed = routes(points, parse_draft(SAMPLE_TEXT))
        above = {label: sorted(h.level + ":" + h.rule for h in higher) for label, (own, higher) in routed.items()}
        self.assertNotIn("1", routed)  # nothing stands above the model
        self.assertEqual(above["3"], ["1:1.6"])
        self.assertEqual(above["4"], ["1:1.6", "3:3.3"])  # Level 3's flag covers its own section only
        # Level 5 sees the Level 4 flags on the paragraphs its own flags sit in, and Level 3's flag only in that flag's section.
        own5 = sorted(f.quote[:20] for f in routed["5"][0])
        self.assertEqual(own5, ["Teams without slack ", "reflection always im"])
        self.assertEqual(above["5"], ["1:1.6", "3:3.3", "4:4.2", "4:4.5"])
        from runner.organize import covers
        draft = parse_draft(SAMPLE_TEXT)
        by_rule = {(f.level, f.rule): f for p in points for f in p.flags}
        sections = {p.index: p.section for p in draft.paragraphs}
        self.assertIsNone(covers(by_rule[("1", "1.6")], draft))  # the model covers everything
        self.assertEqual({sections[i] for i in covers(by_rule[("3", "3.3")], draft)}, {"Slack Time as the Condition for Reflection"})
        self.assertEqual(len(covers(by_rule[("4", "4.2")], draft)), 1)  # a sentence-level flag covers its own paragraph

    def test_organized_round_through_the_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self._ids(root)
            reply_4 = f"## Your flags\n- {ids['intro']}.1 | follows | {ids['prop']}.1 | Both turn on whether slack is a condition or a gradient.\n\n## Disputes\nNone\n"
            reply_3 = (f"## Your flags\n- {ids['should']}.1 | stands\n\n## Disputes\n"
                       f"- {ids['prop']}.1 | The heading says \"Condition\", so the gradient may be the slip, not the fork.\n")
            answer_1 = "## Q1\nVerdict: keep\nReason: The proposition says \"the more\", a gradient, against a heading that says \"Condition\".\n"
            provider = StubProvider({"1": LEVEL_1_P, "3": LEVEL_3, "4": LEVEL_4_I, "A3": reply_3, "A4": reply_4, "A1": answer_1})
            out = root / "run-01"
            log = run_cascade(SAMPLE, out, provider, Options(split="never", organize=True), log=lambda _: None)
            order = [level for level, _ in provider.calls]
            self.assertEqual(sorted(order[-3:-1]), ["A3", "A4"])  # the checkers below reply at once...
            self.assertEqual(order[-1], "A1")  # ...then the disputed flag's checker answers
            self.assertTrue(all(len(h) == 1 for h in provider.histories[-3:]))  # each resumed with its own task and report
            self.assertIn("Conferring with the levels above you", provider.calls[-2][1] + provider.calls[-3][1])
            text = (out / "decisions.md").read_text()
            self.assertIn("## Root questions: answer these first", text)
            self.assertIn("Decision: Condition or gradient?", text)  # the root's question is its checker's own decision
            self.assertIn("Both turn on whether slack is a condition or a gradient.", text)
            self.assertIn("Level 3 disputed this flag", text)
            self.assertIn("kept it", text)
            self.assertTrue((out / "decisions-flat.md").exists())
            data = json.loads((out / "decisions.json").read_text())
            self.assertEqual((data["roots"][0]["flag_id"], data["roots"][0]["followers"]), (f"{ids['prop']}.1", [f"{ids['intro']}.1"]))
            self.assertEqual((log["roots"], log["follows"], log["disputes"], log["withdrawn"]), (1, 1, 1, 0))

    def test_claude_code_path_and_root_rulings_across_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self._ids(root)
            run1 = root / "run-01"
            run1.mkdir()
            for level in ("1", "3", "4"):
                write_bundles(SAMPLE, run1, level, Options(full=True, split="never"))
            for name, text in (("level-1.md", LEVEL_1_P), ("level-3.md", LEVEL_3), ("level-4.md", LEVEL_4_I)):
                (run1 / name).write_text(text, encoding="utf-8")
                label = name[6:-3]
                write_json(run1 / f"executor-{label}.json", receipt_for(run1, label, "fixture", "stop", None, "offline-fixture"))
            write_script(SAMPLE, run1, Options())
            step1 = write_routes(run1, SAMPLE, Options())
            self.assertEqual(sorted(m.name for _, m, _, _ in step1), ["route-3.md", "route-4.md"])
            message = (run1 / "route-4.md").read_text()
            self.assertIn(f"{ids['intro']}.1 | Level 4, rule 4.4", message)
            self.assertIn(f"{ids['prop']}.1 | Level 1, rule 1.6", message.split("# Flags above yours")[1])
            self.assertEqual(len(write_routes(run1, SAMPLE, Options())), 2)  # still waiting for both replies
            (run1 / "reply-4.md").write_text(f"## Your flags\n- {ids['intro']}.1 | follows | {ids['prop']}.1 | same choice\n")
            (run1 / "reply-3.md").write_text(f"## Your flags\n- {ids['should']}.1 | stands\n\n## Disputes\nNone\n")
            self.assertEqual(write_routes(run1, SAMPLE, Options()), [])  # no disputes: nothing more to route
            merge_directory(run1, SAMPLE, log=lambda _: None)
            root_id = json.loads((run1 / "decisions.json").read_text())["roots"][0]["id"]
            self.assertIn(root_id, (run1 / "decisions.md").read_text())

            # The author answers the root question; the next round rechecks a revised body sentence elsewhere.
            (root / "rulings.md").write_text(f"{root_id} | answer | a condition\n")
            revised = root / "draft-2.md"
            revised.write_text(revise(SAMPLE_TEXT, "which is why slack teams hold longer reviews", "which would explain why slack teams hold longer reviews"))
            run_recheck(run1, revised, root / "run-02", StubProvider(), Options(), root / "rulings.md", log=lambda _: None)
            data = json.loads((root / "run-02" / "decisions.json").read_text())
            status = {p["id"]: p["status"] for p in data["points"]}
            self.assertEqual((status[ids["prop"]], status[ids["intro"]]), ("decided", "decided"))  # the root and its follower
            self.assertNotEqual(status[ids["should"]], "decided")  # a flag outside the root is still open
            self.assertIn("answer: a condition", (root / "run-02" / "decisions.md").read_text())

    def test_resolve_withdrawals_circles_and_bad_replies(self):
        from runner.organize import Reply, resolve
        flags = parse_flags(LEVEL_1_P, "1", "1") + parse_flags(LEVEL_4_I, "4", "4") + parse_flags(LEVEL_3, "3", "3")
        points = merge_flags(flags, SAMPLE_TEXT)
        assign_flag_ids(points)
        index = {f.level: f for p in points for f in p.flags}
        one, three, four = index["1"].id, index["3"].id, index["4"].id
        routed = {"4": ([index["4"]], [index["1"], index["3"]]), "3": ([index["3"]], [index["1"]])}
        replies = {"4": ([Reply(four, "follows", three, "x")], []), "3": ([Reply(three, "follows", one, "y")], [])}
        kept, organized = resolve(points, replies, {}, routed)
        self.assertEqual([(r.flag_id, r.followers) for r in organized.roots], [(one, sorted([three, four], key=lambda f: f))])  # chains end at the top
        # A flag whose checker withdraws it leaves the list, and a follower of a withdrawn flag stands, with a note.
        points = merge_flags(flags, SAMPLE_TEXT)
        assign_flag_ids(points)
        replies = {"4": ([Reply(four, "follows", three, "x")], []), "3": ([Reply(three, "withdraw", "", "misread")], [])}
        kept, organized = resolve(points, replies, {}, routed)
        self.assertEqual(organized.roots, [])
        self.assertEqual(len(organized.withdrawn), 1)
        self.assertTrue(any("withdrew" in n for n in organized.notes))
        # A reply naming a flag that was not routed to the checker is ignored.
        points = merge_flags(flags, SAMPLE_TEXT)
        assign_flag_ids(points)
        kept, organized = resolve(points, {"3": ([Reply(three, "follows", four, "z")], [])}, {}, routed)
        self.assertEqual(organized.roots, [])
        self.assertTrue(any("not among the flags routed" in n for n in organized.notes))

    def test_learning_counts_rulings_on_root_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = root / "decisions.json"
            roots = [{"id": f"R-{i:08x}", "flag_id": f"D-{i:08x}.1", "keys": [f"D-{i:08x}|4|4.4"]} for i in range(3)]
            decisions.write_text(json.dumps({"points": [], "roots": roots}))
            (root / "rulings.md").write_text("\n".join(f"{r['id']} | taste" for r in roots) + "\n")
            self.assertEqual([p.rule for p in learn(read_rulings(root / "rulings.md"), [decisions])], ["4.4"])


if __name__ == "__main__":
    unittest.main()
