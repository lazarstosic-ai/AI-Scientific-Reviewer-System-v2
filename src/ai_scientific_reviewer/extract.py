from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .types import ManuscriptComponents


_DOI_RE = re.compile(
    r"\b(10\.\d{4,9}/[^\s\"<>]+)\b",
    flags=re.IGNORECASE,
)


def extract_dois(text: str) -> list[str]:
    dois = []
    for m in _DOI_RE.finditer(text or ""):
        doi = m.group(1).rstrip(").,;:]}'\"")
        dois.append(doi)
    # de-dup, keep order
    seen = set()
    out = []
    for d in dois:
        key = d.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _find_section(text: str, section_names: Iterable[str]) -> tuple[str, str]:
    """
    Returns (section_text, remainder_after_section_start).
    Very lightweight, heading-based extraction.
    """
    if not text:
        return "", ""
    lines = [ln.strip() for ln in text.splitlines()]
    lower = [ln.lower() for ln in lines]
    targets = {s.lower() for s in section_names}
    start_idx = None
    for i, ln in enumerate(lower):
        if ln in targets:
            start_idx = i
            break
        # allow "Abstract:" style
        for t in targets:
            if ln.startswith(t + ":"):
                start_idx = i
                lines[i] = lines[i].split(":", 1)[1].strip()
                break
        if start_idx is not None:
            break
    if start_idx is None:
        return "", text

    # section ends at next all-caps-ish heading or known headings
    end_idx = len(lines)
    stop_words = {
        "keywords",
        "introduction",
        "materials and methods",
        "methods",
        "methodology",
        "results",
        "discussion",
        "conclusion",
        "conclusions",
        "references",
        "bibliography",
    }
    for j in range(start_idx + 1, len(lines)):
        if not lines[j]:
            continue
        lj = lower[j]
        if lj in stop_words:
            end_idx = j
            break
        if re.fullmatch(r"[A-Z0-9 \-]{6,}", lines[j]) and len(lines[j].split()) <= 8:
            end_idx = j
            break
    section = "\n".join([ln for ln in lines[start_idx:end_idx] if ln]).strip()
    remainder = "\n".join(lines[end_idx:]).strip()
    return section, remainder


def extract_components(raw_text: str, headings: list[str] | None = None) -> ManuscriptComponents:
    headings = headings or []
    abstract, after_abs = _find_section(raw_text, ["Abstract"])
    references, before_refs = _find_section(raw_text, ["References", "Bibliography"])

    # crude title guess: first non-empty line before abstract
    title = ""
    if raw_text:
        pre = raw_text.splitlines()
        for ln in pre[:20]:
            ln = ln.strip()
            if not ln:
                continue
            if ln.lower() in {"abstract", "keywords"}:
                break
            title = ln
            break

    keywords_section, _ = _find_section(raw_text, ["Keywords"])
    keywords = []
    if keywords_section.lower().startswith("keywords"):
        pass
    if keywords_section:
        # split by comma/semicolon
        ktxt = keywords_section.replace("Keywords", "").replace("keywords", "").strip(" :")
        parts = re.split(r"[;,]", ktxt)
        keywords = [p.strip() for p in parts if p.strip()]

    body_text = raw_text
    if references:
        body_text = before_refs

    return {
        "title": title,
        "abstract": abstract.strip(),
        "keywords": keywords,
        "body_text": (body_text or "").strip(),
        "references_text": (references or "").strip(),
        "headings": headings,
    }


def extract_references_list(references_text: str) -> list[str]:
    if not references_text:
        return []
    # remove leading "References" heading if present
    txt = references_text.strip()
    txt = re.sub(r"(?i)^\s*(references|bibliography)\s*\n+", "", txt).strip()
    # split by blank lines first
    chunks = [c.strip() for c in re.split(r"\n\s*\n", txt) if c.strip()]
    if len(chunks) >= 2:
        return chunks
    # fallback: split by numbered entries
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    joined = "\n".join(lines)
    numbered = re.split(r"\n(?=\s*\d+[\.\)])", joined)
    numbered = [n.strip() for n in numbered if n.strip()]
    return numbered if len(numbered) > 1 else [txt]

