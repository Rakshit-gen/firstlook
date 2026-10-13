"""A timeline of what happened, built from the data rather than the model."""

from datetime import datetime

from .env import Env


def timeline(env: Env, minutes: int = 180) -> list[tuple[datetime, str]]:
    rows = [
        (t, f"deploy {d.service} {d.version}" + (f": {d.change}" if d.change else ""))
        for t, d in env.deploys(minutes)
    ]
    rows += [(a.fired, f"alert {a.name} on {a.service}") for a in env.alerts()]
    return sorted(rows, key=lambda r: r[0])
