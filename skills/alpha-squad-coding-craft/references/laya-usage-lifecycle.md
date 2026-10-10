# Durable Codex usage lifecycle

Use this helper only for an explicitly scoped task with existing Laya decisions.
It is stdlib Python on the local Unix Codex host. It never enables recording,
creates a decision, estimates tokens, changes a Laya database, or reads unrelated
conversation contents. The existing collector reads session identity metadata to
discover descendants and filters native usage to the registered root turns.
Missing Laya or incomplete accounting must not block ordinary task work.

Paths below are relative to the installed skill. Keep the private ledger outside
the repository, in a task-specific location covered by the user's retention
policy. Its atomic snapshots contain identifiers, numeric evidence, exact usage
events and receipts; no task text or reasoning. Use one ledger per task, including
verified continuations; never reuse it for a later unrelated user request.

## Register before dispatch, bind after verification

Resolve native identities from the current task's metadata, not lifetime totals.
After the existing selection and recording-consent gates, initialize and register
the root's explicit task decision and attempt. Do not borrow a child's decision
to label parent orchestration. If no honest root decision/configuration binding
exists, report incomplete root coverage and continue the task.

```bash
python3 scripts/laya_usage_lifecycle.py init --ledger /private/tmp/task-usage.json --codex-home /path/to/codex-home --root-thread ROOT_THREAD --root-turn ROOT_TURN
python3 scripts/laya_usage_lifecycle.py register --ledger /private/tmp/task-usage.json --attempt-ref ROOT_ATTEMPT --decision-id ROOT_DECISION --root-turn ROOT_TURN --role root
python3 scripts/laya_usage_lifecycle.py bind --ledger /private/tmp/task-usage.json --attempt-ref ROOT_ATTEMPT --thread-id ROOT_THREAD --turn-id ROOT_NATIVE_TURN --verified
```

Before **each** child or descendant dispatch, persist its existing decision and
new attempt, alongside the existing assignment-event workflow:

```bash
python3 scripts/laya_usage_lifecycle.py register --ledger /private/tmp/task-usage.json --attempt-ref CHILD_ATTEMPT --decision-id CHILD_DECISION --root-turn ROOT_TURN --role child
```

Immediately after the host verifies successful dispatch and its exact native
turn/configuration scope, bind it:

```bash
python3 scripts/laya_usage_lifecycle.py bind --ledger /private/tmp/task-usage.json --attempt-ref CHILD_ATTEMPT --thread-id CHILD_THREAD --turn-id CHILD_NATIVE_TURN --verified
```

`--verified` asserts that the entire native turn belongs to this single attempt
and configuration. Never set it for mixed, split or inferred assignments. Native
identity bindings are immutable. Resume/follow-up calls get separate attempt
registrations and native turns even when they reuse the same child thread. For
a verified task continuation with a new root turn, first register its root
attempt with that new root turn, then register participating children. The
collector's expected child count is the unique bound child threads, not the
number of turns or events. An unbound registration (including a failed or
interrupted dispatch) stays visibly incomplete; do not delete it to claim full
coverage. Recover a missed binding from the actual host receipt, never guess.

## Checkpoint and delivery

After children finish, and before the root's final reply:

```bash
python3 scripts/laya_usage_lifecycle.py checkpoint --ledger /private/tmp/task-usage.json --deliver --consent-confirmed
```

Omit `--deliver --consent-confirmed` for collection/preparation only. The consent
flag asserts separately verified permission; it does not enable anything.
Delivery invokes `laya mcp`, performs native MCP initialization and schema
discovery, then calls `laya_feedback` with the prepared arguments. The actual
Laya client still enforces its service-owned consent marker and uses its durable
outbox. An incompatible schema is an explicit delivery error, not permission to
drop ordering fields. `--laya /path/to/laya` selects an already installed binary.
No installation is performed.

Every event is atomically committed to the ledger **before** sending. Every
receipt is atomically committed after acknowledgement. A crash in either gap is
recovered by rerunning checkpoint on the same ledger. The same native evidence
produces the same event ID and exact payload. A growing native checkpoint creates
a new cumulative event on the same stream. `stored`, `queued_local`, `prepared`,
`not_recorded`, and failure receipts remain distinct in `status` output.
`queued_local` is durable in Laya's outbox, not service-confirmed storage.
Unconfirmed and queued events retry unchanged; permanent rejections and disabled
recording do not automatically retry. Never enable recording to repair delivery.

Inspect both `coverage_complete` and `delivery_complete`. Exit 2 indicates
unavailable/incomplete accounting, an unverified final boundary, or (when
`--deliver` is requested) events not yet `stored`. `prepared`, `queued_local`,
`not_recorded`, and delivery errors are not service storage claims. Without
`--deliver`, exit 0 only confirms checkpoint coverage; delivery can remain pending.
Report the actual state in the handoff. Ordinary coding work may still finish.

## Bounded collection after final reply

A foreground checkpoint cannot include its own future final reply. Before sending
that reply, launch a bounded watcher if the host permits a detached local process:

```bash
python3 scripts/laya_usage_lifecycle.py finalize --ledger /private/tmp/task-usage.json --watch-seconds 60 --poll-seconds 2 --background --deliver --consent-confirmed
```

This returns its PID and ledger path, continues collecting the same task scope
after the reply, and exits after the bounded watch. It does not schedule future
tasks or create an unlimited harvester. Maximum watch is 600 seconds; MCP calls
have separate bounded timeouts. No idle interval is treated as proof that all
usage flushed. With no explicit final response identity, finalization remains
`checkpoint_only`, even if the last checkpoint includes the final reply.

When the host exposes exact root final response IDs, pass one or more
`--final-response-id NATIVE_RESPONSE_ID` values (cover every registered root
turn) to a foreground or background finalize. It waits for their actual native
usage records and marks `final_response_observed`; coverage and delivery must
still be checked separately. Do not substitute a thread ID, task-completed marker,
message text, or guessed ID for a native usage response ID.

```bash
python3 scripts/laya_usage_lifecycle.py finalize --ledger /private/tmp/task-usage.json --watch-seconds 30 --final-response-id ROOT_FINAL_RESPONSE --deliver --consent-confirmed
python3 scripts/laya_usage_lifecycle.py status --ledger /private/tmp/task-usage.json
```

The watcher is not a managed service: process/host termination can interrupt it.
Resume with the same finalize command and ledger. `scheduled` is not a completion
receipt. If the host cannot detach or final evidence remains unavailable, disclose
the checkpoint limitation; do not delay or repeat task work to manufacture usage.
