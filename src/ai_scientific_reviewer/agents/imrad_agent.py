from __future__ import annotations

import re
from typing import Any

from ..types import AgentOutput


def _has_heading(headings: list[str], variants: list[str], body_text: str) -> bool:
    hv = {h.strip().lower() for h in (headings or []) if h and h.strip()}
    for v in variants:
        if v.lower() in hv:
            return True
    # fallback: search in text as standalone line
    for v in variants:
        if re.search(rf"(?im)^\s*{re.escape(v)}\s*$", body_text or ""):
            return True
    return False


def _assess_methods(body_text: str) -> dict[str, Any]:
    t = (body_text or "").lower()
    signals = {
        "aim_or_rq": bool(re.search(r"\b(research question|hypothes(is|es)|aim|objective|purpose)\b", t)),
        "sample_or_data": bool(re.search(r"\b(sample|participants|dataset|data set|corpus|n\s*=)\b", t)),
        "instruments_tools": bool(re.search(r"\b(instrument|questionnaire|survey|tool|apparatus|software|platform)\b", t)),
        "procedure": bool(re.search(r"\b(procedure|protocol|steps|workflow|we (collected|measured|recorded))\b", t)),
        "analysis": bool(re.search(r"\b(statistical|analysis|regression|anova|t-test|model|training|validation|p-value|confidence interval)\b", t)),
        "reproducibility": bool(re.search(r"\b(code|repository|github|osf|materials available|reproduce)\b", t)),
        "ethics": bool(re.search(r"\b(ethics|ethical|irb|institutional review|consent|approval)\b", t)),
        "limitations": bool(re.search(r"\b(limitations?|threats to validity)\b", t)),
    }
    missing = [k for k, v in signals.items() if not v]
    return {"signals": signals, "missing": missing}


def run_imrad_methodology_check(headings: list[str], body_text: str, references_present: bool) -> AgentOutput:
    warnings: list[str] = []
    errors: list[str] = []

    structure = {
        "introduction": _has_heading(headings, ["Introduction"], body_text),
        "methods": _has_heading(headings, ["Materials and Methods", "Methods", "Methodology"], body_text),
        "results": _has_heading(headings, ["Results"], body_text),
        "discussion": _has_heading(headings, ["Discussion"], body_text),
        "conclusion": _has_heading(headings, ["Conclusion", "Conclusions"], body_text),
        "references": bool(references_present),
    }
    missing_sections = [k for k, v in structure.items() if not v]
    if missing_sections:
        warnings.append("IMRAD/section structure appears incomplete (heading-based detection).")

    methods_assessment = _assess_methods(body_text)
    major_weaknesses: list[str] = []
    if not structure["methods"]:
        major_weaknesses.append("Methods/Methodology section not clearly identified.")
    if not methods_assessment["signals"]["analysis"]:
        major_weaknesses.append("Data analysis plan not clearly described.")
    if not methods_assessment["signals"]["sample_or_data"]:
        major_weaknesses.append("Sample/dataset description not clearly stated.")

    data: dict[str, Any] = {
        "imrad_presence": structure,
        "missing_sections": missing_sections,
        "methodology_signals": methods_assessment["signals"],
        "methodology_missing": methods_assessment["missing"],
        "major_methodological_weaknesses": major_weaknesses,
        "notes": [
            "Section detection is heading-based; manuscripts with nonstandard headings may require manual verification.",
            "Methodology signals are keyword heuristics; absence does not prove the element is missing.",
        ],
    }
    return {
        "agent": "Methodology and IMRAD Structure Agent",
        "ok": True,
        "warnings": warnings,
        "errors": errors,
        "data": data,
    }

