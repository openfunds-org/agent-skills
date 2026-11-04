#!/usr/bin/env python3
"""Shared utilities for the openfunds Terms and Conditions (OFTC) pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

STAGE_MARKER_RE = re.compile(r"^## (Page|Section) (\d+)\s*$", re.MULTILINE)


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_space(value: object) -> str:
    """Collapse consecutive whitespace into single spaces and strip ends."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def iter_staged_blocks(text: str) -> Iterator[tuple[str, int, str]]:
    """Yield (location_type, location_number, raw_block_text) from a staged Markdown document."""
    matches = list(STAGE_MARKER_RE.finditer(text))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        yield match.group(1).lower(), int(match.group(2)), text[start:end].strip()


def parse_staged_map(text: str) -> dict[tuple[str, int], str]:
    """Return a dict mapping (location_type, location_number) to whitespace-normalised block text."""
    return {
        (loc_type, number): clean_space(block)
        for loc_type, number, block in iter_staged_blocks(text)
    }


def read_json(path: str | Path) -> dict:
    """Read and parse a UTF-8 JSON file, raising ValueError with a clear message on failure."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"JSON file not found: {file_path}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {file_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level JSON object in {file_path}")
    return data


def write_json(path: str | Path, payload: object) -> None:
    """Write a JSON payload with UTF-8 encoding and trailing newline."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
