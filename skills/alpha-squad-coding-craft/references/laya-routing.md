# Optional Laya routing

This adapter requires the installed `laya-model-advisor` skill and compatible
MCP tools. Read that skill for local session metadata, filtered model catalog,
policy selection and async waiting. Check the actual tool schema: preferences
must accept `squad` and role advice must return `advice.delegation`. If either is
missing, unavailable or fails, explain and use Alpha Squad's standalone manual
flow. Do not require Laya for standalone work or automatically install it.

When routing returns a `decision_id`, recording has separate explicit consent,
and a compatible `laya_feedback` tool is available, read
[laya-feedback.md](laya-feedback.md) before the first routed spawn. Feedback
availability never gates routing or task execution.

## One-window configuration

The orchestrator stays on the verified current-session model and reasoning.
Never switch or restart the main session. Current metadata must be resolved
before delegation; do not infer it from the available-model catalog.

Read preferences. Old advice-only consent does not authorize role routing.
On first activation in a session, or a requested change, use ONE structured
window with these steps, all submitted together:

1. **Current session:** confirm the exact orchestrator pair. Explain that Laya
   will choose model parameters for necessary subagents, not change this session
   or authorize task actions.
2. **Advice policy:** always, conditional, or auto, using the advisor's wording.
3. **Execution model:** one option per eligible model. For auto this is the only
   permitted model for explorer, worker, tester and researcher. For the other
   policies it is the current manual selection for those roles.
4. **Execution reasoning:** for auto, the maximum (proposed default at most
   high); otherwise the current manually selected effort. Apply local filtering.
5. **Reviewer model:** use the orchestrator, or select one eligible model for
   ordinary reviews. High complexity, high risk or uncertainty always selects
   the exact orchestrator pair; this exception is separate from the execution
   ceiling and must be disclosed here.
6. **Reviewer reasoning:** supported, locally enabled effort for the configured
   ordinary-review model; ignored if inheriting the orchestrator.
7. **Final confirmation:** Confirm and continue / Revise selections / Cancel.
   Confirmation covers all preceding steps, including bounded role routing.
   Do not open a second confirmation window or invent a live answer summary.

Preserve submitted choices on revision; save nothing on cancellation or invalid
input. After all pairs revalidate and the last step is confirmed, save preferences
once with `squad={"enabled": true, "reviewer": pair_or_null}`, policy, verified
models, and the execution ceiling only for auto. The MCP returns configuration,
not permission to execute a task. Non-auto execution selections are session-only.
If the host cannot display all steps in one request, report the limitation rather
than silently splitting the flow. Keep async input pending until actual submission.

## Before a necessary spawn

### Opt-in structured orchestration

Use this path only when the user is testing the versioned efficiency policy and
the live tool advertises `orchestration`; otherwise retain the existing flow.
Send `orchestration` alongside `advisor`, not inside the inference state:

```json
{"schema_version":1,"enabled":true,"run_id":"<stable local run ID>","stage_id":"<bounded stage ID>","snapshot_revision":"<task snapshot revision>","independent_work":false,"dependencies_known":true,"required_roles":[],"constraint_refs":["<applicable constraint reference>"]}
```

Keep run, stage and snapshot IDs stable for the same factual task. Change the
snapshot when scope, files or evidence changes; never replace evidence with an
ID alone. Set independent work and dependency status from the actual task, not
from a desire to use more agents. Preserve roles explicitly required by the
user or applicable Skill. A parent assessment does not classify different child
tasks. Same-snapshot role calls may reuse raw assessment inside the worker, but
each returned role route still needs current authorization and host validation.

Consume `orchestration_plan` directly; do not ask another model to rewrite it.
`direct` means no optional child; required validation still runs. `delegate`
permits considering only required roles with useful bounded work, not spawning
the whole role list mechanically. `needs_context` means obtain the missing
evidence or conservatively handle the task; it is not a request for more agents.
Reviewer obligations remain even while clarification is pending. Plans never
grant execution permission or override a user/Skill constraint. Conflicts need
resolution, not silent omission of the stronger constraint.

If the response marks orchestration unsupported, use the ordinary delegation
gate and report that structured coverage is unavailable. A `stale_assessment`
error requires reconciling changed evidence or policy before a new request with
a new request ID; do not dispatch from the rejected result or blindly retry.
Retain the returned decision ID and `reused_from_decision_id` for evidence.
Cached raw Laya usage describes its source evaluation, not fresh inference.
For this opt-in policy, read [laya-execution.md](laya-execution.md) before the
first dispatch for the stage ledger, bounded retry check and actual receipts.

Apply Alpha Squad's delegation gate first. Assess each bounded subtask (or reuse
an identical assessment only while scope, policy and model availability match).
Call `laya_tell_me` with a short factual state and:

```json
{
  "advisor": {
    "role": "worker",
    "current_model": "<verified orchestrator ID>",
    "current_reasoning_effort": "<verified orchestrator effort>",
    "models": [{"id": "<verified ID>", "reasoning_efforts": ["<allowed effort>"]}]
  }
}
```

Use roles explorer, worker, tester, researcher or reviewer. Never route the
orchestrator. Catalog and settings stay out of the model's inference state.
When the installed tool advertises retrieval-scope fields, pass
`advisor.task_family` for this subtask's factual category (`documentation`,
`migration`, or another canonical slug; unknown stays `general`). Pass
`advisor.task_lineage` from the known stable source task, retaining it across
retries, reviews and related child attempts even when their categories differ.
Follow the advisor skill's bounds. Do not use a fresh decision/attempt ID as
proof of an independent task. Omit unknown lineage; cases without it cannot
establish held-out evaluation coverage. These fields only filter historical
context and never grant recording consent, change labels or activate a version.
Older tools without these advertised fields retain the existing routing flow.
For non-auto execution roles also pass `advisor.execution_choice` containing the
confirmed session-only `{model, reasoning_effort}` from setup. Preserve this pair
until explicitly revised; it is not the orchestrator pair or a persisted ceiling.

- Execution roles follow the existing advisor policy. Auto stays on the approved
  model with effort at or below its ceiling; unavailable ceilings require setup.
- Reviewer: high complexity/risk or uncertain uses the exact orchestrator pair;
  otherwise use the configured reviewer pair, defaulting to the orchestrator.
  Do not compare model version strings or silently substitute another pair.
- If `needs_setup` or `needs_verified_pair`, resolve those before any spawn.
- If `ask_user`, show ONE window containing policy, model, effort and a final
  confirmation step. Explain the affected role; do not overwrite the execution
  ceiling with a reviewer choice. For reviewers only offer the parent and the
  configured reviewer, and require the parent for difficult reviews. Changes to
  persisted squad settings use the complete configuration window above. A valid
  explicit selection may be used for this subtask even though the tool does not
  record that later UI answer. Revalidate it before constructing spawn parameters.
- If `ask_user=false`, use `delegation.spawn_parameters` only when non-null,
  accepted, still within the saved constraints and valid against fresh host data.
  Null parameters or a malformed response are never permission to guess.

The HOST, not MCP, calls its native spawn tool with the exact role, model and
reasoning. In Codex pass `agent_type`, `model`, `reasoning_effort` and
`fork_turns="none"` (or a bounded numeric context when supported); full-history
forks cannot accept overrides. Supply a self-contained bounded task. Check role
configuration for model overrides that would defeat the chosen pair; never
rewrite existing role files automatically. Distinguish the requested assignment
from the effective one. If the host cannot verify the effective assignment,
report that limitation and do not claim routing succeeded or start affected work.

For isolated dispatch, include only the objective, role, relevant file/symbol
references, applicable safety/user/AGENTS constraints, dependency summaries,
acceptance checks and known run/stage/decision/attempt IDs. References must be
readable by the child. Do not copy full chat history, repository scans or raw
tool logs by default. If the packet is too large for the verified host window,
compress by relevance without silently truncating constraints; unknown token
capacity stays unknown and byte counts are not native tokens. Record actual
context isolation as unsupported/unknown unless the host verifies it; a requested
`fork_turns` value alone does not prove effective isolation or token savings.

Keep handoffs to conclusions, changed/evidence locations, test results, risks,
next actions and original feedback receipts. Preserve a child's first score
before summarizing its handoff; never fabricate it from the parent's judgment.

On each new task announce exact resolved initial assignments using separate
orchestrator, reviewer and execution-role entries when reviewer differs. Before
any dynamically changed spawn, announce the new exact assignment and the Laya
reason. Initial reviewer uses the orchestrator until a review assessment exists;
initial auto execution roles use the saved ceiling until subtask assessment.
These are configured assignments, not claims that all roles have started.

For missing/failed Laya, preserve the current orchestrator and ask for standalone
manual assignments in its single window unless already confirmed for this task.
Never silently reuse an unassessed automatic route. Keep the skill's accounting
contract, independent review, and task-execution permission boundaries unchanged.
