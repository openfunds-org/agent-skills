#!/usr/bin/env python3
"""Validate an evidence-backed OFTC extraction before workbook creation."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

from oftc_common import clean_space, parse_staged_map, read_json, write_json

DISPOSITIONS = {"mapped", "duplicate", "out_of_scope", "insufficient_evidence", "unresolved"}
REQUIRED_RULE_FIELDS = {"OFTC005010", "OFTC005020", "OFTC005040", "OFTC005110", "OFTC005250"}
MODEL_FORBIDDEN_FIELDS = {"OFST010020", "OFST020050", "OFST020000", "OFTC005005", "OFTC005050"}
PERCENTAGE_FORBIDDEN_TERMS = {
    "Extension of notice periods",
    "Redemption in kind",
    "Side pockets",
    "Suspension of subscriptions, repurchases and redemptions",
    "Payout delay",
    "Minimum retention",
}


def parse_staged(text: str) -> dict[tuple[str, int], str]:
    """Backwards-compatible wrapper around parse_staged_map."""
    return parse_staged_map(text)


def load_schema(path: str | Path) -> tuple[dict, dict[str, dict]]:
    """Load the runtime field schema and return (schema, {ofid: field_spec})."""
    schema = read_json(path)
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise ValueError(f"Schema {path} has no 'fields' list.")
    return schema, {field["ofid"]: field for field in fields}


def is_valid_iso_date(value: str) -> bool:
    """Return True if value is a valid YYYY-MM-DD calendar date."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_type(ofid: str, value: object, spec: dict, errors: list[str], label: str) -> None:
    """Validate that a field value matches its schema data_type."""
    kind = str(spec.get("data_type") or "").lower()
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{label}: {ofid} must be an integer, got {value!r}.")
    elif kind in {"double", "number"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{label}: {ofid} must be a finite number, got {value!r}.")
    elif kind == "string":
        if not isinstance(value, str):
            errors.append(f"{label}: {ofid} must be text, got {value!r}.")
    elif kind == "date":
        if not isinstance(value, str) or not is_valid_iso_date(value):
            errors.append(f"{label}: {ofid} must be a valid YYYY-MM-DD calendar date, got {value!r}.")
    elif kind == "boolean":
        if value not in ("yes", "no"):
            errors.append(f"{label}: {ofid} must be 'yes' or 'no', got {value!r}.")


def populated(fields: dict, ofid: str) -> bool:
    """Return True if a field is present and non-empty."""
    return fields.get(ofid) not in (None, "")


def validate_field_logic(
    fields: dict,
    errors: list[str],
    warnings: list[str],
    label: str,
) -> None:
    """Enforce openfunds OFTC cross-field dependencies and domain constraints."""
    for field in sorted(REQUIRED_RULE_FIELDS):
        if not populated(fields, field):
            errors.append(f"{label}: required field {field} is blank.")

    term_type = fields.get("OFTC005020")

    if populated(fields, "OFTC005300"):
        value = fields["OFTC005300"]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not 0 <= value <= 1:
                errors.append(f"{label}: OFTC005300 must be a decimal fraction between 0 and 1.")
        if not populated(fields, "OFTC005310"):
            errors.append(f"{label}: OFTC005310 is required when OFTC005300 is populated.")
        if term_type in PERCENTAGE_FORBIDDEN_TERMS:
            errors.append(f"{label}: OFTC005300 must be left blank when OFTC005020 is {term_type!r}.")

    characteristic = fields.get("OFTC005110")
    if characteristic == "Recurring Frequency":
        if not populated(fields, "OFTC005120"):
            errors.append(f"{label}: recurring terms require OFTC005120.")
        if any(populated(fields, f) for f in ("OFTC005140", "OFTC005150", "OFTC005160", "OFTC005180",
                                              "OFTC005210", "OFTC005220", "OFTC005230")):
            errors.append(f"{label}: recurring terms must not use specified-period offsets or reference dates.")
    elif characteristic == "Specified Period":
        if populated(fields, "OFTC005120"):
            errors.append(f"{label}: specified-period terms must not populate OFTC005120.")
        if not populated(fields, "OFTC005140"):
            errors.append(f"{label}: specified-period terms require OFTC005140.")
        if not populated(fields, "OFTC005160"):
            errors.append(f"{label}: specified-period terms require OFTC005160.")
        start_offset = fields.get("OFTC005140")
        end_offset = fields.get("OFTC005150")
        if isinstance(start_offset, int) and not isinstance(start_offset, bool) and start_offset < 0:
            errors.append(f"{label}: OFTC005140 start day offset cannot be negative ({start_offset}).")
        if isinstance(end_offset, int) and not isinstance(end_offset, bool):
            if end_offset < 0:
                errors.append(f"{label}: OFTC005150 end day offset cannot be negative ({end_offset}).")
            elif isinstance(start_offset, int) and not isinstance(start_offset, bool) and end_offset < start_offset:
                errors.append(f"{label}: OFTC005150 ({end_offset}) cannot be less than OFTC005140 ({start_offset}).")
        if fields.get("OFTC005180") == "yes" and populated(fields, "OFTC005150"):
            errors.append(f"{label}: OFTC005150 must be blank when OFTC005180 is 'yes'.")
        if fields.get("OFTC005180") != "yes" and not populated(fields, "OFTC005150"):
            warnings.append(f"{label}: specified period has no end offset and is not marked in perpetuity.")
        refs = [populated(fields, "OFTC005210"), populated(fields, "OFTC005220")]
        if sum(refs) != 1:
            errors.append(f"{label}: specified periods require exactly one of OFTC005210 or OFTC005220.")
        if populated(fields, "OFTC005210"):
            ref_ofid = fields.get("OFTC005210")
            if isinstance(ref_ofid, str) and not re.fullmatch(r"OF[A-Z]{2}\d{6}", ref_ofid):
                errors.append(f"{label}: OFTC005210 must be a valid openfunds OFID (e.g. OFST020560), got {ref_ofid!r}.")
            if populated(fields, "OFTC005230"):
                errors.append(f"{label}: OFTC005230 must be blank when OFTC005210 is populated.")
    elif characteristic == "Perpetual":
        if any(populated(fields, f) for f in ("OFTC005120", "OFTC005140", "OFTC005150", "OFTC005160", "OFTC005180",
                                              "OFTC005210", "OFTC005220", "OFTC005230")):
            errors.append(f"{label}: perpetual terms must not use frequency or specified-period fields.")

    if populated(fields, "OFTC005320"):
        amt = fields["OFTC005320"]
        if isinstance(amt, (int, float)) and not isinstance(amt, bool) and amt <= 0:
            errors.append(f"{label}: OFTC005320 monetary amount must be positive, got {amt!r}.")
        if not populated(fields, "OFTC005330"):
            errors.append(f"{label}: OFTC005330 currency is required when OFTC005320 is populated.")
    if populated(fields, "OFTC005330"):
        ccy = fields["OFTC005330"]
        if isinstance(ccy, str) and not re.fullmatch(r"[A-Z]{3}", ccy):
            errors.append(f"{label}: OFTC005330 must be a 3-letter uppercase ISO 4217 currency code, got {ccy!r}.")
        if not populated(fields, "OFTC005320"):
            errors.append(f"{label}: OFTC005330 cannot be populated without OFTC005320.")

    large_fields = ("OFTC005440", "OFTC005450", "OFTC005470", "OFTC005480")
    if any(populated(fields, f) for f in large_fields) and term_type != "Large redemption":
        errors.append(f"{label}: large-redemption fields require OFTC005020 = 'Large redemption'.")
    if term_type == "Large redemption" and not populated(fields, "OFTC005440"):
        errors.append(f"{label}: a Large redemption row requires OFTC005440.")
    if populated(fields, "OFTC005470"):
        delay = fields["OFTC005470"]
        if isinstance(delay, int) and not isinstance(delay, bool) and delay <= 0:
            errors.append(f"{label}: OFTC005470 delay in days must be a positive integer, got {delay!r}.")
        if not populated(fields, "OFTC005480"):
            errors.append(f"{label}: OFTC005480 is required when OFTC005470 is populated.")
    if populated(fields, "OFTC005480") and not populated(fields, "OFTC005470"):
        errors.append(f"{label}: OFTC005480 cannot be populated without OFTC005470.")

    if populated(fields, "OFTC005410") != populated(fields, "OFTC005420"):
        errors.append(f"{label}: OFTC005410 and OFTC005420 must be populated together.")
    if populated(fields, "OFTC005410"):
        floor = fields["OFTC005410"]
        if isinstance(floor, int) and not isinstance(floor, bool) and floor <= 0:
            errors.append(f"{label}: OFTC005410 minimum retention floor must be positive, got {floor!r}.")
    if term_type == "Minimum retention" and not populated(fields, "OFTC005410"):
        errors.append(f"{label}: a Minimum retention row requires OFTC005410 and OFTC005420.")

    if populated(fields, "OFTC008020") and not populated(fields, "OFTC008010"):
        errors.append(f"{label}: OFTC008020 (Term Valid To) requires OFTC008010 (Term Valid From) to be populated.")
    if populated(fields, "OFTC008010") and populated(fields, "OFTC008020"):
        v_from = fields["OFTC008010"]
        v_to = fields["OFTC008020"]
        if isinstance(v_from, str) and isinstance(v_to, str) and is_valid_iso_date(v_from) and is_valid_iso_date(v_to):
            if v_to < v_from:
                errors.append(f"{label}: OFTC008020 ({v_to}) cannot be earlier than OFTC008010 ({v_from}).")

    if term_type == "other" and not clean_space(fields.get("OFTC005040")):
        errors.append(f"{label}: 'other' requires a clear OFTC005040 description.")


def validate_data(
    data: dict,
    schema: dict,
    field_map: dict[str, dict],
    staged_text: str | None = None,
    manifest: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the full extraction payload against schema, staged text and manifest."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["Extraction payload must be a JSON object."], warnings

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be a JSON object.")
        metadata = {}

    for key in ("fund_name", "source_file", "source_sha256"):
        if not clean_space(metadata.get(key)):
            errors.append(f"metadata.{key} is required.")
    if clean_space(metadata.get("source_sha256")) and not re.fullmatch(r"[0-9a-f]{64}", str(metadata["source_sha256"])):
        errors.append("metadata.source_sha256 must be a lower-case 64-character SHA-256 hash.")
    if manifest:
        if metadata.get("source_file") != manifest.get("source_file"):
            errors.append("metadata.source_file does not match the source manifest.")
        if metadata.get("source_sha256") != manifest.get("source_sha256"):
            errors.append("metadata.source_sha256 does not match the source manifest.")
        if manifest.get("unreadable_locations"):
            warnings.append(
                f"Source manifest reports unreadable locations: {manifest['unreadable_locations']}. "
                "Confirm they were visually inspected."
            )
    if metadata.get("schema_version") not in (None, schema["schema_version"]):
        errors.append(f"metadata.schema_version must be {schema['schema_version']}.")
    if metadata.get("document_scope") != "binding":
        errors.append("metadata.document_scope must be 'binding' before a workbook can be written.")
    if not clean_space(metadata.get("scope_evidence")):
        errors.append("metadata.scope_evidence is required and must explain why the source is operative.")

    classes = data.get("share_classes")
    if not isinstance(classes, list) or not classes:
        errors.append("At least one share class is required.")
        classes = []
    class_ids: set[str] = set()
    for idx, share_class in enumerate(classes, 1):
        label = f"share_classes[{idx}]"
        if not isinstance(share_class, dict):
            errors.append(f"{label}: must be a JSON object.")
            continue
        class_id = clean_space(share_class.get("class_id"))
        extension = clean_space(share_class.get("extension"))
        if not class_id or class_id in class_ids:
            errors.append(f"{label}: class_id is required and must be unique.")
        class_ids.add(class_id)
        if not extension:
            errors.append(f"{label}: extension is required.")
        isin = clean_space(share_class.get("isin"))
        if isin and not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
            errors.append(f"{label}: invalid ISIN shape {isin!r}.")

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("Candidate ledger is empty. Run discovery before mapping.")
        candidates = []
    candidate_map: dict[str, dict] = {}
    for idx, candidate in enumerate(candidates, 1):
        label = f"candidates[{idx}]"
        if not isinstance(candidate, dict):
            errors.append(f"{label}: must be a JSON object.")
            continue
        cid = clean_space(candidate.get("candidate_id"))
        if not cid or cid in candidate_map:
            errors.append(f"{label}: candidate_id is required and must be unique.")
        candidate_map[cid] = candidate
        disposition = candidate.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{label}: disposition must be one of {sorted(DISPOSITIONS)}.")
        if disposition != "mapped" and candidate.get("rule_ids"):
            errors.append(f"{label}: only mapped candidates may list rule_ids.")
        if disposition != "mapped" and not clean_space(candidate.get("reason")):
            errors.append(f"{label}: non-mapped candidates require a reason.")

    rules = data.get("rules")
    if not isinstance(rules, list):
        errors.append("rules must be a JSON list.")
        rules = []
    rule_ids: set[str] = set()
    blocks = parse_staged_map(staged_text) if staged_text else None
    for idx, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            errors.append(f"rules[{idx}]: must be a JSON object.")
            continue
        rid = clean_space(rule.get("rule_id"))
        label = f"rule {rid or idx}"
        if not rid or rid in rule_ids:
            errors.append(f"rules[{idx}]: rule_id is required and must be unique.")
        rule_ids.add(rid)

        applies = rule.get("applies_to")
        if not isinstance(applies, list) or not applies:
            errors.append(f"{label}: applies_to must name at least one class_id.")
            applies = []
        if len(applies) != len(set(applies)):
            errors.append(f"{label}: applies_to contains duplicate class_ids.")
        for class_id in applies:
            if class_id not in class_ids:
                errors.append(f"{label}: unknown class_id {class_id!r}.")

        group_sources = rule.get("group_sources")
        if not isinstance(group_sources, list) or not group_sources:
            errors.append(f"{label}: group_sources must list the candidate IDs forming the rule package.")
            group_sources = []
        for cid in group_sources:
            if cid not in candidate_map:
                errors.append(f"{label}: unknown candidate {cid!r} in group_sources.")
            elif candidate_map[cid].get("disposition") != "mapped":
                errors.append(f"{label}: candidate {cid!r} is not marked mapped.")

        fields = rule.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"{label}: fields must be a JSON object.")
            fields = {}
        for ofid, value in fields.items():
            if ofid in MODEL_FORBIDDEN_FIELDS:
                errors.append(f"{label}: {ofid} is generated by the writer and must not be supplied.")
                continue
            if ofid not in field_map:
                errors.append(f"{label}: unknown field {ofid}.")
                continue
            if value in (None, ""):
                continue
            spec = field_map[ofid]
            validate_type(ofid, value, spec, errors, label)
            allowed = spec.get("allowed_values") or []
            if allowed and value not in allowed:
                errors.append(f"{label}: {ofid} value {value!r} is not one of {allowed!r}.")
        validate_field_logic(fields, errors, warnings, label)

        evidence = rule.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label}: at least one evidence record is required.")
            evidence = []
        supported: set[str] = set()
        for jdx, item in enumerate(evidence, 1):
            elabel = f"{label} evidence[{jdx}]"
            if not isinstance(item, dict):
                errors.append(f"{elabel}: must be a JSON object.")
                continue
            cid = item.get("candidate_id")
            if cid not in group_sources:
                errors.append(f"{elabel}: candidate_id must appear in group_sources.")
            quote = clean_space(item.get("quote"))
            if not quote:
                errors.append(f"{elabel}: quote is required.")
            supports_raw = item.get("supports")
            if supports_raw is not None and not isinstance(supports_raw, list):
                errors.append(f"{elabel}: supports must be a list of OFIDs.")
                supports_raw = []
            supports = set(supports_raw or [])
            supported.update(supports)
            for ofid in supports:
                if not populated(fields, ofid):
                    errors.append(f"{elabel}: supports {ofid}, but the field is not populated.")
            if blocks is not None:
                key = (str(item.get("location_type", "")).lower(), item.get("location"))
                source_block = blocks.get(key)
                if source_block is None:
                    errors.append(f"{elabel}: source location {key!r} does not exist in the staged file.")
                elif quote and quote not in source_block:
                    errors.append(f"{elabel}: verbatim quote was not found at {key[0]} {key[1]}.")

        evidence_required = {
            f for f, value in fields.items()
            if value not in (None, "") and f != "OFTC005040" and f in field_map
        }
        missing_support = evidence_required - supported
        if missing_support:
            errors.append(f"{label}: populated fields lack evidence support: {sorted(missing_support)}.")

    expected_links: dict[str, set[str]] = {cid: set() for cid in candidate_map}
    for rule in rules:
        if isinstance(rule, dict):
            for cid in rule.get("group_sources") or []:
                if cid in expected_links and rule.get("rule_id"):
                    expected_links[cid].add(rule["rule_id"])
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("disposition") == "mapped":
            cid = candidate.get("candidate_id")
            listed = set(candidate.get("rule_ids") or [])
            if not listed:
                errors.append(f"candidate {cid}: mapped candidate has no rule_ids.")
            unknown = listed - rule_ids
            if unknown:
                errors.append(f"candidate {cid}: unknown rule_ids {sorted(unknown)}.")
            expected = expected_links.get(cid, set())
            if listed != expected:
                errors.append(
                    f"candidate {cid}: rule_ids must match linked rules exactly; expected {sorted(expected)}."
                )
    return errors, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate an OFTC extraction JSON payload.")
    ap.add_argument("extraction", help="Path to extraction.json")
    ap.add_argument("--schema", required=True, help="Path to field-schema.json")
    ap.add_argument("--staged", help="Path to staged.md")
    ap.add_argument("--manifest", help="Path to source-manifest.json")
    ap.add_argument("--report", help="Optional path to write validation report JSON")
    args = ap.parse_args()

    try:
        data = read_json(args.extraction)
        schema, field_map = load_schema(args.schema)
        staged = Path(args.staged).read_text(encoding="utf-8") if args.staged else None
        manifest = read_json(args.manifest) if args.manifest else None
    except Exception as exc:
        sys.exit(f"error: {exc}")

    errors, warnings = validate_data(data, schema, field_map, staged, manifest)
    result = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "rules": len(data.get("rules") or []) if isinstance(data.get("rules"), list) else 0,
        "candidates": len(data.get("candidates") or []) if isinstance(data.get("candidates"), list) else 0,
    }
    if args.report:
        write_json(args.report, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
