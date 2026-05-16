from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, PackageLoader, select_autoescape


@dataclass(frozen=True)
class ReportArtifacts:
    html: str
    html_path: Path
    pdf_path: Optional[Path]
    agent_outputs_path: Path


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("ai_scientific_reviewer", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_report_html(reviewer_report: dict[str, Any]) -> str:
    env = _env()
    tpl = env.get_template("report.html.j2")
    return tpl.render(report=reviewer_report)


def _flatten_lines(value: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            label = str(key).replace("_", " ").title()
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{label}:")
                lines.extend(_flatten_lines(item, prefix + "  "))
            else:
                lines.append(f"{prefix}{label}: {item}")
    elif isinstance(value, list):
        if not value:
            lines.append(f"{prefix}None.")
        for item in value[:30]:
            if isinstance(item, (dict, list)):
                lines.extend(_flatten_lines(item, prefix + "- "))
            else:
                lines.append(f"{prefix}- {item}")
    else:
        lines.append(f"{prefix}{value}")
    return lines


def report_to_plain_text(reviewer_report: dict[str, Any]) -> str:
    meta = reviewer_report.get("manuscript_metadata") or {}
    sections: list[tuple[str, Any]] = [
        ("Manuscript Metadata", meta),
        ("Abstract Assessment", reviewer_report.get("abstract_assessment")),
        ("DOI Validation Report", reviewer_report.get("doi_validation_report")),
        ("Reference Verification Report", reviewer_report.get("reference_verification_report")),
        ("IMRAD Structure Assessment", reviewer_report.get("imrad_structure_assessment")),
        ("Methodology Assessment", reviewer_report.get("methodology_assessment")),
        ("Ethics and Transparency Notes", reviewer_report.get("ethics_and_transparency_notes")),
        ("Scientific Quality Assessment", reviewer_report.get("scientific_quality_assessment")),
        ("Scopus/WoS Readiness", reviewer_report.get("scopus_wos_readiness")),
        ("Major Weaknesses", reviewer_report.get("major_weaknesses")),
        ("Minor Weaknesses", reviewer_report.get("minor_weaknesses")),
        ("Required Revisions", reviewer_report.get("required_revisions")),
        ("Final Recommendation", reviewer_report.get("final_recommendation")),
    ]

    lines = [
        "AI Scientific Reviewer System - Preliminary Screening Report",
        f"Title: {meta.get('title') or 'Not detected'}",
        f"File: {meta.get('input_filename') or 'Not specified'}",
        f"Recommendation: {reviewer_report.get('final_recommendation') or 'Not specified'}",
        "",
    ]
    for idx, (title, content) in enumerate(sections, start=1):
        lines.append(f"{idx}. {title}")
        lines.extend(_flatten_lines(content if content is not None else "Not available."))
        lines.append("")
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_basic_pdf(path: Path, text: str) -> None:
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(raw_line, width=92) or [""])

    lines_per_page = 48
    pages = [wrapped[i : i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[]]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))

    for page_index, page_lines in enumerate(pages):
        page_obj_num = 3 + page_index * 2
        content_obj_num = page_obj_num + 1
        stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line_index, line in enumerate(page_lines):
            if line_index:
                stream_lines.append("T*")
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
                f"/Contents {content_obj_num} 0 R >>"
            ).encode("ascii")
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_num, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(pdf))


def write_artifacts(
    out_dir: str,
    agent_outputs: dict[str, Any],
    reviewer_report: dict[str, Any],
    write_pdf: bool = True,
) -> ReportArtifacts:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    agent_outputs_path = out / "agent_outputs.json"
    agent_outputs_path.write_text(json.dumps(agent_outputs, ensure_ascii=False, indent=2), encoding="utf-8")

    html = render_report_html(reviewer_report)
    html_path = out / "report.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path: Optional[Path] = None
    if write_pdf:
        pdf_path = out / "report.pdf"
        try:
            from weasyprint import HTML  # type: ignore

            HTML(string=html, base_url=str(out.resolve())).write_pdf(str(pdf_path))
        except Exception:
            _write_basic_pdf(pdf_path, report_to_plain_text(reviewer_report))

    return ReportArtifacts(html=html, html_path=html_path, pdf_path=pdf_path, agent_outputs_path=agent_outputs_path)
