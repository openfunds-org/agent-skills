#!/usr/bin/env python3
"""Create a deterministic candidate ledger from a staged fund document."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from oftc_common import clean_space, iter_staged_blocks, read_json, write_json

ALLOWED_DISPOSITIONS = [
    "mapped",
    "duplicate",
    "out_of_scope",
    "insufficient_evidence",
    "unresolved",
]

PATTERNS = {
    "redemption_restriction": [
        r"lock[ -]?up",
        r"lock[ -]?in",
        r"minimum holding period",
        r"no (?:right|entitlement) to (?:redeem|withdraw)",
        r"not (?:be )?permitted to redeem",
    ],
    "redemption_gate": [
        r"redemption gate",
        r"repurchase limit",
        r"redemption limit",
        r"quarter redemption limit",
        r"redemptions?.{0,100}(?:limited|capped)",
        r"repurchases?.{0,100}(?:limited|capped)",
        r"pro[ -]?rata.{0,100}(?:redemption|repurchase)",
        r"queued?.{0,100}(?:redemption|repurchase)",
    ],
    "redemption_fee": [
        r"early redemption",
        r"redemption (?:fee|charge|deduction|penalty|surcharge)",
        r"liquidity penalty",
        r"exit (?:fee|charge)",
        r"repurchas\w*.{0,80}(?:95%|discount|deduction)",
    ],
    "anti_dilution_levy": [
        r"anti[ -]?dilution levy",
        r"dilution levy",
    ],
    "redemption_in_kind": [
        r"redemption in[ -]?kind",
        r"repayment in[ -]?kind",
        r"redeem\w*.{0,80}in[ -]?kind",
        r"assets? in lieu of cash.{0,80}redemption",
    ],
    "side_pocket": [
        r"side pocket",
        r"side-pocket",
        r"segregat\w*.{0,80}illiquid assets",
    ],
    "suspension": [
        r"suspend\w*.{0,100}(?:redemption|repurchase|subscription|withdrawal)",
        r"(?:redemption|repurchase|subscription|withdrawal).{0,100}suspend",
    ],
    "holdback": [
        r"holdback",
        r"hold back",
        r"withhold\w*.{0,100}(?:redemption|proceeds|payment)",
    ],
    "payout_delay": [
        r"delay\w*.{0,100}(?:redemption|payment|settlement|proceeds)",
        r"(?:redemption|payment|settlement|proceeds).{0,100}(?:delay|defer)",
    ],
    "notice_extension": [
        r"extend\w*.{0,80}notice period",
        r"notice period.{0,80}extend",
    ],
    "minimum_retention": [
        r"minimum holding.{0,160}(?:compulsor|redeem|convert|reduce)",
        r"(?:compulsor|redeem|convert|reduce).{0,160}minimum holding",
        r"minimum (?:account balance|retention)",
    ],
    "large_redemption": [
        r"large redemption",
        r"redemption.{0,100}(?:higher of|greater than|exceed\w*).{0,100}(?:delay|defer)",
    ],
    "subscription_control": [
        r"subscription (?:gate|limit)",
        r"subscription requests?.{0,100}(?:defer|limit|suspend)",
    ],
}


def candidate_id(location_type: str, number: int, snippet: str) -> str:
    """Generate a deterministic 12-hex-character candidate identifier."""
    raw = f"{location_type}:{number}:{clean_space(snippet).lower()}".encode("utf-8")
    return "C-" + hashlib.sha256(raw).hexdigest()[:12].upper()


def candidates_for_block(
    location_type: str,
    number: int,
    text: str,
    context_lines: int = 3,
) -> list[dict]:
    """Scan one page or section block and return merged candidate records."""
    lines = text.splitlines()
    hits: list[tuple[int, int, set[str]]] = []
    for idx in range(len(lines)):
        window = clean_space(" ".join(lines[max(0, idx - 1):min(len(lines), idx + 2)]))
        categories = {
            category
            for category, expressions in PATTERNS.items()
            if any(re.search(expr, window, re.IGNORECASE) for expr in expressions)
        }
        if categories:
            hits.append((max(0, idx - context_lines), min(len(lines), idx + context_lines + 1), categories))

    merged: list[list] = []
    for start, end, categories in hits:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
            merged[-1][2].update(categories)
        else:
            merged.append([start, end, set(categories)])

    out: list[dict] = []
    for start, end, categories in merged:
        snippet = clean_space(" ".join(lines[start:end]))
        out.append({
            "candidate_id": candidate_id(location_type, number, snippet),
            "location_type": location_type,
            "location": number,
            "category_hints": sorted(categories),
            "snippet": snippet,
            "disposition": None,
            "reason": None,
            "rule_ids": [],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Discover candidate OFTC clauses in a staged document.")
    ap.add_argument("staged", help="Path to staged.md")
    ap.add_argument("--manifest", required=True, help="Path to source-manifest.json")
    ap.add_argument("--output", required=True, help="Path to write candidates.json")
    ap.add_argument("--context-lines", type=int, default=3, help="Context lines around each match.")
    args = ap.parse_args()

    staged_path = Path(args.staged)
    if not staged_path.is_file():
        sys.exit(f"Staged file not found: {staged_path}")

    try:
        text = staged_path.read_text(encoding="utf-8")
        manifest = read_json(args.manifest)
    except Exception as exc:
        sys.exit(f"error: {exc}")

    candidates: list[dict] = []
    for location_type, number, block in iter_staged_blocks(text):
        candidates.extend(candidates_for_block(location_type, number, block, args.context_lines))

    data = {
        "source_file": manifest.get("source_file"),
        "source_sha256": manifest.get("source_sha256"),
        "discovery_version": "2.0.1",
        "allowed_dispositions": ALLOWED_DISPOSITIONS,
        "candidates": candidates,
    }
    write_json(args.output, data)
    print(json.dumps({"output": args.output, "candidates": len(candidates)}))


if __name__ == "__main__":
    main()
