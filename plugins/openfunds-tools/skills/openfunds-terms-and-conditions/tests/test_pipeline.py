#!/usr/bin/env python3
"""Comprehensive unit and integration test suite for the openfunds OFTC pipeline."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import openpyxl
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from assess_scope import assess
from build_schema import build, controlled_values
from compare_extractions import compare
from defusedxml_fallback import parse_xml_bytes
from discover_candidates import candidate_id, candidates_for_block
from oftc_common import clean_space, iter_staged_blocks, parse_staged_map
from stage_document import stage_docx
from validate_extraction import is_valid_iso_date, load_schema, validate_data
from write_form import (
    full_description,
    grouping_key,
    sanitize_excel_value,
    transmission_rows,
    write_candidates,
    write_grouped,
    write_questions,
)


def build_minimal_docx(path: Path, xml_body: str) -> None:
    """Create a valid minimal DOCX file containing the provided w:body inner XML."""
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{xml_body}</w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema, cls.field_map = load_schema(ROOT / "reference" / "field-schema.json")
        cls.valid = json.loads((FIXTURES / "valid-extraction.json").read_text(encoding="utf-8"))
        cls.staged = (FIXTURES / "sample-staged.md").read_text(encoding="utf-8")
        cls.manifest = json.loads((FIXTURES / "source-manifest.json").read_text(encoding="utf-8"))

    def validate(self, data: dict, manifest: dict | None = None) -> tuple[list[str], list[str]]:
        return validate_data(
            data,
            self.schema,
            self.field_map,
            self.staged,
            self.manifest if manifest is None else manifest,
        )

    # --- Schema & Build Tests ---

    def test_schema_has_all_32_fields(self) -> None:
        self.assertEqual(32, len(self.schema["fields"]))
        ofids = [f["ofid"] for f in self.schema["fields"]]
        self.assertEqual(["OFST010020", "OFST020050", "OFST020000"], ofids[:3])
        self.assertIn("OFTC008010", ofids)
        self.assertIn("OFTC008020", ofids)

    def test_controlled_values_handles_straight_and_curly_quotes(self) -> None:
        raw = '“Share Class” / "Investor" / “other”'
        self.assertEqual(["Share Class", "Investor", "other"], controlled_values(raw))
        self.assertEqual([], controlled_values("Free text"))

    def test_build_schema_matches_draft_and_finalized_workbooks(self) -> None:
        draft_xlsx = ROOT / "assets" / "openfunds_Fieldlist_v2.14.0_DRAFT.xlsx"
        built_draft = build(draft_xlsx, existing_generated_on=self.schema["generated_on"])
        self.assertEqual(self.schema, built_draft)

        v2_xlsx = ROOT / "assets" / "openfunds_oftc_2.14.0_FINALIZED_V2.xlsx"
        built_v2 = build(v2_xlsx, existing_generated_on="2026-08-07")
        self.assertEqual(30, len(built_v2["fields"]))
        self.assertEqual("FINALIZED_V2", built_v2["source_status"])

    # --- Document Staging & Safe XML Tests ---

    def test_docx_staging_preserves_order_and_ignores_deleted_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "sample.docx"
            xml_body = (
                "<w:p>"
                "<w:r><w:t>Redemptions are subject to a </w:t></w:r>"
                "<w:del><w:r><w:t>10%</w:t></w:r></w:del>"
                "<w:ins><w:r><w:t>5%</w:t></w:r></w:ins>"
                "<w:r><w:t> quarterly gate.</w:t></w:r>"
                "</w:p>"
                "<w:tbl><w:tr>"
                "<w:tc><w:p><w:r><w:t>Class A</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>LU1135392162</w:t></w:r></w:p></w:tc>"
                "</w:tr></w:tbl>"
            )
            build_minimal_docx(docx_path, xml_body)
            blocks, unreadable, method = stage_docx(docx_path)
            self.assertEqual([], unreadable)
            self.assertEqual("docx-xml-accepted-text", method)
            self.assertEqual(2, len(blocks))
            self.assertEqual(("Section", 1, "Redemptions are subject to a 5% quarterly gate."), blocks[0])
            self.assertEqual(("Section", 2, "Class A | LU1135392162"), blocks[1])

    def test_safe_xml_rejects_doctype_and_entities(self) -> None:
        malicious = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "boom">]><foo>&xxe;</foo>'
        with self.assertRaises(ValueError):
            parse_xml_bytes(malicious)

    def test_stage_document_cli_on_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "fund.docx"
            staged_out = Path(tmp) / "staged.md"
            manifest_out = Path(tmp) / "manifest.json"
            build_minimal_docx(docx_path, "<w:p><w:r><w:t>Prospectus text.</w:t></w:r></w:p>")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "stage_document.py"),
                    str(docx_path),
                    "--output",
                    str(staged_out),
                    "--manifest",
                    str(manifest_out),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            manifest = json.loads(manifest_out.read_text(encoding="utf-8"))
            self.assertEqual("section", manifest["location_type"])
            self.assertEqual(1, manifest["locations"])

    # --- Scope Assessment Tests ---

    def test_scope_assessor_flags_subordinate_summary(self) -> None:
        staged = (
            "## Page 3\n\nThis is a summary of principal terms only and is qualified in its entirety "
            "by the Prospectus. The Prospectus shall control."
        )
        result = assess(staged)
        self.assertEqual("manual_scope_review", result["recommendation"])
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("summary_only", codes)
        self.assertIn("prospectus_controls", codes)

    def test_scope_assessor_identifies_likely_binding_prospectus(self) -> None:
        staged = "## Page 1\n\nThis Prospectus sets out the terms that shall apply to all Shareholders."
        result = assess(staged)
        self.assertEqual("likely_binding_but_verify", result["recommendation"])

    # --- Candidate Discovery Tests ---

    def test_candidate_discovery_finds_redemption_in_kind_and_merges_hits(self) -> None:
        text = (
            "The Board may permit repayment in kind from the Sub-Fund assets, subject to independent valuation.\n"
            "In addition, a quarterly redemption gate of 5% applies."
        )
        candidates = candidates_for_block("page", 93, text, 1)
        self.assertEqual(1, len(candidates))
        self.assertIn("redemption_in_kind", candidates[0]["category_hints"])
        self.assertIn("redemption_gate", candidates[0]["category_hints"])
        self.assertEqual(
            candidate_id("page", 93, candidates[0]["snippet"]),
            candidates[0]["candidate_id"],
        )

    # --- Validation Logic Tests ---

    def test_valid_fixture(self) -> None:
        errors, warnings = self.validate(copy.deepcopy(self.valid))
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_controlled_value_casing_is_strict(self) -> None:
        data = copy.deepcopy(self.valid)
        data["rules"][0]["fields"]["OFTC005120"] = "Quarterly"
        errors, _ = self.validate(data)
        self.assertTrue(any("OFTC005120" in error and "not one of" in error for error in errors))

    def test_large_redemption_fields_require_large_redemption_term(self) -> None:
        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"]["OFTC005440"] = "Requests above 5% are delayed"
        rule["evidence"][0]["supports"].append("OFTC005440")
        errors, _ = self.validate(data)
        self.assertTrue(any("large-redemption fields require" in error for error in errors))

    def test_large_redemption_delay_requires_positive_days_and_day_basis(self) -> None:
        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"] = {
            "OFTC005010": "Share Class",
            "OFTC005020": "Large redemption",
            "OFTC005040": "Delayed execution above 5%",
            "OFTC005110": "Perpetual",
            "OFTC005250": "Fund",
            "OFTC005440": "Above 5% of Fund NAV",
            "OFTC005470": 0,
        }
        rule["evidence"][0]["supports"] = [
            "OFTC005010",
            "OFTC005020",
            "OFTC005110",
            "OFTC005250",
            "OFTC005440",
            "OFTC005470",
        ]
        errors, _ = self.validate(data)
        self.assertTrue(any("OFTC005470 delay in days must be a positive integer" in e for e in errors))
        self.assertTrue(any("OFTC005480 is required when OFTC005470 is populated" in e for e in errors))

    def test_percentage_requires_basis_and_forbids_non_percentage_terms(self) -> None:
        data = copy.deepcopy(self.valid)
        del data["rules"][0]["fields"]["OFTC005310"]
        data["rules"][0]["evidence"][0]["supports"].remove("OFTC005310")
        errors, _ = self.validate(data)
        self.assertTrue(any("OFTC005310 is required" in error for error in errors))

        data2 = copy.deepcopy(self.valid)
        rule2 = data2["rules"][0]
        rule2["fields"]["OFTC005020"] = "Redemption in kind"
        errors2, _ = self.validate(data2)
        self.assertTrue(any("OFTC005300 must be left blank" in e for e in errors2))

    def test_specified_period_offset_and_reference_date_validation(self) -> None:
        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"] = {
            "OFTC005010": "Share Class",
            "OFTC005020": "Redemption fee",
            "OFTC005040": "Early redemption fee",
            "OFTC005110": "Specified Period",
            "OFTC005140": 365,
            "OFTC005150": 180,
            "OFTC005160": "calendar days",
            "OFTC005210": "INVALID_OFID",
            "OFTC005250": "Subscription Tranche",
            "OFTC005300": 0.02,
            "OFTC005310": "NAV redeemed",
        }
        rule["evidence"][0]["supports"] = [
            k for k in rule["fields"] if k != "OFTC005040"
        ]
        errors, _ = self.validate(data)
        self.assertTrue(any("cannot be less than OFTC005140" in e for e in errors))
        self.assertTrue(any("OFTC005210 must be a valid openfunds OFID" in e for e in errors))

    def test_calendar_date_and_validity_window_validation(self) -> None:
        self.assertTrue(is_valid_iso_date("2026-09-17"))
        self.assertFalse(is_valid_iso_date("2026-02-30"))
        self.assertFalse(is_valid_iso_date("17-09-2026"))

        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"]["OFTC008020"] = "2026-01-01"
        rule["evidence"][0]["supports"].append("OFTC008020")
        errors, _ = self.validate(data)
        self.assertTrue(any("OFTC008020 (Term Valid To) requires OFTC008010" in e for e in errors))

        rule["fields"]["OFTC008010"] = "2026-06-01"
        rule["evidence"][0]["supports"].append("OFTC008010")
        errors2, _ = self.validate(data)
        self.assertTrue(any("cannot be earlier than OFTC008010" in e for e in errors2))

    def test_monetary_amount_and_currency_validation(self) -> None:
        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"]["OFTC005320"] = -500
        rule["fields"]["OFTC005330"] = "euros"
        rule["evidence"][0]["supports"].extend(["OFTC005320", "OFTC005330"])
        errors, _ = self.validate(data)
        self.assertTrue(any("OFTC005320 monetary amount must be positive" in e for e in errors))
        self.assertTrue(any("OFTC005330 must be a 3-letter uppercase ISO 4217" in e for e in errors))

    def test_minimum_retention_validation(self) -> None:
        data = copy.deepcopy(self.valid)
        rule = data["rules"][0]
        rule["fields"] = {
            "OFTC005010": "Investor",
            "OFTC005020": "Minimum retention",
            "OFTC005040": "Minimum holding floor",
            "OFTC005110": "Perpetual",
            "OFTC005250": "Investor",
        }
        rule["evidence"][0]["supports"] = ["OFTC005010", "OFTC005020", "OFTC005110", "OFTC005250"]
        errors, _ = self.validate(data)
        self.assertTrue(any("Minimum retention row requires OFTC005410 and OFTC005420" in e for e in errors))

    def test_duplicate_applies_to_and_unreadable_page_warning(self) -> None:
        data = copy.deepcopy(self.valid)
        data["rules"][0]["applies_to"] = ["SC-A", "SC-A"]
        manifest = copy.deepcopy(self.manifest)
        manifest["unreadable_locations"] = [4]
        errors, warnings = self.validate(data, manifest=manifest)
        self.assertTrue(any("duplicate class_ids" in e for e in errors))
        self.assertTrue(any("unreadable locations" in w for w in warnings))

    # --- Workbook & Markdown Writer Tests ---

    def test_formula_injection_sanitization(self) -> None:
        self.assertEqual("'=SUM(A1:A2)", sanitize_excel_value("=SUM(A1:A2)"))
        self.assertEqual("'+cmd|' /C calc'!A0", sanitize_excel_value("+cmd|' /C calc'!A0"))
        self.assertEqual("Normal text", sanitize_excel_value("Normal text"))
        self.assertEqual(0.05, sanitize_excel_value(0.05))

    def test_writer_creates_reviewable_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            form = Path(tmp) / "draft.xlsx"
            review = Path(tmp) / "review.md"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "write_form.py"),
                    str(FIXTURES / "valid-extraction.json"),
                    "--schema",
                    str(ROOT / "reference" / "field-schema.json"),
                    "--staged",
                    str(FIXTURES / "sample-staged.md"),
                    "--manifest",
                    str(FIXTURES / "source-manifest.json"),
                    "--out-form",
                    str(form),
                    "--out-review",
                    str(review),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            wb = load_workbook(form, read_only=True, data_only=True)
            self.assertEqual(
                [
                    "Run_metadata",
                    "_Validation_lists",
                    "Transmission_view",
                    "Grouped_view",
                    "Evidence",
                    "Candidate_ledger",
                    "Open_questions",
                ],
                wb.sheetnames,
            )
            ws = wb["Transmission_view"]
            headers = [cell.value for cell in ws[1]]
            self.assertEqual(32, len(headers))
            row = dict(zip(headers, [cell.value for cell in ws[5]]))
            self.assertEqual("Sample Umbrella - Sample Fund", row["OFST010020"])
            self.assertEqual("Class A", row["OFST020050"])
            self.assertEqual("quarterly", row["OFTC005120"])
            self.assertTrue(row["OFTC005005"])
            self.assertIn("DRAFT FOR FUND REVIEW", review.read_text(encoding="utf-8"))

    def test_grouped_view_keeps_each_rule_row(self) -> None:
        data = copy.deepcopy(self.valid)
        second = copy.deepcopy(data["rules"][0])
        second["rule_id"] = "RULE-GATE-2"
        data["rules"].append(second)
        rows = transmission_rows(data)
        wb = openpyxl.Workbook()
        ws = wb.active
        write_grouped(ws, self.schema, data, rows)
        self.assertEqual(3, ws.max_row)

    def test_write_candidates_highlights_unresolved_without_error(self) -> None:
        data = copy.deepcopy(self.valid)
        data["candidates"].append({
            "candidate_id": "C-UNRES-1",
            "location_type": "page",
            "location": 2,
            "category_hints": ["holdback"],
            "snippet": "Ambiguous holdback wording.",
            "disposition": "unresolved",
            "reason": "Two interpretations exist.",
            "rule_ids": [],
        })
        wb = openpyxl.Workbook()
        ws = wb.active
        write_candidates(ws, data)
        self.assertEqual(3, ws.max_row)
        self.assertEqual("00FFF2CC", ws.cell(3, 4).fill.fgColor.rgb)

    # --- Repeatability Comparison Tests ---

    def test_repeatability_ignores_rule_id_and_preserves_duplicate_keys(self) -> None:
        first = copy.deepcopy(self.valid)
        second = copy.deepcopy(self.valid)
        second["rules"][0]["rule_id"] = "A-DIFFERENT-MODEL-ID"
        second["candidates"][0]["rule_ids"] = ["A-DIFFERENT-MODEL-ID"]
        result = compare(first, second)
        self.assertTrue(result["identical_after_normalisation"])

        # Add a second rule with identical identity fields to first, ensure count is preserved
        dup_rule = copy.deepcopy(first["rules"][0])
        dup_rule["rule_id"] = "RULE-GATE-DUP"
        first["rules"].append(dup_rule)
        diff_result = compare(first, second)
        self.assertFalse(diff_result["identical_after_normalisation"])
        self.assertEqual(1, len(diff_result["rules_only_in_run_a"]))


if __name__ == "__main__":
    unittest.main()
