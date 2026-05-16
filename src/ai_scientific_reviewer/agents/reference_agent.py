from __future__ import annotations

import re
from typing import Any, Optional

from ..crossref import CrossrefClient, CrossrefError
from ..types import AgentOutput


def _looks_like_apa7(ref: str) -> bool:
    # Very rough: "Surname, A." and year in parentheses.
    return bool(re.search(r"\b[A-Z][a-zA-Z\-']+,\s*[A-Z]\.", ref)) and bool(re.search(r"\(\s*\d{4}\s*\)", ref))


def _extract_year(ref: str) -> Optional[int]:
    m = re.search(r"\(\s*(\d{4})\s*\)", ref)
    return int(m.group(1)) if m else None


def _extract_title_guess(ref: str) -> Optional[str]:
    # Heuristic: in APA, title often after year. We take text after "(YYYY)." up to next period.
    m = re.search(r"\(\s*\d{4}\s*\)\.\s*(.+?)\.\s", ref)
    if not m:
        return None
    title = m.group(1).strip()
    return title or None


def _crossref_best_match(query: str, crossref: CrossrefClient) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]], Optional[str]]:
    try:
        resp = crossref.works_query_bibliographic(query=query, rows=3)
        items = (((resp or {}).get("message") or {}).get("items") or []) if isinstance(resp, dict) else []
        if not items:
            return None, [], None
        return items[0], items[:3], None
    except CrossrefError as e:
        return None, [], str(e)


def _to_apa7_suggestion(item: dict[str, Any]) -> Optional[str]:
    # Only produce a suggestion when core metadata exists.
    titles = item.get("title") or []
    if not titles:
        return None
    title = titles[0]
    year = None
    for key in ("issued", "published-print", "published-online"):
        dp = (item.get(key) or {}).get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            year = dp[0][0]
            break
    authors = item.get("author") or []
    if not authors:
        return None
    author_bits = []
    for a in authors[:20]:
        family = (a.get("family") or "").strip()
        given = (a.get("given") or "").strip()
        initials = "".join([p[0] + "." for p in given.split() if p])
        if family and initials:
            author_bits.append(f"{family}, {initials}")
        elif family:
            author_bits.append(family)
    if not author_bits:
        return None
    author_str = ", ".join(author_bits)
    container = ""
    if (item.get("container-title") or []):
        container = (item["container-title"] or [""])[0]
    volume = item.get("volume")
    issue = item.get("issue")
    page = item.get("page")
    doi = item.get("DOI")

    parts = [f"{author_str} ({year}). {title}."]
    if container:
        j = container
        if volume:
            j += f", {volume}"
            if issue:
                j += f"({issue})"
        if page:
            j += f", {page}"
        j += "."
        parts.append(j)
    if doi:
        parts.append(f"https://doi.org/{doi}")
    return " ".join(parts).replace("  ", " ").strip()


def run_reference_verification(references: list[str], crossref: CrossrefClient) -> AgentOutput:
    warnings: list[str] = []
    errors: list[str] = []

    if not references:
        return {
            "agent": "Reference Verification and APA Formatting Agent",
            "ok": False,
            "warnings": [],
            "errors": ["No references detected."],
            "data": {"references_count": 0},
        }

    results: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    apa_issues: list[dict[str, Any]] = []
    apa_suggestions: list[dict[str, Any]] = []

    for idx, ref in enumerate(references, start=1):
        ref_clean = " ".join((ref or "").split()).strip()
        if not ref_clean:
            continue

        year = _extract_year(ref_clean)
        title_guess = _extract_title_guess(ref_clean)
        looks_apa = _looks_like_apa7(ref_clean)
        if not looks_apa:
            apa_issues.append({"ref_index": idx, "issue": "Does not resemble APA 7 pattern (heuristic).", "ref": ref_clean})

        # Basic completeness checks
        if year is None or not re.search(r"\b[A-Z][a-zA-Z\-']+,\s*[A-Z]\.", ref_clean):
            incomplete.append(
                {"ref_index": idx, "reason": "Missing year or author initials pattern (heuristic).", "ref": ref_clean}
            )

        query = title_guess or ref_clean
        best, top3, err = _crossref_best_match(query=query, crossref=crossref)
        if err:
            unverifiable.append({"ref_index": idx, "error": err, "ref": ref_clean})
            continue
        if not best:
            unverifiable.append({"ref_index": idx, "reason": "No Crossref match found.", "ref": ref_clean})
            continue

        # Compare minimal signals
        best_title = (best.get("title") or [""])[0] if isinstance(best.get("title"), list) else ""
        title_match = False
        if title_guess and best_title:
            a = re.sub(r"\W+", " ", title_guess).strip().lower()
            b = re.sub(r"\W+", " ", best_title).strip().lower()
            title_match = a in b or b in a

        year_match = True
        if year is not None:
            best_year = None
            dp = (best.get("issued") or {}).get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                best_year = dp[0][0]
            year_match = (best_year == year) if best_year is not None else True

        record = {
            "ref_index": idx,
            "ref": ref_clean,
            "crossref_top3": [
                {
                    "DOI": it.get("DOI"),
                    "title": (it.get("title") or [""])[0] if (it.get("title") or []) else None,
                    "container_title": (it.get("container-title") or [""])[0] if (it.get("container-title") or []) else None,
                    "year": ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                    "score": it.get("score"),
                }
                for it in top3
            ],
            "signals": {"title_match": title_match, "year_match": year_match, "looks_like_apa7": looks_apa},
        }
        results.append(record)

        suggestion = _to_apa7_suggestion(best)
        if suggestion:
            apa_suggestions.append({"ref_index": idx, "suggested_apa7": suggestion})

    if apa_issues:
        warnings.append("Some references may not follow APA 7 formatting (heuristic).")
    if unverifiable:
        warnings.append("Some references could not be verified via Crossref (may be non-indexed or incomplete).")

    data: dict[str, Any] = {
        "references_count": len(references),
        "verified_candidates": results,
        "incomplete_candidates": incomplete,
        "unverifiable_candidates": unverifiable,
        "apa_formatting_issues": apa_issues,
        "apa7_suggestions": apa_suggestions,
        "notes": [
            "Crossref matching is best-effort and may fail for books, local journals, or items not registered with Crossref.",
            "APA checks are heuristic; final formatting should be validated by an editor.",
        ],
    }
    return {
        "agent": "Reference Verification and APA Formatting Agent",
        "ok": True,
        "warnings": warnings,
        "errors": errors,
        "data": data,
    }

