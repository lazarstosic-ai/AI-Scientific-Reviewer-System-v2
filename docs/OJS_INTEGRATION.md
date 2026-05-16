# Optional OJS integration (concept)

This project is a standalone screening tool. If you want to integrate with OJS (Open Journal Systems), typical options are:

1. **External screening service**
   - Run `ai-scirev review` on an upload event (e.g., via an editorial assistant workflow).
   - Store `report.html` / `report.pdf` as an attachment to the submission.

2. **OJS plugin (advanced)**
   - Implement an OJS plugin that posts the manuscript file to a local/internal API endpoint running this tool.
   - The API returns the structured JSON + rendered artifacts.

Notes:
- OJS plugin development depends on your OJS version and hosting model.
- This repository currently does not ship an OJS plugin; it provides the core analysis pipeline and UI/CLI.

