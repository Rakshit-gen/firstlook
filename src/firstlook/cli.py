"""Command line entry point."""

import argparse
import sys

from . import __version__
from .baseline import baseline
from .env import ScenarioEnv
from .note import incident_note
from .scenario import SCENARIOS, ScenarioError, builtin, load, load_all


def pick(name: str):
    """A built-in scenario by name, or a scenario file by path."""
    return load(name) if name.endswith(".json") else builtin(name)


def cmd_scenarios(args) -> int:
    for s in load_all(SCENARIOS):
        print(f"{s.name:20} {s.title}")
    return 0


def cmd_run(args) -> int:
    scenario = pick(args.scenario)
    env = ScenarioEnv(scenario)
    state = {"finding": baseline(env), "notes": ["rules only: no model was used"]}
    print(incident_note(state, env, scenario.title), end="")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="firstlook",
        description="An on-call agent that takes the first look at an incident.",
    )
    p.add_argument("--version", action="version", version=f"firstlook {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scenarios", help="list the built-in incident scenarios")
    s.set_defaults(func=cmd_scenarios)

    s = sub.add_parser("run", help="investigate one scenario")
    s.add_argument("scenario", help="a built-in scenario name, or a scenario .json file")
    s.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ScenarioError, ValueError, OSError) as e:
        print(f"firstlook: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
