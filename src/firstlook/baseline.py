"""A triager with no model: fixed rules over the same data.

It finds the first service to change (looking down the dependency graph
from the alerting services), blames a deploy if one landed just before, and
otherwise guesses from which metric moved. It's what the agent has to beat.
"""

from datetime import timedelta

from .env import Env
from .finding import Action, Finding
from .scenario import METRICS
from .shift import find_shift

REAL_CHANGE = 5.0
DEPLOY_WINDOW = timedelta(minutes=15)

# Which metric moved first -> (cause, action) when no deploy explains it.
BY_METRIC = {
    "error_rate": ("unknown", "escalate"),
    "p99_ms": ("dependency", "escalate"),
    "cpu": ("capacity", "scale_up"),
    "memory": ("capacity", "restart"),
    "db_connections": ("capacity", "restart"),
    "disk_used": ("disk", "escalate"),
    "rps": ("traffic", "rate_limit"),
}


def _below(env: Env, roots: list[str]) -> list[str]:
    seen, todo = [], list(roots)
    while todo:
        s = todo.pop(0)
        if s not in seen:
            seen.append(s)
            todo += env.depends_on(s)
    return seen


def baseline(env: Env, minutes: int = 120) -> Finding:
    alerts = env.alerts()
    roots = sorted({a.service for a in alerts}) or env.services()
    first = None  # (time, service, metric, shift)
    for service in _below(env, roots):
        for metric in METRICS:
            points = env.metric(service, metric, minutes)
            shift = find_shift([v for _, v in points])
            if shift and shift.score >= REAL_CHANGE:
                when = points[shift.index][0]
                # On a tie, the service further down the call graph wins: callers
                # fail in the same minute as the thing they call.
                deeper = first and when == first[0] and service in _below(env, [first[1]])[1:]
                if first is None or when < first[0] or deeper:
                    first = (when, service, metric, shift)
    if first is None:
        return Finding(
            service=roots[0],
            cause="unknown",
            summary="No metric moved beyond its noise.",
            evidence=[],
            confidence="low",
            action=Action(kind="escalate", service=roots[0]),
        )
    when, service, metric, shift = first
    evidence = [f"{service} {metric}", f"at {when:%H:%M} UTC"]
    deploys = [
        (t, d)
        for t, d in env.deploys(minutes)
        if d.service == service and timedelta(0) <= when - t <= DEPLOY_WINDOW
    ]
    if deploys:
        t, d = deploys[-1]
        gap = int((when - t).total_seconds() // 60)
        return Finding(
            service=service,
            cause="deploy",
            summary=f"{service} {metric} changed at {when:%H:%M}, {gap} min after"
            f" {d.version} was deployed.",
            evidence=[*evidence, f"{t:%H:%M} UTC {service} {d.version}"],
            confidence="medium",
            action=Action(kind="rollback", service=service, detail=f"undo {d.version}"),
        )
    cause, kind = BY_METRIC[metric]
    return Finding(
        service=service,
        cause=cause,
        summary=f"{service} {metric} was the first thing to change, at {when:%H:%M}.",
        evidence=evidence,
        confidence="low",
        action=Action(kind=kind, service=service),
    )
