"""Run the real agent graph on the bad-deploy scenario with a scripted model.

No API key and no network: the "model" replays the tool calls and the
conclusion below. Everything else is the real thing: the tools answer from
the scenario, the conclusion is checked against those answers, and the run
stops for approval (approved here by "demo").

    uv run python examples/scripted_run.py
"""

import sys
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.types import Command

sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from fakes import calls, scripted  # noqa: E402

from firstlook.agent import build_agent, memory  # noqa: E402
from firstlook.env import ScenarioEnv  # noqa: E402
from firstlook.executor import ScenarioExecutor  # noqa: E402
from firstlook.note import incident_note  # noqa: E402
from firstlook.scenario import builtin  # noqa: E402

TURNS = [
    calls(("dependencies", {"service": "checkout"})),
    calls(
        ("query_metric", {"service": "payments", "metric": "error_rate"}),
        ("recent_deploys", {"service": "payments"}),
    ),
    calls(("search_logs", {"service": "payments"}), ("read_runbook", {"service": "payments"})),
    AIMessage("payments started failing a minute after v2.14.0; rolling back."),
]

FINDING = {
    "service": "payments",
    "cause": "deploy",
    "summary": "payments v2.14.0 went out at 14:58 and its error rate jumped a minute"
    " later, with refund tokenizing errors. checkout fails because it calls payments.",
    "evidence": [
        "14:58 UTC payments v2.14.0",
        "TypeError: cannot read property 'last4' of undefined at RefundHandler.tokenize",
        "upstream payments returned 500",  # not in any answer the model asked for
    ],
    "confidence": "high",
    "action": {"kind": "rollback", "service": "payments", "detail": "back to the previous version"},
}

scenario = builtin("bad-deploy")
env = ScenarioEnv(scenario)
app = build_agent(
    scripted(TURNS, [FINDING]), env, checkpointer=memory(), executor=ScenarioExecutor(scenario)
)
cfg = {"configurable": {"thread_id": "demo"}}
out = app.invoke({}, cfg)
print("Paused for approval:", out["__interrupt__"][0].value["action"], file=sys.stderr)
app.invoke(Command(resume={"approved": True, "by": "demo"}), cfg)
print(incident_note(app.get_state(cfg).values, env, scenario.title), end="")
