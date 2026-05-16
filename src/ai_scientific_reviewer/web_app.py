from __future__ import annotations

import base64
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .graph import run_pipeline
from .ingest_docx import ingest_docx
from .reporting import write_artifacts


@dataclass(frozen=True)
class RunArtifacts:
    out_dir: Path
    html_path: Path
    json_path: Path
    pdf_path: Optional[Path]


_RUNS: dict[str, RunArtifacts] = {}
_RUNS_LOCK = threading.Lock()


def _load_index_html() -> str:
    static_path = Path(__file__).with_name("static") / "index.html"
    return static_path.read_text(encoding="utf-8")


app = FastAPI(title="AI Scientific Reviewer System")

# Allow the GUI to be opened either from the server (http://127.0.0.1:8000)
# or directly as a local file (file://...). In the latter case, the browser
# enforces CORS, so we allow all origins for this local-tool use case.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _load_index_html()


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(content={"ok": True})


@app.post("/api/review")
async def review(
    file: UploadFile = File(...),
    journal_scope_text: str = Form(""),
    crossref_mailto: str = Form(""),
    rate_limit_delay_s: float = Form(1.0),
    crossref_timeout_s: float = Form(20.0),
    generate_pdf: bool = Form(True),
) -> JSONResponse:
    try:
        if not file.filename or not file.filename.lower().endswith(".docx"):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Only .docx files are supported in this web UI."},
            )

        with tempfile.TemporaryDirectory() as td:
            in_path = Path(td) / file.filename
            in_path.write_bytes(await file.read())

            doc = ingest_docx(str(in_path))
            state = run_pipeline(
                raw_text=doc.text,
                input_filename=doc.filename,
                headings=doc.headings,
                journal_scope_text=journal_scope_text.strip() or None,
                crossref_mailto=crossref_mailto.strip() or None,
                crossref_user_agent=os.getenv("CROSSREF_USER_AGENT"),
                crossref_timeout_s=float(crossref_timeout_s),
                rate_limit_delay_s=float(rate_limit_delay_s),
            )
            reviewer = (state.get("reviewer_report") or {}).get("data") or {}

            # Persist artifacts for download after this request completes
            run_out = Path(tempfile.mkdtemp(prefix="ai-scirev-"))
            artifacts = write_artifacts(
                out_dir=str(run_out),
                agent_outputs=state,
                reviewer_report=reviewer,
                write_pdf=bool(generate_pdf),
            )
    except Exception as e:
        # If the connection drops, the browser shows only "Failed to fetch".
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Server error: {e}"})

    run_id = str(state.get("run_id") or "")
    with _RUNS_LOCK:
        _RUNS[run_id] = RunArtifacts(
            out_dir=run_out,
            html_path=artifacts.html_path,
            json_path=artifacts.agent_outputs_path,
            pdf_path=artifacts.pdf_path,
        )

    return JSONResponse(
        content={
            "ok": True,
            "run_id": run_id,
            "final_recommendation": reviewer.get("final_recommendation"),
            "report_html": artifacts.html,
            "downloads": {
                "report_view": f"/api/view/{run_id}/report.html",
                "report_print": f"/api/view/{run_id}/report.html?print=1",
                "report_html": f"/api/download/{run_id}/report.html",
                "agent_outputs_json": f"/api/download/{run_id}/agent_outputs.json",
                "report_pdf": f"/api/download/{run_id}/report.pdf" if artifacts.pdf_path else None,
            },
        }
    )


@app.get("/api/view/{run_id}/report.html", response_class=HTMLResponse)
def view_html(run_id: str) -> Response:
    with _RUNS_LOCK:
        art = _RUNS.get(run_id)
    if not art:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Unknown run_id."})  # type: ignore[return-value]
    return HTMLResponse(content=art.html_path.read_text(encoding="utf-8"))


@app.get("/api/download/{run_id}/report.html", response_model=None)
def download_html(run_id: str) -> Response:
    with _RUNS_LOCK:
        art = _RUNS.get(run_id)
    if not art:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Unknown run_id."})  # type: ignore[return-value]
    return FileResponse(path=str(art.html_path), filename="report.html", media_type="text/html")


@app.get("/api/download/{run_id}/agent_outputs.json", response_model=None)
def download_json(run_id: str) -> Response:
    with _RUNS_LOCK:
        art = _RUNS.get(run_id)
    if not art:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Unknown run_id."})  # type: ignore[return-value]
    return FileResponse(path=str(art.json_path), filename="agent_outputs.json", media_type="application/json")


@app.get("/api/download/{run_id}/report.pdf", response_model=None)
def download_pdf(run_id: str) -> Response:
    with _RUNS_LOCK:
        art = _RUNS.get(run_id)
    if not art or not art.pdf_path or not art.pdf_path.exists():
        return JSONResponse(status_code=404, content={"ok": False, "error": "PDF not available for this run."})
    return FileResponse(path=str(art.pdf_path), filename="report.pdf", media_type="application/pdf")


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
