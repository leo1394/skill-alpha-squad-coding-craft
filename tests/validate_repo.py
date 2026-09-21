#!/usr/bin/env python3
"""Validate manifests, YAML frontmatter, funding, roles, and installers."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "alpha-squad-coding-craft"
EXPECTED_LICENSE = "Apache-2.0"
EXPECTED_ROLES = {"explorer", "worker", "tester", "researcher", "reviewer"}
FUNDING_PLATFORMS = {
    "community_bridge", "github", "issuehunt", "ko_fi", "liberapay",
    "open_collective", "patreon", "tidelift", "polar", "buy_me_a_coffee",
    "thanks_dev", "custom",
}
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
HEX_COLOR = re.compile(r"^#[0-9A-F]{6}$", re.I)
FORBIDDEN_MODEL_IDS = re.compile(
    r"\b(?:gpt-\d|claude-\d|deepseek-(?:chat|reasoner))",
    re.I,
)


def read_json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"{relative} must contain an object"
    return value


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} must start with YAML frontmatter"
    closing = text.find("\n---\n", 4)
    assert closing >= 0, f"{path} frontmatter is not closed"
    metadata = yaml.safe_load(text[4:closing])
    assert isinstance(metadata, dict), f"{path} frontmatter must be an object"
    return metadata, text[closing + 5 :]


def non_empty_string(value: Any, label: str) -> str:
    assert isinstance(value, str) and value.strip(), f"{label} must be non-empty"
    return value


def validate_portable_manifest(portable: dict[str, Any]) -> None:
    schema = read_json("tests/schemas/agent-plugins-1.0.0.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(portable, schema)
    assert portable["name"] == PLUGIN_NAME
    version = non_empty_string(portable.get("version"), "plugin.json version")
    assert SEMVER.fullmatch(version), "plugin.json version must be strict semver"
    non_empty_string(portable.get("description"), "plugin.json description")
    assert portable.get("license") == EXPECTED_LICENSE
    author = portable.get("author")
    assert isinstance(author, dict), "plugin.json author must be an object"
    non_empty_string(author.get("name"), "plugin.json author.name")
    keywords = portable.get("keywords")
    assert isinstance(keywords, list) and keywords
    assert all(isinstance(item, str) and item.strip() for item in keywords)


def validate_codex_manifest(manifest: dict[str, Any], portable: dict[str, Any]) -> None:
    allowed = {
        "id", "name", "version", "description", "skills", "apps",
        "mcpServers", "interface", "author", "homepage", "repository",
        "license", "keywords",
    }
    assert set(manifest) <= allowed, "Codex manifest has unsupported fields"
    assert manifest["name"] == portable["name"]
    assert manifest["version"] == portable["version"]
    assert SEMVER.fullmatch(manifest["version"])
    non_empty_string(manifest.get("description"), "Codex description")
    assert manifest.get("license") == EXPECTED_LICENSE
    assert manifest.get("skills") == "./skills/"
    author = manifest.get("author")
    assert isinstance(author, dict) and set(author) <= {"name", "email", "url"}
    non_empty_string(author.get("name"), "Codex author.name")
    keywords = manifest.get("keywords")
    assert isinstance(keywords, list) and all(
        isinstance(item, str) and item.strip() for item in keywords
    )

    interface = manifest.get("interface")
    assert isinstance(interface, dict), "Codex interface must be an object"
    allowed_interface = {
        "displayName", "shortDescription", "longDescription",
        "developerName", "category", "capabilities", "websiteURL",
        "privacyPolicyURL", "termsOfServiceURL", "brandColor",
        "composerIcon", "logo", "logoDark", "screenshots",
        "defaultPrompt", "default_prompt",
    }
    assert set(interface) <= allowed_interface, "Codex interface has unsupported fields"
    for field in (
        "displayName", "shortDescription", "longDescription",
        "developerName", "category",
    ):
        non_empty_string(interface.get(field), f"Codex interface.{field}")
    capabilities = interface.get("capabilities")
    assert isinstance(capabilities, list) and all(
        isinstance(item, str) and item.strip() for item in capabilities
    )
    prompts = interface.get("defaultPrompt", interface.get("default_prompt"))
    assert isinstance(prompts, list) and prompts
    assert all(isinstance(item, str) and item.strip() for item in prompts)
    color = interface.get("brandColor")
    assert color is None or (isinstance(color, str) and HEX_COLOR.fullmatch(color))


def validate_claude_manifest(manifest: dict[str, Any], portable: dict[str, Any]) -> None:
    allowed = {
        "name", "version", "description", "author", "homepage",
        "repository", "license", "keywords",
    }
    assert set(manifest) <= allowed, "Claude manifest has unsupported fields"
    assert manifest["name"] == portable["name"]
    assert manifest["version"] == portable["version"]
    assert SEMVER.fullmatch(manifest["version"])
    non_empty_string(manifest.get("description"), "Claude description")
    assert manifest.get("license") == EXPECTED_LICENSE
    author = manifest.get("author")
    assert isinstance(author, dict) and set(author) <= {"name", "email", "url"}
    non_empty_string(author.get("name"), "Claude author.name")


def validate_skill() -> None:
    skill_path = ROOT / "skills/alpha-squad-coding-craft/SKILL.md"
    metadata, body = read_frontmatter(skill_path)
    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == PLUGIN_NAME
    non_empty_string(metadata.get("description"), "Skill description")
    assert body.strip()
    assert "## Completion token usage" in body
    assert "Omit the entire completion-statistics line" in body
    assert "`unavailable` placeholders" in body
    assert "Token usage: total <tokens>" in body
    assert "Elapsed time: about <hours> hours <minutes> minutes" in body
    assert "Subagents created: <count>." in body
    assert "Subagents created: 0" in body
    assert "Token usage：" not in body
    assert "Subagents created：" not in body
    assert "Do not count failed spawn attempts" in body
    assert "Open one native structured selection window" in body
    assert "Step 1 — orchestrator, reviewer" in body
    assert "Step 2 — explorer, worker, tester, researcher" in body
    assert "Final confirmation" in body
    assert "Confirm and continue" in body
    assert "Revise selections" in body
    assert "Treat the full two-window interaction as a blocking gate" in body
    assert "Do not use ordinary chat" in body
    assert "must not mark an active Goal as `blocked`" in body
    assert "Pass the selected model and reasoning setting explicitly" in body
    assert "For every new user-started task" in body
    assert "first user-facing task-status sentence" in body
    assert "task in the same chat or session" in body
    assert "gate keeps the task orchestrator-only" in body
    assert "Agent models: orchestrator, reviewer:" in body
    assert "<exact-session-model> (<exact-session-reasoning>)" in body
    assert "<selected-model> (<selected-reasoning>)" in body
    model_section = body.split("## Model and reasoning selection", 1)[1].split(
        "## Delegation gate", 1
    )[0]
    for forbidden in ("host default", "host managed", "silently inheriting"):
        assert forbidden not in model_section.lower()
    assert FORBIDDEN_MODEL_IDS.search(skill_path.read_text(encoding="utf-8")) is None

    openai_path = skill_path.parent / "agents/openai.yaml"
    openai = yaml.safe_load(openai_path.read_text(encoding="utf-8"))
    assert isinstance(openai, dict) and set(openai) <= {
        "interface", "policy", "dependencies",
    }
    interface = openai.get("interface")
    assert isinstance(interface, dict)
    assert set(interface) <= {
        "display_name", "short_description", "icon_small", "icon_large",
        "brand_color", "default_prompt",
    }
    non_empty_string(interface.get("display_name"), "openai interface.display_name")
    description = non_empty_string(
        interface.get("short_description"),
        "openai interface.short_description",
    )
    assert 25 <= len(description) <= 64
    prompt = non_empty_string(
        interface.get("default_prompt"),
        "openai interface.default_prompt",
    )
    assert f"${PLUGIN_NAME}" in prompt
    policy = openai.get("policy")
    assert isinstance(policy, dict) and set(policy) <= {"allow_implicit_invocation"}
    assert isinstance(policy.get("allow_implicit_invocation"), bool)


def validate_roles() -> None:
    role_dir = ROOT / "skills/alpha-squad-coding-craft/assets/codex-agents"
    role_paths = list(role_dir.glob("*.toml"))
    assert {path.stem for path in role_paths} == EXPECTED_ROLES
    for path in role_paths:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
        assert set(data) == {
            "name", "description", "sandbox_mode", "developer_instructions",
        }
        assert data["name"] == path.stem
        non_empty_string(data["description"], f"{path} description")
        non_empty_string(
            data["developer_instructions"],
            f"{path} developer_instructions",
        )
        assert data["sandbox_mode"] in {"read-only", "workspace-write"}
        assert "model" not in data and "model_reasoning_effort" not in data
        assert FORBIDDEN_MODEL_IDS.search(text) is None

    claude_paths = list((ROOT / "agents").glob("*.md"))
    assert {path.stem for path in claude_paths} == EXPECTED_ROLES
    for path in claude_paths:
        metadata, body = read_frontmatter(path)
        assert set(metadata) == {"name", "description"}
        assert metadata["name"] == path.stem
        non_empty_string(metadata["description"], f"{path} description")
        assert body.strip()
        assert FORBIDDEN_MODEL_IDS.search(path.read_text(encoding="utf-8")) is None


def validate_funding() -> None:
    funding_path = ROOT / ".github/FUNDING.yml"
    funding = yaml.safe_load(funding_path.read_text(encoding="utf-8"))
    assert isinstance(funding, dict) and funding, "FUNDING.yml must not be empty"
    assert set(funding) <= FUNDING_PLATFORMS, "FUNDING.yml has an unknown platform"
    for platform, configured in funding.items():
        values = configured if isinstance(configured, list) else [configured]
        limit = 4 if platform in {"github", "custom"} else 1
        assert 1 <= len(values) <= limit, f"invalid {platform} funding count"
        assert all(
            isinstance(value, str) and value.strip() for value in values
        ), f"{platform} funding values must be non-empty strings"
        if platform == "custom":
            assert all(
                value.startswith(("https://", "http://")) for value in values
            ), "custom funding values must be URLs"


def main() -> int:
    portable = read_json("plugin.json")
    validate_portable_manifest(portable)
    validate_codex_manifest(read_json(".codex-plugin/plugin.json"), portable)
    validate_claude_manifest(read_json(".claude-plugin/plugin.json"), portable)
    validate_skill()
    validate_roles()
    validate_funding()
    installer = ROOT / "skills/alpha-squad-coding-craft/scripts/install_codex_agents.py"
    compile(installer.read_text(encoding="utf-8"), str(installer), "exec")
    distribution_installer = ROOT / "scripts/install_codex.py"
    compile(
        distribution_installer.read_text(encoding="utf-8"),
        str(distribution_installer),
        "exec",
    )
    assert (ROOT / "setup.sh").is_file()
    assert (ROOT / "setup.ps1").is_file()
    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
