# Host adapters

The core workflow is host neutral. Map it to native mechanisms without copying
provider-specific model IDs into `SKILL.md`.

## Codex

Personal custom agents are standalone TOML files under `~/.codex/agents/`;
project-scoped agents use `.codex/agents/`. A role file can omit `model` and
`model_reasoning_effort`, allowing the host's spawn configuration or parent
session to resolve them. For `explorer`, `worker`, `tester`, and `researcher`,
the orchestrator must pass the user's validated model and reasoning selection
on every spawn. `reviewer` uses the exact current-session assignment in standalone
mode; the optional Laya adapter may use the separately approved reviewer pair.

On first activation, use `scripts/install_codex_agents.py` to install missing
personal role files when the user and host permit the filesystem write. Never
replace an existing file without an explicit `--force` request.

Reference: <https://learn.chatgpt.com/docs/agent-configuration/subagents>

## Claude Code

Claude Code plugins use Markdown agent definitions. This repository places the
five role definitions in the plugin root `agents/` directory and omits model
frontmatter so a session choice is never persisted globally. Before delegating,
verify that the active Claude host can enumerate, bind, and report a per-agent
model and reasoning combination. If it cannot, stop at the selection gate and
report the limitation.

Reference: <https://claude.com/docs/plugins/overview>

## DeepSeek

The raw DeepSeek API does not define a filesystem skill, plugin, or subagent
manifest. A surrounding harness must supply those capabilities.

`deepseek-harness` supports directory skills containing `SKILL.md` and scans
documented skill roots including `.agents/skills`. Map delegation and user
questions through that harness's supported interfaces. Do not assume that
Codex TOML or Claude Markdown agents are understood by another DeepSeek host.

References:

- <https://api-docs.deepseek.com/>
- <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md>
- <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/capability-seams.md>

## Selection UI

Hosts differ in popup APIs, permissions, model identifiers, and reasoning
controls. On Codex, inspect the tools exposed for the current mode. Prefer
`request_user_input` only when it is callable in that mode; a Plan-only tool
must not be called in Default mode. When `request_user_input_async` is available,
use it and follow the asynchronous lifecycle below. Issue ONE structured request
with four fields: current-session confirmation, execution-role model, reasoning,
and **Final confirmation**. The last field offers **Confirm and continue**,
**Revise selections**, and **Cancel**, covering all earlier answers. Do not claim
the static question can display a live summary of unsubmitted answers. Do not
list every model/effort combination or open a separate confirmation request.

Do not use ordinary chat for this request when the structured tool is
available. Do not use a sandbox, filesystem, network, or command approval as a
substitute. The client owns the outer submit button label, so require the user
to choose **Confirm and continue** in the final step and submit all fields. If
the structured picker is unavailable, report the capability limitation and
wait; do not proceed through a chat fallback.

Keep a pending selection as waiting for user input. Do not mark a Goal
`blocked`, complete, or failed merely because the user has not answered,
dismissed a window, or has not yet clicked the final confirmation. When the
host cannot enumerate, validate, bind, or report an exact combination, do not
delegate the affected roles. Never print a model-assignment line containing a
default, management, inheritance, or availability placeholder.

### Asynchronous Codex input

`request_user_input_async` returns immediately. Its `accepted: true` response
means the question was accepted for display, not that the user answered it.
Answers arrive later as user input. Neither the first preselected option nor
a timer is consent.

After issuing the single selection-and-confirmation request, wait in the same turn. Use
`clock.sleep` when exposed, with `duration_ms` no greater than 60000; it wakes
early for new user input. If a wait completes without a submitted answer,
continue waiting on the same stage. Brief commentary may explain the pending
state, but do not emit `final`, create another picker, or mark the Goal blocked
merely to yield. A final response is not an asynchronous wait primitive.

Validate all submitted fields and the final Confirm and continue answer together.
Only then emit the required Agent models line and proceed. On Revise selections,
reopen the same window preserving valid choices; Cancel changes nothing. On an
explicit dismissal/reopen request, reissue the window; on interruption or
continuation alone, preserve the stage
and do not assume dismissal. Do not invent a pending-request query API when
the host exposes none.

### Lifecycle verification

For a live host check, leave the window untouched for more than 60 seconds,
then submit it. Verify the window remains usable, there is only one request
in total, no final response precedes submission, and no work starts before
the final confirmation step is submitted. Also check Revise selections and an unrelated user message:
neither may silently confirm the assignment. A Goal continuation must preserve
the pending stage rather than create a duplicate window.

Session traces can verify request/submission/final ordering; they cannot prove
that the client visually retained the window. Repository and installer tests
also do not prove popup behavior. Report live UI verification as pending unless
it was actually observed; do not claim a client-side UI fix from skill edits.

## Token accounting

On Codex, the orchestrator uses the read-only collector described in
[token-accounting.md](token-accounting.md). Read that reference before collecting.
No active Goal is required: a missing get_goal counter does not mean local usage
is unavailable. Children report work results, not a mandatory telemetry block.

Validate task scope, unique response counting, nested children, resumed turns,
duplicate archived logs, missing child logs and malformed records with
`tests/test_token_usage.py`. Never count a session lifetime total as a new task.
Native quotas are not consumed tokens. Retain the existing elapsed-time and
created-subagent reporting rules; statistics never justify ending a pending
selection window.

For other hosts use authoritative scoped usage, or state why it is unavailable.
