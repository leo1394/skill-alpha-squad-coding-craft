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
    requests a change.

Before the first delegated call, announce the assignments in one line:

`orchestrator、reviewer：<exact-session-model> <exact-session-reasoning>；explorer、worker、tester、researcher：<selected-model> <selected-reasoning>。`

Use the host's exact user-facing model and reasoning names. This line must not
contain placeholders or vague labels such as `default`, `managed`, `inherited`,
`unknown`, `unspecified`, or `unavailable`. If any exact value is unresolved,
the model-selection gate remains incomplete and no delegated role may start.

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
usage summary.

Track every actual orchestrator and subagent run or attempt with its stable run
ID. Retries and resumed runs consume tokens and must each be counted once. Only
deduplicate repeated usage records for the same stable run ID; conflicting
records make the total unavailable.

If the host supplies an authoritative task or goal total that explicitly
includes the orchestrator and every child run, use that total directly. Never
add an inclusive parent total to child totals. Otherwise sum exclusive per-run
`total_tokens` records after confirming that every tracked run is present. If a
run has no total, sum input and output tokens only when the host documents those
counters as non-overlapping. Never estimate from text length or context-window
size.

Only print a token-usage line when an authoritative, complete overall total can
be established for the orchestrator and every subagent run. Include role totals
only for roles whose authoritative totals are available, followed by the
overall total:

`Token usage：orchestrator <tokens>；explorer <tokens>；worker <tokens>；reviewer <tokens>；total <tokens>。`

When the host exposes only an authoritative inclusive total, print only that
known total:

`Token usage：total 123。`

The example role list is illustrative; also support `tester` and `researcher`,
and combine multiple agents that used the same role. The overall total must
include the orchestrator and every subagent.

If no authoritative inclusive total exists and any participating run is
missing, or the host does not document whether a parent total includes child
runs, do not invent a total. Omit the entire token-usage line. Never print
`unavailable` placeholders or a partial token-usage line.

## Portability

The core workflow is provider-neutral. Keep provider model IDs, host-specific
paths, and invocation syntax in adapters or session state. Do not write a
session's model selection back into this skill or its distributed role
templates.
