#!/usr/bin/env python3
"""Prepare an unsent Laya scenario manifest from a dispatch plan."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from prepare_laya_usage import (
    NATIVE_SOURCE,
    UsageInputError,
    canonical_hash,
    checked_bindings,
    checked_segments,
    make_event,
)


MAX_STAGES = 128
MAX_TEXT_BYTES = 1024 * 1024
MAX_SCENARIO_VALUE = 1_000_000_000
MAX_MANIFEST_BYTES = 16 * 1024
INPUT_SOURCE = (
    "text-proxy-v1; ASCII/4 + non-ASCII codepoints; declared stage passes; "
    "not native tokens"
)
NATIVE_INPUT_MODE = "native-envelope-v1"
NATIVE_INPUT_SOURCE = (
    "native-envelope-v1; observed min/max input envelope and summed output; "
    "range-sensitivity scenario only; context mapping and declared unsplit passes "
    "are explicit hypothetical scenario-v1 assumptions, not native unsplit "
    "execution; min/max are not initial/final observed context"
)
CONTEXT_KEYS = (
    "task_snapshot_hash",
    "code_revision",
    "test_snapshot_hash",
    "tool_environment_id",
    "external_inputs_hash",
    "acceptance_policy",
)
RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
)


class ScenarioInputError(UsageInputError):
    pass


def _text(value, maximum=None, allow_empty=False):
    return (isinstance(value, str) and (allow_empty or bool(value))
            and (maximum is None or len(value) <= maximum))


def _exact_keys(value, keys):
    return isinstance(value, dict) and set(value) == set(keys)


def _valid_datetime(value):
    if not _text(value, 512) or RFC3339.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _proxy_tokens(value):
    ascii_count = sum(ord(character) < 128 for character in value)
    nonascii_count = len(value) - ascii_count
    return (ascii_count + 3) // 4 + nonascii_count


def _checked_metadata(plan, keys):
    if not _exact_keys(plan, keys):
        raise ScenarioInputError("scenario plan shape is invalid")
    if not _text(plan["run_id"], 512):
        raise ScenarioInputError("scenario run identity is invalid")
    if not _valid_datetime(plan["observed_at"]):
        raise ScenarioInputError("scenario observation time is invalid")
    if not _text(plan["meter_identity"], 512):
        raise ScenarioInputError("scenario meter identity is invalid")

    orchestrator = plan["orchestrator"]
    if not _exact_keys(orchestrator, ("model", "reasoning_effort", "source", "reference")):
        raise ScenarioInputError("orchestrator metadata is invalid")
    if (not _text(orchestrator["model"], 256)
            or not _text(orchestrator["reasoning_effort"], 64)
            or orchestrator["source"] != "host"
            or not _text(orchestrator["reference"], 512)):
        raise ScenarioInputError("orchestrator metadata is invalid")


def _checked_stages(stages, stage_keys):
    if not isinstance(stages, list) or not 1 <= len(stages) <= MAX_STAGES:
        raise ScenarioInputError("scenario stages are invalid")
    identities = set()
    for stage in stages:
        if not _exact_keys(stage, stage_keys):
            raise ScenarioInputError("scenario stage shape is invalid")
        identity = tuple(stage[field] for field in (
            "thread_id", "turn_id", "root_turn_id"))
        if (any(not _text(value) for value in identity)
                or identity in identities):
            raise ScenarioInputError("scenario stage identity is invalid")
        if type(stage["passes"]) is not int or not 1 <= stage["passes"] <= 100:
            raise ScenarioInputError("scenario stage passes are invalid")
        identities.add(identity)
    return identities


def _checked_text_plan(plan):
    keys = (
        "run_id", "observed_at", "orchestrator", "meter_identity",
        "initial_context_text", "stages",
    )
    _checked_metadata(plan, keys)
    if not _text(plan["initial_context_text"], allow_empty=True):
        raise ScenarioInputError("scenario initial context is invalid")
    stages = plan["stages"]
    identities = _checked_stages(stages, (
        "thread_id", "turn_id", "root_turn_id", "context_text",
        "work_output_text", "passes",
    ))
    text_values = [plan["initial_context_text"]]
    stage_values = []
    for stage in stages:
        if (not _text(stage["context_text"], allow_empty=True)
                or not _text(stage["work_output_text"], allow_empty=True)):
            raise ScenarioInputError("scenario stage text is invalid")
        text_values.extend((stage["context_text"], stage["work_output_text"]))
        values = {
            "context_growth_tokens": _proxy_tokens(stage["context_text"]),
            "work_output_tokens": _proxy_tokens(stage["work_output_text"]),
            "passes": stage["passes"],
        }
        if any(value > MAX_SCENARIO_VALUE for value in values.values()):
            raise ScenarioInputError("scenario value exceeds its limit")
        stage_values.append(values)

    try:
        total_bytes = sum(len(value.encode("utf-8")) for value in text_values)
    except UnicodeEncodeError:
        raise ScenarioInputError("scenario text encoding is invalid") from None
    if total_bytes > MAX_TEXT_BYTES:
        raise ScenarioInputError("scenario text exceeds its limit")
    initial_tokens = _proxy_tokens(plan["initial_context_text"])
    if initial_tokens > MAX_SCENARIO_VALUE:
        raise ScenarioInputError("scenario value exceeds its limit")
    return identities, initial_tokens, stage_values, INPUT_SOURCE, []


def _checked_native_plan(plan):
    keys = (
        "input_mode", "run_id", "observed_at", "orchestrator",
        "meter_identity", "stages",
    )
    _checked_metadata(plan, keys)
    if plan["input_mode"] != NATIVE_INPUT_MODE:
        raise ScenarioInputError("scenario input mode is invalid")
    identities = _checked_stages(plan["stages"], (
        "thread_id", "turn_id", "root_turn_id", "passes",
    ))
    return identities


def _checked_plan(plan):
    if isinstance(plan, dict) and "input_mode" in plan:
        return _checked_native_plan(plan), None, None, NATIVE_INPUT_SOURCE, None
    return _checked_text_plan(plan)


def _native_scenario_values(ordered, stages):
    checked = []
    for (unused_binding, segment), stage in zip(ordered, stages):
        components = segment.get("native_components")
        keys = (
            "status", "input_tokens", "output_tokens", "min_input_tokens",
            "max_input_tokens", "checkpoint",
        )
        if (not _exact_keys(components, keys)
                or components["status"] != "available"):
            raise ScenarioInputError("native component usage is unavailable")
        numbers = [components[key] for key in (
            "input_tokens", "output_tokens", "min_input_tokens",
            "max_input_tokens",
        )]
        if any(type(value) is not int or value < 0 for value in numbers):
            raise ScenarioInputError("native component counts are invalid")
        input_tokens, output_tokens, minimum, maximum = numbers
        if input_tokens + output_tokens != segment["total_tokens"]:
            raise ScenarioInputError("native component sums do not match segment total")
        if not 0 <= minimum <= maximum <= input_tokens:
            raise ScenarioInputError("native input envelope is invalid")
        count = segment["response_count"]
        if count == 1:
            envelope_is_consistent = minimum == maximum == input_tokens
        else:
            envelope_is_consistent = (
                maximum + (count - 1) * minimum <= input_tokens
                <= minimum + (count - 1) * maximum
            )
        if not envelope_is_consistent:
            raise ScenarioInputError("native input envelope is inconsistent")
        if not _text(components["checkpoint"], 512):
            raise ScenarioInputError("native component checkpoint is invalid")
        checked.append((minimum, maximum, output_tokens,
                        components["checkpoint"], stage["passes"]))

    initial_tokens = min(value[0] for value in checked)
    stage_values = [
        {
            "context_growth_tokens": maximum - initial_tokens,
            "work_output_tokens": output_tokens,
            "passes": passes,
        }
        for unused_minimum, maximum, output_tokens, unused_checkpoint, passes in checked
    ]
    derived = [initial_tokens]
    for value in stage_values:
        derived.extend((value["context_growth_tokens"],
                        value["work_output_tokens"], value["passes"]))
    if any(value > MAX_SCENARIO_VALUE for value in derived):
        raise ScenarioInputError("scenario value exceeds its limit")
    return initial_tokens, stage_values, [value[3] for value in checked]


def _manifest_event(report, plan, ordered, usage_events, initial_tokens, stage_values,
                    input_source, component_checkpoints):
    first_binding = ordered[0][0]
    evidence_refs = [plan["orchestrator"]["reference"]]
    for unused_binding, segment in ordered:
        if segment["checkpoint"] not in evidence_refs:
            evidence_refs.append(segment["checkpoint"])
    for checkpoint in component_checkpoints:
        if checkpoint not in evidence_refs:
            evidence_refs.append(checkpoint)
    usage_ids = [event["event_id"] for event in usage_events]
    event = {
        "protocol_version": 1,
        "decision_id": first_binding["decision_id"],
        "attempt_ref": first_binding["attempt_ref"],
        "kind": "run_manifest",
        "source": {
            "host": "codex",
            "role": "orchestrator",
            "actor_type": "agent",
        },
        "payload": {
            "manifest_version": 1,
            "run_id": plan["run_id"],
            "host_root_ref": "codex-root:" + canonical_hash([
                report["root_thread_id"], sorted(report["root_turn_ids"]),
            ]),
            "mode": "laya",
            "observed_at": plan["observed_at"],
            "terminal_checkpoint": "events:" + canonical_hash(sorted(usage_ids)),
            "context": {key: None for key in CONTEXT_KEYS},
            "meter": {
                "unit": "tokens",
                "identity": plan["meter_identity"],
                "scope": "host_only",
                "excluded_components": ["local_laya_inference"],
            },
            "segments": [
                {
                    "decision_id": binding["decision_id"],
                    "attempt_ref": binding["attempt_ref"],
                    "usage_event_id": event_id,
                }
                for (binding, unused_segment), event_id in zip(ordered, usage_ids)
            ],
            "outcome_event_ids": [],
            "coverage": {
                "status": "partial",
                "evidence_refs": evidence_refs,
            },
            "scenario": {
                "orchestrator_model": plan["orchestrator"]["model"],
                "reasoning_effort": plan["orchestrator"]["reasoning_effort"],
                "initial_context_tokens": initial_tokens,
                "stages": stage_values,
                "input_source": input_source,
            },
        },
    }
    event["event_id"] = "manifest-" + canonical_hash(event)
    encoded = json.dumps(
        event, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ScenarioInputError("run manifest exceeds its size limit")
    return event


def prepare(report, bindings, plan):
    try:
        plan_identities, initial_tokens, stage_values, input_source, component_checkpoints = (
            _checked_plan(plan))
        segments = checked_segments(report)
        mapped, unbound_count = checked_bindings(bindings, segments)
        if len(mapped) != len(plan["stages"]):
            raise ScenarioInputError("scenario plan does not cover bound native segments")
        mapped_by_identity = {
            tuple(binding[field] for field in (
                "thread_id", "turn_id", "root_turn_id")): (binding, segment)
            for binding, segment in mapped
        }
        if set(mapped_by_identity) != plan_identities:
            raise ScenarioInputError("scenario plan does not match native bindings")
        ordered = [
            mapped_by_identity[tuple(stage[field] for field in (
                "thread_id", "turn_id", "root_turn_id"))]
            for stage in plan["stages"]
        ]
        if component_checkpoints is None:
            initial_tokens, stage_values, component_checkpoints = (
                _native_scenario_values(ordered, plan["stages"]))
        usage_events = [make_event(binding, segment) for binding, segment in ordered]
        manifest = _manifest_event(
            report, plan, ordered, usage_events, initial_tokens, stage_values,
            input_source, component_checkpoints)
        return {
            "status": "ok",
            "events": usage_events + [manifest],
            "unbound_segments": unbound_count,
            "errors": [],
        }
    except (UsageInputError, ScenarioInputError) as error:
        return {
            "status": "unavailable",
            "events": [],
            "unbound_segments": 0,
            "errors": [str(error)],
        }


def _load_json(path, label):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ScenarioInputError(f"unable to read {label} JSON") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(
            _load_json(args.report, "report"),
            _load_json(args.bindings, "bindings"),
            _load_json(args.plan, "plan"),
        )
    except ScenarioInputError as error:
        result = {
            "status": "unavailable",
            "events": [],
            "unbound_segments": 0,
            "errors": [str(error)],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
