from __future__ import annotations

import argparse
import json
from pathlib import Path

from .graph import run_pipeline
from .ingest_docx import ingest_docx
from .reporting import write_artifacts


def _cmd_review(args: argparse.Namespace) -> int:
    inp = Path(args.input)
    if not inp.exists():
        raise SystemExit(f"Input not found: {inp}")

    if inp.suffix.lower() == ".docx":
        doc = ingest_docx(str(inp))
        raw_text = doc.text
        filename = doc.filename
        headings = doc.headings
    else:
        raw_text = inp.read_text(encoding="utf-8", errors="replace")
        filename = inp.name
        headings = []

    state = run_pipeline(
        raw_text=raw_text,
        input_filename=filename,
        headings=headings,
        journal_scope_text=args.journal_scope,
        crossref_mailto=args.crossref_mailto,
        crossref_user_agent=args.crossref_user_agent,
        crossref_timeout_s=float(args.crossref_timeout_s),
        rate_limit_delay_s=float(args.rate_limit_delay_s),
    )

    reviewer = (state.get("reviewer_report") or {}).get("data") or {}
    artifacts = write_artifacts(out_dir=args.out, agent_outputs=state, reviewer_report=reviewer, write_pdf=not args.no_pdf)

    print(f"Wrote: {artifacts.agent_outputs_path}")
    print(f"Wrote: {artifacts.html_path}")
    if artifacts.pdf_path:
        print(f"Wrote: {artifacts.pdf_path}")
    else:
        print("PDF not generated (install extra: pip install -e \".[pdf]\").")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="ai-scirev")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("review", help="Analyze a manuscript and write HTML/PDF report.")
    r.add_argument("--input", required=True, help="Path to .docx or .txt manuscript file.")
    r.add_argument("--out", required=True, help="Output directory.")
    r.add_argument("--crossref-mailto", default=None, help="Email for Crossref polite requests (recommended).")
    r.add_argument("--crossref-user-agent", default=None, help="Override User-Agent header.")
    r.add_argument("--crossref-timeout-s", default=20.0, type=float, help="Crossref request timeout seconds.")
    r.add_argument("--rate-limit-delay-s", default=1.0, type=float, help="Delay between Crossref calls.")
    r.add_argument("--no-pdf", action="store_true", help="Disable PDF generation.")
    r.add_argument("--journal-scope", default=None, help="Optional journal aims/scope text for scope-alignment heuristic.")
    r.set_defaults(func=_cmd_review)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
