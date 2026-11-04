#!/usr/bin/env python3
"""Build the runtime OFTC schema from the official openfunds field workbook."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from oftc_common import sha256_file, write_json

LINKAGE_FIELDS = ("OFST010020", "OFST020050", "OFST020000")


def clean_excel_text(value: object) -> str | None:
    """Clean Excel XML carriage-return escapes while preserving text."""
    if value is None:
        return None
    return str(value).replace("_x000D_\n", "\n").replace("_x000D_", "\n")


def controlled_values(raw: object) -> list[str]:
    """Extract quoted controlled values from an openfunds Values specification."""
    if not raw or "/" not in str(raw):
        return []
    return re.findall(r'["“”]([^"“”]+)["“”]', str(raw))


def build(source: str | Path, existing_generated_on: str | None = None) -> dict:
    """Parse an openfunds field list workbook into the runtime JSON schema."""
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Workbook not found: {source_path}")

    wb = load_workbook(source_path, read_only=True, data_only=True)
    fields: list[dict] = []

    if "FieldSet" in wb.sheetnames:
        ws = wb["FieldSet"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            ofid = row[1]
            if not (ofid in LINKAGE_FIELDS or (isinstance(ofid, str) and ofid.startswith("OFTC"))):
                continue
            fields.append({
                "group": row[0],
                "ofid": ofid,
                "name": row[2],
                "data_type": row[3],
                "description": clean_excel_text(row[4]),
                "values_text": clean_excel_text(row[5]),
                "allowed_values": controlled_values(row[5]),
                "level": row[6],
                "example": str(row[7]) if row[7] is not None else None,
                "link_reference": row[8],
                "introduced": str(row[9]) if row[9] is not None else None,
                "valid_until": str(row[10]) if row[10] is not None else None,
            })
        source_status = "FINALIZED_V2"
        source_date = "2026-08-07"
    else:
        ws = wb[wb.sheetnames[0]]
        raw_fields: dict[str, dict] = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            ofid = row[0]
            if not (ofid in LINKAGE_FIELDS or (isinstance(ofid, str) and ofid.startswith("OFTC"))):
                continue
            raw_fields[ofid] = {
                "group": "Linkage" if ofid in LINKAGE_FIELDS else "Terms Configuration",
                "ofid": ofid,
                "name": row[1],
                "data_type": row[2],
                "description": clean_excel_text(row[3]),
                "values_text": clean_excel_text(row[4]),
                "allowed_values": controlled_values(row[4]),
                "level": row[5],
                "tags": row[6],
                "example": str(row[7]) if row[7] is not None else None,
                "link_reference": row[8],
                "introduced": str(row[9]) if row[9] is not None else None,
                "valid_until": str(row[10]) if row[10] is not None else None,
            }
        for ofid in LINKAGE_FIELDS:
            if ofid in raw_fields:
                fields.append(raw_fields.pop(ofid))
        for ofid in sorted(raw_fields):
            fields.append(raw_fields[ofid])
        source_status = "DRAFT_CONSULTATION"
        source_date = "2026-09-17"

    return {
        "schema_name": "openfunds-oftc",
        "schema_version": "2.14.0",
        "source_file": source_path.name,
        "source_sha256": sha256_file(source_path),
        "source_status": source_status,
        "source_date": source_date,
        "generated_on": existing_generated_on or date.today().isoformat(),
        "controlled_value_policy": "Values column is authoritative; values are case-sensitive.",
        "fields": fields,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build or check the openfunds OFTC field schema.")
    ap.add_argument("source", nargs="?", default="assets/openfunds_Fieldlist_v2.14.0_DRAFT.xlsx")
    ap.add_argument("--output", default="reference/field-schema.json")
    ap.add_argument("--check", action="store_true", help="Verify output matches existing schema file.")
    args = ap.parse_args()

    out_path = Path(args.output)
    existing_date = None
    if out_path.is_file():
        try:
            existing_date = json.loads(out_path.read_text(encoding="utf-8")).get("generated_on")
        except Exception:
            existing_date = None

    try:
        schema = build(args.source, existing_generated_on=existing_date)
    except Exception as exc:
        sys.exit(f"error: {exc}")

    rendered = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not out_path.is_file():
            sys.exit(f"Schema file not found: {out_path}")
        if out_path.read_text(encoding="utf-8") != rendered:
            sys.exit(f"Schema mismatch: {out_path} does not match {args.source}")
        print(json.dumps({
            "check": "passed",
            "fields": len(schema["fields"]),
            "source_sha256": schema["source_sha256"],
        }))
        return

    write_json(out_path, schema)
    print(json.dumps({
        "output": str(out_path),
        "fields": len(schema["fields"]),
        "source_sha256": schema["source_sha256"],
    }))


if __name__ == "__main__":
    main()
