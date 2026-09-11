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
controls. Use the native structured preference picker whenever it is available,
and show only model and reasoning combinations the host can bind to delegated
calls. If the picker is unavailable, ask in chat and wait. Lack of a picker is
never permission to continue without a choice. When the host cannot enumerate,
validate, bind, or report an exact combination, do not delegate the affected
roles. Never print a model-assignment line containing a default, management,
inheritance, or availability placeholder.

## Token accounting

Use the host's native per-run or task usage records. Aggregate all orchestrator
and spawned-agent attempts exactly once by stable run ID, including retries and
resumed runs. Deduplicate only repeated records for the same run. A host may
expose input, output, cached, reasoning, or total counters with different
semantics; prefer a documented inclusive task total when it covers every child,
and never add that parent total to child records. If inclusion semantics or
complete subagent usage are unavailable, report that limitation instead of
estimating. When the inclusive total is authoritative but per-role counters are
absent, print only the known total. When a complete total cannot be established,
omit the token-usage line entirely.
