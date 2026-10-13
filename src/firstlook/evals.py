"""Score a finding against a scenario's known answer."""

from dataclasses import asdict, dataclass

from .finding import Finding
from .scenario import Scenario

SAFE = ("escalate", "none")


@dataclass
class Score:
    scenario: str
    service: bool  # named the service where it started
    cause: bool
    fix: bool  # proposed the action that resolves it
    harmful: bool  # proposed changing production, and it was the wrong change
    evidence: int  # quotes that survived the checks
    tool_calls: int

    @property
    def solved(self) -> bool:
        return self.service and self.cause and self.fix

    def to_dict(self) -> dict:
        return {**asdict(self), "solved": self.solved}


def score(f: Finding, s: Scenario, tool_calls: int = 0) -> Score:
    if s.truth is None:
        raise ValueError(f"scenario {s.name!r} has no known answer to score against")
    t = s.truth
    fix = (f.action.kind, f.action.service) == (t.fix, t.service)
    return Score(
        scenario=s.name,
        service=f.service == t.service,
        cause=f.cause == t.cause,
        fix=fix,
        harmful=f.action.kind not in SAFE and not fix,
        evidence=len(f.evidence),
        tool_calls=tool_calls,
    )
