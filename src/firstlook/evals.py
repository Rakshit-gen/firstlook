"""Score a finding against a scenario's known answer."""

from dataclasses import asdict, dataclass

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .agent import build_agent
from .baseline import baseline
from .env import ScenarioEnv
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


def run_one(model, s: Scenario) -> Score:
    """Investigate one scenario and score it. model=None runs the rules
    baseline. The proposed action is scored, never carried out: the run is
    declined at the approval step."""
    env = ScenarioEnv(s)
    if model is None:
        return score(baseline(env), s)
    app = build_agent(model, env, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": s.name}}
    out = app.invoke({}, cfg)
    if "__interrupt__" in out:
        out = app.invoke(Command(resume={"approved": False, "by": "eval"}), cfg)
    return score(out["finding"], s, out.get("tool_calls", 0))


def table(scores: list[Score]) -> str:
    def mark(ok: bool) -> str:
        return "yes" if ok else "-"

    rows = [f"{'scenario':20} service cause fix  harmful evidence tools"]
    for s in scores:
        rows.append(
            f"{s.scenario:20} {mark(s.service):7} {mark(s.cause):5} {mark(s.fix):4}"
            f" {'YES' if s.harmful else '-':7} {s.evidence:8} {s.tool_calls:5}"
        )
    solved = sum(s.solved for s in scores)
    harmful = sum(s.harmful for s in scores)
    rows.append(f"solved {solved}/{len(scores)}, harmful actions {harmful}")
    return "\n".join(rows) + "\n"
