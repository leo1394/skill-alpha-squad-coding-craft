#!/usr/bin/env python3
"""Read Codex task-scoped usage without exposing conversation contents."""
import argparse
import json
import os
from pathlib import Path


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
                    parents[thread] = spawn.get("parent_thread_id")
            except (OSError, ValueError, AttributeError):
                # Unrelated unreadable histories are not task evidence.
                continue
    related = {root_thread}
    while True:
        children = {thread for thread, parent in parents.items() if parent in related}
        if children <= related:
            break
        related.update(children)
    if root_thread not in paths:
        errors.append("root session log not found")
    responses = {}
    turn_totals = {}
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
                            or type(total) is not int or total < 0):
                        errors.append("missing response identity or valid total_tokens")
                        continue
                    key = (thread, response)
                    value = (turn, payload["root_turn_id"], total)
                    if key in responses and responses[key] != value:
                        errors.append("conflicting duplicate response usage")
                    responses[key] = value
                    snapshot = payload.get("turn_token_usage", {}).get("total_tokens")
                    if type(snapshot) is not int or snapshot < 0:
                        errors.append("missing valid turn usage checksum")
                    else:
                        turn_key = (thread, turn)
                        turn_totals[turn_key] = max(turn_totals.get(turn_key, 0), snapshot)
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
    return {
        "status": "unavailable" if errors else "ok",
        "total_tokens": None if errors else sum(subtotals.values()),
        "orchestrator_tokens": subtotals.get(root_thread),
        "subagent_tokens": sum(value for key, value in subtotals.items() if key != root_thread),
        "subagents_with_usage": child_count,
        "root_thread_id": root_thread,
        "root_turn_ids": sorted(root_turns),
        "checkpoint": checkpoint,
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
