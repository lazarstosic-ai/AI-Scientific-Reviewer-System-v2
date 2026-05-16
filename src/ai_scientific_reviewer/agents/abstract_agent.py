from __future__ import annotations

import re
from typing import Any

from ..types import AgentOutput


def _word_count(text: str) -> int:
    words = re.findall(r"\b\w+\b", text or "")
    return len(words)


def _contains_component(text: str, patterns: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in patterns)


def run_abstract_analysis(abstract_text: str) -> AgentOutput:
    warnings: list[str] = []
    errors: list[str] = []

    if not abstract_text.strip():
        return {
            "agent": "Abstract Analysis Agent",
            "ok": False,
            "warnings": [],
            "errors": ["Abstract not found or empty."],
            "data": {"word_count": 0},
        }

    wc = _word_count(abstract_text)
    if wc < 150:
        warnings.append("Abstract is shorter than 150 words.")
    if wc > 250:
        warnings.append("Abstract is longer than 250 words.")

    components = {
        "background": _contains_component(abstract_text, [r"\bbackground\b", r"\bcontext\b", r"\bmotivation\b"]),
        "aim": _contains_component(abstract_text, [r"\baim\b", r"\bobjective\b", r"\bpurpose\b", r"\bwe (aim|seek)\b"]),
        "methodology": _contains_component(abstract_text, [r"\bmethod\b", r"\bmethodology\b", r"\bwe (used|conducted)\b"]),
        "results": _contains_component(abstract_text, [r"\bresult(s)?\b", r"\bwe found\b", r"\bfindings\b", r"\bshow(s|ed)\b"]),
        "conclusion": _contains_component(abstract_text, [r"\bconclusion(s)?\b", r"\bwe conclude\b", r"\bindicates\b"]),
        "contribution": _contains_component(abstract_text, [r"\bcontribution\b", r"\bnovel\b", r"\bthis paper (presents|proposes)\b"]),
    }

    missing = [k for k, v in components.items() if not v]
    suggestions: list[str] = []
    if missing:
        suggestions.append(
            "Add explicit elements for: " + ", ".join(missing) + " (use clear cue phrases)."
        )
    suggestions.append("Prefer a structured flow: Background → Aim → Methods → Results → Conclusion → Contribution.")
    suggestions.append("Include at least one quantitative result if applicable (effect size, accuracy, p-value, N).")

    data: dict[str, Any] = {
        "word_count": wc,
        "within_150_250": 150 <= wc <= 250,
        "components_present": components,
        "missing_components": missing,
        "suggestions": suggestions,
    }
    return {
        "agent": "Abstract Analysis Agent",
        "ok": True,
        "warnings": warnings,
        "errors": errors,
        "data": data,
    }

