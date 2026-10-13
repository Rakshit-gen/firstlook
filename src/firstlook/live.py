"""An Env over real systems: Prometheus for metrics and alerts, and plain
files for deploys, logs and runbooks.

The config (a dict, usually read from TOML) says where each lives:

    prometheus = "http://localhost:9090"
    deploys = "deploys.jsonl"    # {"service", "version", "at", "by", "change"} per line
    logs = "logs.jsonl"          # {"time", "service", "level", "message"} per line
    runbooks = "runbooks"        # a folder of <service>.md files

    [queries]                    # PromQL per metric; {service} is filled in
    error_rate = '...'

    [services.checkout]
    depends_on = ["payments"]

Paths are relative to the config file.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .alerts import Alert
from .generate import LogLine
from .prom import Prometheus
from .scenario import METRICS, Deploy


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class LiveEnv:
    def __init__(self, config: dict, base: Path, prom=None, now: datetime | None = None):
        if "services" not in config or "prometheus" not in config:
            raise ValueError("config needs prometheus and at least one [services.<name>]")
        unknown = set(config.get("queries", {})) - set(METRICS)
        if unknown:
            raise ValueError(f"unknown metric in [queries]: {', '.join(sorted(unknown))}")
        self.config = config
        self.base = Path(base)
        self.prom = prom or Prometheus(config["prometheus"])
        self.now = now or datetime.now(UTC).replace(second=0, microsecond=0)

    def _path(self, key: str) -> Path | None:
        return self.base / self.config[key] if key in self.config else None

    def _since(self, minutes: int) -> datetime:
        return self.now - timedelta(minutes=minutes)

    def services(self) -> list[str]:
        return sorted(self.config["services"])

    def _check(self, service: str) -> None:
        if service not in self.config["services"]:
            raise KeyError(f"no service {service!r} (have: {', '.join(self.services())})")

    def alerts(self) -> list[Alert]:
        since = {
            (m.get("alertname"), m.get("service")): v
            for m, v in self.prom.query("ALERTS_FOR_STATE", self.now)
        }
        out = []
        for m, _ in self.prom.query('ALERTS{alertstate="firing"}', self.now):
            key = (m.get("alertname", "?"), m.get("service", m.get("job", "?")))
            fired = datetime.fromtimestamp(since[key], UTC) if key in since else self.now
            out.append(Alert(key[0], key[1], "", fired, 0.0, 0.0))
        return sorted(out, key=lambda a: (a.fired, a.service))

    def metric(self, service: str, metric: str, minutes: int) -> list[tuple[datetime, float]]:
        self._check(service)
        query = self.config.get("queries", {}).get(metric)
        if query is None:
            return []
        promql = query.replace("{service}", service)
        return self.prom.query_range(promql, self._since(minutes), self.now)

    def logs(self, service: str, minutes: int) -> list[LogLine]:
        self._check(service)
        path = self._path("logs")
        if path is None:
            return []
        since = self._since(minutes)
        lines = [
            LogLine(_time(r["time"]), r["service"], r.get("level", "info"), r["message"])
            for r in _jsonl(path)
            if r.get("service") == service
        ]
        return [line for line in lines if since <= line.time <= self.now]

    def deploys(self, minutes: int) -> list[tuple[datetime, Deploy]]:
        path = self._path("deploys")
        if path is None:
            return []
        since = self._since(minutes)
        out = []
        for r in _jsonl(path):
            t = _time(r["at"])
            if since <= t <= self.now:
                d = Deploy(r["service"], r["version"], 0, r.get("by", "ci"), r.get("change", ""))
                out.append((t, d))
        return sorted(out, key=lambda td: td[0])

    def depends_on(self, service: str) -> list[str]:
        self._check(service)
        return list(self.config["services"][service].get("depends_on", []))

    def runbook(self, service: str) -> str | None:
        self._check(service)
        folder = self._path("runbooks")
        page = folder / f"{service}.md" if folder else None
        return page.read_text() if page and page.exists() else None
