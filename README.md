# Alpha Squad Coding Craft

A portable orchestration skill for complex coding work. It coordinates the
`orchestrator`, `explorer`, `worker`, `tester`, `researcher`, and `reviewer`
roles without embedding provider-specific model identifiers.

## Features

- One provider-neutral `SKILL.md` core.
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

The skill enumerates the models and reasoning controls exposed by the current
host. It never assumes that a named model exists. On first activation in every
new session, it opens one native structured window with two required fields:
Step 1 confirms the current-session pair for `orchestrator` and `reviewer`, and
Step 2 selects one supported model-and-reasoning pair for `explorer`, `worker`,
`tester`, and `researcher`. It then opens a separate Final confirmation window
that requires **Confirm and continue** before any substantive work or subagent
creation begins.

The structured windows are mandatory when the host provides them. The skill
does not replace either window with a chat question or an unrelated permission
dialog. If structured input is unavailable, it reports the limitation and
waits. An unanswered or dismissed selection remains waiting for user input and
does not by itself mark a Goal as blocked.

On hosts with asynchronous structured input, a request acknowledgement is
not a user answer. The skill keeps the turn alive while each window is pending,
waits for the actual submission, and does not send a final response or recreate
the window on a Goal continuation. It uses only input tools available in the
current mode. This prevents the workflow from ending immediately after opening
a picker; visual retention still depends on the host and requires a live check.

The `orchestrator` and `reviewer` use the current session assignment. If a
previous selection becomes unavailable, the skill opens selection again rather
than silently substituting another model.

For every user-started task while the skill is active, its first task-status
sentence prints one compact assignment line with the exact model and reasoning
names for all roles. This repeats for later tasks in the same chat or session,
even when the cached selection is unchanged or the task remains
orchestrator-only. The skill never replaces exact assignments with defaults,
management labels, inheritance labels, or unavailable placeholders.

## Token usage summary

Every task using this skill ends its final answer with a statistics line, including
orchestrator-only tasks and incomplete or paused work. The skill uses an
authoritative inclusive task total or complete exclusive per-run accounting;
it never estimates missing counters or adds child usage twice. Accounting is
scoped to the current task and preserved across continuation and compaction.

The line reports total tokens, elapsed wall-clock time rounded to minutes, and
unique successful child creations (including descendants). Failed spawn
attempts do not increase the count; resuming the same child does not count twice.

`Token usage: total <tokens>; Elapsed time: <formatted duration>; Subagents created: <count>.`

Each delegated or resumed assignment requests a child completion record with
agent/run identity, native token count, source, scope, checkpoint, and descendant
records. Missing native counters are explicitly unavailable; children still
return their results. The parent prefers native settled records and deduplicates
cumulative reports. Pre-final checkpoint usage is labelled as such.

If combined usage is incomplete but exclusive current-task orchestrator usage is
known, the summary falls back to:

`Token usage: orchestrator-only 12500 (subagent usage incomplete); Elapsed time: about 8 minutes; Subagents created: 2.`

Durations below one hour omit the hours component, for example `about 8 minutes`.
Longer durations include hours and remaining minutes, for example `about 1 hour
8 minutes`. Singular units are used for 1.

Missing metrics never suppress the line. Replace only the unavailable value
with a reason, retaining all other known metrics, for example:

`Token usage: total unavailable (host does not expose complete task usage); Elapsed time: about 8 minutes; Subagents created: 2.`

The summary is the final content of the final answer, not merely a progress
message or host UI counter. Pending model selection still keeps the turn open;
the summary requirement does not authorize ending a pending selection early.

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
