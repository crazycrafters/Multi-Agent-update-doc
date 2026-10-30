"""Conservative deterministic guard after independent model audit.
Semantic entailment still needs human review. Uploads never auto-verify artifacts.
Automatic changes must be verbatim supported spans, never inferred achievements.
"""

import re
from .schemas import Edit

PERSONAL = {"VERIFIED", "CANDIDATE_CONFIRMED"}
NUMBER = re.compile(r"\d+(?:[.,]\d+)?(?:\s*%|\b)")


def check_edit(edit: Edit, claim, evidence: dict, audit: dict) -> tuple[bool, str]:
    if not claim or edit.previous_text != claim.text:
        return False, "Claim does not match source version"
    if not edit.new_text.strip() or edit.previous_text == edit.new_text:
        return False, "Empty or unchanged proposal"
    if audit.get("verdict") != "PASS":
        return False, "Independent audit did not pass"
    records = [evidence.get(i) for i in edit.evidence_ids]
    if not records or any(r is None or r.status not in PERSONAL for r in records):
        return (
            False,
            "Requires verified or specifically candidate-confirmed personal evidence",
        )
    if not any(edit.new_text.strip() in r.text for r in records):
        return (
            False,
            "Revised wording must be a verbatim evidence span; human confirmation required",
        )
    if NUMBER.search(edit.new_text) and not any(
        r.status == "VERIFIED"
        and r.kind == "measurement"
        and edit.new_text.strip() in r.text
        for r in records
    ):
        return False, "Numerical claims need verified measurement evidence"
    if any(
        r.status == "CONTRADICTED" and edit.new_text.strip() in r.text
        for r in evidence.values()
    ):
        return False, "Conflicting evidence exists"
    return True, "Supported by eligible evidence and independent audit"


def metric_changes(baseline, final):
    return {
        "absolute_change": final - baseline,
        "percentage_point_change": (final - baseline) * 100,
        "relative_percentage_change": None
        if baseline == 0
        else (final - baseline) / abs(baseline) * 100,
    }
