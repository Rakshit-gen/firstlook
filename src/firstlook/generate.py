"""Turn a scenario into per-minute metrics and log lines."""

import random
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from .scenario import Scenario

NOISE = 0.03  # +-3% wobble on every point, so nothing is perfectly flat


def _rng(*parts) -> random.Random:
    # Stable across runs and Python versions, unlike hash().
    return random.Random(zlib.crc32("/".join(map(str, parts)).encode()))


def series(s: Scenario, service: str, metric: str) -> list[float]:
    """One value per minute for the whole scenario."""
    rng = _rng(s.name, service, metric)
    base = s.baseline(service, metric)
    effects = sorted(
        (e for e in s.effects if (e.service, e.metric) == (service, metric)), key=lambda e: e.at
    )
    out = []
    for minute in range(s.minutes):
        value = base
        for e in effects:
            if minute >= e.at:
                start = value
                done = 1.0 if e.ramp <= 0 else min(1.0, (minute - e.at + 1) / e.ramp)
                value = start + (e.to - start) * done
        out.append(value * (1 + rng.uniform(-NOISE, NOISE)))
    return out


@dataclass(frozen=True)
class LogLine:
    time: datetime
    service: str
    level: str
    message: str


def logs(s: Scenario, service: str) -> list[LogLine]:
    rng = _rng(s.name, service, "logs")
    out = []
    for p in (p for p in s.logs if p.service == service):
        end = s.minutes if p.until is None else p.until
        for minute in range(p.at, end):
            for _ in range(p.per_minute):
                t = s.start + timedelta(minutes=minute, seconds=rng.uniform(0, 60))
                out.append(LogLine(t, service, p.level, p.message))
    return sorted(out, key=lambda line: line.time)
