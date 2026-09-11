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
- Final token accounting across the orchestrator and all spawned agents when
  the host exposes complete usage metrics.
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
host. It never assumes that a named model exists. Before the first
`explorer`, `worker`, `tester`, or `researcher` call in every new session, it
opens the host's native structured picker and requires both a model and a
reasoning selection. If the picker is unavailable, it asks in chat and waits.
No specialized agent starts until the host validates and can apply both values.

The `orchestrator` and `reviewer` use the current session assignment. If a
previous selection becomes unavailable, the skill opens selection again rather
than silently substituting another model.

Before delegation, the skill prints one compact assignment line with the exact
model and reasoning names for all roles. It never replaces them with defaults,
management labels, inheritance labels, or unavailable placeholders. When a host
cannot enumerate, validate, apply, or report the selected combination, the
skill stops before delegation and reports that limitation.

## Token usage summary

At completion, the skill requests the host's native usage counters, aggregates
every actual attempt once by stable run ID, and prints an overall total that
includes the orchestrator and every subagent. An authoritative parent total is
used directly only when the host documents that it includes all child runs; it
is never added to child totals. The skill never estimates missing counters. If
only that inclusive total is available, the output contains only the known
total. If the host does not expose a complete, unambiguous total, the skill
omits the token-usage line entirely.

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
