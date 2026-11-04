#!/usr/bin/env python3
"""Compare repeated extraction runs after normalising model-written identifiers."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys

from oftc_common import clean_space, read_json, write_json

IDENTITY_FIELDS = (
    "OFTC005010",
    "OFTC005020",
    "OFTC005110",
    "OFTC005120",
    "OFTC005140",
    "OFTC005150",
    "OFTC005180",
    "OFTC005250",
    "OFTC005300",
    "OFTC005410",
    "OFTC005440",
    "OFTC008010",
    "OFTC008020",
)


def quote_hashes(rule: dict) -> tuple[str, ...]:
    """Return sorted 12-char SHA-256 digests of normalised evidence quotes."""
    values: list[str] = []
    for evidence in rule.get("evidence") or []:
        quote = clean_space(evidence.get("quote")).lower()
        values.append(hashlib.sha256(quote.encode("utf-8")).hexdigest()[:12])
    return tuple(sorted(values))


def base_rule_key(rule: dict) -> tuple:
    """Build a model-ID-independent identity tuple for a rule row."""
    fields = rule.get("fields") or {}
    return (
        tuple(sorted(rule.get("group_sources") or [])),
        tuple((field, fields.get(field)) for field in IDENTITY_FIELDS),
        quote_hashes(rule),
    )


def normalised_rule(rule: dict) -> dict:
    """Return a canonical dict representation of a rule row without model-assigned rule_id."""
    return {
        "group_sources": sorted(rule.get("group_sources") or []),
        "applies_to": sorted(rule.get("applies_to") or []),
        "fields": rule.get("fields") or {},
        "evidence": sorted(
            [
                {
                    "candidate_id": e.get("candidate_id"),
                    "location_type": e.get("location_type"),
                    "location": e.get("location"),
                    "quote": clean_space(e.get("quote")),
                    "supports": sorted(e.get("supports") or []),
                }
                for e in rule.get("evidence") or []
            ],
            key=lambda e: (e["candidate_id"] or "", e["location"] or 0, e["quote"]),
        ),
        "open_questions": sorted(rule.get("open_questions") or []),
    }


def index_rules(rules: list[dict]) -> dict[tuple, dict]:
    """Index rules by base_rule_key plus an occurrence ordinal so collisions are never overwritten."""
    counts: Counter = Counter()
    indexed: dict[tuple, dict] = {}
    for rule in sorted(rules, key=lambda r: (str(base_rule_key(r)), str(normalised_rule(r)))):
        bkey = base_rule_key(rule)
        counts[bkey] += 1
        indexed[(*bkey, counts[bkey])] = rule
    return indexed


def compare(a: dict, b: dict) -> dict:
    """Compare two extraction JSON dictionaries and return structured repeatability metrics."""
    a_candidates = {c["candidate_id"]: c for c in a.get("candidates") or []}
    b_candidates = {c["candidate_id"]: c for c in b.get("candidates") or []}
    candidate_ids = set(a_candidates) | set(b_candidates)
    candidate_differences: list[dict] = []
    for cid in sorted(candidate_ids):
        if cid not in a_candidates or cid not in b_candidates:
            candidate_differences.append({"candidate_id": cid, "difference": "missing from one run"})
            continue
        left = a_candidates[cid]
        right = b_candidates[cid]
        if (left.get("disposition"), left.get("reason")) != (right.get("disposition"), right.get("reason")):
            candidate_differences.append({
                "candidate_id": cid,
                "run_a": {"disposition": left.get("disposition"), "reason": left.get("reason")},
                "run_b": {"disposition": right.get("disposition"), "reason": right.get("reason")},
            })

    a_rules = index_rules(a.get("rules") or [])
    b_rules = index_rules(b.get("rules") or [])
    only_a = [normalised_rule(a_rules[k]) for k in sorted(set(a_rules) - set(b_rules), key=str)]
    only_b = [normalised_rule(b_rules[k]) for k in sorted(set(b_rules) - set(a_rules), key=str)]
    changed: list[dict] = []
    for key in sorted(set(a_rules) & set(b_rules), key=str):
        left, right = normalised_rule(a_rules[key]), normalised_rule(b_rules[key])
        if left != right:
            changed.append({"identity": str(key), "run_a": left, "run_b": right})
    union = len(set(a_rules) | set(b_rules))
    agreement = 1.0 if union == 0 else len(set(a_rules) & set(b_rules)) / union
    return {
        "same_source": a.get("metadata", {}).get("source_sha256") == b.get("metadata", {}).get("source_sha256"),
        "candidate_differences": candidate_differences,
        "rules_only_in_run_a": only_a,
        "rules_only_in_run_b": only_b,
        "matched_rules_with_differences": changed,
        "rule_inventory_jaccard": round(agreement, 6),
        "identical_after_normalisation": not candidate_differences and not only_a and not only_b and not changed,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare two OFTC extraction JSON files.")
    ap.add_argument("run_a", help="First extraction JSON file")
    ap.add_argument("run_b", help="Second extraction JSON file")
    ap.add_argument("--output", help="Optional path to write comparison JSON")
    args = ap.parse_args()

    try:
        a = read_json(args.run_a)
        b = read_json(args.run_b)
    except Exception as exc:
        sys.exit(f"error: {exc}")

    result = compare(a, b)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
