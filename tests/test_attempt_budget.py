import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/alpha-squad-coding-craft/scripts/assess_attempt_budget.py"
SPEC = importlib.util.spec_from_file_location("assess_attempt_budget", SCRIPT)
BUDGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUDGET)


def pair(model="model-a", effort="medium"):
    return {"model": model, "reasoning_effort": effort}


def proposal(kind="initial", parent=None, reason=None, evidence=None, requested=None):
    return {
        "run_id": "run-1", "stage_id": "stage-1", "attempt_kind": kind,
        "parent_attempt_ref": parent, "change_reason": reason,
        "evidence_refs": evidence or [], "requested": requested or pair(),
    }


def dispatch(event_id, attempt, ordinal, requested=None, role="worker", decision="decision-1",
             native_ref=None, execution_role="worker"):
    attempt_kind = {1: "initial", 2: "repair", 3: "upgrade"}.get(ordinal, "manual")
    payload = {
        "requested": requested or pair(),
        "execution": {
            "contract": "dispatch_receipt_v1", "run_id": "run-1", "stage_id": "stage-1",
            "ordinal": ordinal, "policy_version": "bounded-attempts-v1",
            "enforcement": "advisory", "role": execution_role,
            "attempt_kind": attempt_kind, "status": "started",
            "native_execution_ref": native_ref or f"native:{attempt}",
        },
    }
    if ordinal > 1:
        payload.update({
            "parent_attempt_ref": f"attempt-{ordinal - 1}",
            "change_reason": f"Direction for attempt {ordinal}",
            "evidence_refs": [f"evidence:{ordinal}"],
        })
    return {
        "event_id": event_id, "decision_id": decision, "attempt_ref": attempt,
        "kind": "assignment", "source": {"role": role},
        "payload": payload,
    }


def outcome(event_id, attempt, ordinal, dispatch_id, result="failure", failure="acceptance",
            role="worker", decision="decision-1"):
    return {
        "event_id": event_id, "decision_id": decision, "attempt_ref": attempt,
        "kind": "outcome", "source": {"role": role},
        "payload": {"outcome": result, "status": result, "execution": {
            "contract": "attempt_outcome_v1", "run_id": "run-1", "stage_id": "stage-1",
            "ordinal": ordinal, "policy_version": "bounded-attempts-v1",
            "enforcement": "advisory", "dispatch_event_id": dispatch_id,
            "result": result, "failure_class": failure,
        }},
    }


def attempt(number, result="failure", failure="acceptance", requested=None):
    attempt_id = f"attempt-{number}"
    dispatch_id = f"dispatch-{number}"
    return [
        dispatch(dispatch_id, attempt_id, number, requested),
        outcome(f"outcome-{number}", attempt_id, number, dispatch_id, result, failure),
    ]


def assess(events, proposed):
    return BUDGET.assess({"events": events, "proposal": proposed})


class AttemptBudgetTests(unittest.TestCase):
    def test_initial_is_advisory_and_never_claims_spawn_or_reservation(self):
        result = assess([], proposal())
        self.assertTrue(result["eligible_for_authorization"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["observed_attempts"], 0)
        self.assertEqual(result["next_ordinal"], 1)
        self.assertEqual(result["reason_codes"], [])
        self.assertEqual(result["enforcement"], "advisory")
        self.assertIn("no_atomic_reservation", result["limitations"])
        self.assertIn("fresh_host_catalog_policy_and_confirmation_still_required", result["limitations"])
        self.assertNotIn("reservation", result)
        self.assertNotIn("spawn", result)

    def test_repair_requires_same_pair_parent_and_new_direction(self):
        events = attempt(1)
        valid = proposal("repair", "attempt-1", "Address the failing acceptance test",
                         ["test:failure-1"], pair())
        result = assess(events, valid)
        self.assertTrue(result["eligible_for_authorization"])
        self.assertEqual(result["next_ordinal"], 2)

        variants = {
            "different-pair": {**valid, "requested": pair("model-b", "high")},
            "wrong-parent": {**valid, "parent_attempt_ref": "other"},
            "no-direction": {**valid, "change_reason": None},
            "no-evidence": {**valid, "evidence_refs": []},
            "wrong-kind": {**valid, "attempt_kind": "upgrade"},
        }
        for label, candidate in variants.items():
            with self.subTest(label=label):
                self.assertFalse(assess(events, candidate)["eligible_for_authorization"])

    def test_upgrade_is_third_attempt_only_and_budget_stops_after_three(self):
        events = attempt(1) + attempt(2, failure="capability")
        candidate = proposal("upgrade", "attempt-2", "Use newly authorized capability",
                             ["review:capability-gap"], pair("model-b", "high"))
        result = assess(events, candidate)
        self.assertTrue(result["eligible_for_authorization"])
        self.assertEqual(result["next_ordinal"], 3)
        self.assertFalse(result["execution_authorized"])
        self.assertIn("fresh_host_catalog_policy_and_confirmation_still_required", result["limitations"])

        exhausted = assess(events + attempt(3, requested=pair("model-b", "high")),
                           proposal("upgrade", "attempt-3", "More evidence", ["test:new"], pair("model-c", "high")))
        self.assertFalse(exhausted["eligible_for_authorization"])
        self.assertIn("automatic_budget_exhausted", exhausted["reason_codes"])
        self.assertEqual(exhausted["observed_attempts"], 3)

    def test_unknown_infrastructure_risk_and_success_pause_retry(self):
        cases = [
            ("unknown", "unknown"),
            ("failure", "infrastructure"),
            ("failure", "risk"),
            ("success", None),
        ]
        for result, failure in cases:
            with self.subTest(result=result, failure=failure):
                events = attempt(1, result=result, failure=failure)
                assessed = assess(events, proposal(
                    "repair", "attempt-1", "Retry direction", ["evidence:new"], pair()
                ))
                self.assertFalse(assessed["eligible_for_authorization"])
                self.assertTrue(set(assessed["reason_codes"]) & {
                    "previous_outcome_does_not_allow_retry",
                    "resolve_infrastructure_risk_or_unknown_first",
                })

    def test_actual_attempt_is_deduplicated_across_roles_decisions_and_receipts(self):
        first = dispatch("dispatch-1", "attempt-1", 1, role="worker", decision="decision-a")
        repeated = dispatch("dispatch-observation", "attempt-1", 1, role="reviewer", decision="decision-b")
        terminal = outcome("outcome-1", "attempt-1", 1, "dispatch-1", decision="decision-a")
        exact_replay = copy.deepcopy(first)
        result = assess([first, repeated, exact_replay, terminal], proposal(
            "repair", "attempt-1", "Repair direction", ["review:new"], pair()
        ))
        self.assertEqual(result["observed_attempts"], 1)
        self.assertEqual(result["next_ordinal"], 2)
        self.assertTrue(result["eligible_for_authorization"])

        conflict = copy.deepcopy(first)
        conflict["payload"]["requested"] = pair("other", "high")
        with self.assertRaisesRegex(ValueError, "conflicting content"):
            assess([first, conflict], proposal())

    def test_execution_role_change_does_not_create_another_attempt_or_reset_budget(self):
        first = dispatch("dispatch-1", "attempt-1", 1, role="orchestrator",
                         execution_role="worker")
        changed = dispatch("dispatch-observation", "attempt-1", 1, role="reviewer",
                           execution_role="reviewer")
        terminal = outcome("outcome-1", "attempt-1", 1, "dispatch-1")
        result = assess([first, changed, terminal], proposal(
            "repair", "attempt-1", "Repair direction", ["review:new"], pair()
        ))
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("conflicting_attempt_role", result["reason_codes"])
        self.assertEqual(result["observed_attempts"], 1)
        self.assertEqual(result["next_ordinal"], 2)

    def test_incomplete_or_conflicting_ledgers_fail_closed(self):
        cases = {
            "gap": attempt(2),
            "missing-assignment": [outcome("outcome-1", "attempt-1", 1, "dispatch-1")],
            "missing-outcome": [dispatch("dispatch-1", "attempt-1", 1)],
            "conflicting-ordinal": [dispatch("dispatch-1", "attempt-1", 1),
                                    dispatch("dispatch-2", "attempt-1", 2)],
            "duplicate-outcome": [dispatch("dispatch-1", "attempt-1", 1),
                                  outcome("outcome-1", "attempt-1", 1, "dispatch-1"),
                                  outcome("outcome-2", "attempt-1", 1, "dispatch-1")],
        }
        candidate = proposal("repair", "attempt-1", "Repair", ["evidence"], pair())
        for label, ledger in cases.items():
            with self.subTest(label=label):
                result = assess(ledger, candidate)
                self.assertFalse(result["eligible_for_authorization"])
                self.assertIn("incomplete_or_conflicting_ledger", result["reason_codes"])

    def test_every_outcome_must_match_its_dispatch_and_receipts_remain_advisory(self):
        first = attempt(1)
        first[1]["payload"]["execution"]["dispatch_event_id"] = "wrong-dispatch"
        events = first + attempt(2, failure="capability")
        result = assess(events, proposal(
            "upgrade", "attempt-2", "Capability upgrade", ["review:new"], pair("model-b", "high")
        ))
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("outcome_dispatch_mismatch", result["reason_codes"])

        ordinal_four = [dispatch("dispatch-4", "attempt-4", 4),
                        outcome("outcome-4", "attempt-4", 4, "dispatch-4")]
        telemetry = assess(ordinal_four, proposal(
            "repair", "attempt-4", "Observed overspend", ["receipt:4"], pair()
        ))
        self.assertFalse(telemetry["eligible_for_authorization"])
        self.assertIn("automatic_budget_exhausted", telemetry["reason_codes"])
        self.assertFalse(telemetry["execution_authorized"])

    def test_any_earlier_blocked_outcome_prevents_a_later_upgrade(self):
        events = attempt(1, failure="infrastructure") + attempt(2, failure="capability")
        result = assess(events, proposal(
            "upgrade", "attempt-2", "Capability upgrade", ["review:new"], pair("model-b", "high")
        ))
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("resolve_infrastructure_risk_or_unknown_first", result["reason_codes"])

    def test_historical_dispatch_kind_and_status_must_match_the_policy_chain(self):
        wrong_kind = attempt(1)
        wrong_kind[0]["payload"]["execution"]["attempt_kind"] = "repair"
        result = assess(wrong_kind, proposal(
            "repair", "attempt-1", "Repair direction", ["review:new"], pair()
        ))
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("historical_chain_requires_review", result["reason_codes"])

        wrong_status = attempt(1)
        wrong_status[0]["payload"]["execution"]["status"] = "failed"
        result = assess(wrong_status, proposal(
            "repair", "attempt-1", "Repair direction", ["review:new"], pair()
        ))
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("historical_chain_requires_review", result["reason_codes"])

    def test_latest_post_outcome_review_can_block_retry_or_report_high_risk(self):
        cases = [
            ({"outcome": "blocked"}, "review_blocker_requires_resolution"),
            ({"outcome": "approved", "proposed_labels": {"risk": "high"}},
             "review_blocker_requires_resolution"),
            ({"choice": "declined"}, "user_direction_required"),
        ]
        for index, (payload, reason) in enumerate(cases):
            with self.subTest(payload=payload):
                event = {
                    "event_id": f"blocker-{index}", "decision_id": "decision-1",
                    "attempt_ref": "attempt-1",
                    "kind": "user_choice" if "choice" in payload else "review",
                    "source": {"role": "reviewer"}, "payload": payload,
                }
                result = assess(attempt(1) + [event], proposal(
                    "repair", "attempt-1", "Repair direction", ["review:new"], pair()
                ))
                self.assertFalse(result["eligible_for_authorization"])
                self.assertIn(reason, result["reason_codes"])

    def test_legacy_attempts_fail_closed_but_matching_pre_spawn_assignment_is_not_double_counted(self):
        legacy = dispatch("legacy", "attempt-legacy", 1)
        del legacy["payload"]["execution"]
        result = assess([legacy], proposal())
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("legacy_attempt_coverage_unknown", result["reason_codes"])

        pre_spawn = dispatch("pre-spawn", "attempt-1", 1)
        del pre_spawn["payload"]["execution"]
        result = assess([pre_spawn] + attempt(1), proposal(
            "repair", "attempt-1", "Repair direction", ["review:new"], pair()
        ))
        self.assertTrue(result["eligible_for_authorization"])
        self.assertEqual(result["observed_attempts"], 1)
        self.assertEqual(result["next_ordinal"], 2)

    def test_unknown_requested_pair_and_invalid_receipts_fail_closed(self):
        invalid_pair = proposal()
        invalid_pair["requested"] = {"model": "model-a", "reasoning_effort": None}
        result = assess([], invalid_pair)
        self.assertFalse(result["eligible_for_authorization"])
        self.assertIn("verified_requested_pair_required", result["reason_codes"])

        bad_enforcement = dispatch("dispatch-1", "attempt-1", 1)
        bad_enforcement["payload"]["execution"]["enforcement"] = "automatic"
        too_large = dispatch("dispatch-large", "attempt-large", 1_000_001)
        missing_role = dispatch("dispatch-missing-role", "attempt-missing-role", 1)
        del missing_role["payload"]["execution"]["role"]
        invalid_role = dispatch("dispatch-invalid-role", "attempt-invalid-role", 1)
        invalid_role["payload"]["execution"]["role"] = "parent"
        for label, event in [
                ("enforcement", bad_enforcement), ("ordinal", too_large),
                ("missing-role", missing_role), ("invalid-role", invalid_role)]:
            with self.subTest(receipt=label):
                with self.assertRaises(ValueError):
                    assess([event], proposal())


class AttemptBudgetCliTests(unittest.TestCase):
    def run_cli(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            encoded = json.dumps(document, sort_keys=True)
            path.write_text(encoded)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(path)],
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(path.read_text(), encoded)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            return completed

    def test_cli_prints_same_advisory_assessment_without_side_effects(self):
        document = {"events": attempt(1), "proposal": proposal(
            "repair", "attempt-1", "Target failing check", ["test:1"], pair()
        )}
        completed = self.run_cli(document)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), BUDGET.assess(document))
        self.assertEqual(completed.stderr, "")

    def test_cli_rejects_invalid_or_oversized_input(self):
        invalid = self.run_cli({"events": [], "proposal": {}})
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("Invalid budget input", invalid.stderr)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(path)],
                text=True, capture_output=True, timeout=10,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("exceeds 2 MiB", completed.stderr)


if __name__ == "__main__":
    unittest.main()
