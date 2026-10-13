"""The tools the agent can call. Each returns a short plain-text answer: the
model reads text, and short answers keep the context small."""

from langchain_core.tools import tool

from .env import Env
from .scenario import METRICS
from .shift import find_shift

REAL_CHANGE = 5.0  # shift score above which a change is more than noise


def make_tools(env: Env) -> list:
    @tool
    def list_alerts() -> str:
        """List the alerts that are firing, oldest first, with the system's services."""
        alerts = env.alerts()
        lines = [a.describe() for a in alerts] or ["No alerts firing."]
        lines.append("Services: " + ", ".join(env.services()))
        return "\n".join(lines)

    @tool
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

    return [list_alerts, query_metric]
