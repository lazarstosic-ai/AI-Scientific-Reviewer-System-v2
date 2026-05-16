from __future__ import annotations

import os
import uuid
from typing import Any, Callable

from langgraph.graph import END, StateGraph

from .agents.abstract_agent import run_abstract_analysis
from .agents.doi_agent import run_doi_validation
from .agents.imrad_agent import run_imrad_methodology_check
from .agents.editorial_screening_agent import run_editorial_screening
from .agents.reference_agent import run_reference_verification
from .agents.reviewer_report_agent import run_reviewer_report
from .crossref import CrossrefClient, CrossrefConfig
from .extract import extract_components, extract_dois, extract_references_list
from .types import ReviewState


def _supervisor_extract(state: ReviewState) -> ReviewState:
    raw = state.get("raw_text") or ""
    headings = (state.get("components") or {}).get("headings") or []
    comps = extract_components(raw_text=raw, headings=headings)
    refs = extract_references_list(comps.get("references_text") or "")
    dois = extract_dois(raw)
    state["components"] = comps
    state["references"] = refs
    state["extracted_dois"] = dois
    state["supervisor_report"] = {
        "agent": "Supervisor Agent",
        "ok": True,
        "warnings": [],
        "errors": [],
        "data": {
            "title_detected": bool(comps.get("title")),
            "abstract_detected": bool(comps.get("abstract")),
            "references_detected": len(refs),
            "doi_strings_detected": len(dois),
            "headings_detected": comps.get("headings") or [],
            "routing": [
                "Abstract Analysis Agent",
                "DOI Validation Agent",
                "Reference Verification and APA Formatting Agent",
                "Methodology and IMRAD Structure Agent",
                "Reviewer Report Agent",
            ],
        },
    }
    return state


def _abstract_node(state: ReviewState) -> ReviewState:
    abstract = (state.get("components") or {}).get("abstract") or ""
    state["abstract_assessment"] = run_abstract_analysis(abstract)
    return state


def _crossref_client_from_state(state: ReviewState) -> CrossrefClient:
    cfg = CrossrefConfig(
        mailto=state.get("crossref_mailto") or os.getenv("CROSSREF_MAILTO"),
        user_agent=state.get("crossref_user_agent") or os.getenv("CROSSREF_USER_AGENT"),
        timeout_s=float(state.get("crossref_timeout_s") or 20.0),
        rate_limit_delay_s=float(state.get("rate_limit_delay_s") or 1.0),
    )
    return CrossrefClient(cfg)


def _doi_node(state: ReviewState) -> ReviewState:
    crossref = _crossref_client_from_state(state)
    state["doi_validation"] = run_doi_validation(
        dois=state.get("extracted_dois") or [],
        references=state.get("references") or [],
        crossref=crossref,
    )
    return state


def _reference_node(state: ReviewState) -> ReviewState:
    crossref = _crossref_client_from_state(state)
    state["reference_verification"] = run_reference_verification(references=state.get("references") or [], crossref=crossref)
    return state


def _imrad_node(state: ReviewState) -> ReviewState:
    comps = state.get("components") or {}
    body = comps.get("body_text") or (state.get("raw_text") or "")
    headings = comps.get("headings") or []
    refs_present = bool((comps.get("references_text") or "").strip())
    state["imrad_methodology"] = run_imrad_methodology_check(headings=headings, body_text=body, references_present=refs_present)
    return state


def _reviewer_node(state: ReviewState) -> ReviewState:
    state["reviewer_report"] = run_reviewer_report(state)
    return state


def _editorial_screening_node(state: ReviewState) -> ReviewState:
    comps = state.get("components") or {}
    state["editorial_screening"] = run_editorial_screening(
        raw_text=state.get("raw_text") or "",
        title=comps.get("title") or "",
        abstract=comps.get("abstract") or "",
        keywords=comps.get("keywords") or [],
        references=state.get("references") or [],
        journal_scope_text=state.get("journal_scope_text"),
    )
    return state


def build_graph() -> Any:
    g = StateGraph(ReviewState)
    g.add_node("supervisor_extract", _supervisor_extract)
    g.add_node("abstract_agent", _abstract_node)
    g.add_node("doi_agent", _doi_node)
    g.add_node("reference_agent", _reference_node)
    g.add_node("imrad_agent", _imrad_node)
    g.add_node("editorial_screening_agent", _editorial_screening_node)
    g.add_node("reviewer_report_agent", _reviewer_node)

    g.set_entry_point("supervisor_extract")
    g.add_edge("supervisor_extract", "abstract_agent")
    g.add_edge("abstract_agent", "doi_agent")
    g.add_edge("doi_agent", "reference_agent")
    g.add_edge("reference_agent", "imrad_agent")
    g.add_edge("imrad_agent", "editorial_screening_agent")
    g.add_edge("editorial_screening_agent", "reviewer_report_agent")
    g.add_edge("reviewer_report_agent", END)
    return g.compile()


def run_pipeline(
    raw_text: str,
    input_filename: str = "",
    headings: list[str] | None = None,
    journal_scope_text: str | None = None,
    crossref_mailto: str | None = None,
    crossref_user_agent: str | None = None,
    crossref_timeout_s: float = 20.0,
    rate_limit_delay_s: float = 1.0,
) -> ReviewState:
    app = build_graph()
    init: ReviewState = {
        "run_id": str(uuid.uuid4()),
        "input_filename": input_filename,
        "raw_text": raw_text,
        "components": {"headings": headings or []},
        "journal_scope_text": journal_scope_text,
        "crossref_mailto": crossref_mailto,
        "crossref_user_agent": crossref_user_agent,
        "crossref_timeout_s": float(crossref_timeout_s),
        "rate_limit_delay_s": float(rate_limit_delay_s),
    }
    return app.invoke(init)
