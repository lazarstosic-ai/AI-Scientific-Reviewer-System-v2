from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document


@dataclass(frozen=True)
class DocxIngestResult:
    filename: str
    text: str
    headings: list[str]


def ingest_docx(path: str) -> DocxIngestResult:
    p = Path(path)
    doc = Document(str(p))
    paragraphs: list[str] = []
    headings: list[str] = []

    for para in doc.paragraphs:
        txt = (para.text or "").strip()
        if not txt:
            continue
        style_name = getattr(getattr(para, "style", None), "name", "") or ""
        if style_name.lower().startswith("heading"):
            headings.append(txt)
        paragraphs.append(txt)

    text = "\n".join(paragraphs).strip()
    return DocxIngestResult(filename=p.name, text=text, headings=headings)

