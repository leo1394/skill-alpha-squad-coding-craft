# Opt-in execution ledger and bounded attempts

Use only with the opt-in structured orchestration policy. Standalone Squad and
older Laya keep their existing workflow. These controls are **advisory**: the
helper does not spawn, reserve a slot, authorize actions or change a model.

## Before dispatch

Retain one stage ledger for each bounded work unit, keyed by stable run/stage
IDs. Role changes, new decision IDs, new events and resumed native calls do not
reset its budget. A real new model attempt gets a new local attempt_ref; native
identity is recorded separately. Do not split or rename stages to evade limits.

Default policy `bounded-attempts-v1`: initial attempt, at most one targeted
same-pair repair with new evidence/direction, then at most one authorized
upgrade. No more than three automatic model attempts per stage. A failed native
spawn is infrastructure evidence, not proof of model inability. Resolve tool or
network failures before selecting a different model. New risk, authorization
issues or required user decisions pause automatic dispatch immediately.

Run the read-only helper on the stage's observed event ledger and proposal:

```bash
python3 scripts/assess_attempt_budget.py --input stage-budget.json
```

Input has exactly `events` and `proposal`. Events are the original feedback
envelopes, including versioned dispatch/outcome receipts and evidence events.
Proposal fields are `run_id`, `stage_id`, `attempt_kind` (initial/repair/upgrade/
manual), `parent_attempt_ref` (null initially), `change_reason` (null initially),
`evidence_refs` (array), and `requested` (`model`, `reasoning_effort`). IDs and
ledger files are maintained by the orchestrator, not entered by the user.

Use the complete stage ledger, not only the latest role's events. The helper
checks caller-provided records; it cannot discover omitted attempts or prove
the records authentic. `eligible_for_authorization` is never permission. Retain
its input fingerprint, then recheck the current host catalog, Laya route,
constraints and any required user confirmation immediately before native spawn.
Do not reuse this result after new evidence, an attempt, or a policy change.
Only one parent dispatches the stage; parallel check-then-spawn calls have no
atomic reservation and must not be presented as a hard budget guarantee.

At exhaustion, pause the stage with evidence and request direction. Do not end
the entire Goal or silently create another stage. Manual overrides require an
explicit user decision and remain labelled manual, not policy-compliant auto.

## After observed execution

Only when recording is separately authorized and the live schema accepts the
extension, append `payload.execution` to an existing assignment/outcome event.
Check actual service capability when available; a newer bridge does not prove
an older service supports the contract. Unsupported collection never prevents
normal work, but do not strip metadata and claim complete execution coverage.

Shared execution fields: `contract`, `run_id`, `stage_id`, positive `ordinal`,
`policy_version: "bounded-attempts-v1"`, `enforcement: "advisory"`. The envelope's
decision_id associates the plan and attempt_ref identifies this actual attempt.
Use the advertised JSON schema for exact field and reference limits.

- Dispatch contract: `dispatch_receipt_v1`, plus actual execution `role`
  (distinct from the envelope's reporting source.role), `attempt_kind`, `status`
  (started/failed/unknown), `native_execution_ref`, `context_isolation`
  (isolated/unsupported/unknown), `context_evidence_ref`, and `input_size`
  (`value`, `unit`, `source`). Started requires an observed native execution
  reference; isolated requires actual host evidence, not a requested fork flag.
  Unknown size is null; bytes/characters are never native_tokens. Existing
  requested/effective pairs and their provenance remain separate.
- Outcome contract: `attempt_outcome_v1`, plus `dispatch_event_id`, `result`,
  `failure_class`, `first_feedback_event_id`, `test_event_ids`, `review_event_ids`,
  `usage_event_ids`, and nullable `duration_ms`. Preserve unknown references as
  null/empty, not fabricated IDs. References must belong to this decision and
  attempt; cross-attempt reviews need their own explicit evidence binding, not
  relabelling a reviewer's original event. Provide at least one legacy outcome/
  status alias matching result so existing review queues retain failed outcomes.

Do not wait for a complete outcome before sending a child's first score. A later
outcome references that original event. Missing referenced events are retryable
dependencies: retain the exact original event in the durable outbox and replay
after dependencies arrive. Do not mint a new ID or change first scores to pass
validation. One terminal outcome is immutable; contrary later evidence is a
separate test/review, not an overwritten outcome.

Actual over-budget execution is still recorded, including ordinal four and its
usage/quality. Telemetry acceptance never retroactively authorizes the action.
Report violations and unknown coverage rather than hiding them. Keep receipt
states (stored/queued_local/not_recorded/quarantined) literal in handoffs.
