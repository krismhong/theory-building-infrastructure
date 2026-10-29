"""Reliability regressions on synthetic data and mocked adapters; no network/model calls."""
import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from runner.cascade import ROOT, run_cascade, run_recheck, write_bundles, merge_directory
from runner.prompts import Options, RULESET_ID
from runner.providers import (Completion, StubProvider, AnthropicProvider, OpenAICompatibleProvider,
                              IncompleteCompletionError, RefusalError, checked_completion, _level_of)
from runner.report_contract import ReportContractError, validate_report, receipt_for, write_json, read_json

SAMPLE = ROOT / "examples/sample-draft.md"
QUIET = lambda _: None

def clean(level):
    return f"Ruleset: {RULESET_ID}\n\n## Level {level}\n\nNo issues found at Level {level}.\n\n### Pass down\nNone\n"

def flag():
    return (f"Ruleset: {RULESET_ID}\n\n## Level 4\n\n"
            "[ISSUE] Rule 4.4. Location: Slack Time as the Condition for Reflection, paragraph 3\n"
            'Quote: "Teams should protect slack time"\n'
            "What fails: Synthetic contract observation.\nDecision: Confirm the intended premise?\n"
            "Kind: fork\nAssessment: indeterminate\n\n### Pass down\nNone\n")

def submit(out, label, text):
    (out / f"level-{label}.md").write_text(text, encoding="utf-8")
    write_json(out / f"executor-{label}.json", receipt_for(out, label, "scripted-test", "stop", None, "offline-fixture"))

class TestMergeCompletion(unittest.TestCase):
    def test_atomic_status_write_retries_transient_lock_and_preserves_old_record_on_failure(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json";write_json(path,{"status":"running"})
            original=os.replace;calls=[]
            def transient(*args,**kwargs):
                calls.append(1)
                if len(calls)==1:raise PermissionError("Synthetic transient lock")
                return original(*args,**kwargs)
            with patch("runner.report_contract.os.replace",side_effect=transient),patch("runner.report_contract.time.sleep"):
                write_json(path,{"status":"completed"})
            self.assertEqual(len(calls),2);self.assertEqual(read_json(path)["status"],"completed")
            before=path.read_bytes()
            with patch("runner.report_contract.os.replace",side_effect=PermissionError("Synthetic persistent lock")),patch("runner.report_contract.time.sleep"):
                with self.assertRaises(PermissionError):write_json(path,{"status":"incomplete"})
            self.assertEqual(path.read_bytes(),before)

    def test_missing_and_empty_prepared_reports_never_make_clean_decisions(self):
        for mode in ("missing", "empty"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                write_bundles(SAMPLE,out,"all",Options(split="never"))
                if mode=="empty":
                    for job in read_json(out/"jobs.json"): submit(out,job["label"],"")
                with self.assertRaises(ReportContractError): merge_directory(out,SAMPLE,log=QUIET)
                self.assertFalse((out/"decisions.md").exists())
                self.assertEqual(read_json(out/"merge-status.json")["status"],"incomplete")

    def test_clean_full_and_split_runs_with_explicit_none_are_valid(self):
        for split in ("never","always"):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                write_bundles(SAMPLE,out,"all",Options(split=split))
                jobs=read_json(out/"jobs.json")
                for job in jobs: submit(out,job["label"],clean(job["level"]))
                merge_directory(out,SAMPLE,log=QUIET)
                self.assertEqual(read_json(out/"merge-status.json")["completed_tasks"],[j["label"] for j in jobs])
                self.assertEqual(read_json(out/"decisions.json")["points"],[])

    def test_malformed_reports_are_not_silently_parsed_as_clean(self):
        good=flag()
        bad=["", " \n", clean("4").replace("No issues found at Level 4.",""),
             good.replace("### Pass down\nNone",""), good.replace("None\n",""),
             good.replace("## Level 4","## Level 3"),good.replace(RULESET_ID,"older"),
             good.replace("[ISSUE]","[BROKEN]"),good.replace("Assessment: indeterminate\n",""),
             good.replace("Kind: fork","Kind: forkish"),good.replace("Rule 4.4","Rule 4.999"),
             good.replace("Decision: Confirm the intended premise?","Decision:"),
             good.replace("Quote:","Quote two:"),good.replace("Teams should protect slack time","Unquoted invented words"),
             good.replace("Kind: fork","Kind: fork\nKind: slip"),
             clean("4").replace("### Pass down","Quote: orphan\n### Pass down"),
             clean("4").replace("No issues found at Level 4.", "Unfinished narrative."),
             clean("4").replace("None", "None\n- Introduction | A routed paragraph.")]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ReportContractError): validate_report(text,"4",SAMPLE.read_text(encoding="utf-8"))
        validate_report(good,"4",SAMPLE.read_text(encoding="utf-8"))

    def test_receipts_must_confirm_exact_task_bundle_and_report(self):
        mutations=[("model",""),("backend",""),("executor_id",""),("task","5"),("status","failed"),("completion_confirmed",False),
                   ("report_sha256","0"*64),("bundle_sha256","0"*64),("stop_reason","length"),
                   ("stop_reason","content_filter"),("stop_reason","mystery"),("stop_reason",[])]
        for key,value in mutations:
            with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp); write_bundles(SAMPLE,out,"4",Options(full=True,split="never"))
                submit(out,"4",flag()); receipt=read_json(out/"executor-4.json");receipt[key]=value
                write_json(out/"executor-4.json",receipt)
                with self.assertRaises(ReportContractError): merge_directory(out,SAMPLE,log=QUIET)

    def test_missing_receipt_and_unexpected_report_reject(self):
        for mode in ("receipt","extra"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);write_bundles(SAMPLE,out,"3",Options());submit(out,"3",clean("3"))
                if mode=="receipt": (out/"executor-3.json").unlink()
                else: (out/"level-4.md").write_text(clean("4"),encoding="utf-8")
                with self.assertRaises(ReportContractError): merge_directory(out,SAMPLE,log=QUIET)

    def test_changed_inputs_and_invalid_job_manifests_reject(self):
        for mode in ("draft","bundle","ruleset","duplicate","unsafe","empty"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);write_bundles(SAMPLE,out,"3",Options());submit(out,"3",clean("3"))
                draft=SAMPLE
                if mode=="draft":
                    draft=out/"changed.md";draft.write_text(SAMPLE.read_text(encoding="utf-8")+"\nChanged.",encoding="utf-8")
                elif mode=="bundle": (out/"bundle-3.md").write_text("changed",encoding="utf-8")
                elif mode=="ruleset": write_json(out/"ruleset.json",{})
                else:
                    jobs=read_json(out/"jobs.json")
                    if mode=="duplicate":jobs+=jobs
                    elif mode=="unsafe":jobs[0]["label"]="../outside"
                    else:jobs=[]
                    write_json(out/"jobs.json",jobs)
                with self.assertRaises(ReportContractError):merge_directory(out,draft,log=QUIET)

    def test_invalid_remerge_archives_previous_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);run_cascade(SAMPLE,out,StubProvider(),Options(),log=QUIET)
            original=(out/"decisions.json").read_bytes()
            (out/"level-3.md").write_text("",encoding="utf-8")
            with self.assertRaises(ReportContractError):merge_directory(out,log=QUIET)
            self.assertFalse((out/"decisions.json").exists())
            self.assertEqual((out/"decisions.json.previous").read_bytes(),original)
            self.assertFalse(read_json(out/"merge-status.json")["decisions_current"])
            self.assertEqual(read_json(out/"run.json")["status"],"incomplete")
            self.assertEqual(read_json(out/"execution.json")["status"],"failed")

    def test_unchanged_recheck_with_zero_new_jobs_preserves_prior_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            run_cascade(SAMPLE,old,StubProvider(),Options(),log=QUIET)
            provider=StubProvider();result=run_recheck(old,SAMPLE,new,provider,Options(),log=QUIET)
            self.assertEqual(provider.calls,[]);self.assertEqual(result["status"],"completed")
            self.assertEqual(read_json(new/"jobs.json"),[])

    def test_manual_route_rejects_incomplete_report_set(self):
        from runner.cascade import write_routes
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);write_bundles(SAMPLE,out,"all",Options())
            with self.assertRaises(ReportContractError):write_routes(out,SAMPLE)
            self.assertFalse((out/"routes.json").exists())

    def test_incomplete_previous_round_cannot_become_clean_zero_job_recheck(self):
        class Fail(StubProvider):
            def complete(self,*a,**k):raise RuntimeError("Synthetic outage")
        with tempfile.TemporaryDirectory() as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            with self.assertRaises(ReportContractError):run_cascade(SAMPLE,old,Fail(),Options(),log=QUIET)
            provider=StubProvider()
            with self.assertRaises(ReportContractError):run_recheck(old,SAMPLE,new,provider,Options(),log=QUIET)
            self.assertEqual(provider.calls,[])
            self.assertFalse((new/"decisions.json").exists())

    def test_prior_decisions_are_bound_to_prepared_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            run_cascade(SAMPLE,old,StubProvider(),Options(),log=QUIET)
            write_bundles(SAMPLE,new,"all",Options(),old)
            (old/"decisions.json").write_text('{"points":[]}',encoding="utf-8")
            with self.assertRaises(ReportContractError):merge_directory(new,SAMPLE,prev_dir=old,log=QUIET)

class TestUnusableCompletions(unittest.TestCase):
    def test_stop_and_text_contract_retains_unusable_completion(self):
        for text,reason in [("", "stop"),(" \n","end_turn"),(None,"stop"),(["text"],"stop"),
                            ("Partial",""),("Partial","unknown"),("Partial","tool_calls"),
                            ("Partial","refusal"),("Partial","content_filter"),("Partial",[])]:
            with self.subTest(text=text,reason=reason):
                result=Completion(text,"mock",reason,{"output_tokens":17})
                with self.assertRaises((IncompleteCompletionError,RefusalError)) as error:checked_completion(result)
                self.assertIs(error.exception.completion,result)
        for reason in ("stop","end_turn","stop_sequence"):
            result=Completion("Completed.","mock",reason)
            self.assertIs(checked_completion(result),result)

    def test_compatible_adapter_rejects_bad_payloads_without_network(self):
        messages=[({"content":None},"content_filter"),({"content":"","refusal":"Synthetic refusal"},"stop"),
                  ({"content":""},"stop"),({"content":[]},"stop"),({"content":"Not done"},"tool_calls"),
                  ({"content":"Not done","tool_calls":[{}]},"stop"),({"content":"Not done"},None)]
        payloads=[{"model":"mock","choices":[{"message":m,"finish_reason":r}],"usage":{"output_tokens":9}} for m,r in messages]
        payloads += [{"usage":{"output_tokens":9},"choices":[]},{"usage":{"output_tokens":9},"choices":[None]}]
        for payload in payloads:
            with self.subTest(payload=payload),patch.dict("os.environ",{},clear=True):
                provider=OpenAICompatibleProvider("mock","http://synthetic.invalid",retries=0)
                with patch("runner.providers.urllib.request.urlopen",return_value=io.BytesIO(json.dumps(payload).encode())) as call:
                    with self.assertRaises((IncompleteCompletionError,RefusalError)) as error:provider.complete("synthetic","synthetic")
                self.assertEqual(error.exception.completion.usage["output_tokens"],9);call.assert_called_once()

    def test_anthropic_empty_and_refusal_keep_usage(self):
        for text,reason in [("","end_turn"),("Synthetic refusal","refusal"),(None,"end_turn")]:
            with self.subTest(text=text,reason=reason):
                sdk=MagicMock()
                message=SimpleNamespace(stop_reason=reason,model="mock",content=[SimpleNamespace(type="text",text=text)],
                                        usage=SimpleNamespace(input_tokens=7,output_tokens=3))
                sdk.Anthropic.return_value.messages.stream.return_value.__enter__.return_value.get_final_message.return_value=message
                with patch.dict("sys.modules",{"anthropic":sdk}):
                    with self.assertRaises((IncompleteCompletionError,RefusalError)) as error:
                        AnthropicProvider("mock",retries=0).complete("synthetic","synthetic")
                self.assertEqual(error.exception.completion.usage["output_tokens"],3)

class TestPartialFailure(unittest.TestCase):
    def test_successes_and_failed_usage_survive_parallel_failure(self):
        class Partial:
            name="offline-fixture";model="not-a-model"
            def __init__(self):self.barrier=threading.Barrier(5)
            def complete(self,system,user,history=None):
                level=_level_of(system);self.barrier.wait(timeout=10)
                if level=="2":raise IncompleteCompletionError(Completion("Partial.","mock","length",{"output_tokens":11}))
                return Completion(clean(level),"mock","stop",{"output_tokens":12})
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with self.assertRaises(ReportContractError):run_cascade(SAMPLE,out,Partial(),Options(split="never"),log=QUIET)
            self.assertEqual(sorted(p.name for p in out.glob("level-[1-5].md")),["level-1.md","level-3.md","level-4.md","level-5.md"])
            self.assertEqual(len(read_json(out/"jobs.json")),5)
            state=read_json(out/"run.json");self.assertEqual(state["status"],"incomplete")
            self.assertEqual(state["levels"]["2"]["usage"]["output_tokens"],11)
            self.assertTrue((out/"incomplete-2.md").exists())
            for level in ("1","3","4","5"):
                self.assertEqual(read_json(out/f"executor-{level}.json")["status"],"completed")
            self.assertFalse((out/"decisions.md").exists())
            with self.assertRaises(ReportContractError):merge_directory(out,log=QUIET)
            with self.assertRaises(FileExistsError):run_cascade(SAMPLE,out,StubProvider(),Options(),log=QUIET)

    def test_custom_provider_bad_schema_and_empty_completion_cannot_merge(self):
        class Bad:
            def __init__(self,text):self.text=text
            def complete(self,*a,**k):return Completion(self.text,"mock","stop",{"output_tokens":1})
        for text in ("","This is not a checker report."):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                with self.assertRaises(ReportContractError):run_cascade(SAMPLE,out,Bad(text),Options(),log=QUIET)
                self.assertEqual(read_json(out/"run.json")["status"],"incomplete")
                self.assertFalse((out/"decisions.json").exists())

    def test_recheck_split_failure_keeps_completed_sibling(self):
        class FailFive(StubProvider):
            def complete(self,system,user,history=None):
                if _level_of(system)=="5":raise RuntimeError("Synthetic outage")
                return super().complete(system,user,history)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/"old";out=root/"recheck"
            run_cascade(SAMPLE,old,StubProvider(),Options(),log=QUIET)
            draft=root/"revised.md";draft.write_text(SAMPLE.read_text(encoding="utf-8").replace("which is why slack teams","which may explain why slack teams"),encoding="utf-8")
            with self.assertRaises(ReportContractError):run_recheck(old,draft,out,FailFive(),Options(split="always"),log=QUIET)
            self.assertTrue(list(out.glob("level-4*.md")))
            self.assertFalse(list(out.glob("level-5*.md")))
            self.assertEqual(read_json(out/"run.json")["status"],"incomplete")

    def test_success_is_on_disk_before_slow_sibling_finishes(self):
        release=threading.Event();saved=threading.Event();errors=[]
        class Slow(StubProvider):
            def complete(self,system,user,history=None):
                if _level_of(system)!="1":release.wait(timeout=10)
                return super().complete(system,user,history)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            def run():
                try:run_cascade(SAMPLE,out,Slow(),Options(split="never"),log=lambda line:saved.set() if line.startswith("Level 1 done") else None)
                except BaseException as error:errors.append(error)
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(saved.wait(timeout=10))
                self.assertTrue((out/"level-1.md").exists())
                self.assertTrue((out/"executor-1.json").exists())
                self.assertFalse((out/"decisions.json").exists())
            finally:release.set();worker.join(timeout=15)
            self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
            self.assertEqual(read_json(out/"run.json")["status"],"completed")
