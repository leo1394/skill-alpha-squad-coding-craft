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

Treat the host's advertised capabilities as authoritative. Never guess a model
identifier, assume a provider-specific default, or select a model that the
current host does not expose.

1. The orchestrator uses the current session model and reasoning setting.
2. The reviewer inherits those exact settings through the host's native
   inheritance mechanism. If exact inheritance is unavailable, pass the current
   session model and reasoning setting explicitly.
3. Resolve the exact current-session model name and reasoning setting before
   any delegation. Do not replace either value with a default, an inferred
   value, or a runtime-management label.
4. Before the first `explorer`, `worker`, `tester`, or `researcher` call in each
   new user-started session, enumerate the model and reasoning combinations the
   host can apply to those calls.
5. Present a structured preference-selection window and require the user to
   select both a model and a reasoning setting. Show only combinations the host
   currently supports. A model and reasoning pair explicitly selected by the
   user earlier in the same session satisfies this step only after host
   validation.
6. Treat selection as a blocking gate. Do not start `explorer`, `worker`,
   `tester`, or `researcher` until both selections are known, validated, and can
   be passed to the delegated call. Never continue without an explicit,
   validated pair.
7. If the structured selection tool is unavailable, ask for the two values in
   chat and wait. If the host cannot enumerate, validate, or apply the selected
   combination, report the limitation and do not delegate those roles.
8. If a stored or previously selected combination is unavailable or no longer
   supported, reopen selection instead of substituting another value.
9. Pass the selected model and reasoning setting explicitly on every
   `explorer`, `worker`, `tester`, and `researcher` call. Verify the effective
   assignment before announcing that the role started.
10. Keep the validated selection only for the current user-started session. Ask
    again in every new session, after an availability change, or when the user
    requests a change. Reusing the selection never suppresses the per-task
    announcement below.

For every new user-started task while this skill is active, including a later
task in the same chat or session, resolve or revalidate the assignments before
substantive work. The first user-facing task-status sentence must be exactly one
model-assignment line in this format:

`Agent models: orchestrator, reviewer: <exact-session-model> (<exact-session-reasoning>); explorer, worker, tester, researcher: <selected-model> (<selected-reasoning>).`

Print this sentence on every user-started task even when the assignment is
unchanged, the selection was cached earlier in the session, or the delegation
gate keeps the task orchestrator-only. Do not print a skill-activation notice,
plan, progress update, or other task-status sentence before it. A required
structured selection window or blocking chat selection question is a
prerequisite interaction; immediately after selection, make the model line the
first task-status sentence.

Use the host's exact user-facing model and reasoning names. The model line must
not contain placeholders or vague labels such as `default`, `managed`,
`inherited`, `unknown`, `unspecified`, or `unavailable`. If any exact value is
unresolved, the model-selection gate remains incomplete and substantive work
may not start.

Do not use a filesystem or command approval dialog for model selection. Model
choice uses the host's preference-selection UI. An ordinary chat question is
only the blocking fallback when that UI is unavailable.

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
   decisions.

Run independent tasks in parallel and dependent tasks in order. Do not spawn
every role mechanically. Do not claim an agent contributed unless the host
actually started that role and returned a result.

## Completion token usage

Before finishing a task that used this skill, query the host's native usage
accounting for the orchestrator and every spawned agent run. Prefer the same
authoritative task or goal usage source the host uses for its built-in final
usage summary. Record the task start and completion timestamps and compute the
elapsed wall-clock time, rounded to the nearest whole minute.

Track every actual orchestrator and subagent run or attempt with its stable run
ID. Also track every successfully created subagent by its stable agent or child
thread ID. Retries and resumed runs consume tokens and must each be counted
once. Only deduplicate repeated usage records for the same stable run ID;
conflicting records make the total unavailable.

Sum exclusive per-run `total_tokens` records after confirming that every
tracked orchestrator and subagent run is present. Compute the subagent subtotal
from all child runs, including retries and resumed runs, then compute the
overall total as orchestrator plus subagents. An authoritative inclusive task
or goal total may verify that result, but never add it to per-run totals. If a
run has no total, sum input and output tokens only when the host documents those
counters as non-overlapping. Never estimate from text length or context-window
size.

Only print the completion statistics when authoritative orchestrator, subagent,
and overall totals can all be established. The subagent subtotal must include
every child role and every child run, and `total` must equal orchestrator plus
subagents.

Use exactly one English line in this format:

`Token usage: total <tokens>; Elapsed time: about <hours> hours <minutes> minutes; Subagents created: <count>.`

Do not print separate token subtotals, a separate subagent-count line, full-width
punctuation, or non-English labels in this completion statistic.

Count unique successful subagent creations by stable agent or child thread ID.
Do not count failed spawn attempts. Resuming the same subagent does not increase
the count; spawning a new subagent for a retry does. Include every role:
`explorer`, `worker`, `tester`, `researcher`, and `reviewer`.

If any participating run is missing or inclusion semantics are ambiguous, do
not invent token totals. Omit the entire completion-statistics line and never
print `unavailable` placeholders or a partial line. For an orchestrator-only
task with complete usage data, use `Subagents created: 0` within the standard
line.

## Portability

The core workflow is provider-neutral. Keep provider model IDs, host-specific
paths, and invocation syntax in adapters or session state. Do not write a
session's model selection back into this skill or its distributed role
templates.
