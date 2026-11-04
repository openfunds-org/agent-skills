#!/usr/bin/env python3
"""
check_changelog.py — CI guard for plugin version, changelog, and public document hygiene.

Checks on pull requests (against BASE_REF, default origin/main):
  1. Document guard: no .pdf, .docx, or .xlsx files outside `plugins/*/skills/*/assets/*.xlsx`
     have been added or modified.
  2. Version + Changelog guard: for each `plugins/<name>/` directory with content files changed,
     require BOTH:
       - the `version` in `plugins/<name>/.claude-plugin/plugin.json` differs from the base ref, AND
       - `plugins/<name>/CHANGELOG.md` was modified.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

META = {".claude-plugin/plugin.json", "CHANGELOG.md"}
APPROVED_ASSET_RE = re.compile(r"^plugins/[^/]+/skills/[^/]+/assets/[^/]+\.xlsx$", re.IGNORECASE)
BLOCKED_DOC_RE = re.compile(r"\.(pdf|docx|xlsx)$", re.IGNORECASE)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def changed_files(base: str) -> list[str]:
    out = _run("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD")
    if out.returncode != 0:
        sys.exit(f"check_changelog: could not diff against '{base}':\n{out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def _version_at(ref: str, plugin: str) -> str | None:
    out = _run("show", f"{ref}:plugins/{plugin}/.claude-plugin/plugin.json")
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout).get("version")
    except json.JSONDecodeError:
        return None


def _head_version(plugin: str) -> str | None:
    path = Path(f"plugins/{plugin}/.claude-plugin/plugin.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError:
        return None


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    files = changed_files(base)

    violations: list[str] = []

    for f in files:
        if BLOCKED_DOC_RE.search(f) and not APPROVED_ASSET_RE.match(f):
            violations.append(f"  Blocked document in PR: {f} (only .xlsx templates in assets/ are permitted)")

    per_plugin: dict[str, list[str]] = {}
    for f in files:
        parts = f.split("/")
        if len(parts) >= 3 and parts[0] == "plugins":
            per_plugin.setdefault(parts[1], []).append("/".join(parts[2:]))

    checked = 0
    for plugin, rels in sorted(per_plugin.items()):
        if not any(r not in META for r in rels):
            continue
        checked += 1
        new_plugin = _version_at(base, plugin) is None
        if not new_plugin and _version_at(base, plugin) == _head_version(plugin):
            violations.append(
                f"  {plugin}: content changed but version not bumped "
                f"(plugins/{plugin}/.claude-plugin/plugin.json)"
            )
        if "CHANGELOG.md" not in rels:
            violations.append(
                f"  {plugin}: content changed but no CHANGELOG entry added "
                f"(plugins/{plugin}/CHANGELOG.md)"
            )

    if violations:
        print("PR hygiene guard FAILED:\n", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        print(
            "\nPolicy: changing a plugin's content requires bumping its version in "
            ".claude-plugin/plugin.json and adding a CHANGELOG.md entry, and no "
            "fund documents (.pdf/.docx/.xlsx) may be committed outside assets/.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"PR hygiene guard OK — {checked} plugin(s) with content changes checked against {base}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
