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
and `usage`. Check the live tool schema for kind-specific fields and limits. The
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
    "kind": {"enum": ["assignment", "test", "review", "outcome", "user_choice", "usage"]},
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
    }
  },
  "allOf": [
    {
      "if": {"properties": {"kind": {"const": "assignment"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/assignment_payload"}}}
    },
    {
      "if": {"properties": {"kind": {"enum": ["test", "review", "outcome"]}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/scored_payload"}}}
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
