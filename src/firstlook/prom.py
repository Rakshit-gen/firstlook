"""A small client for the Prometheus HTTP API (query and query_range)."""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime


class PromError(RuntimeError):
    pass


class Prometheus:
    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.url}{path}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                body = json.load(r)
        except urllib.error.HTTPError as e:
            # Prometheus explains bad queries in the body of a 400.
            try:
                body = json.load(e)
            except ValueError:
                raise PromError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise PromError(f"{self.url}: {e}") from e
        if body.get("status") != "success":
            raise PromError(f"{body.get('errorType', 'error')}: {body.get('error', body)}")
        return body["data"]

    def query(self, promql: str, at: datetime | None = None) -> list[tuple[dict, float]]:
        """An instant query: (labels, value) for each series."""
        params = {"query": promql}
        if at:
            params["time"] = at.timestamp()
        data = self._get("/api/v1/query", params)
        return [(r["metric"], float(r["value"][1])) for r in data["result"]]

    def query_range(
        self, promql: str, start: datetime, end: datetime, step: int = 60
    ) -> list[tuple[datetime, float]]:
        """Points of the first series a range query returns (queries here are
        expected to aggregate to one series)."""
        data = self._get(
            "/api/v1/query_range",
            {"query": promql, "start": start.timestamp(), "end": end.timestamp(), "step": step},
        )
        if not data["result"]:
            return []
        return [
            (datetime.fromtimestamp(float(t), UTC), float(v))
            for t, v in data["result"][0]["values"]
            if v not in ("NaN", "+Inf", "-Inf")
        ]
