from fakes import calls, scripted
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from firstlook.agent import build_agent
from firstlook.env import ScenarioEnv
from firstlook.scenario import load

ENV = ScenarioEnv(load("scenarios/bad-deploy.json"))

GOOD = {
    "service": "payments",
    "cause": "deploy",
    "summary": "payments v2.14.0 broke the refund handler.",
    "evidence": ["14:58 UTC payments v2.14.0"],
    "confidence": "high",
    "action": {"kind": "rollback", "service": "payments", "detail": "previous version"},
}


def test_intake_briefs_the_model_with_the_alerts():
    out = build_agent(scripted([AIMessage("done")], [GOOD]), ENV).invoke({})
    system, human, _ = out["messages"]
    assert "first responder" in system.content
    assert human.content.startswith("It is 2026-10-01 16:00 UTC. You've been paged.")
    assert "HighErrorRate on checkout" in human.content


def test_tool_calls_loop_until_the_model_stops():
    model = scripted(
        [
            calls(
                ("recent_deploys", {}),
                ("query_metric", {"service": "payments", "metric": "error_rate", "minutes": 120}),
            ),
            calls(("search_logs", {"service": "payments"})),
            AIMessage("payments v2.14.0 broke refunds."),
        ],
        [GOOD],
    )
    out = build_agent(model, ENV).invoke({})
    tool_answers = [m for m in out["messages"] if m.type == "tool"]
    assert [m.name for m in tool_answers] == ["recent_deploys", "query_metric", "search_logs"]
    assert "payments v2.14.0" in tool_answers[0].content
    assert out["messages"][-1].content == "payments v2.14.0 broke refunds."
    # The model saw each tool answer before its next turn.
    assert len(model.seen) == 4 and model.seen[2][-1].name == "search_logs"  # 3 turns + conclusion


def test_the_tool_budget_stops_a_runaway_model():
    model = scripted(
        [calls(("list_alerts", {})) for _ in range(3)]
        + [calls(("list_alerts", {}), ("recent_deploys", {}))],
        [GOOD],
    )
    out = build_agent(model, ENV, max_tool_calls=4).invoke({})
    answers = [m for m in out["messages"] if m.type == "tool"]
    assert len(answers) == 5  # 3 run, then 2 refused because 3 + 2 > 4
    assert all(m.content.startswith("Not run: the budget of 4") for m in answers[3:])
    assert out["tool_calls"] == 3
    assert out["notes"][0] == "stopped investigating at the budget of 4 tool calls"
    # The deploy list was never fetched, so the quoted deploy line is not evidence.
    assert out["finding"].action.kind == "escalate"


def test_a_repeated_call_is_not_run_again():
    deploys = ("recent_deploys", {"minutes": 60})
    model = scripted([calls(deploys), calls(deploys, ("list_alerts", {})), AIMessage("ok")], [GOOD])
    out = build_agent(model, ENV).invoke({})
    answers = [m for m in out["messages"] if m.type == "tool"]
    assert [m.name for m in answers] == ["recent_deploys", "recent_deploys", "list_alerts"]
    assert answers[1].content.startswith("You already made this exact call")
    assert answers[2].content.startswith("HighErrorRate")


def test_conclusion_comes_after_the_investigation():
    model = scripted(
        [calls(("recent_deploys", {})), AIMessage("It's the payments deploy.")], [GOOD]
    )
    out = build_agent(model, ENV).invoke({})
    assert out["finding"].service == "payments"
    assert out["finding"].action.kind == "rollback"
    last_prompt = model.seen[-1]
    assert last_prompt[-1].content.startswith("Now give your conclusion.")
    assert last_prompt[-2].content == "It's the payments deploy."


def test_the_action_waits_for_a_person():
    model = scripted([calls(("recent_deploys", {})), AIMessage("deploy")], [GOOD])
    app = build_agent(model, ENV, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "inc-1"}}
    out = app.invoke({}, cfg)
    (question,) = out["__interrupt__"]
    assert question.value["action"] == {
        "kind": "rollback",
        "service": "payments",
        "detail": "previous version",
    }
    assert "approved" not in out
    out = app.invoke(Command(resume={"approved": False, "by": "sam"}), cfg)
    assert out["approved"] is False and out["approver"] == "sam"


def test_escalations_need_no_approval():
    escalate = {**GOOD, "evidence": [], "action": {"kind": "escalate", "service": "payments"}}
    out = build_agent(scripted([AIMessage("no idea")], [escalate]), ENV).invoke({})
    assert "__interrupt__" not in out and "approved" not in out
