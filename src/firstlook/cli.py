"""Command line entry point."""

import argparse
import getpass
import os
import sys

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from . import __version__
from .agent import build_agent
from .baseline import baseline
from .env import ScenarioEnv
from .executor import ScenarioExecutor, describe
from .finding import Action
from .llm import DEFAULT_MODEL, make_model
from .note import incident_note
from .scenario import SCENARIOS, ScenarioError, builtin, load, load_all


def pick(name: str):
    """A built-in scenario by name, or a scenario file by path."""
    return load(name) if name.endswith(".json") else builtin(name)


def cmd_scenarios(args) -> int:
    for s in load_all(SCENARIOS):
        print(f"{s.name:20} {s.title}")
    return 0


def ask_approval(question: dict, ask=None) -> dict:
    ask = ask or input
    action = Action(**question["action"])
    print(f"\nProposed: {describe(action)}  ({question['confidence']} confidence)")
    print(f"  {question['summary']}")
    for q in question["evidence"]:
        print(f"  evidence: {q}")
    while True:
        answer = ask("Do it? [y/N] ").strip().lower()
        if answer in ("y", "yes", "n", "no", ""):
            return {"approved": answer in ("y", "yes"), "by": getpass.getuser()}


def model_spec(args) -> str:
    if args.model:
        return args.model
    return DEFAULT_MODEL if os.environ.get("GROQ_API_KEY") else "rules"


def cmd_run(args) -> int:
    scenario = pick(args.scenario)
    env = ScenarioEnv(scenario)
    spec = model_spec(args)
    if spec == "rules":
        state = {"finding": baseline(env), "notes": ["rules only: no model was used"]}
        print(incident_note(state, env, scenario.title), end="")
        return 0
    app = build_agent(
        make_model(spec), env, checkpointer=InMemorySaver(), executor=ScenarioExecutor(scenario)
    )
    cfg = {"configurable": {"thread_id": scenario.name}}
    out = app.invoke({}, cfg)
    while "__interrupt__" in out:
        (question,) = out["__interrupt__"]
        if args.approve:
            answer = {"approved": True, "by": "--approve"}
        else:
            answer = ask_approval(question.value)
        out = app.invoke(Command(resume=answer), cfg)
    print(incident_note(app.get_state(cfg).values, env, scenario.title), end="")
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
    s.add_argument(
        "--model",
        help=f"rules, or groq:<model id> (default: {DEFAULT_MODEL} when GROQ_API_KEY is set,"
        " else rules)",
    )
    s.add_argument(
        "--approve", action="store_true", help="approve the proposed action without asking"
    )
    s.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ScenarioError, ValueError, OSError) as e:
        print(f"firstlook: {e}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nstopped; no action was taken", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
