from __future__ import annotations

import re
from typing import Any, Optional

from ..crossref import CrossrefClient, CrossrefError
from ..types import AgentOutput


_DOI_SYNTAX = re.compile(r"^10\.\d{4,9}/\S+$", flags=re.IGNORECASE)


def _normalize_doi(doi: str) -> str:
    d = (doi or "").strip()
    d = re.sub(r"(?i)^https?://(dx\.)?doi\.org/", "", d).strip()
    d = d.strip().strip(".;,)")
    return d


def _crossref_item_to_flat(meta: dict[str, Any]) -> dict[str, Any]:
    title = ""
    if isinstance(meta.get("title"), list) and meta["title"]:
        title = meta["title"][0]
    container = ""
    if isinstance(meta.get("container-title"), list) and meta["container-title"]:
        container = meta["container-title"][0]
    year = None
    for key in ("published-print", "published-online", "issued"):
        part = meta.get(key, {})
        date_parts = part.get("date-parts")
        if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
            year = date_parts[0][0]
            break
    authors = []
    for a in meta.get("author", []) or []:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        full = " ".join([p for p in [given, family] if p]).strip()
        if full:
            authors.append(full)
    return {
        "doi": meta.get("DOI"),
        "title": title,
        "container_title": container,
        "year": year,
        "authors": authors,
        "type": meta.get("type"),
        "publisher": meta.get("publisher"),
        "url": meta.get("URL"),
    }


def _weak_match(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    aa = re.sub(r"\W+", " ", a).strip().lower()
    bb = re.sub(r"\W+", " ", b).strip().lower()
    if not aa or not bb:
        return False
    return aa in bb or bb in aa


def run_doi_validation(dois: list[str], references: list[str], crossref: CrossrefClient) -> AgentOutput:
    warnings: list[str] = []
    errors: list[str] = []

    normalized = [_normalize_doi(d) for d in (dois or [])]
    normalized = [d for d in normalized if d]

    syntax_valid: list[str] = []
    syntax_invalid: list[str] = []
    for d in normalized:
        if _DOI_SYNTAX.match(d):
            syntax_valid.append(d)
        else:
            syntax_invalid.append(d)

    valid: list[dict[str, Any]] = []
    missing_metadata: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []

    # map doi -> reference strings that mention it
    doi_to_refs: dict[str, list[str]] = {}
    for ref in references or []:
        rlow = ref.lower()
        for d in syntax_valid:
            if d.lower() in rlow:
                doi_to_refs.setdefault(d, []).append(ref)

    for d in syntax_valid:
        try:
            resp = crossref.works_by_doi(d)
            msg = (resp or {}).get("message")
            if not isinstance(msg, dict):
                missing_metadata.append({"doi": d, "reason": "Crossref response missing 'message' object."})
                continue
            flat = _crossref_item_to_flat(msg)
            if not flat.get("title") and not flat.get("container_title"):
                missing_metadata.append({"doi": d, "reason": "Crossref metadata lacks title/container."})
                continue

            # check metadata mismatch against the reference text that contains the DOI (when present)
            refs = doi_to_refs.get(d, [])
            if refs:
                ref_text = " ".join(refs)
                title_ok = _weak_match(flat.get("title"), ref_text)
                year_ok = (str(flat.get("year")) in ref_text) if flat.get("year") else False
                journal_ok = _weak_match(flat.get("container_title"), ref_text)
                if not (title_ok or journal_ok) or (flat.get("year") and not year_ok):
                    mismatch.append(
                        {
                            "doi": d,
                            "crossref": flat,
                            "reference_snippet": ref_text[:500],
                            "signals": {"title_match": title_ok, "journal_match": journal_ok, "year_match": year_ok},
                        }
                    )
                else:
                    valid.append({"doi": d, "crossref": flat})
            else:
                # DOI appears in manuscript body but not in references
                unverifiable.append(
                    {
                        "doi": d,
                        "crossref": flat,
                        "note": "DOI found outside reference list or reference match not detected.",
                    }
                )
        except CrossrefError as e:
            unverifiable.append({"doi": d, "error": str(e)})

    if syntax_invalid:
        warnings.append("Some extracted DOIs fail basic DOI syntax validation.")

    data: dict[str, Any] = {
        "extracted_dois_count": len(normalized),
        "syntax_valid": syntax_valid,
        "syntax_invalid": syntax_invalid,
        "valid": valid,
        "missing_metadata": missing_metadata,
        "metadata_mismatch": mismatch,
        "unverifiable": unverifiable,
        "notes": [
            "Crossref validation uses the REST API; failures may be due to connectivity, rate limiting, or missing registrations.",
            "Metadata mismatch signals are heuristic and should be checked by an editor.",
        ],
    }

    ok = True
    if not normalized:
        warnings.append("No DOIs detected in manuscript/reference list.")
    return {"agent": "DOI Validation Agent", "ok": ok, "warnings": warnings, "errors": errors, "data": data}

