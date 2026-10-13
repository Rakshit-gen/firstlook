"""Command line entry point."""

import argparse
import getpass
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from . import __version__
from .agent import build_agent
from .baseline import baseline
from .env import ScenarioEnv
from .evals import run_one, table
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


def show_proposal(question: dict) -> None:
    action = Action(**question["action"])
    print(f"\nProposed: {describe(action)}  ({question['confidence']} confidence)")
    print(f"  {question['summary']}")
    for q in question["evidence"]:
        print(f"  evidence: {q}")


def ask_approval(question: dict, ask=None) -> dict:
    ask = ask or input
    show_proposal(question)
    while True:
        answer = ask("Do it? [y/N] ").strip().lower()
        if answer in ("y", "yes", "n", "no", ""):
            return {"approved": answer in ("y", "yes"), "by": getpass.getuser()}


def progress(node: str, update: dict) -> str | None:
    """One line about what a graph step did, for people watching a run."""
    if node == "investigate":
        calls = update["messages"][-1].tool_calls
        if calls:
            return "  " + ", ".join(
                c["name"] + "(" + ", ".join(f"{k}={v}" for k, v in c["args"].items()) + ")"
                for c in calls
            )
        return "  done looking; writing up"
    if node == "over_budget":
        return "  out of tool calls; writing up with what it has"
    return None


def drive(app, inp, cfg, quiet: bool):
    """Run the graph until it ends or stops for a question; return the question."""
    for chunk in app.stream(inp, cfg, stream_mode="updates"):
        for node, update in chunk.items():
            if node == "__interrupt__":
                return update[0]
            line = progress(node, update or {})
            if line and not quiet:
                print(line, file=sys.stderr)
    return None


def model_spec(args) -> str:
    if args.model:
        return args.model
    return DEFAULT_MODEL if os.environ.get("GROQ_API_KEY") else "rules"


def write_note(note: str, path: str | None) -> None:
    if path:
        Path(path).write_text(note)
        print(f"wrote {path}", file=sys.stderr)
    else:
        print(note, end="")


def saver(path: str) -> SqliteSaver:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def default_db() -> str:
    return os.environ.get("FIRSTLOOK_DB", str(Path.home() / ".firstlook" / "runs.db"))


def cmd_run(args) -> int:
    if args.pause and model_spec(args) == "rules":
        raise ValueError("--pause needs a model: the rules baseline doesn't stop to ask")
    scenario = pick(args.scenario)
    env = ScenarioEnv(scenario)
    spec = model_spec(args)
    if spec == "rules":
        state = {"finding": baseline(env), "notes": ["rules only: no model was used"]}
        write_note(incident_note(state, env, scenario.title), args.output)
        return 0
    checkpointer = saver(args.db) if args.pause else InMemorySaver()
    app = build_agent(
        make_model(spec), env, checkpointer=checkpointer, executor=ScenarioExecutor(scenario)
    )
    thread = f"{scenario.name}-{uuid.uuid4().hex[:6]}"
    where = str(Path(args.scenario).resolve()) if args.scenario.endswith(".json") else scenario.name
    cfg = {"configurable": {"thread_id": thread}, "metadata": {"scenario": where, "model": spec}}
    if not args.quiet:
        print(f"Investigating {scenario.name} with {spec}", file=sys.stderr)
    question = drive(app, {}, cfg, args.quiet)
    if question is not None and args.pause:
        show_proposal(question.value)
        print(f"\nSaved as {thread}. Decide later with: firstlook decide {thread} yes|no")
        return 0
    while question is not None:
        if args.approve:
            answer = {"approved": True, "by": "--approve"}
        else:
            answer = ask_approval(question.value)
        question = drive(app, Command(resume=answer), cfg, args.quiet)
    write_note(incident_note(app.get_state(cfg).values, env, scenario.title), args.output)
    return 0


def cmd_decide(args) -> int:
    checkpointer = saver(args.db)
    cfg = {"configurable": {"thread_id": args.thread}}
    saved = checkpointer.get_tuple(cfg)
    if saved is None:
        raise ValueError(f"no saved run {args.thread!r} in {args.db}")
    scenario = pick(saved.metadata["scenario"])
    env = ScenarioEnv(scenario)
    app = build_agent(
        make_model(saved.metadata["model"]),
        env,
        checkpointer=checkpointer,
        executor=ScenarioExecutor(scenario),
    )
    if "approve" not in app.get_state(cfg).next:
        raise ValueError(f"{args.thread} is not waiting for a decision")
    answer = {"approved": args.decision == "yes", "by": args.by or getpass.getuser()}
    meta = {k: saved.metadata[k] for k in ("scenario", "model")}
    app.invoke(Command(resume=answer), {**cfg, "metadata": meta})
    write_note(incident_note(app.get_state(cfg).values, env, scenario.title), args.output)
    return 0


def cmd_waiting(args) -> int:
    latest = {}
    for t in saver(args.db).list(None):  # newest first
        latest.setdefault(t.config["configurable"]["thread_id"], t)
    waiting = [
        (thread, t)
        for thread, t in latest.items()
        if any(w[1] == "__interrupt__" for w in t.pending_writes or [])
    ]
    for thread, t in waiting:
        print(f"{thread:24} {t.metadata.get('model', '?')}")
    if not waiting:
        print("No runs are waiting for a decision.")
    return 0


def cmd_eval(args) -> int:
    scenarios = [pick(n) for n in args.scenario] or load_all(SCENARIOS)
    spec = model_spec(args)
    model = None if spec == "rules" else make_model(spec)
    scores = []
    for s in scenarios:
        if not args.quiet:
            print(f"{s.name} ...", file=sys.stderr)
        scores.append(run_one(model, s))
    if args.json:
        print(json.dumps({"model": spec, "scores": [s.to_dict() for s in scores]}, indent=2))
    else:
        print(f"model: {spec}")
        print(table(scores), end="")
    return 0 if all(s.solved for s in scores) else 1


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
    s.add_argument("-q", "--quiet", action="store_true", help="don't show progress")
    s.add_argument(
        "--pause",
        action="store_true",
        help="save the run at the approval step instead of asking; finish it with decide",
    )
    s.add_argument("-o", "--output", help="write the incident note to this file")
    s.add_argument("--db", default=default_db(), help="where paused runs are kept")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("decide", help="approve or decline a paused run")
    s.add_argument("thread", help="the name printed by run --pause")
    s.add_argument("decision", choices=["yes", "no"])
    s.add_argument("--by", help="who decided (default: your user name)")
    s.add_argument("-o", "--output", help="write the incident note to this file")
    s.add_argument("--db", default=default_db(), help="where paused runs are kept")
    s.set_defaults(func=cmd_decide)

    s = sub.add_parser("waiting", help="list paused runs that need a decision")
    s.add_argument("--db", default=default_db(), help="where paused runs are kept")
    s.set_defaults(func=cmd_waiting)

    s = sub.add_parser("eval", help="score runs against the scenarios' known answers")
    s.add_argument("scenario", nargs="*", help="scenarios to run (default: all built-in)")
    s.add_argument("--model", help="rules, or groq:<model id> (same default as run)")
    s.add_argument("--json", action="store_true", help="print the scores as JSON")
    s.add_argument("-q", "--quiet", action="store_true", help="don't show progress")
    s.set_defaults(func=cmd_eval)
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
