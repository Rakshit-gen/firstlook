"""Alerts the way a monitoring system would fire them: a threshold held for
a few minutes."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .generate import series
from .scenario import Scenario


@dataclass(frozen=True)
class Rule:
    name: str
    metric: str
    above: float
    minutes: int = 3


RULES = (
    Rule("HighErrorRate", "error_rate", 0.05),
    Rule("HighLatency", "p99_ms", 1000),
    Rule("CPUSaturated", "cpu", 0.9, 5),
    Rule("MemoryHigh", "memory", 0.9, 5),
    Rule("DiskAlmostFull", "disk_used", 0.9),
    Rule("DBPoolExhausted", "db_connections", 95),
)


@dataclass(frozen=True)
class Alert:
    name: str
    service: str
    metric: str
    fired: datetime
    value: float
    threshold: float

    def describe(self) -> str:
        return (
            f"{self.name} on {self.service}: {self.metric} {self.value:.3g}"
            f" (threshold {self.threshold:g}) since {self.fired:%H:%M} UTC"
        )


def fired(s: Scenario, rules=RULES) -> list[Alert]:
    out = []
    for service in s.services:
        for rule in rules:
            values = series(s, service, rule.metric)
            run = 0
            for minute, v in enumerate(values):
                run = run + 1 if v > rule.above else 0
                if run == rule.minutes:
                    at = s.start + timedelta(minutes=minute)
                    out.append(Alert(rule.name, service, rule.metric, at, v, rule.above))
                    break
    return sorted(out, key=lambda a: (a.fired, a.service))
