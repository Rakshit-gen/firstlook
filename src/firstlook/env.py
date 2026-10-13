"""Where the agent's tools get their data.

`Env` is what the tools need. `ScenarioEnv` serves a recorded scenario;
other backends (a real Prometheus, log files) implement the same methods.
"""

from datetime import datetime, timedelta
from typing import Protocol

from .alerts import Alert, fired
from .generate import LogLine, logs, series
from .scenario import Deploy, Scenario


class Env(Protocol):
    now: datetime

    def services(self) -> list[str]: ...
    def alerts(self) -> list[Alert]: ...
    def metric(self, service: str, metric: str, minutes: int) -> list[tuple[datetime, float]]: ...
    def logs(self, service: str, minutes: int) -> list[LogLine]: ...
    def deploys(self, minutes: int) -> list[tuple[datetime, Deploy]]: ...
    def depends_on(self, service: str) -> list[str]: ...
    def runbook(self, service: str) -> str | None: ...


class ScenarioEnv:
    """Serves one scenario, as seen at its last minute."""

    def __init__(self, scenario: Scenario):
        self.s = scenario
        self.now = scenario.start + timedelta(minutes=scenario.minutes)
        self._logs: dict[str, list[LogLine]] = {}

    def _since(self, minutes: int) -> datetime:
        return self.now - timedelta(minutes=minutes)

    def services(self) -> list[str]:
        return sorted(self.s.services)

    def _check(self, service: str) -> None:
        if service not in self.s.services:
            raise KeyError(f"no service {service!r} (have: {', '.join(self.services())})")

    def alerts(self) -> list[Alert]:
        return fired(self.s)

    def metric(self, service: str, metric: str, minutes: int) -> list[tuple[datetime, float]]:
        self._check(service)
        since = self._since(minutes)
        points = [
            (self.s.start + timedelta(minutes=i), v)
            for i, v in enumerate(series(self.s, service, metric))
        ]
        return [(t, v) for t, v in points if t >= since]

    def logs(self, service: str, minutes: int) -> list[LogLine]:
        self._check(service)
        if service not in self._logs:
            self._logs[service] = logs(self.s, service)
        since = self._since(minutes)
        return [line for line in self._logs[service] if line.time >= since]

    def deploys(self, minutes: int) -> list[tuple[datetime, Deploy]]:
        since = self._since(minutes)
        out = [(self.s.start + timedelta(minutes=d.at), d) for d in self.s.deploys]
        return [(t, d) for t, d in out if t >= since]

    def depends_on(self, service: str) -> list[str]:
        self._check(service)
        return self.s.depends_on(service)

    def runbook(self, service: str) -> str | None:
        self._check(service)
        return self.s.runbooks.get(service)
