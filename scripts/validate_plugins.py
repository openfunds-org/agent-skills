#!/usr/bin/env python3
"""
validate_plugins.py — Validate plugins and portable Agent Skills in the openfunds repository.

Checks:
  1. .claude-plugin/marketplace.json exists, is valid JSON, and every listed plugin exists.
  2. Each plugin has a valid .claude-plugin/plugin.json (name, version, description).
  3. Each skill under plugins/*/skills/*/ has a valid SKILL.md:
     - Valid UTF-8 with no BOM or null bytes across all text files.
     - Valid YAML frontmatter with no tabs.
     - Frontmatter `name` matches folder name, lowercase alphanumeric + hyphens, <= 64 chars, no 'claude'/'anthropic'.
     - Frontmatter `description` is non-empty, <= 1024 chars.
     - Optional `compatibility` <= 500 chars; optional `metadata` mapping of string values.
     - No host-specific keys (`model`, `tools`, `permissions`).
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


REPO_ROOT = Path(__file__).resolve().parent.parent
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
HOST_SPECIFIC_KEYS = {"model", "tools", "permissions"}
TEXT_SUFFIXES = {".json", ".md", ".py", ".txt", ".yaml", ".yml", ".sh"}


def read_utf8(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path.relative_to(REPO_ROOT)} has a UTF-8 BOM")
    if b"\x00" in raw:
        raise ValueError(f"{path.relative_to(REPO_ROOT)} contains null bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.relative_to(REPO_ROOT)} is not valid UTF-8: {exc}") from exc


def parse_frontmatter(text: str, path: Path) -> dict:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path.relative_to(REPO_ROOT)}: SKILL.md must begin with YAML frontmatter `---`")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"{path.relative_to(REPO_ROOT)}: SKILL.md frontmatter has no closing `---`") from exc
    source = "\n".join(lines[1:closing])
    if "\t" in source:
        raise ValueError(f"{path.relative_to(REPO_ROOT)}: SKILL.md frontmatter contains tab characters")
    if yaml is not None:
        parsed = yaml.safe_load(source)
        if not isinstance(parsed, dict):
            raise ValueError(f"{path.relative_to(REPO_ROOT)}: SKILL.md frontmatter must be a YAML mapping")
        return parsed
    result = {}
    for line in source.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def validate_skill(skill_dir: Path) -> list[str]:
    errors = []
    skill_file = skill_dir / "SKILL.md"
    rel = skill_dir.relative_to(REPO_ROOT)
    if not skill_dir.is_dir() or not skill_file.is_file():
        return [f"{rel} is missing SKILL.md"]

    try:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                read_utf8(path)
        metadata = parse_frontmatter(read_utf8(skill_file), skill_file)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    name = metadata.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        errors.append(f"{rel}: frontmatter 'name' must contain lowercase letters, numbers and single hyphens")
    elif len(name) > 64:
        errors.append(f"{rel}: frontmatter 'name' exceeds 64 characters")
    elif name != skill_dir.name:
        errors.append(f"{rel}: frontmatter name {name!r} does not match directory {skill_dir.name!r}")
    elif "claude" in name or "anthropic" in name:
        errors.append(f"{rel}: frontmatter name {name!r} contains reserved word")

    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{rel}: frontmatter 'description' must be a non-empty string")
    elif len(description) > 1024:
        errors.append(f"{rel}: frontmatter 'description' exceeds 1024 characters ({len(description)})")

    compatibility = metadata.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str) or not compatibility.strip():
            errors.append(f"{rel}: 'compatibility' must be a non-empty string")
        elif len(compatibility) > 500:
            errors.append(f"{rel}: 'compatibility' exceeds 500 characters")

    custom = metadata.get("metadata")
    if custom is not None and yaml is not None:
        if not isinstance(custom, dict):
            errors.append(f"{rel}: 'metadata' must be a mapping")
        elif any(not isinstance(v, str) for v in custom.values()):
            errors.append(f"{rel}: 'metadata' values must be strings")

    found_host = HOST_SPECIFIC_KEYS.intersection(metadata)
    if found_host:
        errors.append(f"{rel}: host-specific frontmatter keys present: {', '.join(sorted(found_host))}")

    return errors


def validate_plugin(plugin_dir: Path) -> list[str]:
    errors = []
    rel = plugin_dir.relative_to(REPO_ROOT)
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        errors.append(f"{rel}: missing .claude-plugin/plugin.json")
        return errors

    try:
        manifest = json.loads(read_utf8(manifest_path))
    except Exception as exc:
        return [f"{rel}/.claude-plugin/plugin.json: invalid JSON ({exc})"]

    for key in ("name", "version", "description"):
        val = manifest.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{rel}/.claude-plugin/plugin.json: missing or empty '{key}'")

    if manifest.get("name") != plugin_dir.name:
        errors.append(f"{rel}/.claude-plugin/plugin.json: name {manifest.get('name')!r} != directory {plugin_dir.name!r}")

    ver = manifest.get("version", "")
    if ver and not SEMVER_PATTERN.fullmatch(ver):
        errors.append(f"{rel}/.claude-plugin/plugin.json: invalid semver version {ver!r}")

    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        errors.append(f"{rel}: missing skills/ directory")
        return errors

    skill_folders = [p for p in sorted(skills_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    if not skill_folders:
        errors.append(f"{rel}: no skills found in skills/")
    for skill_folder in skill_folders:
        errors.extend(validate_skill(skill_folder))

    return errors


def validate_marketplace() -> list[str]:
    errors = []
    mp_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    if not mp_path.is_file():
        return ["Missing .claude-plugin/marketplace.json"]
    try:
        mp = json.loads(read_utf8(mp_path))
    except Exception as exc:
        return [f".claude-plugin/marketplace.json: invalid JSON ({exc})"]

    plugins = mp.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errors.append(".claude-plugin/marketplace.json: 'plugins' must be a non-empty list")
        return errors

    for entry in plugins:
        name = entry.get("name")
        source = entry.get("source", "")
        target = (REPO_ROOT / source).resolve()
        if not target.is_dir():
            errors.append(f".claude-plugin/marketplace.json: plugin {name!r} source {source!r} does not exist")
        elif target.name != name:
            errors.append(f".claude-plugin/marketplace.json: plugin name {name!r} does not match folder {target.name!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate openfunds plugins and Agent Skills.")
    parser.add_argument("paths", nargs="*", type=Path, help="Optional plugin or skill paths to validate.")
    args = parser.parse_args()

    errors = []
    if not args.paths:
        errors.extend(validate_marketplace())
        plugins_root = REPO_ROOT / "plugins"
        if plugins_root.is_dir():
            for plugin_dir in sorted(p for p in plugins_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
                errors.extend(validate_plugin(plugin_dir))
    else:
        for p in args.paths:
            resolved = p.resolve()
            if (resolved / "SKILL.md").is_file():
                errors.extend(validate_skill(resolved))
            elif (resolved / ".claude-plugin" / "plugin.json").is_file():
                errors.extend(validate_plugin(resolved))
            else:
                errors.append(f"{p}: not a recognised plugin or skill directory")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        print(f"\nValidation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print("All marketplace, plugin and portable Agent Skill checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
