"""Recorded incidents to run the agent against.

A scenario describes a small system (services and what they call), a normal
baseline for each metric, and what went wrong: deploys, metric effects and
log lines from a given minute on. The generator turns that into metrics and
logs, so a scenario stays a short readable file and the answer is known.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

METRICS = ("rps", "error_rate", "p99_ms", "cpu", "memory", "db_connections", "disk_used")

BASELINE = {
    "rps": 100.0,
    "error_rate": 0.002,
    "p99_ms": 180.0,
    "cpu": 0.35,
    "memory": 0.5,
    "db_connections": 20.0,
    "disk_used": 0.55,
}


class ScenarioError(ValueError):
    pass


@dataclass
class Deploy:
    service: str
    version: str
    at: int  # minute
    by: str = "ci"
    change: str = ""  # what the deploy changed, as a commit or PR title would say


@dataclass
class Effect:
    service: str
    metric: str
    to: float  # value the metric moves to
    at: int  # minute it starts
    ramp: int = 0  # minutes to get there; 0 is a step


@dataclass
class LogPattern:
    service: str
    message: str
    at: int
    per_minute: int = 10
    level: str = "error"
    until: int | None = None


@dataclass
class Truth:
    service: str  # where the cause is
    cause: str  # deploy, config, capacity, dependency, certificate, disk, traffic
    fix: str  # the action that resolves it, e.g. rollback, scale, restart


@dataclass
class Scenario:
    name: str
    title: str
    start: datetime
    minutes: int
    services: dict[str, dict]  # name -> {"depends_on": [...], "baseline": {...}}
    deploys: list[Deploy] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)
    logs: list[LogPattern] = field(default_factory=list)
    truth: Truth | None = None
    runbooks: dict[str, str] = field(default_factory=dict)

    def baseline(self, service: str, metric: str) -> float:
        return self.services[service].get("baseline", {}).get(metric, BASELINE[metric])

    def depends_on(self, service: str) -> list[str]:
        return list(self.services[service].get("depends_on", []))


def parse(doc: dict) -> Scenario:
    try:
        s = Scenario(
            name=doc["name"],
            title=doc["title"],
            start=datetime.fromisoformat(doc["start"].replace("Z", "+00:00")).astimezone(UTC),
            minutes=int(doc.get("minutes", 120)),
            services=doc["services"],
            deploys=[Deploy(**d) for d in doc.get("deploys", [])],
            effects=[Effect(**e) for e in doc.get("effects", [])],
            logs=[LogPattern(**p) for p in doc.get("logs", [])],
            truth=Truth(**doc["truth"]) if "truth" in doc else None,
            runbooks=doc.get("runbooks", {}),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ScenarioError(f"bad scenario: {e}") from e
    for name, svc in s.services.items():
        for dep in svc.get("depends_on", []):
            if dep not in s.services:
                raise ScenarioError(f"{name} depends on unknown service {dep}")
    for thing in [*s.deploys, *s.effects, *s.logs]:
        if thing.service not in s.services:
            raise ScenarioError(f"unknown service {thing.service}")
    for e in s.effects:
        if e.metric not in METRICS:
            raise ScenarioError(f"unknown metric {e.metric} (have: {', '.join(METRICS)})")
    return s


def load(path) -> Scenario:
    with open(path) as f:
        return parse(json.load(f))


def load_all(directory) -> list[Scenario]:
    return [load(p) for p in sorted(Path(directory).glob("*.json"))]
