# Alpha Squad Coding Craft

A portable orchestration skill for complex coding work. It coordinates the
`orchestrator`, `explorer`, `worker`, `tester`, `researcher`, and `reviewer`
roles without embedding provider-specific model identifiers.

## Features

- One provider-neutral `SKILL.md` core.
- Capability-based fallback to sequential single-model roles for web AI chats
  and other hosts without subagents or controllable model/reasoning settings.
- Codex role templates with no `model` or `model_reasoning_effort` fields.
- Claude-compatible Markdown agent definitions.
- Safe first-use Codex bootstrap that preserves existing user files.
- Blocking runtime selection of both model and reasoning controls exposed by
  the host before specialized agents start.
- Mandatory final token, elapsed-time, and subagent summary; unavailable metrics
  retain an explicit reason instead of suppressing the summary.
- Portable and Codex/Claude compatibility manifests for marketplace packaging.

## Install

### Codex quick install

Clone the GitHub repository, then run the setup script. It installs the skill
under `CODEX_HOME/skills` or `~/.codex/skills` and adds only missing role files
under the matching `agents` directory.

macOS and Linux:

```bash
git clone <github-repository-url> alpha-squad-coding-craft
cd alpha-squad-coding-craft
./setup.sh
```

Windows PowerShell:

```powershell
git clone <github-repository-url> alpha-squad-coding-craft
Set-Location alpha-squad-coding-craft
.\setup.ps1
```

Python 3 is required. Existing skill and Agent files are preserved by default.
To update an installed skill or intentionally replace role files, use:

```bash
./setup.sh --force-skill
./setup.sh --force-agents
```

PowerShell uses `-ForceSkill` and `-ForceAgents`. Start a new Codex session
after installation.

For hosts with a native plugin or skill manager, install the repository through
that mechanism instead. The distributable skill is located at:

```text
skills/alpha-squad-coding-craft/
```

The root `plugin.json` is the portable Agent Plugins manifest.
`.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` provide host
compatibility metadata.

### Codex first use without setup

When the skill is first activated on a local Codex host, it checks
`CODEX_HOME/agents` or `~/.codex/agents`. Missing role files are installed from
the bundled templates through the host's normal filesystem approval flow.
Existing files are skipped.

The bootstrap can also be run directly:

```bash
python3 skills/alpha-squad-coding-craft/scripts/install_codex_agents.py
```

Preview changes or choose another Codex home:

```bash
python3 skills/alpha-squad-coding-craft/scripts/install_codex_agents.py --dry-run
python3 skills/alpha-squad-coding-craft/scripts/install_codex_agents.py --codex-home /path/to/.codex
```

Use `--force` only when you intend to replace existing role files.

Plugin installation does not silently trust or execute lifecycle hooks. The
bootstrap therefore runs during the first local Codex activation and remains
subject to the host's filesystem permission policy.

### Claude

The root `agents/` directory contains Claude-style Markdown agent definitions.
Install the repository using the Claude plugin workflow supported by the
current Claude Code release.

### DeepSeek

The portable skill directory can be loaded by hosts that support the Agent
Skills layout, including compatible DeepSeek harnesses. The raw DeepSeek API
does not itself define a filesystem skill or plugin installation format, so the
actual harness must provide skill loading, delegation, and user questions.

## Model selection

These selection steps apply only to native-squad mode. When subagent capability
or verifiable model/reasoning control is missing, the skill keeps the current
session unchanged and uses sequential roles without a model-selection popup.

The skill enumerates the models and reasoning controls exposed by the current
host. It never assumes that a named model exists. On first activation in every
new session, ONE native window contains current-session confirmation, execution
model selection, reasoning selection, and **Final confirmation** as the last
step. Submit all steps with **Confirm and continue** before work or delegation
starts. There is no second confirmation popup; invalid choices or **Revise
selections** reopen the same window. Locally disabled efforts are filtered out.

The structured window is mandatory when the host provides it. The skill
does not replace it with a chat question or an unrelated permission
dialog. If structured input is unavailable, it reports the limitation and
waits. An unanswered or dismissed selection remains waiting for user input and
does not by itself mark a Goal as blocked.

On hosts with asynchronous structured input, a request acknowledgement is
not a user answer. The skill keeps the turn alive while the window is pending,
waits for the actual submission, and does not send a final response or recreate
the window on a Goal continuation. It uses only input tools available in the
current mode. This prevents the workflow from ending immediately after opening
a picker; visual retention still depends on the host and requires a live check.

The `orchestrator` and `reviewer` use the current session assignment. If a
previous selection becomes unavailable, the skill opens selection again rather
than silently substituting another model.

### Optional Oh My Laya routing

Alpha Squad works independently; Laya is not required. With Oh My Laya and
`laya-model-advisor` installed, ask:

```text
Use $alpha-squad-coding-craft with $laya-model-advisor to configure subagent routing.
```

### Web AI chats and limited hosts

This workflow is provider-neutral: ChatGPT, Grok, DeepSeek, Gemini and similar
web AI chats are examples, not a fixed compatibility list. Choose the execution
mode from the conversation's actual capabilities, never its brand. Mentioning
a service does not imply a verified native integration or skill installer.

Make `skills/alpha-squad-coding-craft/SKILL.md` and its referenced resources
accessible to the conversation through the host's supported skill/file mechanism.
A local Codex installation is not automatically available in a web conversation.
Then ask to use Alpha Squad for your task. The skill checks conversation tools,
not whether you are using a browser: capable hosts use native agents; otherwise
the current model sequentially plans, explores, works, tests and self-reviews.
Missing tools remain explicit limitations. No child model selection is shown in
this mode, no subagents are created, and self-review is not independent review.
See the [single-model workflow](skills/alpha-squad-coding-craft/references/single-model.md).

### Native Laya routing behavior

The same setup window includes policy, execution model/effort ceiling, reviewer
model/effort, and final confirmation. The orchestrator never changes. Execution
roles follow Laya's policy; automatic recommendations stay on your chosen model
and within its effort ceiling. Difficult, high-risk or uncertain reviews use the
orchestrator's exact pair; ordinary reviews use your reviewer configuration.

Alpha Squad applies accepted recommendations to native subagent spawn parameters;
MCP does not spawn agents or grant execution permissions. Missing or incompatible
Laya falls back to standalone manual selection. Oh My Laya installs this skill
from this repository's latest default branch; there is no duplicated skill source.

If Laya exposes its optional feedback tool, Alpha Squad can submit redacted
assignment, test, review, outcome, user-choice, and usage events under separate
recording consent. Feedback delivery is durable and idempotent when supported;
missing feedback capability never blocks the coding workflow. See the
[feedback protocol](skills/alpha-squad-coding-craft/references/laya-feedback.md).

For every user-started task while the skill is active, its first task-status
sentence prints one compact assignment line with the exact model and reasoning
names for all roles. This repeats for later tasks in the same chat or session,
even when the cached selection is unchanged or the task remains
orchestrator-only. The skill never replaces exact assignments with defaults,
management labels, inheritance labels, or unavailable placeholders.

## Token usage summary

The orchestrator collects native usage after subagents finish. Subagents return
their work results without a telemetry form. On local Codex the bundled
`collect_token_usage.py` sums task-scoped response records for the orchestrator
and descendants, deduplicates repeated records, and checks coverage against the
spawn ledger. No active Goal is required.

The final line includes total tokens, elapsed time and newly created subagents.
Use the current conversation language for labels, duration units and reasons;
format token counts with comma thousands separators without rounding. English
template:

`Token usage: total <tokens>; Elapsed time: <formatted duration>; Subagents created: <count>.`

Chinese example: `Token 用量：总计 21,910,071；耗时：约 19 分钟；创建子代理：4 个。`

Totals are through the last observed checkpoint; the current final reply and
unflushed usage are not included. Cached/reasoning tokens are not added twice.
Missing logs or incomplete coverage produce an explicit unavailable reason,
never a fabricated count or a partial total labelled complete. Local log formats
can change; other hosts require equivalent native usage support.

## Repository layout

```text
.
├── plugin.json
├── setup.sh / setup.ps1                # one-command Codex installers
├── scripts/install_codex.py            # cross-platform installer core
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── agents/                              # Claude agent definitions
├── skills/alpha-squad-coding-craft/
│   ├── SKILL.md                         # portable workflow
│   ├── agents/openai.yaml               # Codex UI metadata
│   ├── assets/codex-agents/*.toml       # Codex role templates
│   ├── references/adapters.md
│   └── scripts/install_codex_agents.py
└── tests/validate_repo.py
```

## Validate

```bash
python3 -m pip install --requirement tests/requirements.txt
python3 tests/validate_repo.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

Licensed under the [Apache License 2.0](LICENSE).

## Sponsors

Support development through [GitHub Sponsors](https://github.com/sponsors/leo1394).
