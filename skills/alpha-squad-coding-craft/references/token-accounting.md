# Native token accounting

The parent collects usage; children need not report telemetry or inspect logs.
Keep identities and evidence internal. Display the combined total in the existing
completion line, with its checkpoint limitation, not a long telemetry form.

## Codex

1. Resolve `CODEX_HOME` (default `~/.codex`) and this exact `CODEX_THREAD_ID`.
   Locate its session JSONL by matching `session_meta.payload.id`. Inspect only
   metadata and usage, not conversation contents. At task entry retain the latest
   current-task `turn_context.payload.root_turn_id` (or its `turn_id` when the
   host confirms this is a root turn). Do not silently use a previous turn.
2. Track successful child creations, descendants, and participating resumed
   children. Only add root turn IDs for verified continuations of this task.
   A new unrelated user task gets a fresh scope even in the same conversation.
3. After children complete, run the bundled script using the task's exact IDs:

```bash
python3 scripts/collect_token_usage.py \
  --root-thread "$CODEX_THREAD_ID" \
  --root-turn ROOT_TURN_ID \
  --expected-subagents 3
```

Paths are relative to the installed skill, not the user's repository. Repeat
`--root-turn` for multiple verified continuation roots. The expected count comes
from the spawn ledger, never from the script's observed count. It counts unique
participating children/descendants; this can differ from newly created agents
when a prior child is resumed for the current task.

The script reads `sessions/` and `archived_sessions/`, discovers descendants via
native parent metadata, and filters `token_usage_record` by exact task root IDs.
It sums `payload.usage.total_tokens` once per `(thread_id, response_id)` and
cross-checks against native per-turn counters. It does not add cumulative thread
snapshots, cached tokens, reasoning tokens, or another task's responses.

Exit 0 / `status=ok` permits using `total_tokens`. Exit 2 / unavailable means
coverage or evidence failed; report the specific reason, not a partial total or
zero. If a child just finished and logs may not yet be flushed, wait briefly and
retry once. Do not create agents or rerun their work merely to obtain telemetry.
The collector never changes logs, configurations, permissions or sessions.

Local log schemas are version-dependent. Older `event_msg/token_count` snapshots
alone are NOT used to infer task totals: they may include unrelated earlier work.
Use a separately verified native task counter or report the unsupported schema.
No active Goal and no API key are required for this local collection.

The number is through the last observable checkpoint, not a billing statement.
Child final replies are included when logged; the root's not-yet-generated final
reply and in-flight/unflushed usage cannot be included. State this limitation.

Successful reports also contain exclusive native-turn `segments`, deduplicated
response counts and deterministic segment checkpoints. These are not inclusive
task/subtree counters and must not be added to `total_tokens` again. For optional
Laya persistence, follow [laya-feedback.md](laya-feedback.md#codex-usage-delivery):
only exact, confirmed execution bindings can become attempt usage events. The
collector does not submit feedback or grant recording consent.

For an executable registration-to-delivery path, use
[laya-usage-lifecycle.md](laya-usage-lifecycle.md). It persists the exact task
scope and root/child bindings, calls this collector and the existing preparer,
and preserves events before MCP delivery. Its bounded finalizer can continue
collection after the root reply without claiming that quiet logs prove a flush.

Segments may also expose `native_components`: validated input/output sums,
minimum/maximum per-response input counts and a separate component checkpoint.
These are optional metadata, not extra tokens to add to `total_tokens`. Missing,
conflicting or inconsistent components make only that breakdown unavailable;
valid legacy total accounting remains usable. Cached input and reasoning output
are already subsets. Minimum/maximum input are not initial/final context: context
compaction can change their order. A scenario producer must state any conversion
from these counters to hypothetical context retention or work passes as assumptions.

## Other hosts

Use the host's authoritative task or response usage with equivalent task scoping
and deduplication. If it already includes descendants, do not add them again.
Missing counters are unavailable, never estimates from text length or quotas.
