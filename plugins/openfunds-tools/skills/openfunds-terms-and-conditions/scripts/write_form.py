#!/usr/bin/env python3
"""Validate an extraction and write draft transmission, grouped and review views."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from oftc_common import clean_space, read_json
from validate_extraction import load_schema, validate_data

FILL_ROW1 = PatternFill("solid", fgColor="1B365D")
FONT_ROW1 = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

FILL_ROW2 = PatternFill("solid", fgColor="2E5B88")
FONT_ROW2 = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

FILL_ROW3 = PatternFill("solid", fgColor="E8EEF5")
FONT_ROW3 = Font(name="Calibri", size=9, italic=True, color="333333")

FILL_ROW4 = PatternFill("solid", fgColor="F4F7FA")
FONT_ROW4 = Font(name="Calibri", size=8, color="555555")

FONT_DATA = Font(name="Calibri", size=10, color="000000")

NAVY = PatternFill("solid", fgColor="1B365D")
AMBER = PatternFill("solid", fgColor="FFF2CC")
WHITE_BOLD = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
TOP = Alignment(vertical="center", wrap_text=True)
THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t=", "\r=")


def sanitize_excel_value(value: object) -> object:
    """Prevent spreadsheet formula injection on string cells starting with formula triggers."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def grouping_key(source_sha256: str, group_sources: list[str]) -> str:
    """Generate a deterministic UUIDv5 grouping key from the source hash and candidate IDs."""
    seed = f"{source_sha256}:{':'.join(sorted(group_sources))}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "openfunds-oftc:" + seed))


def full_description(rule: dict) -> str:
    """Assemble OFTC005050 verbatim description from deduplicated evidence quotes."""
    seen: set[str] = set()
    quotes: list[str] = []
    for evidence in rule.get("evidence") or []:
        quote = clean_space(evidence.get("quote"))
        if quote and quote not in seen:
            seen.add(quote)
            quotes.append(quote)
    return "\n\n".join(quotes)


def transmission_rows(data: dict) -> list[dict]:
    """Expand rule rows across applicable share classes into transmission rows."""
    classes = {c["class_id"]: c for c in data["share_classes"]}
    rows: list[dict] = []
    for rule in data["rules"]:
        gk = (
            rule.get("grouping_key")
            or rule.get("fields", {}).get("OFTC005005")
            or grouping_key(data["metadata"]["source_sha256"], rule["group_sources"])
        )
        base = {
            "OFST010020": data["metadata"]["fund_name"],
            "OFTC005005": gk,
            **rule["fields"],
            "OFTC005050": full_description(rule),
        }
        for class_id in rule["applies_to"]:
            share_class = classes[class_id]
            rows.append({
                **base,
                "OFST020050": share_class["extension"],
                "OFST020000": share_class.get("isin") or "",
                "_rule_id": rule["rule_id"],
                "_class_id": class_id,
            })
    return rows


def style_header(cell, fill=NAVY) -> None:
    cell.font = WHITE_BOLD
    cell.fill = fill
    cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell.border = BORDER


def write_transmission(ws, schema: dict, rows: list[dict], list_ws) -> None:
    ws.views.sheetView[0].showGridLines = True
    fields = schema["fields"]
    list_col = 0

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 32
    ws.row_dimensions[3].height = 18
    ws.row_dimensions[4].height = 42

    for col, spec in enumerate(fields, 1):
        c1 = ws.cell(1, col, spec["ofid"])
        c1.font = FONT_ROW1
        c1.fill = FILL_ROW1
        c1.alignment = Alignment(horizontal="center", vertical="center")
        c1.border = BORDER

        c2 = ws.cell(2, col, spec["name"])
        c2.font = FONT_ROW2
        c2.fill = FILL_ROW2
        c2.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c2.border = BORDER

        c3 = ws.cell(3, col, spec["data_type"])
        c3.font = FONT_ROW3
        c3.fill = FILL_ROW3
        c3.alignment = Alignment(horizontal="center", vertical="center")
        c3.border = BORDER

        c4 = ws.cell(4, col, spec.get("values_text") or "")
        c4.font = FONT_ROW4
        c4.fill = FILL_ROW4
        c4.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        c4.border = BORDER

        name_len = len(str(spec["name"]))
        width = max(15, min(35, name_len + 4))
        if spec["ofid"] in ("OFST010020", "OFTC005050"):
            width = 40
        elif spec["ofid"] in ("OFTC005040", "OFTC005340", "OFTC005440", "OFTC005450"):
            width = 30
        ws.column_dimensions[get_column_letter(col)].width = width

        allowed = spec.get("allowed_values") or []
        if allowed:
            list_col += 1
            list_letter = get_column_letter(list_col)
            list_ws.cell(1, list_col, spec["ofid"])
            for item_row, item in enumerate(allowed, 2):
                list_ws.cell(item_row, list_col, item)
            formula = f"'_Validation_lists'!${list_letter}$2:${list_letter}${len(allowed) + 1}"
            dv = DataValidation(type="list", formula1=formula, allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{get_column_letter(col)}5:{get_column_letter(col)}1048576")

    for row_no, row in enumerate(rows, 5):
        ws.row_dimensions[row_no].height = 28
        for col, spec in enumerate(fields, 1):
            value = row.get(spec["ofid"])
            cell_val = None if value in (None, "") else sanitize_excel_value(value)
            cell = ws.cell(row_no, col, cell_val)
            cell.font = FONT_DATA
            cell.border = BORDER
            if spec["ofid"] == "OFTC005300" and value is not None:
                cell.number_format = "0.00%"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif spec["data_type"] in ("integer", "double", "number") and value is not None:
                if spec["ofid"] == "OFTC005320":
                    cell.number_format = "#,##0.00"
                else:
                    cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif spec["data_type"] == "date" and value is not None:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(fields))}{max(5, len(rows) + 4)}"


def write_grouped(ws, schema: dict, data: dict, rows: list[dict]) -> None:
    fields = schema["fields"]
    by_rule: dict[str, list[dict]] = {}
    for row in rows:
        by_rule.setdefault(row["_rule_id"], []).append(row)
    headers = (
        ["Rule row ID"]
        + [f["ofid"] for f in fields if f["ofid"] not in ("OFST020050", "OFST020000")]
        + ["# classes", "Applies to share classes", "Applies to ISINs"]
    )
    for col, value in enumerate(headers, 1):
        style_header(ws.cell(1, col, value))
        ws.column_dimensions[get_column_letter(col)].width = (
            45 if value in {"OFTC005040", "OFTC005050", "OFTC005310", "Applies to share classes"} else 18
        )
    for row_no, rule in enumerate(data["rules"], 2):
        expanded = by_rule.get(rule["rule_id"], [])
        if not expanded:
            continue
        representative = expanded[0]
        values = [rule["rule_id"]]
        values += [representative.get(f["ofid"]) for f in fields if f["ofid"] not in ("OFST020050", "OFST020000")]
        values += [
            len(expanded),
            ", ".join(r["OFST020050"] for r in expanded),
            ", ".join(filter(None, (r["OFST020000"] for r in expanded))),
        ]
        for col, value in enumerate(values, 1):
            cell_val = None if value in (None, "") else sanitize_excel_value(value)
            cell = ws.cell(row_no, col, cell_val)
            cell.alignment = TOP
            cell.border = BORDER
    ws.freeze_panes = "A2"


def write_evidence(ws, data: dict) -> None:
    headers = ["Rule row ID", "Candidate ID", "Location", "Verbatim quote", "Supports OFIDs"]
    for col, value in enumerate(headers, 1):
        style_header(ws.cell(1, col, value))
    row_no = 2
    for rule in data["rules"]:
        for evidence in rule.get("evidence") or []:
            values = [
                rule["rule_id"],
                evidence.get("candidate_id"),
                f"{evidence.get('location_type')} {evidence.get('location')}",
                clean_space(evidence.get("quote")),
                ", ".join(evidence.get("supports") or []),
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row_no, col, sanitize_excel_value(value))
                cell.alignment = TOP
                cell.border = BORDER
            row_no += 1
    for col, width in enumerate((20, 20, 16, 100, 60), 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"


def write_candidates(ws, data: dict) -> None:
    headers = [
        "Candidate ID",
        "Location",
        "Category hints",
        "Disposition",
        "Rule IDs",
        "Reason",
        "Discovery snippet",
    ]
    for col, value in enumerate(headers, 1):
        style_header(ws.cell(1, col, value))
    for row_no, candidate in enumerate(data["candidates"], 2):
        values = [
            candidate.get("candidate_id"),
            f"{candidate.get('location_type')} {candidate.get('location')}",
            ", ".join(candidate.get("category_hints") or []),
            candidate.get("disposition"),
            ", ".join(candidate.get("rule_ids") or []),
            candidate.get("reason"),
            candidate.get("snippet"),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row_no, col, sanitize_excel_value(value))
            cell.alignment = TOP
            cell.border = BORDER
            if candidate.get("disposition") in ("unresolved", "insufficient_evidence"):
                cell.fill = AMBER
    for col, width in enumerate((20, 16, 35, 20, 25, 60, 100), 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"


def write_questions(ws, data: dict) -> None:
    headers = ["Scope", "ID", "Question"]
    for col, value in enumerate(headers, 1):
        style_header(ws.cell(1, col, value))
    entries: list[tuple[str, str, str]] = []
    for question in data.get("open_questions") or []:
        entries.append(("fund", data["metadata"]["fund_name"], question))
    for share_class in data.get("share_classes") or []:
        for question in share_class.get("open_questions") or []:
            entries.append(("share class", share_class["class_id"], question))
    for rule in data.get("rules") or []:
        for question in rule.get("open_questions") or []:
            entries.append(("rule", rule["rule_id"], question))
    if not entries:
        entries.append(("none", "", "No open questions."))
    for row_no, values in enumerate(entries, 2):
        for col, value in enumerate(values, 1):
            cell = ws.cell(row_no, col, sanitize_excel_value(value))
            cell.alignment = TOP
            cell.border = BORDER
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 100


def write_metadata(ws, data: dict, schema: dict, errors: list[str], warnings: list[str]) -> None:
    values = [
        ("Output status", "DRAFT FOR FUND REVIEW"),
        ("Fund", data["metadata"]["fund_name"]),
        ("Source file", data["metadata"]["source_file"]),
        ("Source SHA-256", data["metadata"]["source_sha256"]),
        ("Document scope", data["metadata"].get("document_scope")),
        ("Scope evidence", data["metadata"].get("scope_evidence")),
        ("Skill version", data["metadata"].get("skill_version", "2.0.1")),
        ("Schema version", schema["schema_version"]),
        ("Schema source", schema["source_file"]),
        ("Schema SHA-256", schema["source_sha256"]),
        ("Validation errors", len(errors)),
        ("Validation warnings", len(warnings)),
        (
            "Important",
            "This workbook accelerates compilation. It does not certify the fund's terms and requires review by the manager or administrator.",
        ),
    ]
    for row, (key, value) in enumerate(values, 1):
        ws.cell(row, 1, key).font = Font(bold=True)
        ws.cell(row, 2, sanitize_excel_value(value))
        ws.cell(row, 1).border = ws.cell(row, 2).border = BORDER
        ws.cell(row, 1).alignment = ws.cell(row, 2).alignment = TOP
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110


def write_review_markdown(
    path: str | Path,
    data: dict,
    schema: dict,
    rows: list[dict],
    warnings: list[str],
) -> None:
    unresolved = [
        c for c in data["candidates"] if c["disposition"] in {"unresolved", "insufficient_evidence"}
    ]
    lines = [
        f"# Draft review: {data['metadata']['fund_name']}",
        "",
        "**Status:** DRAFT FOR FUND REVIEW  ",
        f"**Source:** {data['metadata']['source_file']}  ",
        f"**Source SHA-256:** `{data['metadata']['source_sha256']}`  ",
        f"**Skill/schema:** {data['metadata'].get('skill_version', '2.0.1')} / openfunds {schema['schema_version']}  ",
        f"**Rule rows:** {len(data['rules'])}; **transmission rows:** {len(rows)}; **candidates:** {len(data['candidates'])}",
        "",
        "This draft accelerates compilation. It does not certify the fund's terms and requires review by the manager or administrator.",
        "",
        "## Open questions",
        "",
    ]
    questions = list(data.get("open_questions") or [])
    for share_class in data.get("share_classes") or []:
        questions += [f"{share_class['extension']}: {q}" for q in share_class.get("open_questions") or []]
    for rule in data.get("rules") or []:
        questions += [f"{rule['rule_id']}: {q}" for q in rule.get("open_questions") or []]
    lines += [f"- {q}" for q in questions] if questions else ["None."]
    lines += ["", "## Unresolved or insufficient-evidence candidates", ""]
    lines += (
        [f"- {c['candidate_id']} ({c['location_type']} {c['location']}): {c.get('reason')}" for c in unresolved]
        if unresolved
        else ["None."]
    )
    if warnings:
        lines += ["", "## Validation warnings", ""] + [f"- {w}" for w in warnings]
    lines += ["", "## Rules and evidence", ""]
    for rule in data["rules"]:
        lines += [
            f"### {rule['rule_id']}: {rule['fields'].get('OFTC005040')}",
            "",
            f"- Term: {rule['fields'].get('OFTC005020')}",
            f"- Applies to: {', '.join(rule['applies_to'])}",
            f"- Grouping key: {grouping_key(data['metadata']['source_sha256'], rule['group_sources'])}",
        ]
        for evidence in rule.get("evidence") or []:
            lines.append(
                f"- {evidence['location_type']} {evidence['location']}: \"{clean_space(evidence['quote'])}\""
            )
        for note in rule.get("notes") or []:
            lines.append(f"- Note: {note}")
        lines.append("")
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate an extraction and write draft OFTC outputs.")
    ap.add_argument("extraction", help="Path to extraction.json")
    ap.add_argument("--schema", required=True, help="Path to field-schema.json")
    ap.add_argument("--staged", required=True, help="Path to staged.md")
    ap.add_argument("--manifest", required=True, help="Path to source-manifest.json")
    ap.add_argument("--out-form", required=True, help="Path to write Excel workbook")
    ap.add_argument("--out-review", required=True, help="Path to write Markdown review")
    args = ap.parse_args()

    try:
        data = read_json(args.extraction)
        schema, field_map = load_schema(args.schema)
        staged = Path(args.staged).read_text(encoding="utf-8")
        manifest = read_json(args.manifest)
    except Exception as exc:
        sys.exit(f"error: {exc}")

    errors, warnings = validate_data(data, schema, field_map, staged, manifest)
    if errors:
        print(json.dumps({"written": False, "errors": errors, "warnings": warnings}, indent=2), file=sys.stderr)
        sys.exit(1)

    rows = transmission_rows(data)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_metadata(wb.create_sheet("Run_metadata"), data, schema, errors, warnings)
    list_ws = wb.create_sheet("_Validation_lists")
    write_transmission(wb.create_sheet("Transmission_view"), schema, rows, list_ws)
    write_grouped(wb.create_sheet("Grouped_view"), schema, data, rows)
    write_evidence(wb.create_sheet("Evidence"), data)
    write_candidates(wb.create_sheet("Candidate_ledger"), data)
    write_questions(wb.create_sheet("Open_questions"), data)
    list_ws.sheet_state = "hidden"

    out_form = Path(args.out_form)
    out_form.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_form)
    write_review_markdown(args.out_review, data, schema, rows, warnings)
    print(json.dumps({
        "written": True,
        "form": str(out_form),
        "review": args.out_review,
        "rule_rows": len(data["rules"]),
        "transmission_rows": len(rows),
        "warnings": len(warnings),
    }))


if __name__ == "__main__":
    main()
