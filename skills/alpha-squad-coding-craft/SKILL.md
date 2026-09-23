---
name: alpha-squad-coding-craft
description: >-
  Coordinate complex coding work with specialized exploration,
  implementation, testing, research, and review agents while selecting only
  models and reasoning controls supported by the current host.
---

# Alpha Squad Coding Craft

The user's explicit instructions take precedence over this skill.

Use the `orchestrator` as planner and integrator. Delegate bounded work to
`explorer`, `worker`, `tester`, `researcher`, and `reviewer`, then integrate,
verify, and report the result. Use these role names in prompts and logs.

## First activation

Identify the current host and its native delegation mechanism.

On a local Codex host, check `CODEX_HOME` or `~/.codex` for these files when
this skill is first activated:

- `agents/explorer.toml`
- `agents/worker.toml`
- `agents/tester.toml`
- `agents/researcher.toml`
- `agents/reviewer.toml`

If any file is missing, explain that the bundled templates contain role
instructions without model settings, then run
`scripts/install_codex_agents.py` through the host's normal filesystem approval
path. The script installs only missing files by default. Never pass `--force`
unless the user explicitly asks to replace existing role files.

Other hosts skip the Codex bootstrap and use their native agent definitions.
Read [references/adapters.md](references/adapters.md) when host-specific setup
is needed.

## Model and reasoning selection

The standalone flow below requires no Laya installation. If the user requests
Laya routing, first check that `laya-model-advisor` and compatible
`laya_tell_me` / `laya_advisor_preferences` tools are available. Only then read
[references/laya-routing.md](references/laya-routing.md). That optional flow
replaces the standalone selection gate; never run both gates. Missing skills,
tools, or inference failures fall back to this standalone flow with a clear
notice, without installing dependencies or inventing an assessment.

Treat the host's advertised capabilities as authoritative. Never guess a model
identifier, assume a provider-specific default, or select a model that the
current host does not expose.

On Codex, resolve the current pair from this conversation's latest `turn_context`
metadata (match `CODEX_THREAD_ID`), then live host data if needed; never substitute
global defaults or ask for manual entry before checking metadata. Read only the
necessary fields. Filter offered efforts using the local Codex config's
`[desktop].enabled-reasoning-efforts` intersected with each model's support.
If absent, hide max, ultra and xmax; show those only when explicitly enabled and
supported. Malformed config requires clarification, not bypass. Revalidate after
submission. Do not change configuration to enable hidden efforts.

1. The orchestrator uses the current session model and reasoning setting.
2. The reviewer inherits those exact settings through the host's native
   inheritance mechanism. If exact inheritance is unavailable, pass the current
   session model and reasoning setting explicitly.
3. Resolve the exact current-session model name and reasoning setting before
   any delegation. Do not replace either value with a default, an inferred
   value, or a runtime-management label.
4. On the first activation in each new user-started session, enumerate the model
   and reasoning combinations the host can apply to delegated calls. Complete
   the required interaction below even when the current task remains
   orchestrator-only.
5. Open ONE native structured window containing all selection fields and a final
   confirmation step, in this order. Do not open a second confirmation window:
   - **Step 1 — orchestrator, reviewer:** show the exact current-session model
     and reasoning pair and require the user to confirm it. These roles cannot
     select a different pair inside this flow. If the user wants another pair,
     wait for them to change the session settings, re-resolve the exact pair,
     and restart Step 1.
   - **Step 2 — Model (explorer, worker, tester, researcher):** list each verified
     model once, not a long Cartesian product of model/effort combinations.
   - **Step 3 — Reasoning:** list locally allowed, host-supported efforts.
     Explain model-specific restrictions and validate the chosen pair on submit.
   - **Final confirmation:** offer **Confirm and continue**, **Revise selections**,
     and **Cancel**. Explain that confirmation covers all preceding selections.
     A static window cannot show a summary of answers not yet submitted; do not
     fabricate one. Keep this as the LAST step in the SAME request.
6. Validate all answers together after submission. Continue only when every pair
   is valid and the final answer is **Confirm and continue**. For invalid input
   or **Revise selections**, reopen the same window with valid answers retained
   and the problem explained. **Cancel** makes no assignment changes.
7. Treat the complete single-window interaction as a blocking gate. Do not start
   substantive work or create any subagent until all fields and Final
   confirmation are submitted. Never infer confirmation from silence, a timeout,
   a previous session, or an unrelated approval.
8. When a native structured user-input tool is available, it is mandatory for
   the complete window. Do not use ordinary chat, commentary, a filesystem approval,
   or a command approval for either selection or Final confirmation. If no
   structured user-input tool is available, report that the required interaction
   cannot be presented and wait without starting substantive work or delegation.
9. A pending, dismissed, or unanswered selection is a waiting-for-user-input
   state. It must not mark an active Goal as `blocked`, complete, or failed.
   Keep the existing request pending. Do not reopen it merely because a Goal
   continues, a wait times out, or no answer has arrived. Reopen only after an
   explicit user request or a host event confirming the request was dismissed
   or cancelled; preserve any submitted selections. Apply the host's separate
   Goal-status policy only if an independent blocking condition remains after
   the required interaction is complete.
10. A model and reasoning pair explicitly selected earlier in the same session
    satisfies the selection only after host validation and Final confirmation in this
    session. If a stored combination is unavailable or no longer supported,
    reopen selection instead of substituting another value.
11. Pass the selected model and reasoning setting explicitly on every
    `explorer`, `worker`, `tester`, and `researcher` call. Verify the effective
    assignment before announcing that the role started.
12. Keep the confirmed assignment only for the current user-started session.
    Run the full interaction again in every new session, after an availability
    change, or when the user requests a change. Reusing the confirmed assignment
    never suppresses the per-task announcement below.

For every new user-started task while this skill is active, including a later
task in the same chat or session, resolve or revalidate the assignments before
substantive work. The first user-facing task-status sentence must be exactly one
model-assignment line in this format:

`Agent models: orchestrator, reviewer: <exact-session-model> (<exact-session-reasoning>); explorer, worker, tester, researcher: <selected-model> (<selected-reasoning>).`

Print this sentence on every user-started task even when the assignment is
unchanged, the selection was cached earlier in the session, or the delegation
gate keeps the task orchestrator-only. Do not print a skill-activation notice,
plan, progress update, or other task-status sentence before it. A required
structured selection and confirmation interaction is a prerequisite;
immediately after Final confirmation, make the model line the first task-status
sentence.

Use the host's exact user-facing model and reasoning names. The model line must
not contain placeholders or vague labels such as `default`, `managed`,
`inherited`, `unknown`, `unspecified`, or `unavailable`. If any exact value is
unresolved, the model-selection gate remains incomplete and substantive work
may not start.

Do not use a filesystem or command approval dialog for model selection. Model
choice uses the host's native structured preference-selection UI. The client
may control the outer submit button's localized label; the final step must
still contain an explicit **Confirm and continue** choice and must not continue
until the user selects it and submits the window.

## Structured input lifecycle

Before opening the window, inspect the input tool's current availability
and response semantics. A blocking tool waits for submitted answers; an async
tool only acknowledges that the request was created. Do not call a tool that
is restricted to a different collaboration mode.

With asynchronous input, `accepted: true` is not a submitted answer. After
creating a request, keep the current turn alive using the host's interruptible
wait mechanism in bounded intervals (at most 60 seconds per call). A wait
timeout changes no selection state. Do not send a final answer while a selection
or Final confirmation request is pending: ending the turn can remove the
interaction before the user submits it. Do not replace this wait with repeated
final status messages or duplicate requests on Goal continuations.

Track the current stage (selection pending, confirmed),
the exact submitted assignments, and the request identifier when the host
provides one. Preserve them across continuation or compaction. Only an actual
user submission advances the stage. Start work only after all fields validate
and the final step explicitly contains Confirm and continue in that same
submission. Preselected options, unrelated messages, elapsed time, and Goal
wakeups are not submissions. If the user changes the task or asks to repair
this selection workflow, handle that request rather than trapping the user in
the pending gate; it does not approve the original task's assignments.

For Codex tool selection and lifecycle verification scenarios, read
[references/adapters.md](references/adapters.md#selection-ui).

## Delegation gate

Keep work with the orchestrator when it is small, localized, and gains little
from separate context. Delegate when any of these conditions apply:

- work spans multiple files, modules, services, or components
- two or more independent workstreams can run in parallel
- repository exploration is needed before implementation
- implementation and verification benefit from separate context
- debugging requires tracing across components
- current or version-specific external facts need verification
- an independent review materially improves confidence
- the user explicitly asks for agents, delegation, or parallel work

When delegation is required but the host has no subagent capability, state the
limitation and continue only when the user's request permits a single-agent
fallback.

## Roles

- `explorer`: map files, symbols, execution paths, dependencies, configuration,
  and tests without editing.
- `worker`: implement a bounded change after scope and acceptance criteria are
  clear.
- `tester`: reproduce behavior and run focused verification independently.
- `researcher`: verify external or version-specific facts using primary sources.
- `reviewer`: inspect the actual change for correctness, security, regression,
  data-integrity, compatibility, and missing-test risks.

Every delegated task must include a concrete objective, scope, constraints,
deliverable, and acceptance criteria. Give one writer ownership of each file or
subsystem unless the orchestrator explicitly coordinates shared ownership.

## Workflow

1. Explore or research when evidence is missing.
2. Let the orchestrator choose the implementation direction.
3. Assign bounded implementation work.
4. Verify the changed behavior independently when useful.
5. Request an independent review for material or high-risk changes.
6. Resolve findings, inspect the final diff, and run focused checks.
7. Report what changed, validation performed, limitations, and unresolved
   decisions. Finish with the mandatory completion summary below, even when
   native token accounting is unavailable.

Run independent tasks in parallel and dependent tasks in order. Do not spawn
every role mechanically. Do not claim an agent contributed unless the host
actually started that role and returned a result.

## Completion summary (mandatory)

Every task that used this skill MUST end its final user-facing answer with the
completion-statistics line below. This is a completion gate, not optional
commentary. Include it for orchestrator-only tasks and when reporting incomplete,
failed, cancelled, or paused work. Missing usage data never permits omitting the
line. Do not send a final answer merely to provide statistics while a structured
selection or confirmation request is pending; its lifecycle rules still apply.

### Capture accounting state

At task entry, before model selection or substantive work, record the task start
timestamp and available native usage baseline. Preserve these across automatic
continuations and compaction; do not restart the clock or lose agent records.
For a later user-started task, open a new accounting scope rather than reporting
the whole conversation's lifetime usage.

Track the task or goal ID, every participating run ID, and every successfully
created child agent/thread ID, with role, status, and usage source. Include all
roles, retries, and resumed runs. Record child creation immediately on success,
not only when its result arrives. A created child that later fails still counts.
Do not count failed spawn attempts as created subagents, but include their token
usage when native accounting attributes consumed tokens to this task.

### Parent-owned token collection

The orchestrator collects native usage AFTER children complete. Subagents return
their work result; do not require an agent_id/run_id/usage_scope/token telemetry
report from them. Keep the spawn ledger internally, including descendants and
resumed calls. A missing child self-report is not missing host accounting.

On local Codex, read [references/token-accounting.md](references/token-accounting.md)
and use the bundled read-only collector. Resolve and retain this task's exact
root thread and root turn IDs at entry from native session metadata. On verified
automatic continuation, add its root turn ID only if it belongs to the SAME
task; never include later unrelated user requests. The collector sums per-response
native total_tokens across the root and related descendants, deduplicating
responses rather than summing cumulative snapshots.

### Resolve metrics before finalizing

Run the collector immediately before the final answer, after waiting for
participating children to finish. Supply the known unique participating subagent
count, including descendants. Use a numeric combined total only when collection
succeeds and scope/coverage match the task. No active Goal is required. Missing
get_goal usage or a missing direct token tool is NOT grounds to skip local logs.

- Use native total_tokens directly. Cached input and reasoning output are already
  components of usage; never add them again. Tokens are not monetary cost.
- Never use lifetime thread totals for a later task or sum cumulative snapshots.
- If an authoritative inclusive task total is used instead, do not add children
  to that inclusive number.
- Report the last observed checkpoint, not an estimate of the current final
  reply. Completed child replies can be included once their records are flushed.
- For missing logs, invalid counters, conflicting duplicates or incomplete
  subagent coverage, report `Token usage: total unavailable (<specific reason>)`.
  Never present a partial sum as the complete total. An explicitly verified
  root-only figure may be labelled `orchestrator-only`, not total.
- On non-Codex hosts use verified native task usage with equivalent scope and
  deduplication; do not run the Codex parser against another host's logs.

Measure elapsed wall-clock time from recorded task entry to the final accounting
checkpoint, including selection, tools, and waits, rounded to the nearest whole
minute. Do not sum parallel agents' durations. If the start timestamp is lost,
recover it from authoritative task events or report unavailable with a reason.
If the rounded duration is below 60 minutes, use `about <minutes> minutes` and
omit the hours component entirely. At 60 minutes or more, include hours and
remaining minutes. Use singular units for 1: `about 1 minute`,
`about 1 hour 0 minutes`, `about 1 hour 1 minute`. A measured duration rounding to
zero is `about 0 minutes`; never use zero as a substitute for a missing timestamp.

Count unique successful subagent creations by stable agent or child thread ID.
Do not count failed spawn attempts. Resuming the same child does not increase the
count; spawning a new child for a retry does. Include explorer, worker, tester,
researcher, reviewer, and descendant agents. Do not count configured roles that
were never spawned or the orchestrator itself. Use `Subagents created: 0` for a
verified orchestrator-only task. If the creation ledger is incomplete, report
unavailable with a reason instead of guessing zero.

### Required final line

Append exactly one English statistics line as the last content of the final
answer, after the outcome, validation, limitations, and any requested follow-up.
A progress update, tool result, hidden log, or built-in UI usage display is not
a substitute. Keep all three labels and use ASCII punctuation:

`Token usage: total <tokens>; Elapsed time: <formatted duration>; Subagents created: <count>.`

For example, a duration under one hour is `Elapsed time: about 8 minutes`;
a longer duration is `Elapsed time: about 2 hours 8 minutes`.
When only exclusive orchestrator accounting is available, use:

`Token usage: orchestrator-only 12500 (subagent usage incomplete); Elapsed time: about 8 minutes; Subagents created: 2.`

When a metric cannot be established, replace only that metric's value with
`unavailable (<specific reason>)`. For example:

`Token usage: total unavailable (host does not expose complete task usage); Elapsed time: about 8 minutes; Subagents created: 2.`

Before sending final, check that all three metrics are present, numeric values
have evidence and the correct task scope, unavailable values have reasons, and
the statistics line is the final content. If any check fails, fix the summary
before sending. Never omit the entire completion-statistics line.

Read [references/adapters.md](references/adapters.md#token-accounting) for
host accounting boundaries and completion verification scenarios.

## Portability

The core workflow is provider-neutral. Keep provider model IDs, host-specific
paths, and invocation syntax in adapters or session state. Do not write a
session's model selection back into this skill or its distributed role
templates.
