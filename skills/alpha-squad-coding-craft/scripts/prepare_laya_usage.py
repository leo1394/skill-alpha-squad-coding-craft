#!/usr/bin/env python3
"""Prepare verified Codex-native usage as unsent Laya feedback events."""
import argparse
import hashlib
import json
from pathlib import Path


MAX_UINT64 = 2 ** 64 - 1
NATIVE_SOURCE = "token_usage_record.payload.usage.total_tokens; deduplicated by thread/response"


class UsageInputError(ValueError):
    pass


def canonical_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_text(value, maximum=None):
    return (isinstance(value, str) and bool(value)
            and (maximum is None or len(value) <= maximum))


def valid_count(value, minimum=0):
    return type(value) is int and minimum <= value <= MAX_UINT64


def expected_stream_id(thread_id, turn_id):
    return "codex-native:" + canonical_hash([thread_id, turn_id])


def checked_segments(report):
    if not isinstance(report, dict) or report.get("status") != "ok":
        raise UsageInputError("usage report is unavailable")
    if report.get("errors"):
        raise UsageInputError("usage report contains collection errors")
    if report.get("source") != NATIVE_SOURCE:
        raise UsageInputError("usage report source is not Codex native usage")
    root_thread_id = report.get("root_thread_id")
    if not valid_text(root_thread_id):
        raise UsageInputError("usage report root thread identity is invalid")
    if not valid_count(report.get("total_tokens")):
        raise UsageInputError("usage report total_tokens is invalid")
    if not valid_count(report.get("response_count"), 1):
        raise UsageInputError("usage report response_count is invalid")
    root_turn_ids = report.get("root_turn_ids")
    segments = report.get("segments")
    if (not isinstance(root_turn_ids, list) or not root_turn_ids
            or any(not valid_text(value) for value in root_turn_ids)
            or len(root_turn_ids) != len(set(root_turn_ids))):
        raise UsageInputError("usage report root turn identities are invalid")
    if not isinstance(segments, list) or not segments:
        raise UsageInputError("usage report has no native segments")
    by_identity = {}
    stream_ids = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise UsageInputError("native segment is malformed")
        identity = tuple(segment.get(field) for field in (
            "thread_id", "turn_id", "root_turn_id"))
        if any(not valid_text(value) for value in identity):
            raise UsageInputError("native segment identity is incomplete")
        if identity in by_identity:
            raise UsageInputError("native segment identity is duplicated")
        total = segment.get("total_tokens")
        response_count = segment.get("response_count")
        checkpoint = segment.get("checkpoint")
        stream_id = segment.get("usage_stream_id")
        if (not valid_count(total) or not valid_count(response_count, 1)
                or not valid_text(checkpoint, 512)):
            raise UsageInputError("native segment counts or checkpoint are invalid")
        if stream_id != expected_stream_id(identity[0], identity[1]):
            raise UsageInputError("native segment stream identity is invalid")
        if stream_id in stream_ids:
            raise UsageInputError("native segment stream identity is duplicated")
        stream_ids.add(stream_id)
        by_identity[identity] = segment
    if set(root_turn_ids) != {identity[2] for identity in by_identity}:
        raise UsageInputError("native segment root turn membership is incomplete")
    if root_thread_id not in {identity[0] for identity in by_identity}:
        raise UsageInputError("native segment root thread membership is incomplete")
    if sum(item["total_tokens"] for item in segments) != report["total_tokens"]:
        raise UsageInputError("native segment totals do not match report total")
    if sum(item["response_count"] for item in segments) != report["response_count"]:
        raise UsageInputError("native segment counts do not match report count")
    return by_identity


def checked_bindings(bindings, segments):
    if not isinstance(bindings, list):
        raise UsageInputError("bindings must be a JSON list")
    mapped = []
    identities = set()
    attempts = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise UsageInputError("binding is malformed")
        identity = tuple(binding.get(field) for field in (
            "thread_id", "turn_id", "root_turn_id"))
        decision_id = binding.get("decision_id")
        attempt_ref = binding.get("attempt_ref")
        if (any(not valid_text(value) for value in identity)
                or not valid_text(decision_id, 128)
                or not valid_text(attempt_ref, 128)):
            raise UsageInputError("binding identity is incomplete")
        if binding.get("configuration_scope_confirmed") is not True:
            raise UsageInputError("binding configuration scope is not confirmed")
        if identity not in segments:
            raise UsageInputError("binding references an unknown native segment")
        if identity in identities:
            raise UsageInputError("native segment is mapped more than once")
        if attempt_ref in attempts:
            raise UsageInputError("attempt is mapped to multiple native segments")
        identities.add(identity)
        attempts.add(attempt_ref)
        mapped.append((binding, segments[identity]))
    return mapped, len(segments) - len(mapped)


def make_event(binding, segment):
    event = {
        "protocol_version": 1,
        "decision_id": binding["decision_id"],
        "attempt_ref": binding["attempt_ref"],
        "kind": "usage",
        "source": {
            "host": "codex",
            "role": "orchestrator",
            "actor_type": "agent",
        },
        "payload": {
            "total_tokens": segment["total_tokens"],
            "source": NATIVE_SOURCE,
            "source_verified": True,
            "scope": "attempt",
            "checkpoint": segment["checkpoint"],
            "parent_scope": None,
            "overlap_status": "non_overlapping",
            "aggregation": "cumulative",
            "usage_stream_id": segment["usage_stream_id"],
            "source_sequence": segment["response_count"],
        },
    }
    event["event_id"] = "usage-" + canonical_hash(event)
    return event


def prepare(report, bindings):
    try:
        segments = checked_segments(report)
        mapped, unbound_count = checked_bindings(bindings, segments)
        events = [make_event(binding, segment) for binding, segment in mapped]
        events.sort(key=lambda item: item["event_id"])
        return {
            "status": "ok",
            "events": events,
            "unbound_segments": unbound_count,
            "errors": [],
        }
    except UsageInputError as error:
        return {
            "status": "unavailable",
            "events": [],
            "unbound_segments": 0,
            "errors": [str(error)],
        }


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise UsageInputError(f"unable to read {path.name}: {error}") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True,
                        help="Unedited JSON output from collect_token_usage.py")
    parser.add_argument("--bindings", type=Path, required=True,
                        help="Explicit confirmed native-segment bindings JSON")
    args = parser.parse_args()
    try:
        result = prepare(load_json(args.report), load_json(args.bindings))
    except UsageInputError as error:
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
