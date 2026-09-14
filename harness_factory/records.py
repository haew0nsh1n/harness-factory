from datetime import datetime, timezone
from pathlib import Path

from .contracts import identifier, load_json, no_symlinks, require, shape, text
from .errors import HarnessError, RecordError
from .package import RUNS, atomic_write, check_package, hash_bytes, json_bytes

STATUSES = ("pending", "running", "awaiting-approval", "awaiting-manual",
            "completed", "failed", "cancelled", "uncertain")
TERMINAL = {"completed", "failed", "cancelled", "uncertain"}


def _timestamp(value, field):
    text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordError(field + ": expected ISO date-time") from exc
    require(parsed.tzinfo is not None, field + ": timezone required")


def _validate_state(state, field):
    shape(state, "status evidence decision by at", field)
    require(isinstance(state["status"], str) and state["status"] in STATUSES, field + ".status: invalid status")
    require(state["decision"] in (None, "approved", "denied"), field + ".decision: invalid decision")
    require((state["decision"] is None) == (state["by"] is None), field + ": decision and identity must agree")
    for name in ("evidence", "by"):
        if state[name] is not None:
            text(state[name], field + "." + name)
    if state["status"] in TERMINAL or state["decision"] is not None:
        text(state["evidence"], field + ".evidence")
    _timestamp(state["at"], field + ".at")


def _transition(specs, snapshots, step, status, evidence, decision, by, at):
    require(step in specs, "record.step: unknown workflow step")
    require(isinstance(status, str) and status in STATUSES, "record.status: unknown status")
    require(decision in (None, "approved", "denied"), "record.decision: expected approved or denied")
    require((decision is None) == (by is None), "record.by: provide identity only with an approval decision")
    if evidence is not None:
        text(evidence, "record.evidence")
    if status in TERMINAL or decision is not None:
        text(evidence, "record.evidence: terminal states and approval decisions require evidence")
    _timestamp(at, "record.at")
    spec = specs[step]
    after = spec.get("approval_timing", "before") == "after"
    current = snapshots.get(step, {"status": "pending", "evidence": None, "decision": None, "by": None, "at": None})
    old = current["status"]
    require(current["decision"] != "denied", "record.approval: denied; progression is blocked")
    require(old not in ("completed", "failed", "cancelled"), "record: terminal step cannot be restarted")
    if decision is not None:
        require(status == "awaiting-approval" and spec["approval"], "record.approval: decision requires an approval gate")
        require(by == spec["approver"], "record.approval: by must match the named approver (human assertion)")
        require(current["decision"] is None, "record.approval: decision is already recorded")
        if after and decision == "approved":
            require(old == "awaiting-approval", "record.approval: submit the draft before recording its human decision")
    if status not in ("pending", "cancelled"):
        for dependency in spec["needs"]:
            prior = snapshots.get(dependency, {})
            require(prior.get("status") == "completed", "record.dependencies: " + dependency + " is not completed")
            if specs[dependency]["approval"]:
                require(prior.get("decision") == "approved" and prior.get("by") == specs[dependency]["approver"],
                        "record.dependencies: " + dependency + " lacks approval")
    requires_approval = spec["approval"] and (
        status == "completed" or (not after and status in ("running", "awaiting-manual", "uncertain")))
    if requires_approval:
        require(current["decision"] == "approved" and current["by"] == spec["approver"],
                "record.approval: explicit approved decision from named approver required")
    transitions = {
        "pending": {"pending", "running", "awaiting-manual", "cancelled"} | (set() if after else {"awaiting-approval"}),
        "awaiting-approval": {"awaiting-approval", "running", "cancelled"} |
                             ({"completed", "failed"} if after else {"awaiting-manual"}),
        "running": {"completed", "failed", "cancelled", "uncertain"} | ({"awaiting-approval"} if after else set()),
        "awaiting-manual": {"completed", "failed", "cancelled", "uncertain"},
        "uncertain": {"completed", "failed", "cancelled"},
    }
    require(status in transitions.get(old, set()), "record.status: invalid transition {} -> {}".format(old, status))
    if status == "awaiting-approval":
        require(spec["approval"], "record.approval: step has no approval gate")
        require(current["decision"] is None, "record.approval: decision is already recorded")
        if after:
            text(evidence, "record.evidence: draft submission or its approval decision requires evidence")
    if after and status == "completed":
        require(old == "awaiting-approval", "record.approval: complete only the submitted and approved output")
    if status == "running":
        require(spec["manual"] is None, "record.manual: explicit handoff requires awaiting-manual")
        require(not after or current["decision"] is None, "record.approval: approved output cannot reenter running")
    if status == "awaiting-manual":
        require(spec["manual"] is not None, "record.manual: step has no manual handoff")
    return {"status": "cancelled" if decision == "denied" else status,
            "evidence": evidence if evidence is not None else current["evidence"],
            "decision": decision or current["decision"], "by": by or current["by"], "at": at}


def _read_record(path, workflow, workflow_hash):
    data = load_json(path)
    shape(data, "schema_version workflow_id workflow_hash run_id steps events", "record")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "record.schema_version: expected 1")
    require(data["workflow_id"] == workflow["id"] and data["workflow_hash"] == workflow_hash,
            "record: workflow changed; reconcile historical records before continuing")
    identifier(data["run_id"], "record.run_id")
    require(path.stem == data["run_id"], "record.run_id: filename mismatch")
    require(isinstance(data["steps"], dict) and isinstance(data["events"], list) and bool(data["events"]),
            "record.history: expected snapshots and a nonempty event array")
    specs = {s["id"]: s for s in workflow["steps"]}
    for step_id, snapshot in data["steps"].items():
        require(step_id in specs, "record.snapshot: unknown step")
        _validate_state(snapshot, "record.snapshot." + step_id)
    snapshots = {}
    for index, event in enumerate(data["events"]):
        field = "record.history[{}]".format(index)
        shape(event, "step status evidence decision by at", field)
        identifier(event["step"], field + ".step")
        state = {key: value for key, value in event.items() if key != "step"}
        _validate_state(state, field)
        current = snapshots.get(event["step"], {})
        decision = by = None
        if current.get("decision") is None:
            decision, by = event["decision"], event["by"]
        else:
            require((event["decision"], event["by"]) == (current["decision"], current["by"]),
                    field + ": approval decision or identity contradicts history")
        requested = "awaiting-approval" if decision == "denied" else event["status"]
        replayed = _transition(specs, snapshots, event["step"], requested, event["evidence"], decision, by, event["at"])
        require(replayed == state, field + ": event contradicts replayed state")
        snapshots[event["step"]] = replayed
    require(data["steps"] == snapshots, "record.snapshot: does not match replayed history")
    return data


def record(package, run, step, status, evidence=None, decision=None, by=None):
    lock = None
    locked = False
    try:
        package = no_symlinks(package)
        check_package(package)
        identifier(run, "record.run")
        identifier(step, "record.step")
        require(status in STATUSES, "record.status: unknown status")
        if evidence is not None:
            text(evidence, "record.evidence")
        if status in TERMINAL or decision is not None:
            text(evidence, "record.evidence: terminal states and approval decisions require evidence")
        require(decision in (None, "approved", "denied"), "record.decision: expected approved or denied")
        require((decision is None) == (by is None), "record.by: provide identity only with an approval decision")
        workflow_path = package / ".harness/workflow.json"
        workflow = load_json(workflow_path)
        workflow_hash = hash_bytes(workflow_path.read_bytes())
        steps = {s["id"]: s for s in workflow["steps"]}
        require(step in steps, "record.step: unknown workflow step")
        spec = steps[step]
        if decision is not None:
            require(status == "awaiting-approval" and spec["approval"], "record.approval: decision requires an approval gate")
            require(by == spec["approver"], "record.approval: by must match the named approver (human assertion)")
        runs = no_symlinks(package / RUNS)
        runs.mkdir(parents=True, exist_ok=True)
        lock = runs / ".record-lock"
        try:
            lock.mkdir()
            locked = True
        except FileExistsError as exc:
            raise RecordError("record: another writer or stale .record-lock exists; review before removing") from exc
        all_records = [_read_record(no_symlinks(p), workflow, workflow_hash)
                       for p in sorted(runs.glob("*.json"))]
        data = next((r for r in all_records if r["run_id"] == run),
                    {"schema_version": 1, "workflow_id": workflow["id"], "workflow_hash": workflow_hash,
                     "run_id": run, "steps": {}, "events": []})
        old = data["steps"].get(step, {}).get("status", "pending")
        if spec["effect"] in ("external-write", "manual"):
            uncertain_runs = [r["run_id"] for r in all_records
                              if r["steps"].get(step, {}).get("status") == "uncertain"]
            if uncertain_runs:
                require(uncertain_runs == [run] and old == "uncertain"
                        and status in ("completed", "failed", "cancelled"),
                        "record: uncertain external-write outcome blocks replay across all runs; reconcile with evidence")
        state = _transition(steps, data["steps"], step, status, evidence, decision, by,
                            datetime.now(timezone.utc).isoformat())
        data["steps"][step] = state
        data["events"].append({"step": step, **state})
        atomic_write(runs / (run + ".json"), json_bytes(data))
        return {"ok": True, "operation": "record", "record": data,
                "notice": "Evidence and approvals are human assertions, not authenticated identities. No workflow action was executed."}
    except (HarnessError, OSError, UnicodeError) as exc:
        raise RecordError("record: " + str(exc)) from exc
    finally:
        if locked:
            try:
                lock.rmdir()
            except OSError as exc:
                raise RecordError("record: unable to remove writer lock: " + str(exc)) from exc
