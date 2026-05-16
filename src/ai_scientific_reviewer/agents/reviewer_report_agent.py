from __future__ import annotations

import textwrap
from typing import Any

from ..types import AgentOutput, Decision, ReviewState


def _pick_recommendation(state: ReviewState) -> Decision:
    # Conservative heuristic: if major methodological issues or many unverifiable refs/DOIs -> Major revision/Reject.
    imrad = (state.get("imrad_methodology") or {}).get("data", {}) if state.get("imrad_methodology") else {}
    major_method = (imrad.get("major_methodological_weaknesses") or []) if isinstance(imrad, dict) else []

    refs = (state.get("reference_verification") or {}).get("data", {}) if state.get("reference_verification") else {}
    unver = (refs.get("unverifiable_candidates") or []) if isinstance(refs, dict) else []

    doi = (state.get("doi_validation") or {}).get("data", {}) if state.get("doi_validation") else {}
    invalid_doi = (doi.get("syntax_invalid") or []) if isinstance(doi, dict) else []
    mismatch_doi = (doi.get("metadata_mismatch") or []) if isinstance(doi, dict) else []

    if major_method and len(major_method) >= 2:
        return "Major revision"
    if len(unver) >= 10 or len(invalid_doi) >= 3 or len(mismatch_doi) >= 3:
        return "Major revision"
    return "Minor revision"


def run_reviewer_report(state: ReviewState) -> AgentOutput:
    components = state.get("components") or {}
    abstract = state.get("abstract_assessment") or {}
    doi = state.get("doi_validation") or {}
    refs = state.get("reference_verification") or {}
    imrad = state.get("imrad_methodology") or {}
    supervisor = state.get("supervisor_report") or {}
    screening = state.get("editorial_screening") or {}

    recommendation: Decision = _pick_recommendation(state)

    major_weaknesses: list[str] = []
    minor_weaknesses: list[str] = []
    required_revisions: list[str] = []
    optional_recommendations: list[str] = []

    # major/minor synth
    imrad_data = imrad.get("data") if isinstance(imrad, dict) else {}
    for w in (imrad_data or {}).get("major_methodological_weaknesses", []) if isinstance(imrad_data, dict) else []:
        major_weaknesses.append(str(w))
        required_revisions.append(str(w))

    doi_data = doi.get("data") if isinstance(doi, dict) else {}
    if isinstance(doi_data, dict) and (doi_data.get("syntax_invalid") or []):
        minor_weaknesses.append("Some DOIs appear syntactically invalid; correct formatting (e.g., 10.xxxx/...).")
        required_revisions.append("Fix invalid DOI strings and ensure they resolve.")
    if isinstance(doi_data, dict) and (doi_data.get("metadata_mismatch") or []):
        major_weaknesses.append("Potential DOI-reference metadata mismatches detected; verify citations.")
        required_revisions.append("Verify each DOI corresponds to the cited work (title/year/journal).")

    refs_data = refs.get("data") if isinstance(refs, dict) else {}
    if isinstance(refs_data, dict) and (refs_data.get("unverifiable_candidates") or []):
        minor_weaknesses.append("Some references are not verifiable via Crossref; ensure completeness and accuracy.")
        required_revisions.append("Complete bibliographic metadata for unverifiable references (authors, year, title, source).")
    if isinstance(refs_data, dict) and (refs_data.get("apa_formatting_issues") or []):
        minor_weaknesses.append("APA 7 formatting inconsistencies present (heuristic).")
        required_revisions.append("Reformat references to APA 7th edition consistently.")

    abs_data = abstract.get("data") if isinstance(abstract, dict) else {}
    if isinstance(abs_data, dict) and abs_data.get("missing_components"):
        minor_weaknesses.append("Abstract is missing expected components (background/aim/method/results/conclusion/contribution).")
        required_revisions.append("Revise abstract to include all key components explicitly.")

    screening_data = screening.get("data") if isinstance(screening, dict) else {}
    if isinstance(screening_data, dict):
        ethics = (screening_data.get("ethics_and_irb_check") or {}).get("level")
        data_av = (screening_data.get("data_availability_check") or {}).get("level")
        coi = (screening_data.get("conflict_of_interest_funding_check") or {}).get("level")
        lang = (screening_data.get("language_quality_check") or {}).get("level")
        scope = (screening_data.get("journal_scope_alignment") or {}).get("level")
        if ethics == "warning":
            major_weaknesses.append("Potential missing ethics/IRB/consent statement for human-subject-related work (heuristic).")
            required_revisions.append("Add a clear ethics/IRB/consent statement where applicable.")
        if data_av == "missing":
            minor_weaknesses.append("No clear data/code availability statement detected (heuristic).")
            required_revisions.append("Add a data/code availability statement (or justify restrictions).")
        if coi != "present":
            minor_weaknesses.append("No clear conflict-of-interest/funding statement detected (heuristic).")
            required_revisions.append("Add explicit COI and funding statements (even if none).")
        if lang == "warning":
            minor_weaknesses.append("Language/readability heuristics indicate potential clarity issues (indicative).")
            optional_recommendations.append("Consider professional language editing for clarity and concision.")
        if scope in {"low", "unknown"}:
            optional_recommendations.append("Confirm journal scope fit; consider adjusting framing/keywords to match aims and scope.")

    optional_recommendations.extend(
        [
            "Add a limitations subsection and explicitly discuss threats to validity.",
            "Add an ethics statement (IRB/consent) if human/animal data are involved.",
            "Provide data/code availability statement to improve reproducibility.",
        ]
    )

    scopus_wos_readiness = {
        "overall": "Needs revision" if recommendation in {"Major revision", "Reject", "Reject and resubmit"} else "Promising with revisions",
        "drivers": [
            "Methodology reporting clarity",
            "Reference verifiability and APA compliance",
            "DOI correctness and metadata consistency",
            "Abstract completeness and concision",
        ],
        "note": "This is a heuristic readiness indicator; final suitability depends on journal scope and novelty.",
    }

    def _fmt_list(items: list[str]) -> str:
        if not items:
            return "None."
        return "\n".join([f"- {i}" for i in items])

    # Reviewer-style response letter (editorial screening / preliminary peer-review)
    response_parts: list[str] = []
    response_parts.append("Reviewer Response (Preliminary Editorial Screening)")
    response_parts.append("")
    response_parts.append(
        f"Recommendation: {recommendation}. This assessment is based on automated screening signals and limited metadata validation (Crossref where available)."
    )
    response_parts.append("")
    response_parts.append("Major Issues")
    response_parts.append(_fmt_list(major_weaknesses))
    response_parts.append("")
    response_parts.append("Minor Issues")
    response_parts.append(_fmt_list(minor_weaknesses))
    response_parts.append("")
    response_parts.append("Required Revisions")
    response_parts.append(_fmt_list(required_revisions))
    response_parts.append("")
    response_parts.append("Optional Recommendations")
    response_parts.append(_fmt_list(optional_recommendations))
    response_parts.append("")
    response_parts.append(
        "Notes: Similarity/AI-text indicators are heuristic and must not be treated as proof. Unverifiable references/DOIs may reflect non-Crossref sources and should be checked manually."
    )
    reviewer_response_text = "\n".join(response_parts).strip()

    data: dict[str, Any] = {
        "manuscript_metadata": {
            "title": components.get("title") or None,
            "keywords": components.get("keywords") or [],
            "input_filename": state.get("input_filename") or None,
            "run_id": state.get("run_id") or None,
        },
        "supervisor_summary": supervisor.get("data"),
        "editorial_screening": screening.get("data"),
        "abstract_assessment": abstract.get("data"),
        "doi_validation_report": doi.get("data"),
        "reference_verification_report": refs.get("data"),
        "imrad_structure_assessment": (imrad.get("data") or {}).get("imrad_presence") if isinstance(imrad.get("data"), dict) else None,
        "methodology_assessment": imrad.get("data"),
        "ethics_and_transparency_notes": [
            "Ethics/reproducibility checks are keyword-based; confirm presence of approvals, consent, and data/code availability manually.",
        ],
        "scientific_quality_assessment": {
            "scientific_contribution": "Unverified (requires content-specific expert judgment).",
            "writing_quality": "Partially assessed via structure/abstract/reference signals.",
            "methodological_rigor": "Assessed via reporting completeness signals; not a validity proof.",
        },
        "scopus_wos_readiness": scopus_wos_readiness,
        "major_weaknesses": major_weaknesses,
        "minor_weaknesses": minor_weaknesses,
        "required_revisions": required_revisions,
        "optional_recommendations": optional_recommendations,
        "reviewer_response": reviewer_response_text,
        "final_recommendation": recommendation,
    }

    return {
        "agent": "Reviewer Report Agent",
        "ok": True,
        "warnings": [],
        "errors": [],
        "data": data,
    }
