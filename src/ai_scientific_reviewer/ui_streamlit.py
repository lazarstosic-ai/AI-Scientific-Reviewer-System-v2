from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from ai_scientific_reviewer.graph import run_pipeline
from ai_scientific_reviewer.ingest_docx import ingest_docx
from ai_scientific_reviewer.reporting import write_artifacts


st.set_page_config(page_title="AI Scientific Reviewer System", layout="wide")
st.title("AI Scientific Reviewer System")
st.caption("Preliminary editorial screening / reviewer-style report (Crossref-backed where possible).")

with st.sidebar:
    st.header("Crossref")
    crossref_mailto = st.text_input("mailto (recommended)", value="")
    rate_delay = st.number_input("Rate-limit delay (s)", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
    timeout_s = st.number_input("Timeout (s)", min_value=5.0, max_value=120.0, value=20.0, step=5.0)
    st.header("Output")
    generate_pdf = st.checkbox("Generate PDF (requires weasyprint)", value=True)

uploaded = st.file_uploader("Upload manuscript (.docx)", type=["docx"])
if not uploaded:
    st.stop()

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / uploaded.name
    path.write_bytes(uploaded.getvalue())

    doc = ingest_docx(str(path))
    state = run_pipeline(
        raw_text=doc.text,
        input_filename=doc.filename,
        headings=doc.headings,
        crossref_mailto=crossref_mailto or None,
        crossref_user_agent=None,
        crossref_timeout_s=float(timeout_s),
        rate_limit_delay_s=float(rate_delay),
    )

    reviewer = (state.get("reviewer_report") or {}).get("data") or {}
    artifacts = write_artifacts(out_dir=td, agent_outputs=state, reviewer_report=reviewer, write_pdf=generate_pdf)

    st.subheader("Final recommendation")
    st.write(reviewer.get("final_recommendation", "Unspecified"))

    st.subheader("Report preview (HTML)")
    st.components.v1.html(artifacts.html, height=800, scrolling=True)

    st.subheader("Downloads")
    st.download_button("Download report.html", data=artifacts.html, file_name="report.html", mime="text/html")
    st.download_button(
        "Download agent_outputs.json",
        data=json.dumps(state, ensure_ascii=False, indent=2),
        file_name="agent_outputs.json",
        mime="application/json",
    )
    if artifacts.pdf_path and artifacts.pdf_path.exists():
        st.download_button(
            "Download report.pdf",
            data=artifacts.pdf_path.read_bytes(),
            file_name="report.pdf",
            mime="application/pdf",
        )
