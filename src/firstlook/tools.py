"""The tools the agent can call. Each returns a short plain-text answer: the
model reads text, and short answers keep the context small."""

import functools

from langchain_core.tools import tool

from .env import Env
from .scenario import METRICS
from .shift import find_shift

REAL_CHANGE = 5.0  # shift score above which a change is more than noise
MAX_CHARS = 1500  # longest tool answer; the rest is cut so one call can't flood the context


def friendly(fn):
    """Turn a bad argument into an answer the model can correct itself from,
    instead of an exception that ends the run."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            out = fn(*args, **kwargs)
        except KeyError as e:
            return f"Error: {e.args[0]}"
        if len(out) > MAX_CHARS:
            cut = out[:MAX_CHARS].rsplit("\n", 1)[0]
            out = f"{cut}\n(cut: {len(out) - len(cut)} more characters; narrow the query)"
        return out

    return wrapper


def make_tools(env: Env) -> list:
    @tool
    @friendly
    def list_alerts() -> str:
        """List the alerts that are firing, oldest first, with the system's services."""
        alerts = env.alerts()
        lines = [a.describe() for a in alerts] or ["No alerts firing."]
        lines.append("Services: " + ", ".join(env.services()))
        return "\n".join(lines)

    @tool
    @friendly
    def query_metric(service: str, metric: str, minutes: int = 60) -> str:
        """Summarise one metric for one service over the last `minutes`: its level now,
        and whether and when it changed. Metrics: rps, error_rate, p99_ms, cpu, memory,
        db_connections, disk_used."""
        if metric not in METRICS:
            return f"Unknown metric {metric!r}. Metrics: {', '.join(METRICS)}"
        points = env.metric(service, metric, minutes)
        if not points:
            return f"No data for {service} {metric} in the last {minutes} minutes."
        values = [v for _, v in points]
        head = f"{service} {metric} over the last {minutes} min: now {values[-1]:.4g},"
        head += f" min {min(values):.4g}, max {max(values):.4g}."
        shift = find_shift(values)
        if shift is None or shift.score < REAL_CHANGE:
            return head + " No real change in this window."
        when = points[shift.index][0]
        direction = "rose" if shift.after > shift.before else "fell"
        return (
            head + f" It {direction} from {shift.before:.4g} to {shift.after:.4g}"
            f" ({shift.ratio:.3g}x) at {when:%H:%M} UTC."
        )

    @tool
    @friendly
    def search_logs(
        service: str, contains: str = "", minutes: int = 30, level: str = "error"
    ) -> str:
        """Group recent log lines for a service by message, most frequent first, with
        counts and when each message was first seen. Filter by text and level
        ("error", "warn", "info" or "any")."""
        lines = [
            line
            for line in env.logs(service, minutes)
            if (level == "any" or line.level == level) and contains.lower() in line.message.lower()
        ]
        if not lines:
            return f"No {level} logs for {service} in the last {minutes} minutes" + (
                f" containing {contains!r}." if contains else "."
            )
        groups: dict[str, list] = {}
        for line in lines:
            groups.setdefault(line.message, []).append(line.time)
        top = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:5]
        out = [f"{len(lines)} {level} lines for {service} in the last {minutes} minutes:"]
        for message, times in top:
            out.append(f"- {len(times)}x since {min(times):%H:%M:%S} UTC: {message}")
        if len(groups) > 5:
            out.append(f"({len(groups) - 5} rarer messages not shown)")
        return "\n".join(out)

    @tool
    @friendly
    def recent_deploys(minutes: int = 120, service: str = "") -> str:
        """List deploys and feature flag changes in the last `minutes`, newest first,
        optionally for one service."""
        found = [(t, d) for t, d in env.deploys(minutes) if not service or d.service == service]
        if not found:
            return f"No deploys in the last {minutes} minutes" + (
                f" to {service}." if service else "."
            )
        out = []
        for t, d in sorted(found, key=lambda td: td[0], reverse=True):
            line = f"- {t:%H:%M} UTC {d.service} {d.version} by {d.by}"
            out.append(line + (f": {d.change}" if d.change else ""))
        return "\n".join(out)

    @tool
    @friendly
    def dependencies(service: str) -> str:
        """What a service calls, and what calls it. Errors often start in a dependency
        and show up in everything above it."""
        calls = env.depends_on(service)
        callers = [s for s in env.services() if service in env.depends_on(s)]
        return (
            f"{service} calls: {', '.join(calls) or 'nothing'}.\n"
            f"Called by: {', '.join(callers) or 'nothing'}."
        )

    @tool
    @friendly
    def read_runbook(service: str) -> str:
        """The team's runbook notes for a service, if there are any."""
        text = env.runbook(service)
        return text if text else f"No runbook for {service}."

    return [list_alerts, query_metric, search_logs, recent_deploys, dependencies, read_runbook]
