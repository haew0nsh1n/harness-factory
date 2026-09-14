from test_package import PackageCase
from harness_factory.errors import HarnessError
import json
import copy

from harness_factory.records import record


class RecordTests(PackageCase):
    def call(self, status, evidence=None, **kwargs):
        return record(self.package, kwargs.pop("run", "run-one"), kwargs.pop("step", "build"),
                      status, evidence, **kwargs)

    def test_completion_requires_start_and_evidence(self):
        self.generate()
        with self.assertRaises(HarnessError):
            self.call("completed", "artifact reviewed")
        self.call("running")
        with self.assertRaises(HarnessError):
            self.call("completed")
        result = self.call("completed", "artifact reviewed")
        self.assertEqual(result["record"]["steps"]["build"]["status"], "completed")
        self.assertEqual(result["record"]["steps"]["build"]["evidence"], "artifact reviewed")
        with self.assertRaises(HarnessError):
            self.call("running")

    def test_failed_dependencies_block_descendants(self):
        self.workflow["steps"].append(self.step(id="next", needs=["build"], inputs=["change"], outputs=["final"]))
        self.generate()
        with self.assertRaisesRegex(HarnessError, "depend"):
            self.call("running", step="next")
        self.call("running")
        self.call("failed", "tests failed")
        with self.assertRaisesRegex(HarnessError, "depend"):
            self.call("running", step="next")

    def test_approval_cannot_be_bypassed_and_denial_blocks(self):
        self.workflow["steps"][0].update(effect="external-write", approval=True, approver="owner")
        self.generate()
        with self.assertRaisesRegex(HarnessError, "approval"):
            self.call("running")
        self.call("awaiting-approval")
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval", decision="approved", by="owner")
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval", "approved", decision="approved", by="stranger")
        self.call("awaiting-approval", "declined", decision="denied", by="owner")
        for status in ["running", "completed", "pending", "awaiting-approval"]:
            with self.subTest(status=status), self.assertRaises(HarnessError):
                self.call(status, "try bypass")

    def test_uncertain_external_write_no_replay_even_new_run(self):
        self.workflow["steps"][0].update(effect="external-write", approval=True, approver="owner")
        self.generate()
        self.call("awaiting-approval", "human approval", decision="approved", by="owner")
        self.call("running")
        self.call("uncertain", "connection lost after submitting")
        for run in ["run-one", "run-two"]:
            with self.subTest(run=run), self.assertRaisesRegex(HarnessError, "uncertain"):
                self.call("running", run=run)
        self.call("completed", "Human confirmed exact external object and receipt")
        result = self.call("pending", run="run-two")
        self.assertEqual(result["record"]["steps"]["build"]["status"], "pending")

    def test_manual_handoff_and_unsafe_run_ids(self):
        self.workflow["steps"][0].update(effect="manual", manual={
            "owner": "owner", "instructions": "Review", "resume_when": "Reviewed evidence"})
        self.generate()
        with self.assertRaises(HarnessError):
            self.call("running")
        self.call("awaiting-manual")
        self.call("completed", "Owner confirmed reviewed artifact")
        with self.assertRaises(HarnessError):
            self.call("pending", run="../escape")

    def test_uncertain_manual_publication_also_blocks_new_run(self):
        self.workflow["steps"][0].update(effect="manual", approval=True, approver="owner", manual={
            "owner": "owner", "instructions": "Publish PR", "resume_when": "PR URL verified"})
        self.generate()
        self.call("awaiting-approval", "human consent", decision="approved", by="owner")
        self.call("awaiting-manual")
        self.call("uncertain", "Owner lost connection during publication")
        with self.assertRaisesRegex(HarnessError, "uncertain"):
            self.call("awaiting-approval", run="run-two")

    def test_corrupt_history_is_not_silently_replaced(self):
        self.generate()
        self.call("pending")
        path = self.package / ".harness/runs/run-one.json"
        path.write_text("{")
        with self.assertRaises(HarnessError):
            self.call("running")
        self.assertEqual(path.read_text(), "{")

    def test_approval_cannot_be_injected_during_completion(self):
        self.workflow["steps"][0].update(approval=True, approver="owner")
        self.generate()
        with self.assertRaisesRegex(HarnessError, "approval"):
            self.call("completed", "Claim", decision="approved", by="owner")
        self.call("awaiting-approval", "Explicit owner approval", decision="approved", by="owner")
        self.call("running")
        self.call("completed", "Actual artifacts checked")
        state = json.loads((self.package / ".harness/runs/run-one.json").read_text())
        self.assertEqual([event["status"] for event in state["events"]],
                         ["awaiting-approval", "running", "completed"])
        self.assertEqual(state["events"][0]["evidence"], "Explicit owner approval")

    def test_lock_and_symlink_runs_fail_closed(self):
        self.generate()
        runs = self.package / ".harness/runs"
        runs.mkdir()
        (runs / ".record-lock").mkdir()
        with self.assertRaisesRegex(HarnessError, "lock"):
            self.call("pending")
        self.assertTrue((runs / ".record-lock").exists())
        (runs / ".record-lock").rmdir()
        (runs / "linked.json").symlink_to(self.root / "license.txt")
        with self.assertRaisesRegex(HarnessError, "symlink"):
            self.call("pending")

    def test_after_approval_requires_draft_submission_then_human_decision(self):
        self.workflow["steps"][0].update(approval=True, approver="owner", approval_timing="after")
        self.workflow["steps"].append(self.step(id="next", needs=["build"], inputs=["change"], outputs=["final"]))
        self.generate()
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval", "No draft yet", decision="approved", by="owner")
        self.call("running")
        with self.assertRaises(HarnessError):
            self.call("completed", "Unapproved draft")
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval")
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval", "Skipped submission", decision="approved", by="owner")
        self.call("awaiting-approval", "Draft: docs/work/change.md; review requested")
        self.call("running")
        self.call("awaiting-approval", "Revised draft: docs/work/change.md")
        self.call("awaiting-approval", "Owner approves the revised draft", decision="approved", by="owner")
        with self.assertRaises(HarnessError):
            self.call("running")
        with self.assertRaisesRegex(HarnessError, "depend"):
            self.call("running", step="next")
        completed = self.call("completed", "Approved artifact and completion checks verified")
        self.assertEqual(completed["record"]["steps"]["build"]["status"], "completed")
        self.call("running", step="next")

    def test_before_approval_does_not_allow_running_then_submit_for_approval(self):
        self.workflow["steps"][0].update(approval=True, approver="owner", approval_timing="before")
        self.generate()
        with self.assertRaisesRegex(HarnessError, "approval"):
            self.call("running")
        self.call("awaiting-approval", "Owner authorizes action", decision="approved", by="owner")
        self.call("running")
        with self.assertRaises(HarnessError):
            self.call("awaiting-approval", "Not an output gate")

    def test_after_approval_denial_is_cancelled_with_preserved_submission(self):
        self.workflow["steps"][0].update(approval=True, approver="owner", approval_timing="after")
        self.generate()
        self.call("running")
        self.call("awaiting-approval", "Draft artifact supplied")
        result = self.call("awaiting-approval", "Owner rejects the draft", decision="denied", by="owner")
        self.assertEqual(result["record"]["steps"]["build"]["status"], "cancelled")
        self.assertEqual(result["record"]["events"][1]["evidence"], "Draft artifact supplied")
        with self.assertRaises(HarnessError):
            self.call("running")

    def test_dangling_manual_uncertainty_cannot_be_erased_from_snapshot(self):
        self.workflow["steps"][0].update(effect="manual", manual={
            "owner": "owner", "instructions": "Publish manually", "resume_when": "Outcome verified"})
        self.generate()
        self.call("awaiting-manual")
        self.call("uncertain", "Publication result unknown")
        path = self.package / ".harness/runs/run-one.json"
        data = json.loads(path.read_text())
        data["steps"] = {}
        path.write_text(json.dumps(data))
        original = path.read_bytes()
        for run in ("run-one", "run-two"):
            with self.subTest(run=run), self.assertRaisesRegex(HarnessError, "history|snapshot"):
                self.call("pending", run=run)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_event_shapes_and_types_block_all_new_progress(self):
        self.generate()
        self.call("running")
        path = self.package / ".harness/runs/run-one.json"
        original = json.loads(path.read_text())
        events = [None, "completed", [], {}, {**original["events"][0], "extra": True},
                  {**original["events"][0], "step": "unknown"},
                  {**original["events"][0], "status": "invented"},
                  {**original["events"][0], "evidence": {}},
                  {**original["events"][0], "at": 3}]
        for event in events:
            data = copy.deepcopy(original)
            data["steps"] = {}
            data["events"] = [event]
            path.write_text(json.dumps(data))
            for run in ("run-one", "run-two"):
                with self.subTest(event=event, run=run), self.assertRaises(HarnessError):
                    self.call("pending", run=run)
        data["events"] = []
        path.write_text(json.dumps(data))
        with self.assertRaises(HarnessError):
            self.call("pending", run="run-two")

    def test_history_replay_rejects_invalid_transitions_even_matching_snapshot(self):
        self.generate()
        self.call("running")
        path = self.package / ".harness/runs/run-one.json"
        data = json.loads(path.read_text())
        event = data["events"][0]
        event.update(status="completed", evidence="Completion without start")
        data["steps"]["build"] = {key: value for key, value in event.items() if key != "step"}
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(HarnessError, "transition|history"):
            self.call("pending", run="run-two")

    def test_history_replay_rejects_mismatched_approval_decisions(self):
        self.workflow["steps"][0].update(approval=True, approver="owner")
        self.generate()
        self.call("awaiting-approval", "Owner approves", decision="approved", by="owner")
        self.call("running")
        path = self.package / ".harness/runs/run-one.json"
        original = json.loads(path.read_text())
        for mutation in ("erased-decision", "changed-actor", "contradictory-snapshot"):
            data = copy.deepcopy(original)
            if mutation == "erased-decision":
                data["events"][1].update(decision=None, by=None)
            elif mutation == "changed-actor":
                data["events"][1]["by"] = "other"
            else:
                data["steps"]["build"]["decision"] = "denied"
            path.write_text(json.dumps(data))
            with self.subTest(mutation=mutation), self.assertRaises(HarnessError):
                self.call("pending", run="run-two")
