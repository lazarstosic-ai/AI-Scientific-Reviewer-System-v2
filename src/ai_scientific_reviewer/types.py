from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class ManuscriptComponents(TypedDict, total=False):
    title: str
    abstract: str
    keywords: list[str]
    body_text: str
    references_text: str
    headings: list[str]


class CrossrefMatch(TypedDict, total=False):
    doi: str
    score: float
    title: str
    container_title: str
    year: int
    authors: list[str]
    url: str


class AgentOutput(TypedDict, total=False):
    agent: str
    ok: bool
    warnings: list[str]
    errors: list[str]
    data: dict[str, Any]


class ReviewState(TypedDict, total=False):
    # inputs
    input_filename: str
    raw_text: str
    components: ManuscriptComponents
    references: list[str]
    extracted_dois: list[str]
    journal_scope_text: Optional[str]

    # per-agent outputs
    supervisor_report: AgentOutput
    abstract_assessment: AgentOutput
    doi_validation: AgentOutput
    reference_verification: AgentOutput
    imrad_methodology: AgentOutput
    editorial_screening: AgentOutput

    # final
    reviewer_report: AgentOutput
    final_report_html: str
    final_report_pdf_path: Optional[str]

    # bookkeeping
    run_id: str
    crossref_mailto: Optional[str]
    crossref_user_agent: Optional[str]
    crossref_timeout_s: float
    rate_limit_delay_s: float


Decision = Literal["Accept", "Minor revision", "Major revision", "Reject", "Reject and resubmit"]
