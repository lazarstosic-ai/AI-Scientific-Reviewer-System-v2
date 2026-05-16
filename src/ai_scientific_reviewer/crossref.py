from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


class CrossrefError(RuntimeError):
    pass


@dataclass(frozen=True)
class CrossrefConfig:
    mailto: Optional[str] = None
    user_agent: Optional[str] = None
    timeout_s: float = 20.0
    rate_limit_delay_s: float = 1.0


class CrossrefClient:
    def __init__(self, config: CrossrefConfig):
        self._config = config
        self._session = requests.Session()
        self._last_request_ts = 0.0

    def _headers(self) -> dict[str, str]:
        ua = self._config.user_agent or os.getenv("CROSSREF_USER_AGENT")
        mailto = self._config.mailto or os.getenv("CROSSREF_MAILTO")
        if not ua:
            if mailto:
                ua = f"AI Scientific Reviewer System (mailto:{mailto})"
            else:
                ua = "AI Scientific Reviewer System (contact: set CROSSREF_MAILTO)"
        headers = {"User-Agent": ua}
        return headers

    def _sleep_for_rate_limit(self) -> None:
        delay = max(0.0, float(self._config.rate_limit_delay_s))
        if delay <= 0:
            return
        now = time.time()
        remaining = (self._last_request_ts + delay) - now
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._sleep_for_rate_limit()
        try:
            resp = self._session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=float(self._config.timeout_s),
            )
            self._last_request_ts = time.time()
        except requests.RequestException as e:
            raise CrossrefError(f"Crossref request failed: {e}") from e

        if resp.status_code == 429:
            raise CrossrefError("Crossref rate limited (HTTP 429). Increase delay or retry later.")
        if resp.status_code >= 400:
            raise CrossrefError(f"Crossref HTTP error {resp.status_code}: {resp.text[:300]}")

        try:
            return resp.json()
        except ValueError as e:
            raise CrossrefError("Crossref returned non-JSON response.") from e

    def works_by_doi(self, doi: str) -> dict[str, Any]:
        doi = doi.strip()
        return self._get(f"https://api.crossref.org/works/{doi}")

    def works_query_bibliographic(self, query: str, rows: int = 3) -> dict[str, Any]:
        return self._get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": query,
                "rows": int(rows),
            },
        )

