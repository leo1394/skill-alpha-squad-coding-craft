# Host adapters

The core workflow is host neutral. Map it to native mechanisms without copying
provider-specific model IDs into `SKILL.md`.

## Codex

Personal custom agents are standalone TOML files under `~/.codex/agents/`;
project-scoped agents use `.codex/agents/`. A role file can omit `model` and
`model_reasoning_effort`, allowing the host's spawn configuration or parent
session to resolve them. For `explorer`, `worker`, `tester`, and `researcher`,
the orchestrator must pass the user's validated model and reasoning selection
on every spawn. `reviewer` must use the exact current-session assignment.

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
use it and follow the asynchronous lifecycle below. Issue the two requests
sequentially:

1. One structured request with two required fields: Step 1 confirms the exact
   current-session pair for `orchestrator` and `reviewer`; Step 2 selects one
   supported model-and-reasoning pair for `explorer`, `worker`, `tester`, and
   `researcher`.
2. A second structured request named **Final confirmation** that displays both
   exact assignments and offers **Confirm and continue** and **Revise
   selections**.

Do not use ordinary chat for either request when the structured tool is
available. Do not use a sandbox, filesystem, network, or command approval as a
substitute. The client owns the outer submit button label, so require the user
to choose **Confirm and continue** inside the final request and submit it. If
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

After issuing the two-field selection request, wait in the same turn. Use
`clock.sleep` when exposed, with `duration_ms` no greater than 60000; it wakes
early for new user input. If a wait completes without a submitted answer,
continue waiting on the same stage. Brief commentary may explain the pending
state, but do not emit `final`, create another picker, or mark the Goal blocked
merely to yield. A final response is not an asynchronous wait primitive.

Validate both submitted fields before opening Final confirmation. Keep that
second request alive using the same wait behavior. On Confirm and continue,
emit the required Agent models line and proceed. On Revise selections, return
to the two-field request. On an explicit dismissal/reopen request, reissue only
the affected stage; on interruption or continuation alone, preserve the stage
and do not assume dismissal. Do not invent a pending-request query API when
the host exposes none.

### Lifecycle verification

For a live host check, leave each window untouched for more than 60 seconds,
then submit it. Verify the window remains usable, there is only one request
per stage, no final response precedes submission, and no work starts before
Final confirmation. Also check Revise selections and an unrelated user message:
neither may silently confirm the assignment. A Goal continuation must preserve
the pending stage rather than create a duplicate window.

Session traces can verify request/submission/final ordering; they cannot prove
that the client visually retained the window. Repository and installer tests
also do not prove popup behavior. Report live UI verification as pending unless
it was actually observed; do not claim a client-side UI fix from skill edits.

## Token accounting

Use the host's native per-run or task usage records. Aggregate all orchestrator
and spawned-agent attempts exactly once by stable run ID, including retries and
resumed runs. Deduplicate only repeated records for the same run. A host may
expose input, output, cached, reasoning, or total counters with different
semantics. Sum all exclusive child records into a `subagents` subtotal and add
that subtotal to the orchestrator total. Use a documented inclusive task total
only to verify the result, never as another summand. If inclusion semantics or
complete subagent usage are unavailable, omit the token-usage line instead of
estimating.

Count unique successful child creations by stable agent or child thread ID.
Failed spawn attempts do not count; resuming an existing child does not add one;
a newly spawned retry does. Measure elapsed wall-clock time from task start to
completion and round it to the nearest whole minute. Emit one English summary:
`Token usage: total <tokens>; Elapsed time: about <hours> hours <minutes>
minutes; Subagents created: <count>.` Omit the entire line when complete token
usage cannot be established.
