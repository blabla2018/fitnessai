from __future__ import annotations

from dataclasses import dataclass
import base64
import csv
import io
import json
import time
from datetime import date
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class IntervalsClient:
    base_url: str
    athlete_id: Optional[str]
    api_key: Optional[str]
    request_pause_seconds: float = 1.0

    def is_configured(self) -> bool:
        return bool(self.athlete_id and self.api_key)

    def configuration_hint(self) -> str:
        return (
            "Set INTERVALS_ATHLETE_ID and INTERVALS_API_KEY to enable syncing from "
            "Intervals."
        )

    def fetch_wellness(self, oldest: date, newest: date) -> list[dict]:
        response_text = self._get(
            f"/api/v1/athlete/{self._athlete_ref()}/wellness.csv",
            {"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        reader = csv.DictReader(io.StringIO(response_text.lstrip("\ufeff")))
        return [row for row in reader]

    def fetch_activities(self, oldest: date, newest: date) -> list[dict]:
        response_text = self._get(
            f"/api/v1/athlete/{self._athlete_ref()}/activities",
            {"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        payload = json.loads(response_text)
        if not isinstance(payload, list):
            raise ValueError("Expected a list of activities from Intervals API.")
        return payload

    def fetch_notes(self, oldest: date, newest: date) -> list[dict]:
        response_text = self._get(
            f"/api/v1/athlete/{self._athlete_ref()}/events",
            {
                "oldest": oldest.isoformat(),
                "newest": newest.isoformat(),
                "category": "NOTE",
            },
        )
        payload = json.loads(response_text)
        if not isinstance(payload, list):
            raise ValueError("Expected a list of note events from Intervals API.")
        return payload

    def fetch_athlete_summary(self, start: date, end: date) -> list[dict]:
        response_text = self._get(
            f"/api/v1/athlete/{self._athlete_ref()}/athlete-summary",
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        payload = json.loads(response_text)
        if not isinstance(payload, list):
            raise ValueError("Expected a list of athlete summary rows from Intervals API.")
        return payload

    def _athlete_ref(self) -> str:
        if not self.athlete_id:
            raise ValueError("Intervals athlete id is not configured.")
        return self.athlete_id

    def _get(self, path: str, query_params: dict[str, str]) -> str:
        if not self.is_configured():
            raise ValueError(self.configuration_hint())

        time.sleep(max(self.request_pause_seconds, 0.0))
        query = urlencode(query_params)
        url = f"{self.base_url}{path}?{query}"
        auth_pair = f"API_KEY:{self.api_key}".encode("utf-8")
        auth_header = base64.b64encode(auth_pair).decode("ascii")
        request = Request(
            url,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Accept": "application/json, text/csv;q=0.9",
                "User-Agent": "fitnessai/0.1 read-only sync",
            },
            method="GET",
        )

        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
