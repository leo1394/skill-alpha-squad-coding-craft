# Optional Laya feedback

Read this reference only when Laya routing produced a `decision_id` and a
compatible `laya_feedback` tool is available. Feedback is optional telemetry:
missing Laya, a missing/failed feedback tool, or recording being disabled must
not block coding, routing, testing, review, or handoff.

Model-selection confirmation is not recording consent. Before sending any
feedback, obtain or verify Laya's separate explicit recording consent. Do not
enable recording, broaden captured content, or install a tool on the user's
behalf. Send only concise, redacted structured evidence; never include secrets,
hidden reasoning, a full conversation, or an unrequested source snapshot.

## Call and identity contract

Pass the event fields directly as the tool arguments (no `event` wrapper):

```json
{"protocol_version":1,"event_id":"client-stable-uuid","decision_id":"laya-decision-uuid","attempt_ref":"local-attempt-uuid","kind":"review","source":{"host":"codex","role":"reviewer","actor_type":"agent"},"payload":{"disposition":"changes_requested","summary":"Rollback path is untested","evidence_refs":["test:rollback"],"scores":[{"rubric_version":"laya-feedback-v1","dimension":"judgment_quality","value":0,"reason":"Risk omitted the untested rollback path","evidence_refs":["test:rollback"],"phase":"initial","source_sequence":1,"observed_at":"2026-09-25T10:00:00Z"}]}}
```

Use a new stable `event_id` for each logical event and retain its exact redacted
payload until delivery is confirmed. `attempt_ref` identifies this execution
attempt; generate it before dispatch if the host has no native run identifier.
Do not present it as a native identifier. `source.role` is the role that actually
observed the event. Agent-reported `user_choice` is still an agent report and is
not a human-confirmed label.

The allowed kinds are `assignment`, `test`, `review`, `outcome`, `user_choice`,
and `usage`; newer hosts also accept optional `run_manifest` scenario evidence.
Check the live tool schema for kind-specific fields and limits. The
shared envelope and scoring contract below are the minimum portable contract.

## Assignment facts

Record an `assignment` event before a routed spawn. Keep all four stages
separate, even when two values happen to match:

- `recommended`: the Laya recommendation.
- `selected`: the user or policy choice accepted for this attempt.
- `requested`: the exact pair supplied to the native spawn call.
- `effective`: the pair the host actually verified on the running child.

Each non-null pair carries its own `model_observation` provenance. An effective
pair is valid only with a verified host observation. If the model is known but
its effort is not, preserve the model and use `reasoning_effort: null`. If the
actual model is unknown, use `effective: null`; never copy the requested pair
into it. A later observation is a new event, not a mutation of the original.
Optional `provider`, `model_revision`, and `catalog_version` belong inside that
pair's `model_observation`; preserve unknown values as null rather than deriving
versions or capability rankings from model names. Preserve optional assignment
`parent_attempt_ref`, `change_reason`, `mixed_configuration`, and a concise
redacted `environment` when actually observed.

When the live schema accepts versioned `payload.execution`, an additional
post-spawn assignment can carry the actual dispatch receipt described in
[laya-execution.md](laya-execution.md). The pre-spawn assignment above is not a
started receipt. Preserve both events and all original scores; never overwrite
the requested/effective distinction or upgrade unknowns to observed facts.

Example:

```json
{"protocol_version":1,"event_id":"assignment-event-uuid","decision_id":"laya-decision-uuid","attempt_ref":"local-attempt-uuid","kind":"assignment","source":{"host":"codex","role":"orchestrator","actor_type":"agent"},"payload":{"recommended":{"model":"model-a","reasoning_effort":"high","model_observation":{"source":"laya","verified":false,"observed_at":"2026-09-25T10:00:00Z","reference":"advice:1"}},"selected":{"model":"model-a","reasoning_effort":"high","model_observation":{"source":"policy","verified":false,"observed_at":"2026-09-25T10:00:01Z","reference":"setup:1"}},"requested":{"model":"model-a","reasoning_effort":"high","model_observation":{"source":"spawn_request","verified":false,"observed_at":"2026-09-25T10:00:02Z","reference":"spawn:1"}},"effective":null,"reason":"Host has not exposed the child assignment","evidence_refs":[]}}
```

## First scores and revisions

A score has exactly one dimension: `judgment_quality`, `model_fit`, or
`outcome_quality`. Use `0` for not satisfied, `1` for partly satisfied, `2` for
satisfied, and `null` when evidence is insufficient. Unknown is never zero.
Passing tests are evidence about the tested behavior, not automatic proof that
the risk judgment or model choice was correct.

The observing child creates its own `phase: "initial"` scores as soon as it has
the relevant evidence. Before handing its result to the parent, it must:

1. freeze the redacted event payload and stable `event_id`;
2. call `laya_feedback` when consent and the tool are available;
3. include the exact event and receipt in its handoff.

The parent may retransmit that exact received event when delivery is unconfirmed.
It must use the same `event_id` and byte-equivalent semantic payload. The parent
must not invent a child's missing first score, change its reason, or submit an
`initial` score in the child's name. It may submit a separate event for evidence
the parent itself observed.

A changed judgment uses a new event ID, `phase: "revision"`, and
`supersedes_event_id` pointing to the prior event. Increase `source_sequence`
within the same attempt and source role. Never overwrite or relabel an initial
score because a reviewer or final outcome disagrees.

## Delivery and handoff

Treat receipts literally:

- `stored`: the service durably committed the event.
- `queued_local`: the client durably committed it to the local outbox, but the
  service has not acknowledged storage. This is not `stored`.
- `not_saved`, `rejected`, or `conflict`: no successful durable delivery claim;
  preserve the event and the exact reason in the handoff.
- `quarantined`: the original event remains durable but has not been accepted;
  report the validation error, do not silently rewrite the original score.
- `not_recorded`: recording was not authorized for this decision; do not retry
  by enabling collection or changing the user's consent.
- no response or an ambiguous response: delivery is unconfirmed. Retry the
  unchanged event with the same ID; never generate a replacement ID merely
  because a receipt was lost.

`stored` and `queued_local` are both durable states but describe different
boundaries. Do not collapse them into a generic success flag. Do not repeatedly
retry permanent schema/content conflicts during task execution. Coding work may
complete even when feedback is unavailable or failed; report the collection
state accurately and do not claim the learning loop completed.

For `usage`, report a known token count only with verified native `source`,
`source_verified: true`, `scope` (`response`, `turn`, `attempt`, `task`, or
`subtree`), an explicit `checkpoint` (null if unavailable), and `overlap_status`
(`non_overlapping`, `overlapping`, or `unknown`). Keep unavailable counts null.
Never sum potentially overlapping parent and child scopes. A missing revision
dependency is retryable; retransmit the unchanged event after its predecessor.

### Codex usage delivery

When routing has a recorded decision and recording consent remains enabled, the
parent prepares usage after the relevant child finishes. Use the scoped native
collector from [token-accounting.md](token-accounting.md); do not ask the child
to estimate tokens or copy the inclusive task total into each child's attempt.
This is an explicit task-scoped metadata read, not background session harvesting.

Retain an exact binding from the dispatch ledger: native `thread_id`, `turn_id`
and `root_turn_id` to the existing Laya `decision_id` and `attempt_ref`. Set
`configuration_scope_confirmed: true` only after verifying that the whole native
turn belongs to that one execution segment and was not split across attempts or
models. A resumed child turn needs its own recorded execution segment. Leave
orchestration spanning several decisions, mixed configurations and unresolved
identities unbound; do not invent an assignment merely to improve coverage.

Pass the unedited successful collector report and these bindings to:

```bash
python3 scripts/prepare_laya_usage.py --report usage.json --bindings bindings.json
```

The helper prints prepared tool arguments only; it never sends feedback, enables
recording or writes to the database. It checks scope consistency, not authenticity
of an arbitrary JSON file. Unknown or inconsistent accounting produces no events.
Check the live `laya_feedback` schema supports `aggregation`, `usage_stream_id`
and `source_sequence` before submission. An older tool must be reported as
incompatible; do not strip ordering metadata to force acceptance.

Call native `laya_feedback` once per prepared event and keep the exact event and
receipt. Retry unchanged events with the same ID under the delivery rules above.
The stable stream identity is independent of the decision; its source sequence
is the deduplicated native response count. New checkpoints produce new events,
while repeated preparation of the same evidence remains idempotent. The parent
is the reporting actor (`orchestrator`); this does not impersonate a child's
judgment or create any score. Unbound segments are excluded and coverage remains
partial, even when the separate completion summary has a valid inclusive total.
Other hosts retain their native usage path; do not run the Codex collector on
Claude, DSH or Pi logs.

### Automatic scenario inputs (Codex, capability-checked)

When recording is already authorized and the live schema supports `run_manifest`
with `scenario`, the parent maintains a small task-scoped plan alongside the
dispatch ledger. Do this as part of normal work, without asking the user to fill
in counters, technical identifiers or a second baseline run. Missing support or
inputs leaves the estimate unavailable; it never blocks the task.

Capture only visible, redacted task material already in scope: shared initial
context, each logical stage's new relevant context and useful work output. Do not
read full unrelated sessions, hidden reasoning, credentials or source trees to
inflate coverage. Do not include the whole shared context again in each stage.
Context/output text is local producer input, not transmitted feedback. Keep local
input artifacts private and subject to the task's retention/privacy requirements.

Do not use a short task/result summary as a substitute for the full input scope
when the actual native total includes system instructions, tool definitions and
repeated context. A `partial` label does not repair this mismatch. Until compatible
native input/output coverage is available, retain usage and first scores but do
not submit that text-proxy manifest as estimated savings. This does not require
a second execution, a measured baseline, or access to hidden reasoning text.

After execution, bind each stage to its verified native segment using the same
`thread_id`, `turn_id`, `root_turn_id` as usage delivery. Include testing, review,
research and retries when they belong to the scope. Preserve plan order; do not
sort by model tier or select only stages that appear to save tokens. `passes` is
the parent's declared estimate of necessary unsplit work passes (1–100), not the
native response count. Record it from the logical work plan without fitting it
to a desired savings result. Unknown inputs are not zero. The hypothetical model
and effort come from the current task's verified orchestrator metadata, not a
global default or the child's assignment.

Prefer `input_mode: "native-envelope-v1"` when the collector exposes validated
`native_components` for every bound segment. The parent creates this plan; users
do not author it:

```json
{"input_mode":"native-envelope-v1","run_id":"stable-task-run-id","observed_at":"2026-10-04T00:00:00Z","orchestrator":{"model":"host-observed-model","reasoning_effort":"medium","source":"host","reference":"native-turn-context-ref"},"meter_identity":"host-accounting-version","stages":[{"thread_id":"child-thread","turn_id":"child-turn","root_turn_id":"task-root-turn","passes":2}]}
```

This mode requires no task text. It uses the smallest observed input count across
bound stages as a shared-context proxy, each stage's largest input minus that
proxy as its context increment, and its summed native output as the output proxy.
Those mappings are explicit hypothetical assumptions: min/max are not observed
initial/final context, and compaction or different host prompts can affect them.
The existing retention/output sensitivity scenarios remain heuristic, not a
confidence interval or proof of savings. Do not fit passes to a desired result.
Component digests are retained alongside usage checkpoints. An unavailable
breakdown must not silently fall back to summary text.

Legacy text-proxy plan shape (compatibility only; not a substitute for native
input coverage):

```json
{"run_id":"stable-task-run-id","observed_at":"2026-10-04T00:00:00Z","orchestrator":{"model":"host-observed-model","reasoning_effort":"medium","source":"host","reference":"native-turn-context-ref"},"meter_identity":"host-accounting-version","initial_context_text":"redacted shared task context","stages":[{"thread_id":"child-thread","turn_id":"child-turn","root_turn_id":"task-root-turn","context_text":"new relevant stage context","work_output_text":"useful visible stage output","passes":1}]}
```

Use only a known accounting identity; do not guess a tokenizer version. With the
unedited successful collector report and existing bindings, run:

```bash
python3 scripts/prepare_laya_scenario.py --report usage.json --bindings bindings.json --plan scenario-plan.json
```

The legacy producer mode estimates text tokens with the explicit `text-proxy-v1` heuristic
(ASCII characters / 4 rounded up, plus non-ASCII codepoints). This is not a native
tokenizer count. It emits numeric scenario inputs, usage references and provenance,
never the input text. Hypothetical passes/output/context remain assumptions; the
actual side uses native usage. Model tier is not a token-saving multiplier.

Submit the returned usage events through native `laya_feedback`, retain their
receipts, then submit the manifest after dependencies report `stored`. Do not
submit the same usage twice through both helpers; their event identities are
stable if an unchanged retry is needed. Keep the final manifest immutable and
submit once per completed scope. Later evidence corrections need explicit version
handling; do not manufacture a new run ID to bypass overlap exclusions.

The producer deliberately reports partial coverage, even when every known segment
has a binding. A ledger and native totals cannot prove complete whole-task context.
If parent orchestration cannot be mapped honestly, leave it unbound and label the
result partial; do not fabricate a child assignment. Sending the plan must not
enable recording, create human labels, activate memory or trigger extra inference.
Other hosts need their own accounting adapter before this producer can be used.

Use this compact child handoff shape when feedback was attempted:

```json
{"feedback_event":{"protocol_version":1,"event_id":"client-stable-uuid","decision_id":"laya-decision-uuid","attempt_ref":"local-attempt-uuid","kind":"test","source":{"host":"codex","role":"tester","actor_type":"agent"},"payload":{"result":"fail","scope":"focused rollback test","summary":"Rollback leaves the migration lock held","evidence_refs":["test:rollback-lock"],"scores":[{"rubric_version":"laya-feedback-v1","dimension":"outcome_quality","value":0,"reason":"Focused rollback test failed","evidence_refs":["test:rollback-lock"],"phase":"initial","source_sequence":1,"observed_at":"2026-09-25T10:04:00Z"}]}},"feedback_receipt":{"status":"queued_local","event_id":"client-stable-uuid"}}
```

## Portable envelope schema

This schema makes the shared envelope, assignment provenance, and score
invariants executable. Kind-specific payload fields remain governed by the live
tool schema.

<!-- laya-feedback-schema:start -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.invalid/laya-feedback-envelope-v1.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["protocol_version", "event_id", "decision_id", "attempt_ref", "kind", "source", "payload"],
  "properties": {
    "protocol_version": {"const": 1},
    "event_id": {"type": "string", "minLength": 1},
    "decision_id": {"type": "string", "minLength": 1},
    "attempt_ref": {"type": "string", "minLength": 1},
    "kind": {"enum": ["assignment", "test", "review", "outcome", "user_choice", "usage", "run_manifest"]},
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["host", "role", "actor_type"],
      "properties": {
        "host": {"type": "string", "minLength": 1},
        "role": {"type": "string", "minLength": 1},
        "actor_type": {"const": "agent"}
      }
    },
    "payload": {"type": "object"}
  },
  "$defs": {
    "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": true},
    "observation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["source", "verified", "observed_at"],
      "properties": {
        "source": {"enum": ["laya", "user", "policy", "spawn_request", "host"]},
        "verified": {"type": "boolean"},
        "observed_at": {"type": "string", "format": "date-time"},
        "reference": {"type": ["string", "null"]},
        "provider": {"type": ["string", "null"]},
        "model_revision": {"type": ["string", "null"]},
        "catalog_version": {"type": ["string", "null"]}
      }
    },
    "assignment_pair": {
      "type": "object",
      "additionalProperties": false,
      "required": ["model", "reasoning_effort", "model_observation"],
      "properties": {
        "model": {"type": "string", "minLength": 1},
        "reasoning_effort": {"type": ["string", "null"], "minLength": 1},
        "model_observation": {"$ref": "#/$defs/observation"}
      }
    },
    "effective_pair": {
      "type": "object",
      "additionalProperties": false,
      "required": ["model", "reasoning_effort", "model_observation"],
      "properties": {
        "model": {"type": "string", "minLength": 1},
        "reasoning_effort": {"type": ["string", "null"], "minLength": 1},
        "model_observation": {
          "type": "object",
          "additionalProperties": false,
          "required": ["source", "verified", "observed_at"],
          "properties": {
            "source": {"const": "host"},
            "verified": {"const": true},
            "observed_at": {"type": "string", "format": "date-time"},
            "reference": {"type": ["string", "null"]},
            "provider": {"type": ["string", "null"]},
            "model_revision": {"type": ["string", "null"]},
            "catalog_version": {"type": ["string", "null"]}
          }
        }
      }
    },
    "score": {
      "type": "object",
      "additionalProperties": false,
      "required": ["rubric_version", "dimension", "value", "reason", "evidence_refs", "phase", "source_sequence", "observed_at"],
      "properties": {
        "rubric_version": {"const": "laya-feedback-v1"},
        "dimension": {"enum": ["judgment_quality", "model_fit", "outcome_quality"]},
        "value": {"type": ["integer", "null"], "enum": [0, 1, 2, null]},
        "reason": {"type": "string", "minLength": 1},
        "evidence_refs": {"$ref": "#/$defs/evidence_refs"},
        "phase": {"enum": ["initial", "revision"]},
        "source_sequence": {"type": "integer", "minimum": 1},
        "observed_at": {"type": "string", "format": "date-time"},
        "supersedes_event_id": {"type": "string", "minLength": 1}
      },
      "allOf": [
        {"if": {"properties": {"phase": {"const": "revision"}}}, "then": {"required": ["supersedes_event_id"]}},
        {"if": {"properties": {"phase": {"const": "initial"}}}, "then": {"not": {"required": ["supersedes_event_id"]}}}
      ]
    },
    "scores": {"type": "array", "items": {"$ref": "#/$defs/score"}},
    "assignment_payload": {
      "type": "object",
      "additionalProperties": false,
      "required": ["recommended", "selected", "requested", "effective", "reason", "evidence_refs"],
      "properties": {
        "execution": {"type": "object", "required": ["contract"], "properties": {"contract": {"const": "dispatch_receipt_v1"}}},
        "recommended": {"oneOf": [{"$ref": "#/$defs/assignment_pair"}, {"type": "null"}]},
        "selected": {"oneOf": [{"$ref": "#/$defs/assignment_pair"}, {"type": "null"}]},
        "requested": {"oneOf": [{"$ref": "#/$defs/assignment_pair"}, {"type": "null"}]},
        "effective": {"oneOf": [{"$ref": "#/$defs/effective_pair"}, {"type": "null"}]},
        "parent_attempt_ref": {"type": ["string", "null"]},
        "change_reason": {"type": ["string", "null"]},
        "mixed_configuration": {"type": "boolean"},
        "environment": {"type": ["object", "null"]},
        "reason": {"type": "string", "minLength": 1},
        "evidence_refs": {"$ref": "#/$defs/evidence_refs"},
        "scores": {"$ref": "#/$defs/scores"}
      }
    },
    "scored_payload": {
      "type": "object",
      "required": ["scores"],
      "properties": {"scores": {"$ref": "#/$defs/scores"}}
    },
    "execution_outcome_payload": {
      "type": "object",
      "required": ["execution"],
      "properties": {
        "execution": {"type": "object", "required": ["contract"], "properties": {"contract": {"const": "attempt_outcome_v1"}}},
        "scores": {"$ref": "#/$defs/scores"}
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"kind": {"const": "assignment"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/assignment_payload"}}}
    },
    {
      "if": {"properties": {"kind": {"enum": ["test", "review"]}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/scored_payload"}}}
    },
    {
      "if": {"properties": {"kind": {"const": "outcome"}}},
      "then": {"properties": {"payload": {"anyOf": [{"$ref": "#/$defs/scored_payload"}, {"$ref": "#/$defs/execution_outcome_payload"}], "allOf": [{"if": {"required": ["execution"]}, "then": {"$ref": "#/$defs/execution_outcome_payload"}}]}}}
    }
  ]
}
```
<!-- laya-feedback-schema:end -->

The portable schema intentionally validates only shared score fields for
`test`, `review`, and `outcome`; it does not replace the live tool's stricter
kind-specific payload schema. `user_choice` and `usage` may have no score. Always
prefer the live schema when it is stricter, and treat a schema mismatch as a
recording failure rather than weakening or guessing fields.
Versioned execution extensions are checked here only for their contract tag;
all execution fields, bounds and references require the live schema and service.
An outcome may reference an already-preserved first score instead of repeating it.
