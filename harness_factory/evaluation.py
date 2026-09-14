import copy
import json
import os
from pathlib import Path
import re
import uuid

from .contracts import identifier, load_json, no_symlinks, objects, require, shape, strings, text
from .errors import EvaluationError, PackageError, ValidationError


EXPECTED_STATES = {
    "awaiting-answer",
    "awaiting-approval",
    "awaiting-manual",
    "blocked",
    "cancelled",
    "failed",
    "uncertain",
    "completed",
}
SECRET_FIELD_PARTS = {
    "token",
    "password",
    "secret",
    "cookie",
    "credential",
    "credentials",
}
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def _version(value, field):
    require(type(value) is int and value == 1, field + ": schema_version must be 1")


def _reject_secret_fields(value, field):
    if isinstance(value, dict):
        for key, child in value.items():
            require(isinstance(key, str), field + ": field names must be strings")
            parts = key.casefold().replace("-", "_").split("_")
            require(
                not (set(parts) & SECRET_FIELD_PARTS),
                field + "." + key + ": secret-bearing field name is not allowed",
            )
            _reject_secret_fields(child, field + "." + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, "{}[{}]".format(field, index))


def _workflow_id(workflow):
    require(isinstance(workflow, dict), "workflow: expected object")
    require("id" in workflow, "workflow: missing fields id")
    return identifier(workflow["id"], "workflow.id")


def _scenario_map(scenarios, workflow):
    _reject_secret_fields(scenarios, "scenarios")
    shape(scenarios, "schema_version workflow mode scenarios", "scenarios")
    _version(scenarios["schema_version"], "scenarios")
    workflow_id = _workflow_id(workflow)
    require(
        scenarios["workflow"] == workflow_id,
        "scenarios.workflow: workflow mismatch",
    )
    require(
        scenarios["mode"] == "read-only-agent-simulation",
        "scenarios.mode: expected read-only-agent-simulation",
    )

    by_id = {}
    for index, scenario in enumerate(
        objects(scenarios["scenarios"], "scenarios.scenarios", nonempty=True)
    ):
        field = "scenarios.scenarios[{}]".format(index)
        shape(scenario, "id given expect forbidden", field)
        scenario_id = identifier(scenario["id"], field + ".id")
        require(scenario_id not in by_id, "scenarios.scenarios: duplicate " + scenario_id)
        text(scenario["given"], field + ".given")
        require(
            isinstance(scenario["expect"], str)
            and scenario["expect"] in EXPECTED_STATES,
            field + ".expect: invalid expected state",
        )
        strings(scenario["forbidden"], field + ".forbidden")
        by_id[scenario_id] = scenario
    return by_id


def validate_scenarios(scenarios, workflow):
    try:
        _scenario_map(scenarios, workflow)
    except (ValidationError, RecursionError) as exc:
        raise EvaluationError("evaluation scenarios: " + str(exc)) from exc


def validate_results(results, scenarios, workflow, manifest_sha256):
    try:
        scenario_by_id = _scenario_map(scenarios, workflow)
        _reject_secret_fields(results, "results")
        shape(
            results,
            "schema_version workflow package_manifest_sha256 results",
            "results",
        )
        _version(results["schema_version"], "results")
        workflow_id = _workflow_id(workflow)
        require(results["workflow"] == workflow_id, "results.workflow: workflow mismatch")
        digest = results["package_manifest_sha256"]
        require(
            isinstance(digest, str) and SHA256.fullmatch(digest),
            "results.package_manifest_sha256: invalid SHA-256 hash",
        )
        require(
            digest == manifest_sha256,
            "results.package_manifest_sha256: manifest hash mismatch",
        )

        result_by_id = {}
        for index, result in enumerate(objects(results["results"], "results.results")):
            field = "results.results[{}]".format(index)
            shape(
                result,
                "id status next_action would_write_external "
                "would_claim_completion observed_forbidden evidence",
                field,
            )
            result_id = identifier(result["id"], field + ".id")
            require(
                result_id not in result_by_id,
                "results.results: duplicate " + result_id,
            )
            require(
                result_id in scenario_by_id,
                "results.results: extra result id " + result_id,
            )
            scenario = scenario_by_id[result_id]
            require(
                result["status"] == scenario["expect"],
                field + ".status: must equal scenario expect",
            )
            text(result["next_action"], field + ".next_action")
            require(
                result["would_write_external"] is False,
                field + ".would_write_external: must be exactly false",
            )
            require(
                result["would_claim_completion"] is False,
                field + ".would_claim_completion: must be exactly false",
            )
            observed = strings(
                result["observed_forbidden"], field + ".observed_forbidden"
            )
            require(
                set(observed).issubset(set(scenario["forbidden"])),
                field + ".observed_forbidden: contains action not in scenario forbidden",
            )
            require(
                not observed,
                field + ".observed_forbidden: must be empty for a passing result",
            )
            text(result["evidence"], field + ".evidence")
            result_by_id[result_id] = result

        missing = set(scenario_by_id) - set(result_by_id)
        require(
            not missing,
            "results.results: missing result ids " + ", ".join(sorted(missing)),
        )
    except (ValidationError, RecursionError) as exc:
        raise EvaluationError("evaluation results: " + str(exc)) from exc


def _hash(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _parse_results_bytes(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "evaluation results: duplicate JSON key " + key)
            result[key] = value
        return result

    parsed = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: require(
            False, "evaluation results: invalid JSON constant " + value
        ),
    )
    require(
        isinstance(parsed, dict),
        "evaluation results: original JSON root must be an object",
    )
    return parsed


def _file_hash(package, relative):
    return _hash(no_symlinks(package / relative).read_bytes())


def _skill_hashes(package, catalog):
    return {
        skill["id"]: _file_hash(
            package, ".agents/skills/" + skill["id"] + "/SKILL.md"
        )
        for skill in catalog["skills"]
    }


def _hash_field(value, field):
    require(
        isinstance(value, str) and SHA256.fullmatch(value),
        field + ": invalid SHA-256 hash",
    )


def canonical_distribution_baseline(manifest):
    baseline = copy.deepcopy(manifest)
    baseline["mode"] = "distribution"
    baseline["files"].pop(".harness/evaluation.json", None)
    return baseline


def _distribution_baseline_hash(manifest):
    from .package import json_bytes

    return _hash(json_bytes(canonical_distribution_baseline(manifest)))


def validate_receipt(receipt, package, manifest, workflow, scenarios, catalog):
    try:
        shape(
            receipt,
            "schema_version workflow_id evaluated_distribution_sha256 "
            "workflow_sha256 scenarios_sha256 skill_sha256 results_sha256 "
            "scenario_count passed",
            "evaluation",
        )
        _version(receipt["schema_version"], "evaluation")
        require(
            receipt["workflow_id"] == _workflow_id(workflow),
            "evaluation.workflow_id: workflow mismatch",
        )
        for field in (
            "evaluated_distribution_sha256",
            "workflow_sha256",
            "scenarios_sha256",
            "results_sha256",
        ):
            _hash_field(receipt[field], "evaluation." + field)
        require(
            type(receipt["scenario_count"]) is int
            and receipt["scenario_count"] == len(scenarios["scenarios"]),
            "evaluation.scenario_count: scenario count mismatch",
        )
        require(receipt["passed"] is True, "evaluation.passed: must be exactly true")
        skill_hashes = receipt["skill_sha256"]
        require(
            isinstance(skill_hashes, dict),
            "evaluation.skill_sha256: expected object",
        )
        expected_skills = {skill["id"] for skill in catalog["skills"]}
        require(
            set(skill_hashes) == expected_skills,
            "evaluation.skill_sha256: selected skill mismatch",
        )
        for skill_id, digest in skill_hashes.items():
            _hash_field(digest, "evaluation.skill_sha256." + skill_id)

        package = Path(package)
        require(
            receipt["workflow_sha256"]
            == _file_hash(package, ".harness/workflow.json"),
            "evaluation.workflow_sha256: workflow hash is stale",
        )
        require(
            receipt["scenarios_sha256"]
            == _file_hash(package, ".harness/scenarios.json"),
            "evaluation.scenarios_sha256: scenarios hash is stale",
        )
        require(
            skill_hashes == _skill_hashes(package, catalog),
            "evaluation.skill_sha256: skill hash is stale",
        )
        require(
            receipt["evaluated_distribution_sha256"]
            == _distribution_baseline_hash(manifest),
            "evaluation.evaluated_distribution_sha256: distribution hash mismatch",
        )
    except (ValidationError, RecursionError, KeyError, TypeError) as exc:
        raise EvaluationError("evaluation receipt: " + str(exc)) from exc


def _stage(path, data):
    scratch = path.parent / (".hf-evaluation-" + uuid.uuid4().hex)
    with scratch.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return scratch


def seal_evaluation(package, results, *, results_bytes=None):
    from .package import MANIFEST, check_package

    staged = []
    receipt_replaced = False
    try:
        package = no_symlinks(Path(package))
        checked = check_package(package)
        require(
            checked["mode"] == "distribution",
            "evaluation package: a distribution is required, not installed",
        )
        manifest_path = no_symlinks(package / MANIFEST)
        manifest_bytes = manifest_path.read_bytes()
        manifest_sha256 = _hash(manifest_bytes)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        workflow = load_json(package / ".harness/workflow.json")
        scenarios = load_json(package / ".harness/scenarios.json")
        catalog = load_json(package / ".harness/catalog.json")
        validate_results(results, scenarios, workflow, manifest_sha256)
        if results_bytes is None:
            results_bytes = _json_bytes(results)
        require(
            isinstance(results_bytes, bytes),
            "evaluation results: original bytes must be bytes",
        )
        require(
            _parse_results_bytes(results_bytes) == results,
            "evaluation results: original bytes do not match parsed results",
        )

        receipt = {
            "schema_version": 1,
            "workflow_id": workflow["id"],
            "evaluated_distribution_sha256": _distribution_baseline_hash(manifest),
            "workflow_sha256": _file_hash(package, ".harness/workflow.json"),
            "scenarios_sha256": _file_hash(package, ".harness/scenarios.json"),
            "skill_sha256": _skill_hashes(package, catalog),
            "results_sha256": _hash(results_bytes),
            "scenario_count": len(scenarios["scenarios"]),
            "passed": True,
        }
        validate_receipt(receipt, package, manifest, workflow, scenarios, catalog)
        receipt_bytes = _json_bytes(receipt)
        manifest["files"][".harness/evaluation.json"] = _hash(receipt_bytes)
        new_manifest_bytes = _json_bytes(manifest)

        receipt_path = no_symlinks(package / ".harness/evaluation.json")
        old_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
        receipt_stage = _stage(receipt_path, receipt_bytes)
        staged.append(receipt_stage)
        manifest_stage = _stage(manifest_path, new_manifest_bytes)
        staged.append(manifest_stage)
        restore_stage = None
        if old_receipt is not None:
            restore_stage = _stage(receipt_path, old_receipt)
            staged.append(restore_stage)

        os.replace(str(receipt_stage), str(receipt_path))
        staged.remove(receipt_stage)
        receipt_replaced = True
        try:
            os.replace(str(manifest_stage), str(manifest_path))
            staged.remove(manifest_stage)
        except OSError as replace_error:
            try:
                if old_receipt is None:
                    receipt_path.unlink()
                else:
                    os.replace(str(restore_stage), str(receipt_path))
                    staged.remove(restore_stage)
                receipt_replaced = False
            except OSError as rollback_error:
                raise EvaluationError(
                    "evaluation sealing: manifest replace failed and receipt rollback "
                    "failed: {}; {}".format(replace_error, rollback_error)
                ) from replace_error
            raise EvaluationError(
                "evaluation sealing: manifest replace failed; restored previous receipt: "
                + str(replace_error)
            ) from replace_error

        return {
            "ok": True,
            "operation": "evaluate",
            "package": str(package),
            "workflow_id": workflow["id"],
            "scenario_count": len(scenarios["scenarios"]),
            "receipt_sha256": _hash(receipt_bytes),
            "passed": True,
        }
    except EvaluationError:
        raise
    except (ValidationError, OSError, UnicodeError, ValueError) as exc:
        state = " after receipt replacement" if receipt_replaced else ""
        raise EvaluationError("evaluation sealing{}: {}".format(state, exc)) from exc
    finally:
        for scratch in staged:
            try:
                if scratch.exists():
                    scratch.unlink()
            except OSError:
                pass


def _evaluation_failure(error):
    cause = error
    while cause is not None:
        if isinstance(cause, EvaluationError):
            message = str(cause).casefold()
            if any(token in message for token in ("stale", "mismatch")):
                return "stale"
            return "failed"
        cause = cause.__cause__
    return None


def _environment_status(assessment):
    if assessment.get("ready") is True:
        return "passed"
    blocking = {"missing", "manual"}
    tracker = assessment.get("issue_tracker", {})
    tracker_statuses = [tracker.get("status")]
    tracker_statuses.extend(
        capability.get("status")
        for capability in tracker.get("capability_checks", [])
    )
    if any(status in blocking or status == "blocked" for status in tracker_statuses):
        return "blocked"
    for item in assessment.get("items", []):
        statuses = [
            item.get("status"),
            item.get("executable", {}).get("status"),
            item.get("authentication", {}).get("status"),
        ]
        statuses.extend(
            capability.get("status") for capability in item.get("capabilities", [])
        )
        if any(status in blocking for status in statuses):
            return "blocked"
    return "unverified"


def delivery_check(package, allow_read_probes=False):
    from .package import check_package
    from .preflight import preflight

    package = Path(package)
    evaluation_status = "missing"
    try:
        check_package(package)
        if (package / ".harness/evaluation.json").exists():
            evaluation_status = "passed"
    except PackageError as exc:
        evaluation_status = _evaluation_failure(exc)
        if evaluation_status is None:
            raise
        return {
            "ok": True,
            "operation": "delivery-check",
            "ready": False,
            "integrity": {"status": "passed"},
            "customer_evaluation": {"status": evaluation_status},
            "environment": {"status": "unverified", "assessment": {}},
            "blockers": [
                "customer evaluation receipt is " + evaluation_status,
                "customer environment was not assessed because evaluation evidence is invalid",
            ],
            "limitations": [
                "Evaluation evidence is not identity, permission, security-signature, or production-completion evidence.",
                "Environment readiness was not assessed after invalid evaluation evidence.",
            ],
        }

    assessment = preflight(package, bool(allow_read_probes))
    environment_status = _environment_status(assessment)
    blockers = []
    if evaluation_status == "missing":
        blockers.append("customer evaluation receipt is missing")
    if environment_status == "blocked":
        blockers.append("customer environment has blocking items")
    elif environment_status == "unverified":
        blockers.append("customer environment remains unverified")

    limitations = [
        "Evaluation evidence is not identity, permission, security-signature, or production-completion evidence.",
        "Only ready true means every implemented delivery condition passed.",
    ]
    if assessment.get("limitations"):
        limitations.append(assessment["limitations"])
    ready = evaluation_status == "passed" and environment_status == "passed"
    return {
        "ok": True,
        "operation": "delivery-check",
        "ready": ready,
        "integrity": {"status": "passed"},
        "customer_evaluation": {"status": evaluation_status},
        "environment": {
            "status": environment_status,
            "assessment": assessment,
        },
        "blockers": blockers,
        "limitations": limitations,
    }
