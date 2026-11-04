#!/usr/bin/env python3
"""Flag evidence that a source is binding, promotional or subordinate to another document."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from oftc_common import parse_staged_map, read_json, write_json

NEGATIVE = {
    "marketing_communication": r"marketing communication",
    "summary_only": r"summary of (?:certain )?(?:principal |key )?terms only",
    "qualified_by_prospectus": r"qualified in its entirety by.{0,160}prospectus",
    "prospectus_controls": r"prospectus shall control",
    "information_only": r"for information purposes only",
    "not_investment_basis": r"not intended to (?:form|serve as) the basis of any investment decision",
    "superseded_by_fund_documents": r"superseded in its entirety by.{0,120}fund documents",
    "pre_marketing": r"pre-marketing",
    "no_fund_exists": r"no fund (?:currently )?(?:in existence|has been established)",
}

POSITIVE = {
    "prospectus": r"\bprospectus\b",
    "offering_memorandum": r"offering memorandum",
    "private_placement_memorandum": r"private placement memorandum",
    "articles": r"articles of (?:incorporation|association)",
    "operative_language": r"(?:shall|must) (?:be|apply|pay|redeem|submit|give)",
}

CRITICAL_NEGATIVE_CODES = {
    "marketing_communication",
    "summary_only",
    "qualified_by_prospectus",
    "prospectus_controls",
    "superseded_by_fund_documents",
    "pre_marketing",
    "no_fund_exists",
}


def assess(staged_text: str) -> dict:
    """Scan staged blocks for positive and negative binding-scope indicators."""
    blocks = parse_staged_map(staged_text)
    findings: list[dict] = []
    for (location_type, location), text in blocks.items():
        for polarity, patterns in (("negative", NEGATIVE), ("positive", POSITIVE)):
            for code, expression in patterns.items():
                match = re.search(expression, text, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 180)
                    end = min(len(text), match.end() + 220)
                    findings.append({
                        "polarity": polarity,
                        "code": code,
                        "location_type": location_type,
                        "location": location,
                        "context": text[start:end],
                    })
    negative_codes = {f["code"] for f in findings if f["polarity"] == "negative"}
    if negative_codes & CRITICAL_NEGATIVE_CODES:
        recommendation = "manual_scope_review"
    elif any(f["polarity"] == "positive" for f in findings):
        recommendation = "likely_binding_but_verify"
    else:
        recommendation = "manual_scope_review"
    return {"recommendation": recommendation, "findings": findings}


def main() -> None:
    ap = argparse.ArgumentParser(description="Assess whether a staged fund document is binding.")
    ap.add_argument("staged", help="Path to staged.md")
    ap.add_argument("--manifest", required=True, help="Path to source-manifest.json")
    ap.add_argument("--output", required=True, help="Path to write scope-assessment.json")
    args = ap.parse_args()

    staged_path = Path(args.staged)
    if not staged_path.is_file():
        sys.exit(f"Staged file not found: {staged_path}")

    try:
        staged = staged_path.read_text(encoding="utf-8")
        manifest = read_json(args.manifest)
    except Exception as exc:
        sys.exit(f"error: {exc}")

    result = {
        "source_file": manifest.get("source_file"),
        "source_sha256": manifest.get("source_sha256"),
        **assess(staged),
    }
    write_json(args.output, result)
    print(json.dumps({
        "output": args.output,
        "recommendation": result["recommendation"],
        "findings": len(result["findings"]),
    }))


if __name__ == "__main__":
    main()
