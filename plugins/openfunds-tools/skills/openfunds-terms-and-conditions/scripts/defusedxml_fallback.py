#!/usr/bin/env python3
"""Safe XML parsing helper rejecting XML external entities (XXE) and DTDs."""

from __future__ import annotations

from xml.etree import ElementTree as ET


def parse_xml_bytes(raw: bytes) -> ET.Element:
    """Parse XML bytes safely, rejecting DOCTYPE/ENTITY declarations."""
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("Unsafe XML: DOCTYPE and ENTITY declarations are forbidden.")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XML: {exc}") from exc
