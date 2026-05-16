from __future__ import annotations

import re
import statistics
from datetime import date
from typing import Any, Optional

from ..types import AgentOutput


def _sentences(text: str) -> list[str]:
    if not text:
        return []
    # lightweight sentence splitter
    parts = re.split(r"(?<=[\.\!\?])\s+", re.sub(r"\s+", " ", text).strip())
    parts = [p.strip() for p in parts if p and len(p.strip()) >= 6]
    return parts


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ž]+(?:'[A-Za-zÀ-ž]+)?", text or "")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _plagiarism_similarity_warning(text: str) -> dict[str, Any]:
    sents = _sentences(text)
    if not sents:
        return {"level": "unknown", "signals": [], "notes": ["No text available for similarity heuristics."]}

    norm_sents = [_norm(s) for s in sents]
    freq: dict[str, int] = {}
    for s in norm_sents:
        if len(s) < 30:
            continue
        freq[s] = freq.get(s, 0) + 1
    repeated = sorted([(k, v) for k, v in freq.items() if v >= 2], key=lambda x: -x[1])
    repeated_count = sum(v for _, v in repeated)
    rep_ratio = repeated_count / max(1, len(sents))

    generic_phrases = [
        "in this study",
        "this paper aims",
        "the purpose of this study",
        "the results show that",
        "this research aims",
        "in conclusion",
    ]
    generic_hits = sum(1 for s in norm_sents if any(p in s for p in generic_phrases))
    generic_ratio = generic_hits / max(1, len(sents))

    # Indicative level only. Not proof of plagiarism/similarity.
    level = "low"
    if rep_ratio >= 0.12 or (rep_ratio >= 0.08 and generic_ratio >= 0.2):
        level = "medium"
    if rep_ratio >= 0.2:
        level = "high"

    examples = [orig for orig in sents if _norm(orig) in dict(repeated[:3])]
    return {
        "level": level,
        "signals": [
            {"name": "repeated_sentences_ratio", "value": round(rep_ratio, 3)},
            {"name": "generic_sentence_ratio", "value": round(generic_ratio, 3)},
            {"name": "repeated_sentence_groups", "value": len(repeated)},
        ],
        "examples": examples[:3],
        "notes": [
            "This is a heuristic similarity warning, not a plagiarism determination.",
            "High repetition can also be caused by templates, formatting artifacts, or methodological boilerplate.",
        ],
    }


def _ai_generated_risk_indicator(text: str) -> dict[str, Any]:
    sents = _sentences(text)
    tokens = _word_tokens(text)
    if not sents or len(tokens) < 200:
        return {
            "level": "unknown",
            "signals": [],
            "notes": ["Insufficient text for an AI-generated risk heuristic (indicative only)."],
        }

    norm_sents = [_norm(s) for s in sents]
    unique_sent_ratio = len(set(norm_sents)) / max(1, len(norm_sents))
    lexical_div = len({t.lower() for t in tokens}) / max(1, len(tokens))
    sent_lens = [len(_word_tokens(s)) for s in sents]
    avg_len = sum(sent_lens) / max(1, len(sent_lens))
    stdev_len = statistics.pstdev(sent_lens) if len(sent_lens) >= 2 else 0.0

    telltales = [
        "as an ai language model",
        "i cannot",
        "i am unable",
        "chatgpt",
        "openai",
    ]
    telltale_hits = sum(1 for s in norm_sents if any(t in s for t in telltales))

    # indicative level only
    score = 0
    if unique_sent_ratio < 0.92:
        score += 1
    if lexical_div < 0.33:
        score += 1
    if avg_len >= 28 and stdev_len < 10:
        score += 1
    if telltale_hits:
        score += 2

    level = "low"
    if score >= 2:
        level = "medium"
    if score >= 4:
        level = "high"

    return {
        "level": level,
        "signals": [
            {"name": "unique_sentence_ratio", "value": round(unique_sent_ratio, 3)},
            {"name": "lexical_diversity", "value": round(lexical_div, 3)},
            {"name": "avg_sentence_words", "value": round(avg_len, 1)},
            {"name": "sentence_length_stdev", "value": round(stdev_len, 1)},
            {"name": "ai_telltale_hits", "value": telltale_hits},
        ],
        "notes": [
            "AI-generated text risk is indicative only and must not be treated as proof.",
            "False positives are possible (e.g., formulaic academic styles, translated text).",
        ],
    }


def _journal_scope_alignment(
    title: str,
    abstract: str,
    keywords: list[str],
    journal_scope_text: Optional[str],
) -> dict[str, Any]:
    if not journal_scope_text or not journal_scope_text.strip():
        return {
            "level": "unknown",
            "notes": ["Journal scope/aims text not provided; alignment could not be assessed."],
        }

    doc_text = " ".join([title or "", abstract or "", ", ".join(keywords or [])]).strip()
    doc_terms = {t for t in (_norm(doc_text).split()) if len(t) >= 4}
    scope_terms = {t for t in (_norm(journal_scope_text).split()) if len(t) >= 4}
    sim = _jaccard(doc_terms, scope_terms)
    overlap = sorted(list(doc_terms & scope_terms))[:40]

    level = "low"
    if sim >= 0.06:
        level = "medium"
    if sim >= 0.12:
        level = "high"

    return {
        "level": level,
        "signals": [{"name": "jaccard_similarity", "value": round(sim, 3)}],
        "overlapping_terms": overlap,
        "notes": [
            "This is a lightweight keyword overlap heuristic; editors should evaluate scope fit manually.",
        ],
    }


def _ethics_irb_check(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    human_signals = bool(
        re.search(r"\b(participants|students|teachers|patients|survey|questionnaire|interview|consent)\b", t)
    )
    ethics_signals = bool(re.search(r"\b(irb|ethics|ethical|institutional review|approval|informed consent)\b", t))

    level = "ok"
    if human_signals and not ethics_signals:
        level = "warning"
    if not human_signals and not ethics_signals:
        level = "unknown"

    return {
        "level": level,
        "signals": {"human_subjects_keywords": human_signals, "ethics_irb_keywords": ethics_signals},
        "notes": [
            "If the study involves humans, an ethics/IRB/consent statement is typically required.",
            "Keyword detection may miss statements placed in footnotes, appendices, or separate submission metadata.",
        ],
    }


def _data_availability_check(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    hits = []
    patterns = {
        "data availability statement": r"\bdata availability\b",
        "code availability statement": r"\bcode availability\b",
        "github repository": r"github\.com",
        "zenodo": r"\bzenodo\b",
        "osf": r"osf\.io|\bopen science framework\b",
        "figshare": r"\bfigshare\b",
        "available on request": r"\bupon request\b|\bon request\b",
    }
    for name, pat in patterns.items():
        if re.search(pat, t):
            hits.append(name)

    level = "missing"
    if hits:
        level = "present"
    return {
        "level": level,
        "hits": hits,
        "notes": [
            "This checks for explicit data/code availability statements or repository links.",
            "Presence does not guarantee accessibility or completeness; verify the links and licensing.",
        ],
    }


def _figures_tables_check(text: str) -> dict[str, Any]:
    t = text or ""
    fig_nums = [int(n) for n in re.findall(r"(?i)\b(?:figure|fig\.)\s*(\d+)\b", t)]
    tab_nums = [int(n) for n in re.findall(r"(?i)\btable\s*(\d+)\b", t)]

    def _gaps(nums: list[int]) -> list[int]:
        if not nums:
            return []
        s = sorted(set(nums))
        gaps = []
        for a, b in zip(s, s[1:]):
            if b - a > 1:
                gaps.extend(list(range(a + 1, b)))
        return gaps

    fig_gaps = _gaps(fig_nums)
    tab_gaps = _gaps(tab_nums)

    level = "ok"
    if (fig_nums and fig_gaps) or (tab_nums and tab_gaps):
        level = "warning"
    if not fig_nums and not tab_nums:
        level = "unknown"

    return {
        "level": level,
        "figures_detected": len(set(fig_nums)),
        "tables_detected": len(set(tab_nums)),
        "figure_number_gaps": fig_gaps,
        "table_number_gaps": tab_gaps,
        "notes": [
            "This checks whether figures/tables appear to be numbered sequentially and referenced in text.",
            "It cannot validate actual image/table presence in the original Word file beyond extracted text.",
        ],
    }


def _citation_freshness_check(references: list[str], today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    cutoff = today.year - 5
    years: list[int] = []
    for ref in references or []:
        for y in re.findall(r"\b(19\d{2}|20\d{2})\b", ref):
            yy = int(y)
            if 1900 <= yy <= today.year + 1:
                years.append(yy)
                break
    if not years:
        return {
            "level": "unknown",
            "notes": ["No reference years detected; freshness could not be assessed."],
        }

    total = len(years)
    recent = sum(1 for y in years if y >= cutoff)
    ratio = recent / max(1, total)

    level = "ok"
    if total >= 10 and ratio < 0.3:
        level = "warning"
    if total < 10:
        level = "unknown"

    return {
        "level": level,
        "signals": {
            "references_with_years": total,
            "recent_references_since_year": cutoff,
            "recent_references_count": recent,
            "recent_ratio": round(ratio, 3),
        },
        "notes": [
            "This is a simple count of references dated within the last 5 years.",
            "Appropriate recency depends on discipline and the manuscript's topic.",
        ],
    }


def _language_quality_check(text: str) -> dict[str, Any]:
    sents = _sentences(text)
    if not sents:
        return {"level": "unknown", "notes": ["No text available for language heuristics."]}

    lens = [len(_word_tokens(s)) for s in sents]
    long_sent = sum(1 for n in lens if n >= 40)
    very_long_sent = sum(1 for n in lens if n >= 60)
    avg = sum(lens) / max(1, len(lens))

    # Very rough "clarity" heuristic
    level = "ok"
    if very_long_sent >= 3 or (len(sents) >= 30 and long_sent / len(sents) > 0.25):
        level = "warning"

    return {
        "level": level,
        "signals": {
            "sentences_estimated": len(sents),
            "avg_sentence_words": round(avg, 1),
            "sentences_40plus_words": long_sent,
            "sentences_60plus_words": very_long_sent,
        },
        "notes": [
            "This is a lightweight readability heuristic; it does not perform grammar checking.",
            "Consider editing for shorter sentences, clearer terminology, and consistent definitions.",
        ],
    }


def _coi_funding_check(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    coi = bool(re.search(r"\b(conflict of interest|competing interests?)\b", t))
    funding = bool(re.search(r"\b(funding|funded by|grant|financial support|supported by)\b", t))
    level = "unknown"
    if coi or funding:
        level = "present"
    return {
        "level": level,
        "signals": {"coi_statement_keywords": coi, "funding_keywords": funding},
        "notes": [
            "Most journals require explicit conflict-of-interest and funding statements (even if none).",
        ],
    }


def run_editorial_screening(
    raw_text: str,
    title: str,
    abstract: str,
    keywords: list[str],
    references: list[str],
    journal_scope_text: Optional[str] = None,
) -> AgentOutput:
    warnings: list[str] = []
    errors: list[str] = []

    text_for_checks = " ".join([title or "", abstract or "", raw_text or ""]).strip()

    similarity = _plagiarism_similarity_warning(text_for_checks)
    ai_risk = _ai_generated_risk_indicator(text_for_checks)
    scope = _journal_scope_alignment(title, abstract, keywords, journal_scope_text)
    ethics = _ethics_irb_check(text_for_checks)
    data_avail = _data_availability_check(text_for_checks)
    figs_tabs = _figures_tables_check(raw_text or "")
    freshness = _citation_freshness_check(references)
    lang = _language_quality_check(text_for_checks)
    coi = _coi_funding_check(text_for_checks)

    if similarity.get("level") in {"medium", "high"}:
        warnings.append("Similarity heuristic flagged notable repetition/generic phrasing (indicative only).")
    if ai_risk.get("level") in {"medium", "high"}:
        warnings.append("AI-generated text risk heuristic flagged elevated signals (indicative only).")
    if ethics.get("level") == "warning":
        warnings.append("Human-subject keywords detected but no clear ethics/IRB/consent statement found (heuristic).")
    if data_avail.get("level") == "missing":
        warnings.append("No clear data/code availability statement detected (heuristic).")
    if coi.get("level") != "present":
        warnings.append("No clear COI/funding statement detected (heuristic).")

    data: dict[str, Any] = {
        "plagiarism_similarity_warning": similarity,
        "ai_generated_text_risk_indicator": ai_risk,
        "journal_scope_alignment": scope,
        "ethics_and_irb_check": ethics,
        "data_availability_check": data_avail,
        "figures_and_tables_check": figs_tabs,
        "citation_freshness_check": freshness,
        "language_quality_check": lang,
        "conflict_of_interest_funding_check": coi,
        "disclaimer": [
            "All additional modules are heuristic screening aids.",
            "They must be treated as indicative signals, not as proof of plagiarism or AI generation.",
        ],
    }

    return {
        "agent": "Editorial Screening Agent",
        "ok": True,
        "warnings": warnings,
        "errors": errors,
        "data": data,
    }

