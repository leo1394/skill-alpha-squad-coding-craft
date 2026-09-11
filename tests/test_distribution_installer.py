from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install_codex.py"
ROLE_NAMES = {"explorer", "worker", "tester", "researcher", "reviewer"}


class DistributionInstallerTest(unittest.TestCase):
    def run_installer(
        self,
        codex_home: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--codex-home",
                str(codex_home),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_install_repeat_and_explicit_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory) / "codex"
            first = self.run_installer(home)
            self.assertEqual(first.returncode, 0, first.stderr)
            skill = home / "skills/alpha-squad-coding-craft/SKILL.md"
            self.assertTrue(skill.is_file())
            role_dir = home / "agents"
            self.assertEqual({path.stem for path in role_dir.glob("*.toml")}, ROLE_NAMES)

            skill.write_text("local skill change\n", encoding="utf-8")
            explorer = role_dir / "explorer.toml"
            explorer.write_text("local agent change\n", encoding="utf-8")
            repeated = self.run_installer(home)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(skill.read_text(encoding="utf-8"), "local skill change\n")
            self.assertEqual(explorer.read_text(encoding="utf-8"), "local agent change\n")

            updated = self.run_installer(home, "--force-skill")
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertIn("name: alpha-squad-coding-craft", skill.read_text(encoding="utf-8"))
            self.assertEqual(explorer.read_text(encoding="utf-8"), "local agent change\n")

            forced = self.run_installer(home, "--force-agents")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn('name = "explorer"', explorer.read_text(encoding="utf-8"))

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory) / "codex"
            result = self.run_installer(home, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(home.exists())


if __name__ == "__main__":
    unittest.main()
