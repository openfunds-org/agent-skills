#!/usr/bin/env python3
"""
scaffold_skill.py — Scaffold a new Agent Skill inside an openfunds plugin.

Usage:
    python3 scripts/scaffold_skill.py --name <skill-name> [--plugin openfunds-tools] [--description "..."]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new Agent Skill.")
    parser.add_argument("--name", required=True, help="Skill directory name (kebab-case, e.g. openfunds-validator).")
    parser.add_argument("--plugin", default="openfunds-tools", help="Target plugin under plugins/ (default: openfunds-tools).")
    parser.add_argument("--description", default="", help="Skill description (what it does and when to trigger it).")
    args = parser.parse_args()

    if not NAME_PATTERN.fullmatch(args.name) or "claude" in args.name or "anthropic" in args.name:
        sys.exit(f"Invalid skill name {args.name!r}: use lowercase letters, numbers and hyphens (no 'claude'/'anthropic').")

    plugin_dir = REPO_ROOT / "plugins" / args.plugin
    if not (plugin_dir / ".claude-plugin" / "plugin.json").is_file():
        sys.exit(f"Plugin not found: {plugin_dir}")

    skill_dir = plugin_dir / "skills" / args.name
    if skill_dir.exists():
        sys.exit(f"Skill already exists: {skill_dir.relative_to(REPO_ROOT)}")

    for sub in ("scripts", "reference", "assets"):
        (skill_dir / sub).mkdir(parents=True, exist_ok=True)

    desc = args.description or f"Describe what {args.name} does and when the assistant should invoke it."
    skill_md = (
        "---\n"
        f"name: {args.name}\n"
        f"description: {desc}\n"
        "license: CC-BY-ND-4.0\n"
        "compatibility: Requires Python 3.9+.\n"
        "metadata:\n"
        "  author: openfunds\n"
        '  version: "0.1.0"\n'
        "---\n\n"
        f"# {args.name}\n\n"
        "Add the step-by-step workflow instructions for this skill here.\n"
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    for legal_file in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        src = REPO_ROOT / legal_file
        if src.is_file():
            (skill_dir / legal_file).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Scaffolded skill at {skill_dir.relative_to(REPO_ROOT)}/")
    rc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "validate_plugins.py"), str(skill_dir)]).returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
