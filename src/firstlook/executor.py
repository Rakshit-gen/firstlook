"""Carry out an approved action.

firstlook never talks to production itself. An executor is the one place an
action happens, so it is easy to see, swap and test:

- `DryRun` only records what it would have done.
- `ScenarioExecutor` plays the action against a recorded scenario and says
  whether it would have fixed it, which is how the evals score a run.
"""

from dataclasses import dataclass, field
from typing import Protocol

from .finding import Action
from .scenario import Scenario


class Executor(Protocol):
    def run(self, action: Action) -> str: ...


VERBS = {
    "rollback": "roll back",
    "restart": "restart",
    "scale_up": "scale up",
    "rate_limit": "rate-limit traffic to",
}


def describe(action: Action) -> str:
    verb = VERBS.get(action.kind, action.kind)
    return f"{verb} {action.service}" + (f" ({action.detail})" if action.detail else "")


@dataclass
class DryRun:
    done: list[Action] = field(default_factory=list)

    def run(self, action: Action) -> str:
        self.done.append(action)
        return f"dry run: would {describe(action)}"


@dataclass
class ScenarioExecutor:
    scenario: Scenario
    done: list[Action] = field(default_factory=list)

    def run(self, action: Action) -> str:
        self.done.append(action)
        t = self.scenario.truth
        if t and (action.kind, action.service) == (t.fix, t.service):
            return f"{describe(action)}: done, and the alerts cleared"
        return f"{describe(action)}: done, but the alerts are still firing"
