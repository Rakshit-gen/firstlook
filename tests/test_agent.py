from fakes import calls, scripted
from langchain_core.messages import AIMessage

from firstlook.agent import build_agent
from firstlook.env import ScenarioEnv
from firstlook.scenario import load

ENV = ScenarioEnv(load("scenarios/bad-deploy.json"))


def test_intake_briefs_the_model_with_the_alerts():
    out = build_agent(scripted([AIMessage("done")]), ENV).invoke({})
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
        ]
    )
    out = build_agent(model, ENV).invoke({})
    tool_answers = [m for m in out["messages"] if m.type == "tool"]
    assert [m.name for m in tool_answers] == ["recent_deploys", "query_metric", "search_logs"]
    assert "payments v2.14.0" in tool_answers[0].content
    assert out["messages"][-1].content == "payments v2.14.0 broke refunds."
    # The model saw each tool answer before its next turn.
    assert len(model.seen) == 3 and model.seen[2][-1].name == "search_logs"
