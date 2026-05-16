# AI Scientific Reviewer System

LangGraph-based multi-agent application for editorial screening and preliminary reviewer reporting of scientific manuscripts.

## Features
- Word (`.docx`) ingestion
- Multi-agent pipeline (LangGraph `StateGraph`)
- JSON outputs from each agent
- Crossref REST API validation for DOIs and references (polite `User-Agent` + `mailto`)
- HTML report generation and optional PDF export
- Optional Streamlit upload UI

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Optional extras:

```powershell
pip install -e ".[pdf,ui]"
```

## Configure Crossref (recommended)

Set an email for Crossref identification:

```powershell
$env:CROSSREF_MAILTO="your.email@domain.com"
```

Optionally override the full `User-Agent`:

```powershell
$env:CROSSREF_USER_AGENT="AI Scientific Reviewer System (mailto:your.email@domain.com)"
```

## Run (CLI)

```powershell
ai-scirev review --input path\to\manuscript.docx --out out
```

Outputs:
- `out\agent_outputs.json`
- `out\report.html`
- `out\report.pdf` (only if `weasyprint` is installed)

## Run (Streamlit UI)

```powershell
streamlit run .\src\ai_scientific_reviewer\ui_streamlit.py
```

## Run (Web UI: index.html served by FastAPI)

This serves an `index.html` GUI and a small API backend.

For GUI-style startup on Windows, double-click `START_GUI.hta`, then click `Start backend and open app`.

Alternative: double-click `START_HERE.cmd` and leave the terminal open. It starts the backend and opens `http://127.0.0.1:8000`.

You may also open `index.html` to check whether the backend is already running, but a browser cannot reliably execute `.cmd` or `.bat` files for security reasons.

Recommended on Windows:

```powershell
.\run_web.ps1
```

Or double-click:

```text
START_HERE.cmd
```

The launcher finds Python automatically (local venv, `py`, `python`, or the bundled Codex runtime), installs dependencies, starts the backend, and opens the browser.

Manual command:

```powershell
ai-scirev-web
```

Then open: `http://127.0.0.1:8000`

## Notes / Non-hallucination policy
- The system never invents DOI numbers or bibliographic metadata.
- When Crossref cannot verify an item, it is explicitly labeled `unverifiable`.
