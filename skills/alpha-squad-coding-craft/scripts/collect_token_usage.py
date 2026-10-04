#!/usr/bin/env python3
"""Read Codex task-scoped usage without exposing conversation contents."""
import argparse
import hashlib
import json
import os
from pathlib import Path


MAX_UINT64 = 2 ** 64 - 1


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def records(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                # A concurrently appended final line can be incomplete.
                if not line.endswith("\n"):
                    return
                raise ValueError(f"Malformed record in {path.name}") from None


def collect(home, root_thread, root_turns, expected_subagents):
    paths = {}
    parents = {}
    invalid_parent_threads = set()
    errors = []
    for folder in (home / "sessions", home / "archived_sessions"):
        for path in folder.rglob("*.jsonl"):
            try:
                first = next(records(path), {})
                if first.get("type") != "session_meta":
                    continue
                meta = first.get("payload", {})
                thread = meta.get("id")
                source = meta.get("source")
                spawn = source.get("subagent", {}) if isinstance(source, dict) else {}
                spawn = spawn.get("thread_spawn", {}) if isinstance(spawn, dict) else {}
                if isinstance(thread, str):
                    paths.setdefault(thread, []).append(path)
                    parent = spawn.get("parent_thread_id")
                    if parent is None or isinstance(parent, str) and parent:
                        parents.setdefault(thread, set()).add(parent)
                    else:
                        invalid_parent_threads.add(thread)
            except (OSError, ValueError, AttributeError):
                # Unrelated unreadable histories are not task evidence.
                continue
    related = {root_thread}
    while True:
        children = {
            thread for thread, candidates in parents.items()
            if candidates & related
        }
        if children <= related:
            break
        related.update(children)
    for thread in related:
        if len(parents.get(thread, set())) > 1:
            errors.append("conflicting session parent identity")
        if thread in invalid_parent_threads:
            errors.append("invalid session parent identity")
    if root_thread not in paths:
        errors.append("root session log not found")
    responses = {}
    response_components = {}
    component_errors = {}
    turn_totals = {}
    turn_component_totals = {}
    turn_component_errors = {}
    checkpoint = None
    turns = set()
    for thread in sorted(related):
        for path in paths.get(thread, []):
            try:
                for record in records(path):
                    if record.get("type") != "token_usage_record":
                        continue
                    payload = record.get("payload", {})
                    if payload.get("root_turn_id") not in root_turns:
                        continue
                    if payload.get("thread_id") != thread:
                        errors.append("usage thread identity mismatch")
                        continue
                    response = payload.get("response_id")
                    turn = payload.get("turn_id")
                    usage = payload.get("usage")
                    total = usage.get("total_tokens") if isinstance(usage, dict) else None
                    if (not isinstance(response, str) or not response
                            or not isinstance(turn, str) or not turn
                            or type(total) is not int or not 0 <= total <= MAX_UINT64):
                        errors.append("missing response identity or valid total_tokens")
                        continue
                    key = (thread, response)
                    value = (turn, payload["root_turn_id"], total)
                    if key in responses and responses[key] != value:
                        errors.append("conflicting duplicate response usage")
                    responses[key] = value
                    input_tokens = usage.get("input_tokens")
                    output_tokens = usage.get("output_tokens")
                    if "input_tokens" not in usage or "output_tokens" not in usage:
                        component_errors.setdefault(key, set()).add(
                            "missing native component counts")
                    elif (type(input_tokens) is not int
                            or not 0 <= input_tokens <= MAX_UINT64
                            or type(output_tokens) is not int
                            or not 0 <= output_tokens <= MAX_UINT64):
                        component_errors.setdefault(key, set()).add(
                            "invalid native component counts")
                    elif input_tokens + output_tokens != total:
                        component_errors.setdefault(key, set()).add(
                            "native component counts do not match total_tokens")
                    else:
                        components = (input_tokens, output_tokens)
                        if (key in response_components
                                and response_components[key] != components):
                            component_errors.setdefault(key, set()).add(
                                "conflicting duplicate native component counts")
                        response_components[key] = components
                    turn_usage = payload.get("turn_token_usage", {})
                    snapshot = turn_usage.get("total_tokens")
                    if (type(snapshot) is not int
                            or not 0 <= snapshot <= MAX_UINT64):
                        errors.append("missing valid turn usage checksum")
                    else:
                        turn_key = (thread, turn)
                        turn_totals[turn_key] = max(turn_totals.get(turn_key, 0), snapshot)
                    input_snapshot = turn_usage.get("input_tokens")
                    output_snapshot = turn_usage.get("output_tokens")
                    if (type(input_snapshot) is not int
                            or not 0 <= input_snapshot <= MAX_UINT64
                            or type(output_snapshot) is not int
                            or not 0 <= output_snapshot <= MAX_UINT64
                            or type(snapshot) is not int
                            or input_snapshot + output_snapshot != snapshot):
                        turn_component_errors.setdefault((thread, turn), set()).add(
                            "missing or invalid native component checksum")
                    else:
                        previous = turn_component_totals.get((thread, turn), (0, 0))
                        turn_component_totals[(thread, turn)] = (
                            max(previous[0], input_snapshot),
                            max(previous[1], output_snapshot),
                        )
                    turns.add(payload["root_turn_id"])
                    stamp = record.get("timestamp")
                    if isinstance(stamp, str):
                        checkpoint = max(checkpoint or stamp, stamp)
            except (OSError, ValueError, AttributeError):
                errors.append(f"unable to read task log: {path.name}")
    subtotals = {}
    observed_turns = {}
    for (thread, _), (turn, _, total) in responses.items():
        subtotals[thread] = subtotals.get(thread, 0) + total
        turn_key = (thread, turn)
        observed_turns[turn_key] = observed_turns.get(turn_key, 0) + total
    if observed_turns != turn_totals:
        errors.append("response totals do not match native turn counters; incomplete records")
    child_count = len(set(subtotals) - {root_thread})
    if root_thread not in subtotals:
        errors.append("no root usage records for requested task")
    if turns != set(root_turns):
        errors.append("one or more requested root turns have no usage records")
    if child_count != expected_subagents:
        errors.append(f"expected {expected_subagents} subagents, found usage for {child_count}")
    if sum(subtotals.values()) > MAX_UINT64:
        errors.append("task usage exceeds supported native count range")
    canonical_responses = sorted(
        (thread, response, turn, root_turn, total)
        for (thread, response), (turn, root_turn, total) in responses.items()
    )
    segment_responses = {}
    for thread, response, turn, root_turn, total in canonical_responses:
        key = (thread, turn, root_turn)
        segment_responses.setdefault(key, []).append((response, total))
    streams = [(thread, turn) for thread, turn, _ in segment_responses]
    if len(streams) != len(set(streams)):
        errors.append("native turn belongs to multiple root turns")
    segments = []
    for (thread, turn, root_turn), values in sorted(segment_responses.items()):
        keys = [(thread, response) for response, _ in values]
        reasons = sorted({reason for key in keys
                          for reason in component_errors.get(key, set())})
        if not reasons:
            reasons.extend(sorted(turn_component_errors.get((thread, turn), set())))
        response_input = sum(response_components.get(key, (0, 0))[0] for key in keys)
        response_output = sum(response_components.get(key, (0, 0))[1] for key in keys)
        if (not reasons
                and turn_component_totals.get((thread, turn))
                != (response_input, response_output)):
            reasons.append("response component sums do not match native turn counters")
        if reasons:
            native_components = {
                "status": "unavailable",
                "reason": "; ".join(reasons),
            }
        else:
            component_records = sorted(
                (response, *response_components[(thread, response)])
                for response, _ in values
            )
            input_values = [value[1] for value in component_records]
            native_components = {
                "status": "available",
                "input_tokens": response_input,
                "output_tokens": response_output,
                "min_input_tokens": min(input_values),
                "max_input_tokens": max(input_values),
                "checkpoint": digest(component_records),
            }
        segments.append({
            "thread_id": thread,
            "turn_id": turn,
            "root_turn_id": root_turn,
            "total_tokens": sum(total for _, total in values),
            "response_count": len(values),
            "checkpoint": digest(values),
            "usage_stream_id": "codex-native:" + digest([thread, turn]).split(":", 1)[1],
            "native_components": native_components,
        })
    ok = not errors
    return {
        "status": "ok" if ok else "unavailable",
        "total_tokens": sum(subtotals.values()) if ok else None,
        "response_count": len(responses) if ok else None,
        "orchestrator_tokens": subtotals.get(root_thread),
        "subagent_tokens": sum(value for key, value in subtotals.items() if key != root_thread),
        "subagents_with_usage": child_count,
        "root_thread_id": root_thread,
        "root_turn_ids": sorted(root_turns),
        "checkpoint": checkpoint,
        "segments": segments if ok else [],
        "scope": "task responses including descendants, through last observed checkpoint",
        "source": "token_usage_record.payload.usage.total_tokens; deduplicated by thread/response",
        "limitations": "Current final reply and unflushed/in-flight usage are not included.",
        "errors": sorted(set(errors)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser())
    parser.add_argument("--root-thread", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--root-turn", action="append", required=True,
                        help="Exact task root turn ID; repeat for verified continuations")
    parser.add_argument("--expected-subagents", type=int, required=True,
                        help="Unique participating children/descendants from the spawn ledger")
    args = parser.parse_args()
    if not args.root_thread or args.expected_subagents < 0:
        parser.error("root thread and nonnegative expected subagent count are required")
    result = collect(args.codex_home.expanduser(), args.root_thread,
                     set(args.root_turn), args.expected_subagents)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
