#!/usr/bin/env python3
"""Check an observed stage ledger before authorization; never spawn or save data."""
import argparse
import hashlib
import json
from pathlib import Path


POLICY = "bounded-attempts-v1"


def text(value):
    return isinstance(value, str) and bool(value.strip())


def pair(value):
    if not isinstance(value, dict) or not text(value.get("model")):
        return None
    if not text(value.get("reasoning_effort")):
        return None
    return value["model"], value["reasoning_effort"]


def assess(document):
    if not isinstance(document, dict) or set(document) != {"events", "proposal"}:
        raise ValueError("expected events and proposal")
    proposal = document["proposal"]
    required = {"run_id", "stage_id", "attempt_kind", "parent_attempt_ref",
                "change_reason", "evidence_refs", "requested"}
    if not isinstance(proposal, dict) or set(proposal) != required:
        raise ValueError("proposal fields do not match the contract")
    if not all(text(proposal[key]) for key in ("run_id", "stage_id", "attempt_kind")):
        raise ValueError("proposal identity is missing")
    if proposal["attempt_kind"] not in {"initial", "repair", "upgrade", "manual"}:
        raise ValueError("unknown attempt kind")
    events = document["events"]
    if not isinstance(events, list) or len(events) > 256:
        raise ValueError("events must be a bounded stage ledger")
    evidence = proposal["evidence_refs"]
    if (not isinstance(evidence, list) or len(evidence) > 32
            or any(not text(item) for item in evidence)
            or len(evidence) != len(set(evidence))):
        raise ValueError("proposal evidence references are invalid")
    if proposal["parent_attempt_ref"] is not None and not text(proposal["parent_attempt_ref"]):
        raise ValueError("invalid parent attempt")
    if proposal["change_reason"] is not None and not text(proposal["change_reason"]):
        raise ValueError("invalid change reason")

    attempts = {}
    legacy_attempts = []
    unique = {}
    conflicts = []
    for event in events:
        if not isinstance(event, dict) or not text(event.get("event_id")):
            raise ValueError("ledger event identity is missing")
        event_id = event["event_id"]
        if event_id in unique:
            if unique[event_id] != event:
                raise ValueError("same event ID has conflicting content")
            continue
        unique[event_id] = event
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("ledger event payload is malformed")
        if event.get("kind") == "review":
            states = [payload.get(key) for key in ("disposition", "outcome", "status")]
            labels = payload.get("proposed_labels", {})
            if (any(state in {"blocked", "rejected", "disagree"} for state in states)
                    or isinstance(labels, dict) and labels.get("risk") == "high"):
                conflicts.append("review_blocker_requires_resolution")
        if event.get("kind") == "user_choice" and (payload.get("accepted") is False
                or payload.get("choice") in {"declined", "rejected", "modified"}):
            conflicts.append("user_direction_required")
        execution = payload.get("execution")
        if execution is None:
            if event.get("kind") in {"assignment", "outcome"}:
                legacy_attempts.append(event)
            continue
        if not isinstance(execution, dict):
            raise ValueError("invalid execution receipt")
        if any(execution.get(key) != proposal[key] for key in ("run_id", "stage_id")):
            raise ValueError("ledger contains another run or stage")
        kind = event.get("kind")
        expected = {"assignment": "dispatch_receipt_v1", "outcome": "attempt_outcome_v1"}
        if (kind not in expected or execution.get("contract") != expected[kind]
                or execution.get("policy_version") != POLICY
                or execution.get("enforcement") != "advisory"):
            raise ValueError("unsupported execution receipt")
        ordinal = execution.get("ordinal")
        if kind == "assignment" and execution.get("role") not in {
                "orchestrator", "explorer", "worker", "tester", "researcher", "reviewer"}:
            raise ValueError("unknown execution role")
        attempt = event.get("attempt_ref")
        if type(ordinal) is not int or not 1 <= ordinal <= 1_000_000 or not text(attempt):
            raise ValueError("invalid attempt identity")
        entry = attempts.setdefault(attempt, {"ordinal": ordinal, "assignment": [], "outcome": []})
        if entry["ordinal"] != ordinal:
            conflicts.append("conflicting_attempt_ordinal")
        entry[kind].append(event)

    for event in legacy_attempts:
        entry = attempts.get(event.get("attempt_ref"))
        if event["kind"] != "assignment" or entry is None or not entry["assignment"]:
            conflicts.append("legacy_attempt_coverage_unknown")
        elif pair(event["payload"].get("requested")) is not None:
            observed_pairs = {pair(item["payload"].get("requested")) for item in entry["assignment"]}
            if pair(event["payload"]["requested"]) not in observed_pairs:
                conflicts.append("mixed_assignment_requires_review")
    ordered = sorted(attempts.items(), key=lambda item: item[1]["ordinal"])
    ordinals = [entry["ordinal"] for _, entry in ordered]
    if ordinals != list(range(1, len(ordered) + 1)):
        conflicts.append("incomplete_or_conflicting_ledger")
    for index, (_, entry) in enumerate(ordered):
        if not entry["assignment"] or len(entry["outcome"]) != 1:
            conflicts.append("incomplete_or_conflicting_ledger")
        requested = {pair(event["payload"].get("requested")) for event in entry["assignment"]}
        if len(requested) > 1 or None in requested:
            conflicts.append("mixed_assignment_requires_review")
        roles = {event["payload"]["execution"]["role"] for event in entry["assignment"]}
        if len(roles) > 1:
            conflicts.append("conflicting_attempt_role")
        dispatch_ids = {event["event_id"] for event in entry["assignment"]}
        for event in entry["outcome"]:
            outcome = event["payload"]["execution"]
            if outcome.get("dispatch_event_id") not in dispatch_ids:
                conflicts.append("outcome_dispatch_mismatch")
            if outcome.get("result") not in {"failure", "partial"}:
                conflicts.append("previous_outcome_does_not_allow_retry")
            if outcome.get("failure_class") not in {"acceptance", "capability"}:
                conflicts.append("resolve_infrastructure_risk_or_unknown_first")
        expected_kind = {1: "initial", 2: "repair", 3: "upgrade"}.get(entry["ordinal"])
        for event in entry["assignment"]:
            payload = event["payload"]
            if (payload["execution"].get("attempt_kind") != expected_kind
                    or payload["execution"].get("status") != "started"):
                conflicts.append("historical_chain_requires_review")
            if index:
                parent_id, parent = ordered[index - 1]
                if (payload.get("parent_attempt_ref") != parent_id
                        or not text(payload.get("change_reason"))
                        or not payload.get("evidence_refs")):
                    conflicts.append("historical_chain_requires_review")
                if entry["ordinal"] == 2:
                    parent_pairs = {pair(event["payload"].get("requested")) for event in parent["assignment"]}
                    if requested != parent_pairs:
                        conflicts.append("repair_must_preserve_requested_pair")

    reasons = list(dict.fromkeys(conflicts))
    next_ordinal = max(ordinals, default=0) + 1
    if len(ordered) >= 3 or next_ordinal > 3:
        reasons.append("automatic_budget_exhausted")
    if proposal["attempt_kind"] == "manual":
        reasons.append("manual_direction_required")
    if pair(proposal["requested"]) is None:
        reasons.append("verified_requested_pair_required")
    if not ordered:
        if proposal["attempt_kind"] != "initial" or proposal["parent_attempt_ref"] is not None:
            reasons.append("initial_attempt_required")
    else:
        previous_id, previous = ordered[-1]
        if proposal["parent_attempt_ref"] != previous_id:
            reasons.append("parent_attempt_mismatch")
        if not previous["outcome"]:
            reasons.append("previous_outcome_required")
        else:
            outcome = previous["outcome"][0]["payload"]["execution"]
            dispatch_ids = {event["event_id"] for event in previous["assignment"]}
            if outcome.get("dispatch_event_id") not in dispatch_ids:
                reasons.append("outcome_dispatch_mismatch")
            if outcome.get("result") not in {"failure", "partial"}:
                reasons.append("previous_outcome_does_not_allow_retry")
            if outcome.get("failure_class") not in {"acceptance", "capability"}:
                reasons.append("resolve_infrastructure_risk_or_unknown_first")
        if not text(proposal["change_reason"]) or not evidence:
            reasons.append("new_evidence_and_repair_direction_required")
        if next_ordinal == 2:
            if proposal["attempt_kind"] != "repair":
                reasons.append("targeted_repair_required")
            previous_pairs = {pair(event["payload"].get("requested")) for event in previous["assignment"]}
            if previous_pairs != {pair(proposal["requested"])}:
                reasons.append("repair_must_preserve_requested_pair")
        elif next_ordinal == 3 and proposal["attempt_kind"] != "upgrade":
            reasons.append("authorized_upgrade_required")
        elif next_ordinal == 3:
            previous_pairs = {pair(event["payload"].get("requested")) for event in previous["assignment"]}
            if pair(proposal["requested"]) in previous_pairs:
                reasons.append("upgrade_requires_a_changed_authorized_pair")

    fingerprint = hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "policy_version": POLICY, "enforcement": "advisory",
        "execution_authorized": False, "eligible_for_authorization": not reasons,
        "run_id": proposal["run_id"], "stage_id": proposal["stage_id"],
        "observed_attempts": len(ordered), "next_ordinal": next_ordinal,
        "reason_codes": list(dict.fromkeys(reasons)), "input_fingerprint": fingerprint,
        "limitations": ["caller_supplied_ledger", "no_atomic_reservation",
                        "fresh_host_catalog_policy_and_confirmation_still_required"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("ledger exceeds 2 MiB; use this stage's structured events")
        result = assess(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"Invalid budget input: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
